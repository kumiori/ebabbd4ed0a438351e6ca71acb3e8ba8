"""Explicit versioned serialization for Probe definitions and trajectories."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import (
    Condition,
    DefinitionError,
    FieldDefinition,
    InputType,
    NarrativeBlock,
    Option,
    OptionGroup,
    OtherControl,
    ProbeDefinition,
    QuestionBlock,
    QuestionDefinition,
    RevisionLineage,
    SectionBlock,
    SectionDefinition,
    StepDefinition,
    Taxonomy,
    TerminalRoute,
)
from .runtime import EventKind, Participation, Trajectory, TrajectoryEvent


class SchemaError(ValueError):
    pass


def probe_from_dict(payload: Mapping[str, Any]) -> ProbeDefinition:
    if payload.get("schema") != "probe-definition/v1":
        raise SchemaError(f"Unsupported Probe schema `{payload.get('schema')}`.")
    def option(raw: Mapping[str, Any]) -> Option:
        return Option(str(raw["value"]), str(raw["label"]))

    def group(raw: Mapping[str, Any]) -> OptionGroup:
        return OptionGroup(
            str(raw["id"]),
            str(raw["label"]),
            tuple(str(value) for value in raw.get("option_values") or ()),
        )

    def condition(raw: Mapping[str, Any] | None) -> Condition | None:
        if not raw:
            return None
        return Condition(str(raw["field_id"]), str(raw["operator"]), raw.get("value"))

    def other(raw: Mapping[str, Any] | None) -> OtherControl:
        value = dict(raw or {})
        return OtherControl(
            enabled=bool(value.get("enabled")),
            field_id=str(value.get("field_id") or ""),
            label=str(value.get("label") or ""),
            placeholder=str(value.get("placeholder") or ""),
            required=bool(value.get("required")),
        )

    def route(raw: Mapping[str, Any]) -> TerminalRoute:
        return TerminalRoute(condition(raw.get("when")), str(raw.get("action") or ""))  # type: ignore[arg-type]

    def field_values(raw: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(raw["id"]),
            "revision": int(raw["revision"]),
            "prompt": str(raw["prompt"]),
            "context": str(raw.get("context") or ""),
            "input_type": InputType(raw.get("input_type") or "single"),
            "required": bool(raw.get("required")),
            "options": tuple(option(item) for item in raw.get("options") or ()),
            "taxonomy_id": str(raw.get("taxonomy_id") or ""),
            "suggestions": tuple(option(item) for item in raw.get("suggestions") or ()),
            "presentation": dict(raw.get("presentation") or {}),
            "other": other(raw.get("other")),
            "min_select": raw.get("min_select"),
            "max_select": raw.get("max_select"),
            "min_items": raw.get("min_items"),
            "visible_if": condition(raw.get("visible_if")),
            "routes": tuple(route(item) for item in raw.get("routes") or ()),
            "item_fields": tuple(
                FieldDefinition(**field_values(item)) for item in raw.get("item_fields") or ()
            ),
            "metadata": dict(raw.get("metadata") or {}),
        }

    questions = tuple(
        QuestionDefinition(
            **field_values(raw),
            skippable=bool(raw.get("skippable", True)),
            flaggable=bool(raw.get("flaggable", True)),
            allow_comment=bool(raw.get("allow_comment")),
            shared_dimension=str(raw.get("shared_dimension") or ""),
            status=str(raw.get("status") or "active"),
            lineage=RevisionLineage(**dict(raw.get("lineage") or {})),
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
            blocks.append(SectionBlock(
                str(raw.get("id") or ""),
                str(raw.get("title") or ""),
                tuple(str(item) for item in raw.get("steps") or ()),
                dict(raw.get("process") or {}),
            ))
        else:
            raise DefinitionError(f"Unsupported block kind `{raw.get('kind')}`.")
    return ProbeDefinition(
        id=str(payload.get("id") or ""),
        revision=int(payload.get("revision") or 0),
        title=str(payload.get("title") or ""),
        status=str(payload.get("status") or "active"),
        blocks=tuple(blocks),
        questions=questions,
        sections=tuple(
            SectionDefinition(
                str(raw["id"]),
                str(raw["title"]),
                tuple(str(value) for value in raw.get("step_ids") or ()),
                bool((raw.get("process") or {}).get("checkpoint")),
                str((raw.get("process") or {}).get("sync_point") or ""),
            )
            for raw in payload.get("sections") or ()
        ),
        steps=tuple(
            StepDefinition(
                str(raw["id"]),
                str(raw["title"]),
                str(raw.get("body") or ""),
                str(raw.get("cta") or ""),
                tuple(str(value) for value in raw.get("field_ids") or ()),
            )
            for raw in payload.get("steps") or ()
        ),
        taxonomies=tuple(
            Taxonomy(
                str(raw["id"]),
                tuple(option(item) for item in raw.get("options") or ()),
                tuple(group(item) for item in raw.get("groups") or ()),
            )
            for raw in payload.get("taxonomies") or ()
        ),
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
    OtherControl,
