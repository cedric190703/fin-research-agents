"""Every number the system emits carries how it was produced and can be replayed."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fin_research.schemas import Metric, Provenance

ToolFn = Callable[..., dict[str, float]]


class ToolRegistry:
    """Registers metric-producing tools and remembers each call for `recompute`."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolFn] = {}
        self._calls: dict[str, tuple[str, dict[str, Any]]] = {}

    def register(self, name: str, fn: ToolFn) -> None:
        self._tools[name] = fn

    def call(self, name: str, *, units: dict[str, str], period: str, **args: Any) -> list[Metric]:
        fn = self._tools[name]
        values = fn(**args)
        data_as_of = datetime.now(UTC)
        h = hashlib.sha256(
            json.dumps({"tool": name, "args": args}, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        metrics: list[Metric] = []
        for key, value in values.items():
            metric_id = f"{name}.{key}.{h}"
            self._calls[metric_id] = (name, {**args, "__key": key})
            metrics.append(
                Metric(
                    id=metric_id,
                    name=key,
                    value=float(value),
                    unit=units.get(key, ""),
                    period=period,
                    provenance=Provenance(
                        tool=name, args=dict(args), data_as_of=data_as_of, hash=h
                    ),
                )
            )
        return metrics

    def recompute(self, metric_id: str) -> float:
        """Replay the stored call and return the value for that metric."""
        name, args = self._calls[metric_id]
        key = args["__key"]
        clean = {k: v for k, v in args.items() if k != "__key"}
        return float(self._tools[name](**clean)[key])
