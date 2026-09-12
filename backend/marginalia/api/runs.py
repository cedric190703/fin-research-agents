"""In-process run registry: state, event fan-out to SSE subscribers, background execution."""

from __future__ import annotations

import queue
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from marginalia.schemas import ResearchResult, RunEvent

Status = Literal["queued", "running", "done", "error"]
_SENTINEL = None


@dataclass
class RunState:
    id: str
    ticker: str
    question: str
    depth: str
    status: Status = "queued"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events: list[RunEvent] = field(default_factory=list)
    result: ResearchResult | None = None
    error: str | None = None
    _subscribers: list[queue.Queue[RunEvent | None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _closed: bool = False

    def publish(self, ev: RunEvent) -> None:
        with self._lock:
            self.events.append(ev)
            for q in self._subscribers:
                q.put(ev)

    def subscribe(self) -> tuple[list[RunEvent], queue.Queue[RunEvent | None]]:
        """Return the backlog so far plus a live queue; the queue closes with None."""
        q: queue.Queue[RunEvent | None] = queue.Queue()
        with self._lock:
            backlog = list(self.events)
            # Checked under the same lock as publish/close, so a subscriber either
            # sees every event in the backlog or receives the rest live.
            if self._closed:
                q.put(_SENTINEL)
            else:
                self._subscribers.append(q)
        return backlog, q

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for q in self._subscribers:
                q.put(_SENTINEL)
            self._subscribers.clear()


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def create(self, ticker: str, question: str, depth: str) -> RunState:
        state = RunState(id=uuid.uuid4().hex[:12], ticker=ticker, question=question, depth=depth)
        self._runs[state.id] = state
        return state

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def list(self) -> list[RunState]:
        return sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)

    def start(
        self, state: RunState, work: Callable[[Callable[[RunEvent], None]], ResearchResult]
    ) -> None:
        def target() -> None:
            state.status = "running"
            try:
                state.result = work(state.publish)
                state.status = "done"
            except Exception as exc:  # surfaced to the client as an error event
                state.status = "error"
                state.error = f"{type(exc).__name__}: {exc}"
                state.publish(
                    RunEvent(
                        run_id=state.id,
                        agent="orchestrator",
                        type="error",
                        payload={"error": state.error, "trace": traceback.format_exc()[-2000:]},
                    )
                )
            finally:
                state.close()

        threading.Thread(target=target, name=f"run-{state.id}", daemon=True).start()
