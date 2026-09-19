"""Deterministic operational and collective projections without interpretation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .model import ProbeDefinition
from .runtime import EventKind, Trajectory, _latest_disposition, reconcile


@dataclass(frozen=True)
class OperationalSummary:
    participations: int
    complete: int
    answered: int
    skipped: int
    flagged: int


@dataclass(frozen=True)
class ResponseFieldRow:
    participant_id: str
    question_id: str
    question_revision: int | None
    state: str
    value: Any
    flagged: bool


def operational_summary(
    probe: ProbeDefinition, trajectories: Iterable[Trajectory]
) -> OperationalSummary:
    items = tuple(trajectories)
    return OperationalSummary(
        participations=len(items),
        complete=sum(reconcile(probe, item).currently_complete for item in items),
        answered=sum(event.kind == EventKind.ANSWERED for item in items for event in item.events),
        skipped=sum(event.kind == EventKind.SKIPPED for item in items for event in item.events),
        flagged=sum(event.kind == EventKind.FLAGGED for item in items for event in item.events),
    )


def project_response_field(
    probe: ProbeDefinition, trajectories: Iterable[Trajectory]
) -> tuple[ResponseFieldRow, ...]:
    rows: list[ResponseFieldRow] = []
    for trajectory in trajectories:
        participant_id = trajectory.participation.participant_id
        for question_id in probe.question_order:
            disposition = _latest_disposition(trajectory.events, question_id)
            flagged = any(
                event.kind == EventKind.FLAGGED and event.question_id == question_id
                for event in trajectory.events
            )
            rows.append(
                ResponseFieldRow(
                    participant_id=participant_id,
                    question_id=question_id,
                    question_revision=disposition.question_revision if disposition else None,
                    state=disposition.kind.value if disposition else "unanswered",
                    value=disposition.value if disposition else None,
                    flagged=flagged,
                )
            )
    return tuple(rows)


def distributions(
    probe: ProbeDefinition, trajectories: Iterable[Trajectory]
) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for question_id in probe.question_order:
        counts: Counter[str] = Counter()
        for trajectory in trajectories:
            event = _latest_disposition(trajectory.events, question_id)
            if event is None:
                counts["unanswered"] += 1
            elif event.kind == EventKind.SKIPPED:
                counts["skipped"] += 1
            elif isinstance(event.value, (list, tuple, set)):
                counts.update(str(value) for value in event.value)
            else:
                counts[str(event.value)] += 1
        output[question_id] = dict(sorted(counts.items()))
    return output


def timeline_events(trajectories: Iterable[Trajectory]) -> tuple[dict[str, Any], ...]:
    events = [
        {
            **event.to_dict(),
            "participant_id": trajectory.participation.participant_id,
            "participation_id": trajectory.participation.id,
            "scope_id": trajectory.participation.scope_id,
        }
        for trajectory in trajectories
        for event in trajectory.events
    ]
    return tuple(sorted(events, key=lambda item: (item["timestamp"], item["id"])))
