"""Per-turn agent trace (the audit trail).

Records the ordered, observable decisions the router made for one question: the
route taken, what was retrieved (pages and scores), which table was matched and
with what score, which tools ran with what arguments and results, and whether
the grounding guard fired. These are ground-truth events, not the model's
self-narrated reasoning, so a failure can be isolated to a specific step. Each
finished turn is appended to data/traces.jsonl for offline analysis.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TRACE_LOG = Path(__file__).resolve().parent.parent / "data" / "traces.jsonl"


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


@dataclass
class Step:
    name: str
    detail: dict
    t_ms: int   # milliseconds since the trace started


@dataclass
class Trace:
    query: str
    insurer_id: int | None = None
    backend: str = ""
    started: float = field(default_factory=time.perf_counter)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    steps: list[Step] = field(default_factory=list)

    def add(self, name: str, **detail):
        """Record one observable step, e.g. tr.add("tool", name=..., ok=...)."""
        self.steps.append(
            Step(name, _jsonable(detail), int((time.perf_counter() - self.started) * 1000))
        )
        return self

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "query": self.query,
            "insurer_id": self.insurer_id,
            "backend": self.backend,
            "steps": [{"name": s.name, "t_ms": s.t_ms, **s.detail} for s in self.steps],
        }


def log_trace(trace: Trace, path: Path = TRACE_LOG) -> None:
    """Append a finished trace to the JSONL audit log. Best-effort; never raises."""
    try:
        with Path(path).open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
    except Exception:
        pass
