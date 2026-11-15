import argparse
import os
import sys

from .agent import DEFAULT_SYSTEM_PROMPT, MaxTurnsExceeded, run
from .tools import TOOLS  # noqa: F401  (import registers the built-in tools)
from .tracing import NullTracer, Tracer

DEFAULT_MODEL = "claude-sonnet-4-5"


def build_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("error: set ANTHROPIC_API_KEY in your environment")
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="chaos", description="Team Chaos's homemade CLI agent harness"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="one-shot prompt; omit it to start an interactive session",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("CHAOS_MODEL", DEFAULT_MODEL),
        help="model to use (default: %(default)s; env: CHAOS_MODEL)",
    )
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--system", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument(
        "--trace",
        default=".chaos/traces.jsonl",
        help="JSONL trace file (default: %(default)s)",
    )
    parser.add_argument("--no-trace", action="store_true", help="disable tracing")
    return parser.parse_args(argv)


def make_tracer(args):
    return NullTracer() if args.no_trace else Tracer(args.trace)


def chat(client, args, tracer):
    messages = []
    while True:
        try:
            prompt = input("chaos> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if prompt.strip() in {"/exit", "/quit"}:
            return
        if not prompt.strip():
            continue
        messages.append({"role": "user", "content": prompt})
        try:
            print(run(client, messages, model=args.model, system=args.system,
                      max_turns=args.max_turns, tracer=tracer))
        except MaxTurnsExceeded as exc:
            print(f"[!] {exc}")


def main(argv=None):
    args = parse_args(argv)
    tracer = make_tracer(args)
    client = build_client()
    if args.prompt:
        messages = [{"role": "user", "content": args.prompt}]
        try:
            print(run(client, messages, model=args.model, system=args.system,
                      max_turns=args.max_turns, tracer=tracer))
        except MaxTurnsExceeded as exc:
            sys.exit(f"[!] {exc}")
    else:
        chat(client, args, tracer)


if __name__ == "__main__":
    main()
