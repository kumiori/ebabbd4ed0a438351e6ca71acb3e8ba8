"""Deterministic operational and collective projections without interpretation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from .model import (
    Interpretation,
    ProbeDefinition,
    RepresentationDefinition,
    RepresentationType,
)
from .runtime import EventKind, Trajectory, _is_eligible, _latest_disposition, reconcile


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
                    state=disposition.kind.value
                    if disposition
                    else "flagged"
                    if flagged
                    else "unanswered",
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
            flagged = any(
                item.kind == EventKind.FLAGGED and item.question_id == question_id
                for item in trajectory.events
            )
            if event is None:
                counts["flagged" if flagged else "unanswered"] += 1
            elif event.kind == EventKind.SKIPPED:
                counts["skipped"] += 1
            else:
                counts.update(str(value) for value in _selected(event.value))
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


@dataclass(frozen=True)
class Denominator:
    cohort: int
    eligible: int
    resolved: int
    answered: int
    selected: int
    skipped: int
    flagged: int
    deferred: int
    unanswered: int

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class RepresentationResult:
    representation_id: str
    representation_type: str
    scope: str
    denominator: Denominator
    data: Mapping[str, Any]
    provenance: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "probe-representation-result/v1",
            "representation_id": self.representation_id,
            "representation_type": self.representation_type,
            "scope": self.scope,
            "denominator": self.denominator.to_dict(),
            "data": dict(self.data),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class ResultsBlock:
    kind: str
    representation_id: str = ""
    result: RepresentationResult | None = None
    narrative: str = ""
    commentary: Interpretation | None = None


@dataclass(frozen=True)
class ResultsProjection:
    title: str
    intro: str
    blocks: tuple[ResultsBlock, ...]


def _state(
    probe: ProbeDefinition, trajectories: tuple[Trajectory, ...], field_id: str
) -> tuple[Denominator, list[tuple[Trajectory, Any]]]:
    answers: list[tuple[Trajectory, Any]] = []
    skipped = unanswered = deferred = flagged = resolved = 0
    eligible = 0
    for trajectory in trajectories:
        if not _is_eligible(probe, trajectory, field_id):
            continue
        eligible += 1
        event = _latest_disposition(trajectory.events, field_id)
        has_flag = any(
            e.kind == EventKind.FLAGGED and e.question_id == field_id for e in trajectory.events
        )
        flagged += int(has_flag)
        if event is None:
            unanswered += 1
        elif event.kind == EventKind.DEFERRED:
            deferred += 1
            resolved += 1
        elif event.kind == EventKind.SKIPPED:
            skipped += 1
            resolved += 1
        else:
            answers.append((trajectory, event.value))
            resolved += 1
    selected = sum(len(_selected(value)) for _, value in answers)
    return Denominator(
        len(trajectories),
        eligible,
        resolved,
        len(answers),
        selected,
        skipped,
        flagged,
        deferred,
        unanswered,
    ), answers


def _selected(value: Any) -> list[Any]:
    if isinstance(value, Mapping) and "selected" in value:
        return list(value.get("selected") or ())
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _provenance(
    probe: ProbeDefinition,
    definition: RepresentationDefinition,
    trajectories: tuple[Trajectory, ...],
) -> dict[str, Any]:
    field_revisions = {
        source.field_id: probe.question(source.field_id).revision
        for source in definition.sources
        if source.field_id
    }
    taxonomy_ids = {
        probe.question(source.field_id).taxonomy_id
        for source in definition.sources
        if source.field_id and probe.question(source.field_id).taxonomy_id
    }
    population = [trajectory.participation.id for trajectory in trajectories]
    snapshot = hashlib.sha256(json.dumps(population, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "probe_id": probe.id,
        "probe_revision": probe.revision,
        "representation_revision": definition.revision,
        "field_revisions": field_revisions,
        "taxonomy_revisions": {
            taxonomy_id: probe.taxonomy(taxonomy_id).revision
            for taxonomy_id in sorted(taxonomy_ids)
        },
        "scope_ids": sorted({item.participation.scope_id for item in trajectories}),
        "participation_ids": population,
        "snapshot_id": snapshot,
        "evaluated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def evaluate_representation(
    probe: ProbeDefinition,
    definition: RepresentationDefinition | str,
    trajectories: Iterable[Trajectory],
    context: Mapping[str, Any] | None = None,
) -> RepresentationResult:
    del context
    item = probe.representation(definition) if isinstance(definition, str) else definition
    population = tuple(trajectories)
    for trajectory in population:
        if trajectory.participation.probe_id != probe.id:
            raise ValueError("Representation population contains a different Probe.")
        if trajectory.participation.probe_revision != probe.revision:
            raise ValueError("Representation population has an incompatible Probe revision.")
    if len({trajectory.participation.scope_id for trajectory in population}) > 1:
        raise ValueError("Representation population spans incompatible scopes.")
    if item.scope.value == "participant" and len(population) != 1:
        raise ValueError("Participant representations require exactly one trajectory.")

    denominator = Denominator(len(population), len(population), 0, 0, 0, 0, 0, 0, len(population))
    data: dict[str, Any]
    if item.type == RepresentationType.TIMELINE:
        data = {"events": list(timeline_events(population))}
    elif item.type == RepresentationType.COMPOSITE:
        components = []
        for index, component in enumerate(item.components):
            if isinstance(component, str):
                components.append(evaluate_representation(probe, component, population))
                continue
            projection = dict(component.projection)
            if component.type == RepresentationType.GROUPED_DISTRIBUTION:
                projection.setdefault("group_by", "taxonomy_group")
            inline = RepresentationDefinition(
                id=f"{item.id}.component.{index + 1}",
                revision=item.revision,
                type=component.type,
                scope=item.scope,
                sources=(component.source,),
                projection=projection,
            )
            components.append(evaluate_representation(probe, inline, population))
        data = {"components": [component.to_dict() for component in components]}
    elif item.type == RepresentationType.COMPARISON:
        roles: dict[str, dict[str, int]] = {}
        denominators: dict[str, dict[str, int]] = {}
        for source in item.sources:
            source_denominator, answers = _state(probe, population, source.field_id)
            counts = Counter(str(value) for _, answer in answers for value in _selected(answer))
            roles[source.role] = dict(sorted(counts.items()))
            denominators[source.role] = source_denominator.to_dict()
        denominator = Denominator(
            len(population),
            len(population),
            sum(value["resolved"] for value in denominators.values()),
            sum(value["answered"] for value in denominators.values()),
            sum(value["selected"] for value in denominators.values()),
            sum(value["skipped"] for value in denominators.values()),
            sum(value["flagged"] for value in denominators.values()),
            sum(value["deferred"] for value in denominators.values()),
            sum(value["unanswered"] for value in denominators.values()),
        )
        data = {"roles": roles, "denominators": denominators}
    else:
        source = item.sources[0]
        denominator, answers = _state(probe, population, source.field_id)
        if item.type in {RepresentationType.DISTRIBUTION, RepresentationType.GROUPED_DISTRIBUTION}:
            counts = Counter(str(value) for _, answer in answers for value in _selected(answer))
            base = denominator.answered or 1
            values = {
                key: {"count": count, "proportion": count / base}
                for key, count in sorted(counts.items())
            }
            data = {"values": values}
            if (
                item.type == RepresentationType.GROUPED_DISTRIBUTION
                or item.projection.get("group_by") == "taxonomy_group"
            ):
                question = probe.question(source.field_id)
                taxonomy_id = str(
                    item.projection.get("taxonomy") or question.taxonomy_id
                )
                groups = probe.taxonomy(taxonomy_id).groups if taxonomy_id else ()
                data["groups"] = {
                    group.id: {
                        "option_ids": list(group.option_values),
                        "count": sum(counts[value] for value in group.option_values),
                    }
                    for group in groups
                }
        elif item.type == RepresentationType.RESPONSES:
            data = {
                "responses": [
                    {"participant_id": trajectory.participation.participant_id, "value": answer}
                    for trajectory, answer in answers
                ]
            }
        elif item.type == RepresentationType.RECORDS:
            data = {
                "records": [
                    {"participant_id": trajectory.participation.participant_id, "value": answer}
                    for trajectory, answer in answers
                ]
            }
        else:
            raise ValueError(f"Unsupported representation type `{item.type}`.")
    return RepresentationResult(
        item.id,
        item.type.value,
        item.scope.value,
        denominator,
        data,
        _provenance(probe, item, population),
    )


def evaluate_results(
    probe: ProbeDefinition, trajectories: Iterable[Trajectory]
) -> ResultsProjection:
    if probe.results is None:
        raise ValueError("Probe has no authored results composition.")
    population = tuple(trajectories)
    blocks = []
    for block in probe.results.blocks:
        if block.representation_id:
            blocks.append(
                ResultsBlock(
                    "representation",
                    block.representation_id,
                    evaluate_representation(probe, block.representation_id, population),
                    commentary=block.commentary,
                )
            )
        else:
            blocks.append(ResultsBlock("narrative", narrative=block.narrative))
    return ResultsProjection(probe.results.title, probe.results.intro, tuple(blocks))


def representation_result_from_dict(payload: Mapping[str, Any]) -> RepresentationResult:
    if payload.get("schema") != "probe-representation-result/v1":
        raise ValueError(f"Unsupported representation result schema `{payload.get('schema')}`.")
    return RepresentationResult(
        str(payload["representation_id"]),
        str(payload["representation_type"]),
        str(payload["scope"]),
        Denominator(
            **(
                {
                    "resolved": int((payload.get("denominator") or {}).get("eligible", 0))
                    - int((payload.get("denominator") or {}).get("unanswered", 0)),
                    **dict(payload.get("denominator") or {}),
                }
            )
        ),
        dict(payload.get("data") or {}),
        dict(payload.get("provenance") or {}),
    )
