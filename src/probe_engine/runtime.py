"""Local interaction, append-only trajectories, reconciliation, and review."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .model import InputType, LocationValue, ProbeDefinition, QuestionDefinition, RevisionLineage


class RuntimeError(ValueError):
    """A runtime operation violates Probe semantics."""


class EventKind(StrEnum):
    ANSWERED = "answered"
    SKIPPED = "skipped"
    FLAGGED = "flagged"
    DEFERRED = "deferred"
    INTEGRATED = "integrated"
    CHECKPOINT = "checkpoint"
    SYNC_POINT_REACHED = "sync_point_reached"


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
    reason_codes: tuple[str, ...] = ()
    reason_note: str = ""
    legacy_reason_codes: tuple[str, ...] = ()
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
            "reason_codes": list(self.reason_codes),
            "reason_note": self.reason_note,
            "legacy_reason_codes": list(self.legacy_reason_codes),
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
    DEFERRED_CURRENT = "deferred_current"
    DEFERRED_PREVIOUS_VALID = "deferred_previous_valid"
    FLAGGED_CURRENT = "flagged_current"
    FLAGGED_PREVIOUS_VALID = "flagged_previous_valid"
    INELIGIBLE = "ineligible"
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
            ReconciliationState.FLAGGED_CURRENT,
            ReconciliationState.FLAGGED_PREVIOUS_VALID,
        }
        return tuple(item.question_id for item in self.questions if item.state in pending)

    @property
    def first_pending_question(self) -> str | None:
        return self.pending_questions[0] if self.pending_questions else None

    @property
    def currently_complete(self) -> bool:
        return not self.pending_questions


class ResolutionState(StrEnum):
    UNRESOLVED = "unresolved"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    DEFERRED = "deferred"
    INELIGIBLE = "ineligible"


@dataclass(frozen=True)
class Resolution:
    field_id: str
    state: ResolutionState
    flagged: bool = False
    inherited_from: str = ""
    event: TrajectoryEvent | None = None


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
        and event.kind in {EventKind.ANSWERED, EventKind.SKIPPED, EventKind.DEFERRED}
    ]
    return relevant[-1] if relevant else None


def _is_eligible(probe: ProbeDefinition, trajectory: Trajectory, field_id: str) -> bool:
    field = probe.field(field_id)
    condition = getattr(field, "visible_if", None)
    if condition is None:
        return True

    def evaluate(item: Any) -> bool:
        if item.operator == "any":
            return any(evaluate(clause) for clause in item.clauses)
        source = _latest_disposition(trajectory.events, item.field_id)
        if source is None or source.kind != EventKind.ANSWERED:
            return False
        value = source.value
        if isinstance(value, Mapping) and "selected" in value:
            value = value.get("selected")
        if item.operator == "contains":
            return isinstance(value, (list, tuple, set)) and item.value in value
        if isinstance(value, (list, tuple, set)):
            return item.value in value
        return value == item.value

    return evaluate(condition)


def reconcile(probe: ProbeDefinition, trajectory: Trajectory) -> Reconciliation:
    if trajectory.participation.probe_id != probe.id:
        raise RuntimeError("Trajectory belongs to a different Probe.")
    results: list[QuestionReconciliation] = []
    for question_id in probe.answerable_order:
        question = probe.field(question_id)
        prior = _latest_disposition(trajectory.events, question_id)
        latest_flag = next(
            (
                event
                for event in reversed(trajectory.events)
                if event.question_id == question_id and event.kind == EventKind.FLAGGED
            ),
            None,
        )
        previous_revision = (
            prior.question_revision
            if prior
            else latest_flag.question_revision
            if latest_flag
            else None
        )
        lineage = getattr(question, "lineage", RevisionLineage())
        if (
            prior
            and previous_revision != question.revision
            and lineage.supersedes_revision is not None
            and lineage.supersedes_revision != previous_revision
        ):
            raise RuntimeError(
                f"Question `{question_id}` revision {question.revision} does not "
                f"supersede encountered revision {previous_revision}."
            )
        reask = bool(prior and previous_revision != question.revision and lineage.reask_if_answered)
        if not _is_eligible(probe, trajectory, question_id):
            state = ReconciliationState.INELIGIBLE
        elif prior is None and latest_flag is not None:
            state = (
                ReconciliationState.FLAGGED_CURRENT
                if latest_flag.question_revision == question.revision
                else ReconciliationState.FLAGGED_PREVIOUS_VALID
            )
        elif prior is None:
            state = (
                ReconciliationState.NEWLY_ADDED
                if trajectory.participation.probe_revision < probe.revision
                else ReconciliationState.UNANSWERED
            )
        elif prior.kind == EventKind.ANSWERED and previous_revision == question.revision:
            state = ReconciliationState.ANSWERED_CURRENT
        elif prior.kind == EventKind.SKIPPED and previous_revision == question.revision:
            state = ReconciliationState.SKIPPED_CURRENT
        elif prior.kind == EventKind.DEFERRED and previous_revision == question.revision:
            state = ReconciliationState.DEFERRED_CURRENT
        elif prior.kind == EventKind.ANSWERED and reask:
            state = ReconciliationState.REANSWER_REQUIRED
        elif prior.kind == EventKind.SKIPPED and reask:
            state = ReconciliationState.RESKIP_OR_ANSWER_REQUIRED
        elif prior.kind == EventKind.DEFERRED and reask:
            state = ReconciliationState.REANSWER_REQUIRED
        elif prior.kind == EventKind.ANSWERED:
            state = ReconciliationState.ANSWERED_PREVIOUS_VALID
        elif prior.kind == EventKind.SKIPPED:
            state = ReconciliationState.SKIPPED_PREVIOUS_VALID
        else:
            state = ReconciliationState.DEFERRED_PREVIOUS_VALID
        results.append(
            QuestionReconciliation(
                question_id=question_id,
                state=state,
                previous_revision=previous_revision,
                current_revision=question.revision,
                change_type=lineage.change_type,
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

    def _question(self, question_id: str) -> QuestionDefinition | Any:
        question = self.probe.field(question_id)
        if self.probe.resolution_parent(question_id) != question_id:
            raise RuntimeError(
                f"Field `{question_id}` inherits resolution from `{self.probe.resolution_parent(question_id)}`."
            )
        if getattr(question, "status", "active") != "active":
            raise RuntimeError(f"Question `{question_id}` is not active.")
        if not _is_eligible(self.probe, self._trajectory, question_id):
            raise RuntimeError(f"Question `{question_id}` is not currently eligible.")
        return question

    def answer(self, question_id: str, value: Any, *, comment: str = "") -> None:
        question = self._question(question_id)
        if isinstance(value, LocationValue):
            value = value.to_dict()
        _validate_answer(question, value, probe=self.probe)
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.ANSWERED,
                question_id=question.id,
                question_revision=question.revision,
                value=value,
                metadata={"comment": comment.strip()} if comment.strip() else {},
            )
        )

    def _reason_values(
        self, kind: str, reason_codes: Iterable[str], note: str, legacy: str
    ) -> tuple[tuple[str, ...], str]:
        taxonomy = (
            self.probe.resolution.skip_reasons
            if kind == "skip"
            else self.probe.resolution.flag_reasons
        )
        allowed = {item.value for item in taxonomy.options}
        codes = tuple(
            dict.fromkeys(str(value).strip() for value in reason_codes if str(value).strip())
        )
        unknown = set(codes) - allowed
        if unknown:
            raise RuntimeError(f"Unknown {kind} reason: {', '.join(sorted(unknown))}.")
        reason_note = str(note or legacy or "").strip()
        if len(reason_note) > 500:
            raise RuntimeError(f"{kind.title()} reason note exceeds 500 characters.")
        note_optional = (
            self.probe.resolution.skip_note_optional
            if kind == "skip"
            else self.probe.resolution.flag_note_optional
        )
        if not note_optional and not reason_note:
            raise RuntimeError(f"{kind.title()} requires a reason note.")
        return codes, reason_note

    def skip(
        self,
        question_id: str,
        *,
        reason: str = "",
        reason_codes: Iterable[str] = (),
        note: str = "",
    ) -> None:
        question = self._question(question_id)
        if not self.probe.resolution.skip_enabled or not getattr(question, "skippable", True):
            raise RuntimeError(f"Question `{question_id}` cannot be skipped.")
        codes, reason_note = self._reason_values("skip", reason_codes, note, reason)
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.SKIPPED,
                question_id=question.id,
                question_revision=question.revision,
                reason=reason_note,
                reason_codes=codes,
                reason_note=reason_note,
            )
        )

    def flag(
        self,
        question_id: str,
        *,
        reason: str = "",
        reason_codes: Iterable[str] = (),
        note: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        question = self._question(question_id)
        if not self.probe.resolution.flag_enabled or not getattr(question, "flaggable", True):
            raise RuntimeError(f"Question `{question_id}` cannot be flagged.")
        codes, reason_note = self._reason_values("flag", reason_codes, note, reason)
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.FLAGGED,
                question_id=question.id,
                question_revision=question.revision,
                reason=reason_note,
                reason_codes=codes,
                reason_note=reason_note,
                metadata=dict(metadata or {}),
            )
        )

    def defer(self, question_id: str, *, reason: str = "") -> None:
        question = self._question(question_id)
        if (
            self.probe.authoring.deferrable_fields
            and question_id not in self.probe.authoring.deferrable_fields
        ):
            raise RuntimeError(f"Question `{question_id}` cannot be deferred.")
        self._trajectory = self._trajectory.append(
            _event(
                EventKind.DEFERRED,
                question_id=question.id,
                question_revision=question.revision,
                reason=reason,
            )
        )

    def resolution(self, field_id: str) -> Resolution:
        parent = self.probe.resolution_parent(field_id)
        if parent != field_id:
            inherited = self.resolution(parent)
            return Resolution(field_id, inherited.state, inherited.flagged, parent, inherited.event)
        if not _is_eligible(self.probe, self._trajectory, field_id):
            return Resolution(field_id, ResolutionState.INELIGIBLE)
        disposition = _latest_disposition(self._trajectory.events, field_id)
        flag = next(
            (
                event
                for event in reversed(self._trajectory.events)
                if event.question_id == field_id and event.kind == EventKind.FLAGGED
            ),
            None,
        )
        if disposition is not None:
            state = {
                EventKind.ANSWERED: ResolutionState.ANSWERED,
                EventKind.SKIPPED: ResolutionState.SKIPPED,
                EventKind.DEFERRED: ResolutionState.DEFERRED,
            }[disposition.kind]
            return Resolution(field_id, state, flag is not None, event=disposition)
        if flag is not None:
            return Resolution(field_id, ResolutionState.UNRESOLVED, True, event=flag)
        return Resolution(field_id, ResolutionState.UNRESOLVED)

    def validate_resolution(self, field_id: str) -> Resolution:
        resolution = self.resolution(field_id)
        if resolution.state == ResolutionState.UNRESOLVED:
            raise RuntimeError(
                f"Question `{field_id}` is unresolved; Answer or Skip before continuing."
            )
        return resolution

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

    def reach_section_boundary(self, section_id: str, store: Any) -> Any:
        """Record a declared process boundary; coordination remains external."""
        try:
            section = self.probe.section(section_id)
        except KeyError as exc:
            raise RuntimeError(f"Unknown section `{section_id}`.") from exc
        if not section.checkpoint and not section.sync_point:
            raise RuntimeError(f"Section `{section_id}` has no process boundary.")
        self._trajectory = self._trajectory.append(
            _event(EventKind.CHECKPOINT, metadata={"section_id": section.id})
        )
        if section.sync_point:
            self._trajectory = self._trajectory.append(
                _event(
                    EventKind.SYNC_POINT_REACHED,
                    metadata={"section_id": section.id, "sync_point": section.sync_point},
                )
            )
        return store.checkpoint(self._trajectory)

    def prepare_finalisation(self, *, idempotency_key: str) -> Trajectory:
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
        return candidate

    def finalise(
        self,
        store: Any,
        *,
        idempotency_key: str,
        prepared: Trajectory | None = None,
    ) -> Any:
        candidate = prepared or self.prepare_finalisation(idempotency_key=idempotency_key)
        if candidate.participation != self._trajectory.participation:
            raise RuntimeError("Prepared finalisation belongs to a different participation.")
        if not any(
            event.kind == EventKind.INTEGRATED
            and event.metadata.get("idempotency_key") == idempotency_key
            for event in candidate.events
        ):
            raise RuntimeError("Prepared finalisation lacks its idempotency event.")
        result = store.integrate(candidate, idempotency_key=idempotency_key)
        self._trajectory = candidate
        return result


def _validate_answer(question: Any, value: Any, *, probe: ProbeDefinition) -> None:
    if value is None or value == "" or value == []:
        raise RuntimeError(f"Question `{question.id}` requires a non-empty answer.")
    selected_value = value
    if (question.other.enabled or question.companions) and isinstance(value, Mapping):
        unknown = set(value) - {"selected", "other", "companions"}
        if unknown:
            raise RuntimeError(f"Question `{question.id}` has unknown composed answer fields.")
        selected_value = value.get("selected")
        other = value.get("other")
        if question.other.enabled:
            if "other" in (selected_value or ()):
                other_text = other.get("value") if isinstance(other, Mapping) else None
                if question.other.required and (
                    not isinstance(other_text, str) or not other_text.strip()
                ):
                    raise RuntimeError(f"Question `{question.id}` requires other text.")
                if other_text is not None and not isinstance(other_text, str):
                    raise RuntimeError(f"Question `{question.id}` other value requires text.")
            elif other not in (None, {}, ""):
                raise RuntimeError(
                    f"Question `{question.id}` has other text without selecting other."
                )
        elif other not in (None, {}, ""):
            raise RuntimeError(f"Question `{question.id}` has no Other control.")
        companions = value.get("companions") or {}
        if not isinstance(companions, Mapping):
            raise RuntimeError(f"Question `{question.id}` companions must be a mapping.")
        known_companions = {field.id: field for field in question.companions}
        if set(companions) - set(known_companions):
            raise RuntimeError(f"Question `{question.id}` has unknown companion answers.")
        for companion_id, companion_value in companions.items():
            if isinstance(companion_value, Mapping) and set(companion_value) == {"value"}:
                companion_value = companion_value["value"]
            _validate_answer(known_companions[companion_id], companion_value, probe=probe)
    allowed = {option.value for option in question.options}
    if question.taxonomy_id:
        allowed = {option.value for option in probe.taxonomy(question.taxonomy_id).options}
    if question.other.enabled:
        allowed.add("other")
    single_types = {InputType.SINGLE, InputType.SINGLE_WITH_OTHER}
    multiple_types = {
        InputType.MULTIPLE,
        InputType.GROUPED_MULTIPLE,
        InputType.MULTIPLE_WITH_OTHER,
    }
    if question.input_type in single_types and selected_value not in allowed:
        raise RuntimeError(f"Invalid option for question `{question.id}`.")
    if question.input_type in multiple_types:
        if isinstance(selected_value, (str, bytes)) or not isinstance(
            selected_value, (list, tuple, set)
        ):
            raise RuntimeError(f"Question `{question.id}` requires a collection of options.")
        if not set(selected_value) <= allowed:
            raise RuntimeError(f"Invalid option for question `{question.id}`.")
    if question.input_type in multiple_types:
        count = len(selected_value)
        if question.min_select is not None and count < question.min_select:
            raise RuntimeError(
                f"Question `{question.id}` requires at least {question.min_select} selections."
            )
        if question.max_select is not None and count > question.max_select:
            raise RuntimeError(
                f"Question `{question.id}` allows at most {question.max_select} selections."
            )
    if question.input_type in {InputType.REPEATABLE, InputType.REPEATABLE_GROUP}:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in value
        ):
            raise RuntimeError(f"Question `{question.id}` requires a list of group items.")
        if question.min_items is not None and len(value) < question.min_items:
            raise RuntimeError(
                f"Question `{question.id}` requires at least {question.min_items} items."
            )
        known_fields = {item.id for item in question.item_fields} | {"id"}
        seen_item_ids: set[str] = set()
        for index, item in enumerate(value):
            item_id = str(item.get("id") or "")
            if not item_id or item_id in seen_item_ids:
                raise RuntimeError(
                    f"Question `{question.id}` item {index} requires a unique stable id."
                )
            seen_item_ids.add(item_id)
            unknown = set(item) - known_fields
            if unknown:
                raise RuntimeError(
                    f"Question `{question.id}` item {index} has unknown fields: "
                    f"{', '.join(sorted(unknown))}."
                )
            missing = {
                field.id
                for field in question.item_fields
                if field.required and not item.get(field.id)
            }
            if missing:
                raise RuntimeError(
                    f"Question `{question.id}` item {index} lacks required fields: "
                    f"{', '.join(sorted(missing))}."
                )
            for field in question.item_fields:
                if field.id in item and item.get(field.id) not in (None, "", []):
                    _validate_answer(field, item[field.id], probe=probe)
    if question.input_type == InputType.NUMBER and not isinstance(value, (int, float)):
        raise RuntimeError(f"Question `{question.id}` requires a number.")
    if question.input_type == InputType.BOOLEAN and not isinstance(value, bool):
        raise RuntimeError(f"Question `{question.id}` requires a boolean.")
    if question.input_type in {InputType.TEXT, InputType.TEXT_WITH_SUGGESTIONS} and not isinstance(
        value, str
    ):
        raise RuntimeError(f"Question `{question.id}` requires text.")
    if question.input_type == InputType.URL:
        from urllib.parse import urlparse

        if (
            not isinstance(value, str)
            or urlparse(value).scheme not in {"http", "https"}
            or not urlparse(value).netloc
        ):
            raise RuntimeError(f"Question `{question.id}` requires an HTTP(S) URL.")
    if question.input_type == InputType.LOCATION:
        if not isinstance(value, Mapping):
            raise RuntimeError(f"Question `{question.id}` requires a structured location.")
        allowed_location = {
            "display_label",
            "locality",
            "region",
            "country",
            "country_code",
            "place_id",
            "latitude",
            "longitude",
        }
        if set(value) - allowed_location or not str(value.get("display_label") or "").strip():
            raise RuntimeError(f"Question `{question.id}` has an invalid structured location.")
        latitude, longitude = value.get("latitude"), value.get("longitude")
        if (latitude is None) != (longitude is None):
            raise RuntimeError(f"Question `{question.id}` location coordinates must be paired.")
        if latitude is not None and (
            not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise RuntimeError(f"Question `{question.id}` has invalid coordinates.")
