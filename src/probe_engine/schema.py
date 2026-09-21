"""Explicit versioned serialization for Probe definitions and trajectories."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import (
    CheckpointDefinition,
    Condition,
    DefinitionError,
    FieldDefinition,
    FlowModeDefinition,
    FingerprintAxis,
    EditorialReviewItem,
    AuthoringDefinition,
    InputType,
    LocationCapabilities,
    NarrativeBlock,
    Option,
    OptionGroup,
    OtherControl,
    ProbeDefinition,
    QuestionBlock,
    QuestionDefinition,
    RevisionLineage,
    RepresentationDefinition,
    RepresentationComponent,
    RepresentationScope,
    RepresentationSource,
    RepresentationType,
    Interpretation,
    ResultBlockDefinition,
    ResultsDefinition,
    ReasonTaxonomy,
    ResolutionDefinition,
    SelectionShortcut,
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
        return Condition(
            str(raw.get("field_id") or ""),
            str(raw.get("operator") or "equals"),
            raw.get("value"),
            tuple(condition(item) for item in raw.get("clauses") or ()),  # type: ignore[arg-type]
        )

    def other(raw: Mapping[str, Any] | None) -> OtherControl:
        value = dict(raw or {})
        return OtherControl(
            enabled=bool(value.get("enabled")),
            field_id=str(value.get("field_id") or ""),
            label=str(value.get("label") or ""),
            placeholder=str(value.get("placeholder") or ""),
            required=bool(value.get("required")),
            visible_if=condition(value.get("visible_if")),
        )

    def capabilities(raw: Mapping[str, Any] | None) -> LocationCapabilities | None:
        if not raw:
            return None
        return LocationCapabilities(
            bool(raw.get("manual_text")),
            bool(raw.get("geolocation_lookup")),
            bool(raw.get("geolocation_requires_user_action", True)),
            str(raw.get("lookup_trigger") or "explicit_action"),
            str(raw.get("lookup_behavior") or "suggest_and_confirm_match"),
        )

    def route(raw: Mapping[str, Any]) -> TerminalRoute:
        return TerminalRoute(
            condition(raw.get("when")),
            str(raw.get("action") or ""),
            dict(raw.get("metadata") or {}),
        )  # type: ignore[arg-type]

    def field_values(raw: Mapping[str, Any], *, nested: bool = False) -> dict[str, Any]:
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
                FieldDefinition(**field_values(item, nested=True))
                for item in raw.get("item_fields") or ()
            ),
            "metadata": dict(raw.get("metadata") or {}),
            "independently_answerable": bool(raw.get("independently_answerable", not nested)),
            "shortcuts": tuple(
                SelectionShortcut(
                    str(item["id"]),
                    str(item["label"]),
                    tuple(str(value) for value in item.get("select") or ()),
                )
                for item in raw.get("shortcuts") or ()
            ),
            "capabilities": capabilities(raw.get("capabilities")),
            "companions": tuple(
                FieldDefinition(**field_values(item, nested=True))
                for item in raw.get("companions") or ()
            ),
            "option_groups": tuple(group(item) for item in raw.get("option_groups") or ()),
            "free_text_field": (
                FieldDefinition(**field_values(raw["free_text_field"], nested=True))
                if raw.get("free_text_field")
                else None
            ),
        }

    questions = tuple(
        QuestionDefinition(
            **field_values(raw),
            skippable=bool(raw.get("skippable", True)),
            skip_action=str(raw.get("skip_action") or "continue"),
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
            blocks.append(
                SectionBlock(
                    str(raw.get("id") or ""),
                    str(raw.get("title") or ""),
                    tuple(str(item) for item in raw.get("steps") or ()),
                    dict(raw.get("process") or {}),
                )
            )
        else:
            raise DefinitionError(f"Unsupported block kind `{raw.get('kind')}`.")

    def representation_component(raw: Mapping[str, Any]) -> str | RepresentationComponent:
        if "representation" in raw:
            return str(raw["representation"])
        source = dict(raw.get("source") or {})
        return RepresentationComponent(
            RepresentationType(raw["type"]),
            RepresentationSource(
                field_id=str(source.get("field") or ""),
                trajectory=str(source.get("trajectory") or ""),
                role=str(source.get("role") or ""),
                path=tuple(str(part) for part in source.get("path") or ()),
            ),
            dict(raw.get("projection") or {}),
        )

    representations = tuple(
        RepresentationDefinition(
            id=str(raw["id"]),
            revision=int(raw["revision"]),
            type=RepresentationType(raw["type"]),
            scope=RepresentationScope(raw["scope"]),
            sources=tuple(
                RepresentationSource(
                    field_id=str(source.get("field") or ""),
                    trajectory=str(source.get("trajectory") or ""),
                    role=str(source.get("role") or ""),
                    path=tuple(str(part) for part in source.get("path") or ()),
                )
                for source in raw.get("sources") or ()
            ),
            projection=dict(raw.get("projection") or {}),
            components=tuple(
                representation_component(value) for value in raw.get("components") or ()
            ),
            title=str(raw.get("title") or ""),
        )
        for raw in payload.get("representations") or ()
    )
    raw_results = payload.get("results")
    results = None
    if raw_results:
        result_blocks = []
        for raw in raw_results.get("blocks") or ():
            if raw.get("type") == "narrative":
                result_blocks.append(
                    ResultBlockDefinition(narrative=str(raw.get("markdown") or ""))
                )
            else:
                commentary = raw.get("commentary")
                result_blocks.append(
                    ResultBlockDefinition(
                        representation_id=str(raw.get("representation") or ""),
                        commentary=Interpretation(
                            str(commentary.get("markdown") or ""),
                            str(commentary.get("kind") or "authored"),
                        )
                        if commentary
                        else None,
                    )
                )
        results = ResultsDefinition(
            str(raw_results.get("title") or ""),
            str(raw_results.get("intro") or ""),
            tuple(result_blocks),
        )
    raw_resolution = dict(payload.get("resolution") or {})
    defaults = ResolutionDefinition()

    def reasons(name: str, default: ReasonTaxonomy) -> ReasonTaxonomy:
        raw = raw_resolution.get(name)
        if not raw:
            return default
        return ReasonTaxonomy(
            str(raw["id"]),
            int(raw["revision"]),
            tuple(option(item) for item in raw.get("options") or ()),
        )

    resolution = ResolutionDefinition(
        skip_reasons=reasons("skip_reasons", defaults.skip_reasons),
        flag_reasons=reasons("flag_reasons", defaults.flag_reasons),
        actions=tuple(str(value) for value in raw_resolution.get("actions") or defaults.actions),
        nothing_substantively_mandatory=bool(
            raw_resolution.get(
                "nothing_substantively_mandatory", defaults.nothing_substantively_mandatory
            )
        ),
        answer_before_meta_actions=bool(
            raw_resolution.get("answer_before_meta_actions", defaults.answer_before_meta_actions)
        ),
        subordinate_fields_inherit_parent_resolution=bool(
            raw_resolution.get(
                "subordinate_fields_inherit_parent_resolution",
                defaults.subordinate_fields_inherit_parent_resolution,
            )
        ),
        skip_enabled=bool(raw_resolution.get("skip_enabled", defaults.skip_enabled)),
        skip_reason_prompt=str(raw_resolution.get("skip_reason_prompt") or ""),
        skip_note_optional=bool(
            raw_resolution.get("skip_note_optional", defaults.skip_note_optional)
        ),
        flag_enabled=bool(raw_resolution.get("flag_enabled", defaults.flag_enabled)),
        flag_prompt=str(raw_resolution.get("flag_prompt") or ""),
        flag_note_optional=bool(
            raw_resolution.get("flag_note_optional", defaults.flag_note_optional)
        ),
        review_editable=bool(raw_resolution.get("review_editable", defaults.review_editable)),
    )
    raw_authoring = dict(payload.get("authoring") or {})
    authoring = AuthoringDefinition(
        language=str(raw_authoring.get("language") or ""),
        default_mode=str(raw_authoring.get("default_mode") or ""),
        show_mode_selection=bool(raw_authoring.get("show_mode_selection")),
        show_welcome_step=bool(raw_authoring.get("show_welcome_step")),
        identity_position=str(raw_authoring.get("identity_position") or ""),
        review=dict(raw_authoring.get("review") or {}),
        step_order=tuple(str(value) for value in raw_authoring.get("step_order") or ()),
        flow_modes=tuple(
            FlowModeDefinition(
                str(item["id"]),
                str(item.get("title") or ""),
                str(item.get("detail") or ""),
                tuple(str(value) for value in item.get("step_ids") or ()),
            )
            for item in raw_authoring.get("flow_modes") or ()
        ),
        profile_fields=tuple(str(value) for value in raw_authoring.get("profile_fields") or ()),
        session_fields=tuple(str(value) for value in raw_authoring.get("session_fields") or ()),
        deferrable_fields=tuple(
            str(value) for value in raw_authoring.get("deferrable_fields") or ()
        ),
        fingerprint_axes=tuple(
            FingerprintAxis(
                str(item["id"]),
                str(item.get("source_field_id") or ""),
                str(item.get("taxonomy_id") or ""),
            )
            for item in raw_authoring.get("fingerprint_axes") or ()
        ),
        editorial_review=tuple(
            EditorialReviewItem(str(item["id"]), str(item["status"]), str(item.get("note") or ""))
            for item in raw_authoring.get("editorial_review") or ()
        ),
        presentation_hints=dict(raw_authoring.get("presentation_hints") or {}),
    )
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
                bool(
                    ((raw.get("process") or {}).get("checkpoint") or {}).get("enabled")
                    if isinstance((raw.get("process") or {}).get("checkpoint"), Mapping)
                    else (raw.get("process") or {}).get("checkpoint")
                ),
                str((raw.get("process") or {}).get("sync_point") or ""),
                CheckpointDefinition(
                    enabled=bool(((raw.get("process") or {}).get("checkpoint") or {}).get("enabled")),
                    review=bool(((raw.get("process") or {}).get("checkpoint") or {}).get("review")),
                    draft_save=bool(((raw.get("process") or {}).get("checkpoint") or {}).get("draft_save")),
                    export_yaml=bool(((((raw.get("process") or {}).get("checkpoint") or {}).get("export") or {}).get("yaml"))),
                )
                if isinstance((raw.get("process") or {}).get("checkpoint"), Mapping)
                else CheckpointDefinition(
                    enabled=bool((raw.get("process") or {}).get("checkpoint")),
                    draft_save=bool((raw.get("process") or {}).get("checkpoint")),
                ),
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
            int(raw.get("revision") or 1),
            dict(raw.get("presentation") or {}),
            )
            for raw in payload.get("taxonomies") or ()
        ),
        representations=representations,
        results=results,
        resolution=resolution,
        authoring=authoring,
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
                reason_codes=tuple(str(value) for value in event.get("reason_codes") or ()),
                reason_note=str(event.get("reason_note") or event.get("reason") or ""),
                legacy_reason_codes=tuple(
                    str(value) for value in event.get("legacy_reason_codes") or ()
                ),
                metadata=dict(event.get("metadata") or {}),
            )
            for event in payload.get("events") or ()
        ),
    )
    (OtherControl,)
