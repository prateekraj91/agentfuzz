import json
from datetime import datetime, timezone
from pathlib import Path

TRACE_DIR = Path("traces")
TRACE_FILE = TRACE_DIR / "agent_trace.jsonl"


def log_event(event_type: str, data: dict) -> None:
    """Append one event to the JSONL trace file."""

    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }

    with TRACE_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, default=str) + "\n")