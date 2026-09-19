"""Local interaction, append-only trajectories, reconciliation, and review."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .model import InputType, ProbeDefinition, QuestionDefinition


class RuntimeError(ValueError):
    """A runtime operation violates Probe semantics."""


class EventKind(StrEnum):
    ANSWERED = "answered"
    SKIPPED = "skipped"
    FLAGGED = "flagged"
    INTEGRATED = "integrated"


@dataclass(frozen=True)
class Participant:
    id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Participation:
    id: str
    participant_id: str
    probe_id: str
    probe_revision: int
    scope_id: str


@dataclass(frozen=True)
class TrajectoryEvent:
    id: str
    kind: EventKind
    timestamp: str
    question_id: str = ""
    question_revision: int | None = None
    value: Any = None
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "timestamp": self.timestamp,
            "question_id": self.question_id,
            "question_revision": self.question_revision,
            "value": self.value,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class Trajectory:
    participation: Participation
    events: tuple[TrajectoryEvent, ...] = ()

    def append(self, event: TrajectoryEvent) -> Trajectory:
        return replace(self, events=(*self.events, event))

    def to_dict(self) -> dict[str, Any]:
        participation = self.participation
        return {
            "schema": "probe-trajectory/v1",
            "participation": {
                "id": participation.id,
                "participant_id": participation.participant_id,
                "probe_id": participation.probe_id,
                "probe_revision": participation.probe_revision,
                "scope_id": participation.scope_id,
            },
            "events": [event.to_dict() for event in self.events],
        }


class ReconciliationState(StrEnum):
    UNANSWERED = "unanswered"
    ANSWERED_CURRENT = "answered_current"
    ANSWERED_PREVIOUS_VALID = "answered_previous_valid"
    REANSWER_REQUIRED = "reanswer_required"
    SKIPPED_CURRENT = "skipped_current"
    SKIPPED_PREVIOUS_VALID = "skipped_previous_valid"
    RESKIP_OR_ANSWER_REQUIRED = "reskip_or_answer_required"
    NEWLY_ADDED = "newly_added"


@dataclass(frozen=True)
class QuestionReconciliation:
    question_id: str
    state: ReconciliationState
    previous_revision: int | None
    current_revision: int
    change_type: str
    reanswer_required: bool
    required: bool


@dataclass(frozen=True)
class Reconciliation:
    questions: tuple[QuestionReconciliation, ...]
    previously_completed: bool = False

    @property
    def pending_questions(self) -> tuple[str, ...]:
        pending = {
            ReconciliationState.UNANSWERED,
            ReconciliationState.REANSWER_REQUIRED,
            ReconciliationState.RESKIP_OR_ANSWER_REQUIRED,
            ReconciliationState.NEWLY_ADDED,
        }
        return tuple(item.question_id for item in self.questions if item.state in pending)

    @property
    def first_pending_question(self) -> str | None:
        return self.pending_questions[0] if self.pending_questions else None

    @property
    def currently_complete(self) -> bool:
        return not any(
            item.required and item.question_id in self.pending_questions for item in self.questions
        )


@dataclass(frozen=True)
class ReviewItem:
    question_id: str
    question_revision: int
    state: str
    value: Any
    flags: tuple[str, ...]
    previous_revision: int | None
    change_type: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _event(kind: EventKind, **kwargs: Any) -> TrajectoryEvent:
    return TrajectoryEvent(id=uuid.uuid4().hex, kind=kind, timestamp=_now(), **kwargs)


def _latest_disposition(
    events: Iterable[TrajectoryEvent], question_id: str
) -> TrajectoryEvent | None:
    relevant = [
        event
        for event in events
        if event.question_id == question_id
        and event.kind in {EventKind.ANSWERED, EventKind.SKIPPED}
    ]
    return relevant[-1] if relevant else None


def reconcile(probe: ProbeDefinition, trajectory: Trajectory) -> Reconciliation:
    if trajectory.participation.probe_id != probe.id:
        raise RuntimeError("Trajectory belongs to a different Probe.")
    results: list[QuestionReconciliation] = []
    for question_id in probe.question_order:
        question = probe.question(question_id)
        prior = _latest_disposition(trajectory.events, question_id)
        previous_revision = prior.question_revision if prior else None
        if (
            prior
            and previous_revision != question.revision
            and question.lineage.supersedes_revision is not None
            and question.lineage.supersedes_revision != previous_revision
        ):
            raise RuntimeError(
                f"Question `{question_id}` revision {question.revision} does not "
                f"supersede encountered revision {previous_revision}."
            )
        reask = bool(
            prior
            and previous_revision != question.revision
            and question.lineage.reask_if_answered
        )
        if prior is None:
            state = (
                ReconciliationState.NEWLY_ADDED
                if trajectory.participation.probe_revision < probe.revision
                else ReconciliationState.UNANSWERED
            )
        elif prior.kind == EventKind.ANSWERED and previous_revision == question.revision:
            state = ReconciliationState.ANSWERED_CURRENT
        elif prior.kind == EventKind.SKIPPED and previous_revision == question.revision:
            state = ReconciliationState.SKIPPED_CURRENT
        elif prior.kind == EventKind.ANSWERED and reask:
            state = ReconciliationState.REANSWER_REQUIRED
        elif prior.kind == EventKind.SKIPPED and reask:
            state = ReconciliationState.RESKIP_OR_ANSWER_REQUIRED
        elif prior.kind == EventKind.ANSWERED:
            state = ReconciliationState.ANSWERED_PREVIOUS_VALID
        else:
            state = ReconciliationState.SKIPPED_PREVIOUS_VALID
        results.append(
            QuestionReconciliation(
                question_id=question_id,
                state=state,
                previous_revision=previous_revision,
                current_revision=question.revision,
                change_type=question.lineage.change_type,
                reanswer_required=reask,
                required=question.required,
            )
        )
    return Reconciliation(
        tuple(results),
        previously_completed=any(event.kind == EventKind.INTEGRATED for event in trajectory.events),
    )


class ProbeRuntime:
    """An entirely local participant runtime; stores are touched only explicitly."""

    def __init__(
        self,
        probe: ProbeDefinition,
        *,
        participant_id: str,
        scope_id: str,
        participation_id: str | None = None,
        trajectory: Trajectory | None = None,
    ) -> None:
        self.probe = probe
        if trajectory is None:
            participation = Participation(
                id=participation_id or uuid.uuid4().hex,
                participant_id=participant_id,
                probe_id=probe.id,
                probe_revision=probe.revision,
                scope_id=scope_id,
            )
            trajectory = Trajectory(participation)
        expected = trajectory.participation
        if expected.participant_id != participant_id:
            raise RuntimeError("Participant mismatch while hydrating trajectory.")
        if expected.probe_id != probe.id:
            raise RuntimeError("Probe mismatch while hydrating trajectory.")
        if expected.scope_id != scope_id:
            raise RuntimeError("Scope mismatch while hydrating trajectory.")
        self._trajectory = trajectory

    @classmethod
    def hydrate(
        cls,
        probe: ProbeDefinition,
        trajectory: Trajectory,
        *,
        participant_id: str,
        scope_id: str,
    ) -> ProbeRuntime:
        return cls(
            probe,
            participant_id=participant_id,
            scope_id=scope_id,
            trajectory=trajectory,
        )

    @property
    def trajectory(self) -> Trajectory:
        return self._trajectory

    def _question(self, question_id: str) -> QuestionDefinition:
        question = self.probe.question(question_id)
        if question.status != "active":
            raise RuntimeError(f"Question `{question_id}` is not active.")
        return question

    def answer(self, question_id: str, value: Any, *, comment: str = "") -> None:
        question = self._question(question_id)
        _validate_answer(question, value)
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.ANSWERED,
                question_id=question.id,
                question_revision=question.revision,
                value=value,
                metadata={"comment": comment.strip()} if comment.strip() else {},
            )
        )

    def skip(self, question_id: str, *, reason: str = "") -> None:
        question = self._question(question_id)
        if not question.skippable:
            raise RuntimeError(f"Question `{question_id}` cannot be skipped.")
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.SKIPPED,
                question_id=question.id,
                question_revision=question.revision,
                reason=reason,
            )
        )

    def flag(self, question_id: str, *, reason: str, metadata: Mapping[str, Any] | None = None) -> None:
        question = self._question(question_id)
        if not question.flaggable:
            raise RuntimeError(f"Question `{question_id}` cannot be flagged.")
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.FLAGGED,
                question_id=question.id,
                question_revision=question.revision,
                reason=reason,
                metadata=dict(metadata or {}),
            )
        )

    def reconciliation(self) -> Reconciliation:
        return reconcile(self.probe, self._trajectory)

    def pending(self) -> tuple[str, ...]:
        return self.reconciliation().pending_questions

    def review(self) -> tuple[ReviewItem, ...]:
        reconciliation = self.reconciliation()
        items: list[ReviewItem] = []
        for item in reconciliation.questions:
            disposition = _latest_disposition(self._trajectory.events, item.question_id)
            flags = tuple(
                event.reason
                for event in self._trajectory.events
                if event.question_id == item.question_id and event.kind == EventKind.FLAGGED
            )
            items.append(
                ReviewItem(
                    question_id=item.question_id,
                    question_revision=item.current_revision,
                    state=item.state.value,
                    value=disposition.value if disposition else None,
                    flags=flags,
                    previous_revision=item.previous_revision,
                    change_type=item.change_type,
                )
            )
        return tuple(items)

    def checkpoint(self, store: Any) -> Any:
        return store.checkpoint(self._trajectory)

    def finalise(self, store: Any, *, idempotency_key: str) -> Any:
        if not idempotency_key:
            raise RuntimeError("Finalisation requires an idempotency key.")
        already_integrated = any(
            event.kind == EventKind.INTEGRATED
            and event.metadata.get("idempotency_key") == idempotency_key
            for event in self._trajectory.events
        )
        candidate = self._trajectory
        if not already_integrated:
            candidate = candidate.append(
                _event(EventKind.INTEGRATED, metadata={"idempotency_key": idempotency_key})
            )
        result = store.integrate(candidate, idempotency_key=idempotency_key)
        self._trajectory = candidate
        return result


def _validate_answer(question: QuestionDefinition, value: Any) -> None:
    if value is None or value == "" or value == []:
        raise RuntimeError(f"Question `{question.id}` requires a non-empty answer.")
    allowed = {option.value for option in question.options}
    if question.input_type == InputType.SINGLE and value not in allowed:
        raise RuntimeError(f"Invalid option for question `{question.id}`.")
    if question.input_type == InputType.MULTIPLE:
        if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
            raise RuntimeError(f"Question `{question.id}` requires a collection of options.")
        if not set(value) <= allowed:
            raise RuntimeError(f"Invalid option for question `{question.id}`.")
    if question.input_type == InputType.NUMBER and not isinstance(value, (int, float)):
        raise RuntimeError(f"Question `{question.id}` requires a number.")
    if question.input_type == InputType.BOOLEAN and not isinstance(value, bool):
        raise RuntimeError(f"Question `{question.id}` requires a boolean.")
