"""Structured audit records. One record per control decision, one trace entry per agent step."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class TraceStep:
    """One reviewable step of the decision chain (what the agent saw, did and why)."""
    agent: str                      # supervisor | network | policy | safety | guard
    action: str                     # e.g. tool name or verdict
    inputs: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    rationale: str = ""
    citations: list = field(default_factory=list)   # [{source, document, section, evidence}]


@dataclass
class AuditRecord:
    scenario: str
    slot: int
    model: str
    state_summary: dict             # predicted/observed demand, queues, priority (RT) backlog, SINR
    proposed: dict                  # raw controller output: beams + power
    constraints: dict               # guard checks on the PROPOSED action: {name: {status, detail}}
    final: dict                     # action actually executed after repair
    repairs: list = field(default_factory=list)
    policy_findings: list = field(default_factory=list)   # policy-agent verdicts with citations
    safety_findings: list = field(default_factory=list)   # safety-agent verdicts
    decision: str = "PENDING"       # APPROVED | REPAIRED | REJECTED
    execution_status: str = "NOT_EXECUTED"
    outcome: dict = field(default_factory=dict)           # KPIs measured after execution
    trace: list = field(default_factory=list)             # list[TraceStep] as dicts
    timestamp: str = field(default_factory=now_iso)

    def add_step(self, step: TraceStep) -> None:
        self.trace.append(asdict(step))

    def to_dict(self) -> dict:
        return asdict(self)
