"""Deterministic tool fault injection for the mock shop."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FaultMode = Literal["timeout", "error500", "malformed", "partial", "stale"]


@dataclass(frozen=True)
class ToolFault:
    tool: str
    mode: FaultMode
    calls: tuple[int, ...] | Literal["all"]


@dataclass
class ToolFaultSchedule:
    faults: list[ToolFault]

    def decide(self, tool: str, call_index: int) -> str | None:
        for fault in self.faults:
            if fault.tool == "verify_identity":
                continue
            if fault.tool != "*" and fault.tool != tool:
                continue
            if fault.tool == "*" and tool == "verify_identity":
                continue
            if fault.calls == "all" or call_index in fault.calls:
                return fault.mode
        return None
