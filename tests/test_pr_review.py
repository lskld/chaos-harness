import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".github", "scripts"))

import pr_review
from chaos.llm import LLMError


def make_pr(**overrides):
    pr = {
        "number": 7,
        "title": "Add thing",
        "body": "does a thing",
        "base": "main",
        "head": "feature",
        "changed_files": 2,
        "additions": 10,
        "deletions": 3,
    }
    pr.update(overrides)
    return pr


BASE_ENV = {
    "GITHUB_REPOSITORY": "lskld/chaos-harness",
    "GITHUB_TOKEN": "gh-token",
    "PR_NUMBER": "7",
    "MISTRAL_API_KEY": "sk-test",
    "GITHUB_WORKSPACE": "/workspace",
}


class FetchDiffTest(unittest.TestCase):
    def test_builds_diff_and_skips_patchless_files(self):
        pages = [
            [
                {"filename": "a.py", "patch": "@@ -1 +1 @@\n-old\n+new"},
                {"filename": "logo.png", "patch": None},
            ]
        ]
        with patch.object(pr_review, "github_get", side_effect=pages) as get:
            diff = pr_review.fetch_diff("o/r", 7, "t", max_chars=10000)
        self.assertIn("diff --git a/a.py b/a.py", diff)
        self.assertIn("+new", diff)
        self.assertIn("1 file(s) without a text patch skipped", diff)
        url = get.call_args.args[1]
        self.assertIn("/repos/o/r/pulls/7/files?per_page=100&page=1", url)

    def test_paginates_until_short_page(self):
        full_page = [{"filename": f"f{i}.py", "patch": "x"} for i in range(100)]
        with patch.object(pr_review, "github_get", side_effect=[full_page, [{"filename": "last.py", "patch": "y"}]]) as get:
            diff = pr_review.fetch_diff("o/r", 7, "t", max_chars=1000000)
        self.assertEqual(get.call_count, 2)
        self.assertIn("last.py", diff)

    def test_truncates_at_cap(self):
        files = [{"filename": "big.py", "patch": "x" * 500}]
        with patch.object(pr_review, "github_get", side_effect=[files]):
            diff = pr_review.fetch_diff("o/r", 7, "t", max_chars=100)
        self.assertLessEqual(len(diff), 100 + 200)
        self.assertIn("truncated to 100 chars", diff)


class BuildMessagesTest(unittest.TestCase):
    def test_includes_pr_metadata_agents_md_and_diff(self):
        messages = pr_review.build_messages(make_pr(), "DIFF TEXT", "AGENTS TEXT")
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("untrusted", messages[0]["content"])
        user = messages[1]["content"]
        self.assertIn("PR #7: Add thing", user)
        self.assertIn("main <- head: feature", user)
        self.assertIn("AGENTS TEXT", user)
        self.assertIn("```diff\nDIFF TEXT\n```", user)

    def test_omits_empty_body_and_missing_agents_md(self):
        messages = pr_review.build_messages(make_pr(body=""), "D", "")
        user = messages[1]["content"]
        self.assertNotIn("PR description", user)
        self.assertNotIn("Repo conventions", user)


class ExtractJsonTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(pr_review.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(pr_review.extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_embedded_in_prose(self):
        self.assertEqual(pr_review.extract_json('here you go: {"a": 1} hope that helps'), {"a": 1})

    def test_garbage_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            pr_review.extract_json("no json at all")


class NormalizeReviewTest(unittest.TestCase):
    def test_sorts_findings_by_severity_and_drops_empty(self):
        raw = {
            "verdict": "changes_requested",
            "summary": "s",
            "findings": [
                {"file": "b.py", "line": 1, "severity": "nit", "message": "nit"},
                {"file": "a.py", "line": 9, "severity": "must_fix", "message": "bug"},
                {"file": "c.py", "severity": "weird", "message": "fallback"},
                {"file": "d.py", "severity": "nit", "message": ""},
            ],
        }
        review = pr_review.normalize_review(raw)
        self.assertEqual(review["verdict"], "changes_requested")
        self.assertEqual([f["severity"] for f in review["findings"]], ["must_fix", "suggestion", "nit"])
        self.assertEqual(review["findings"][1]["file"], "c.py")

    def test_unknown_verdict_becomes_comment(self):
        review = pr_review.normalize_review({"verdict": "ship it"})
        self.assertEqual(review["verdict"], "comment")
        self.assertEqual(review["findings"], [])

    def test_non_int_line_is_dropped(self):
        review = pr_review.normalize_review(
            {"verdict": "comment", "findings": [{"file": "a.py", "line": "9; rm -rf", "severity": "nit", "message": "m"}]}
        )
        self.assertIsNone(review["findings"][0]["line"])


class ScrubSecretsTest(unittest.TestCase):
    def test_redacts_secret_looking_lines(self):
        diff = 'api_key = "sk-live-abcdef123456"\n+    token: ghp_abcdefghijklmnop\nnormal line\n'
        scrubbed = pr_review.scrub_secrets(diff)
        self.assertNotIn("sk-live-abcdef123456", scrubbed)
        self.assertNotIn("ghp_abcdefghijklmnop", scrubbed)
        self.assertIn("***redacted***", scrubbed)
        self.assertIn("normal line", scrubbed)

    def test_keeps_short_values(self):
        self.assertEqual(pr_review.scrub_secrets("token = abc"), "token = abc")

    def test_redacts_bearer_and_basic_schemes(self):
        scrubbed = pr_review.scrub_secrets("Authorization: Bearer ghp_abcdefghijklmnop123")
        self.assertNotIn("ghp_abcdefghijklmnop123", scrubbed)
        self.assertIn("Bearer ***redacted***", scrubbed)

    def test_redacts_known_token_prefixes(self):
        for token in ("ghp_abcdefgh1234567890", "sk-proj-abcdefgh1234", "xoxb-1234567890ab", "AIzaSyabcdefgh1234567"):
            self.assertNotIn(token, pr_review.scrub_secrets(f"leaked {token} here"))

    def test_redacts_url_embedded_credentials(self):
        scrubbed = pr_review.scrub_secrets("clone https://user:hunter2secret@github.com/o/r.git")
        self.assertNotIn("hunter2secret", scrubbed)
        self.assertIn("https://user:***redacted***@github.com", scrubbed)

    def test_redacts_pem_blocks(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\n" + "A" * 64 + "\n" + "B" * 64 + "\n-----END RSA PRIVATE KEY-----\n"
        scrubbed = pr_review.scrub_secrets(pem)
        self.assertNotIn("A" * 64, scrubbed)
        self.assertNotIn("B" * 64, scrubbed)
        self.assertIn("BEGIN ***redacted***", scrubbed)


class EscapeMdTest(unittest.TestCase):
    def test_escapes_markdown_specials(self):
        self.assertEqual(pr_review.escape_md("[x](http://e) `c` *s*"), "\\[x\\]\\(http://e\\) \\`c\\` \\*s\\*")

    def test_plain_text_unchanged(self):
        self.assertEqual(pr_review.escape_md("plain words 123"), "plain words 123")


class RenderCommentTest(unittest.TestCase):
    def test_renders_verdict_summary_and_findings(self):
        review = {
            "verdict": "changes_requested",
            "summary": "one bug",
            "findings": [
                {"file": "src/chaos/llm.py", "line": 42, "severity": "must_fix", "message": "off by one"}
            ],
        }
        body = pr_review.render_comment("mistral-large-latest", make_pr(), review)
        self.assertIn("🛠️ Changes requested", body)
        self.assertIn("one bug", body)
        self.assertIn("`src/chaos/llm.py:42`", body)
        self.assertIn("**must fix**", body)
        self.assertIn("Advisory review", body)

    def test_escapes_untrusted_title_and_messages(self):
        pr = make_pr(title="[click](https://evil.example) `x`")
        review = {
            "verdict": "comment",
            "summary": "summary with [link](https://evil.example)",
            "findings": [
                {"file": "a`b.py", "line": 1, "severity": "nit", "message": "msg with `backtick` and *stars*"}
            ],
        }
        body = pr_review.render_comment("m", pr, review)
        self.assertNotIn("[click](https://evil.example)", body)
        self.assertNotIn("[link](https://evil.example)", body)
        self.assertIn("\\[click\\]", body)
        self.assertNotIn("`backtick`", body)
        self.assertIn("a'b.py:1", body)

    def test_raw_fallback_when_json_unparseable(self):
        review = {"verdict": "comment", "summary": "", "findings": []}
        body = pr_review.render_comment("m", make_pr(), review, raw_text="free-form reply")
        self.assertIn("free-form reply", body)

    def test_raw_fallback_uses_longer_fence_when_reply_contains_fence(self):
        review = {"verdict": "comment", "summary": "", "findings": []}
        body = pr_review.render_comment("m", make_pr(), review, raw_text="code:\n```py\nx = 1\n```")
        self.assertIn("````\ncode:\n```py\nx = 1\n```\n````", body)

    def test_render_error_mentions_failure(self):
        body = pr_review.render_error("m", "boom")
        self.assertIn("could not be completed", body)
        self.assertIn("boom", body)


class PrNumberTest(unittest.TestCase):
    def test_env_wins(self):
        with patch.dict(os.environ, {"PR_NUMBER": "12"}):
            self.assertEqual(pr_review.pr_number(), 12)

    def test_falls_back_to_event_payload(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"number": 34}, fh)
            path = fh.name
        env = {"GITHUB_EVENT_PATH": path}
        with patch.dict(os.environ, env):
            os.environ.pop("PR_NUMBER", None)
            self.assertEqual(pr_review.pr_number(), 34)
        os.unlink(path)


class MainTest(unittest.TestCase):
    def run_main(self, env):
        with patch.dict(os.environ, env, clear=True):
            return pr_review.main()

    def test_skips_without_api_key(self):
        env = {k: v for k, v in BASE_ENV.items() if k != "MISTRAL_API_KEY"}
        with patch.object(pr_review, "chat_stream") as chat_mock, patch.object(pr_review, "post_comment") as post_mock:
            code = self.run_main(env)
        self.assertEqual(code, 0)
        chat_mock.assert_not_called()
        post_mock.assert_not_called()

    def test_posts_structured_review(self):
        review_payload = {
            "verdict": "approve",
            "summary": "looks good",
            "findings": [],
        }
        with patch.object(pr_review, "fetch_pr", return_value=make_pr()), patch.object(
            pr_review, "fetch_diff", return_value="diff"
        ), patch.object(pr_review, "read_agents_md", return_value="agents"), patch.object(
            pr_review, "chat_stream", return_value=Mock(text=json.dumps(review_payload))
        ) as chat_mock, patch.object(
            pr_review, "post_comment"
        ) as post_mock:
            code = self.run_main(BASE_ENV)
        self.assertEqual(code, 0)
        kwargs = chat_mock.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "https://api.mistral.ai/v1")
        self.assertEqual(kwargs["model"], "mistral-large-latest")
        self.assertEqual(kwargs["api_key"], "sk-test")
        post_mock.assert_called_once()
        body = post_mock.call_args.args[3]
        self.assertIn("✅ Approve", body)
        self.assertIn("looks good", body)

    def test_model_and_base_url_overridable(self):
        env = dict(BASE_ENV, REVIEW_MODEL="mistral-large-4-0", MISTRAL_BASE_URL="https://proxy.example/v1")
        with patch.object(pr_review, "fetch_pr", return_value=make_pr()), patch.object(
            pr_review, "fetch_diff", return_value="d"
        ), patch.object(pr_review, "read_agents_md", return_value=""), patch.object(
            pr_review, "chat_stream", return_value=Mock(text='{"verdict": "approve"}')
        ) as chat_mock, patch.object(
            pr_review, "post_comment"
        ):
            code = self.run_main(env)
        self.assertEqual(code, 0)
        kwargs = chat_mock.call_args.kwargs
        self.assertEqual(kwargs["model"], "mistral-large-4-0")
        self.assertEqual(kwargs["base_url"], "https://proxy.example/v1")

    def test_llm_error_posts_failure_comment_and_stays_green(self):
        with patch.object(pr_review, "fetch_pr", return_value=make_pr()), patch.object(
            pr_review, "fetch_diff", return_value="d"
        ), patch.object(pr_review, "read_agents_md", return_value=""), patch.object(
            pr_review, "chat_stream", side_effect=LLMError("API error 500")
        ), patch.object(pr_review, "post_comment") as post_mock, patch.object(pr_review.time, "sleep"):
            code = self.run_main(BASE_ENV)
        self.assertEqual(code, 0)
        body = post_mock.call_args.args[3]
        self.assertIn("could not be completed", body)
        self.assertIn("API error 500", body)

    def test_retries_once_after_transient_error(self):
        with patch.object(pr_review, "fetch_pr", return_value=make_pr()), patch.object(
            pr_review, "fetch_diff", return_value="d"
        ), patch.object(pr_review, "read_agents_md", return_value=""), patch.object(
            pr_review,
            "chat_stream",
            side_effect=[LLMError("ReadTimeout"), Mock(text='{"verdict": "approve", "summary": "ok", "findings": []}')],
        ) as chat_mock, patch.object(
            pr_review, "post_comment"
        ) as post_mock, patch.object(
            pr_review.time, "sleep"
        ) as sleep_mock:
            code = self.run_main(BASE_ENV)
        self.assertEqual(code, 0)
        self.assertEqual(chat_mock.call_count, 2)
        sleep_mock.assert_called_once()
        body = post_mock.call_args.args[3]
        self.assertIn("✅ Approve", body)


    def test_unparseable_reply_posts_raw_text(self):
        with patch.object(pr_review, "fetch_pr", return_value=make_pr()), patch.object(
            pr_review, "fetch_diff", return_value="d"
        ), patch.object(pr_review, "read_agents_md", return_value=""), patch.object(
            pr_review, "chat_stream", return_value=Mock(text="not json at all")
        ), patch.object(
            pr_review, "post_comment"
        ) as post_mock:
            code = self.run_main(BASE_ENV)
        self.assertEqual(code, 0)
        body = post_mock.call_args.args[3]
        self.assertIn("not json at all", body)

    def test_diff_is_scrubbed_before_sending_to_model(self):
        with patch.object(pr_review, "fetch_pr", return_value=make_pr()), patch.object(
            pr_review, "fetch_diff", return_value='api_key = "sk-live-abcdef123456"\n'
        ), patch.object(pr_review, "read_agents_md", return_value=""), patch.object(
            pr_review, "chat_stream", return_value=Mock(text='{"verdict": "approve"}')
        ) as chat_mock, patch.object(
            pr_review, "post_comment"
        ):
            code = self.run_main(BASE_ENV)
        self.assertEqual(code, 0)
        user_message = chat_mock.call_args.kwargs["messages"][1]["content"]
        self.assertNotIn("sk-live-abcdef123456", user_message)
        self.assertIn("***redacted***", user_message)

    def test_unexpected_error_still_exits_zero_and_posts_failure(self):
        with patch.object(pr_review, "fetch_pr", side_effect=RuntimeError("boom")), patch.object(
            pr_review, "post_comment"
        ) as post_mock:
            code = self.run_main(BASE_ENV)
        self.assertEqual(code, 0)
        body = post_mock.call_args.args[3]
        self.assertIn("could not be completed", body)
        self.assertIn("boom", body)


class CallReviewModelTest(unittest.TestCase):
    def test_raises_last_error_after_all_attempts(self):
        with patch.object(pr_review, "chat_stream", side_effect=[LLMError("t1"), LLMError("t2")]), patch.object(
            pr_review.time, "sleep"
        ):
            with self.assertRaises(LLMError) as ctx:
                pr_review.call_review_model(
                    base_url="u", api_key="k", model="m", messages=[], timeout=1, attempts=2
                )
        self.assertIn("t2", str(ctx.exception))

    def test_streams_with_a_max_tokens_cap(self):
        with patch.object(
            pr_review, "chat_stream", return_value=Mock(text='{"verdict": "approve"}')
        ) as stream_mock:
            pr_review.call_review_model(base_url="u", api_key="k", model="m", messages=[])
        kwargs = stream_mock.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 4096)
        self.assertGreater(kwargs["timeout"], 0)

    def test_empty_reply_is_retried(self):
        with patch.object(
            pr_review,
            "chat_stream",
            side_effect=[Mock(text=""), Mock(text='{"verdict": "approve", "summary": "ok", "findings": []}')],
        ) as stream_mock, patch.object(pr_review.time, "sleep"):
            reply = pr_review.call_review_model(base_url="u", api_key="k", model="m", messages=[])
        self.assertEqual(stream_mock.call_count, 2)
        self.assertIn("approve", reply.text)


if __name__ == "__main__":
    unittest.main()
