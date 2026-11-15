import json
import os
from datetime import datetime, timezone


class Tracer:
    def __init__(self, path):
        self.path = path

    def log(self, event, **data):
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


class NullTracer:
    def log(self, event, **data):
        pass
