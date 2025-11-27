from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


LOG_PATH = Path(os.getenv("AGENT_LOG_PATH", "agent.log"))


def log_event(conversation_id: str, event: str, data: Dict[str, Any]) -> None:
    """
    Append a structured log entry as JSON.
    """
    try:
        record = {
            "ts": datetime.utcnow().isoformat(),
            "conversation_id": conversation_id,
            "event": event,
            "data": data,
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Logging should never break the agent; swallow failures.
        return
