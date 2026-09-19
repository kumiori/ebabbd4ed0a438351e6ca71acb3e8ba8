"""Explicit versioned serialization for Probe definitions and trajectories."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import (
    DefinitionError,
    InputType,
    NarrativeBlock,
    Option,
    ProbeDefinition,
    QuestionBlock,
    QuestionDefinition,
    RevisionLineage,
    SectionBlock,
)
from .runtime import EventKind, Participation, Trajectory, TrajectoryEvent


class SchemaError(ValueError):
    pass


def probe_from_dict(payload: Mapping[str, Any]) -> ProbeDefinition:
    if payload.get("schema") != "probe-definition/v1":
        raise SchemaError(f"Unsupported Probe schema `{payload.get('schema')}`.")
    questions = tuple(
        QuestionDefinition(
            id=str(raw["id"]),
            revision=int(raw["revision"]),
            prompt=str(raw["prompt"]),
            context=str(raw.get("context") or ""),
            input_type=InputType(raw.get("input_type") or "single"),
            options=tuple(Option(str(item["value"]), str(item["label"])) for item in raw.get("options") or ()),
            required=bool(raw.get("required")),
            skippable=bool(raw.get("skippable", True)),
            flaggable=bool(raw.get("flaggable", True)),
            allow_comment=bool(raw.get("allow_comment")),
            shared_dimension=str(raw.get("shared_dimension") or ""),
            status=str(raw.get("status") or "active"),
            lineage=RevisionLineage(**dict(raw.get("lineage") or {})),
            metadata=dict(raw.get("metadata") or {}),
        )
        for raw in payload.get("questions") or ()
    )
    blocks = []
    for raw in payload.get("blocks") or ():
        if raw.get("kind") == "narrative":
            blocks.append(NarrativeBlock(str(raw.get("markdown") or "")))
        elif raw.get("kind") == "question":
            blocks.append(QuestionBlock(str(raw.get("question_id") or "")))
        elif raw.get("kind") == "section":
            blocks.append(SectionBlock(str(raw.get("id") or ""), str(raw.get("title") or "")))
        else:
            raise DefinitionError(f"Unsupported block kind `{raw.get('kind')}`.")
    return ProbeDefinition(
        id=str(payload.get("id") or ""),
        revision=int(payload.get("revision") or 0),
        title=str(payload.get("title") or ""),
        status=str(payload.get("status") or "active"),
        blocks=tuple(blocks),
        questions=questions,
        metadata=dict(payload.get("metadata") or {}),
    )


def trajectory_from_dict(payload: Mapping[str, Any]) -> Trajectory:
    if payload.get("schema") != "probe-trajectory/v1":
        raise SchemaError(f"Unsupported trajectory schema `{payload.get('schema')}`.")
    raw = dict(payload.get("participation") or {})
    participation = Participation(
        id=str(raw["id"]),
        participant_id=str(raw["participant_id"]),
        probe_id=str(raw["probe_id"]),
        probe_revision=int(raw["probe_revision"]),
        scope_id=str(raw["scope_id"]),
    )
    return Trajectory(
        participation,
        tuple(
            TrajectoryEvent(
                id=str(event["id"]),
                kind=EventKind(event["kind"]),
                timestamp=str(event["timestamp"]),
                question_id=str(event.get("question_id") or ""),
                question_revision=event.get("question_revision"),
                value=event.get("value"),
                reason=str(event.get("reason") or ""),
                metadata=dict(event.get("metadata") or {}),
            )
            for event in payload.get("events") or ()
        ),
    )
