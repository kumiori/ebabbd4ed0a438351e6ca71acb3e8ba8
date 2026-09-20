"""YAML and augmented-Markdown front ends for canonical Probe definitions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import yaml

from .model import (
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

DIRECTIVE_PATTERN = re.compile(r"\{\{\s*question\s*:\s*(?P<id>[a-zA-Z0-9][a-zA-Z0-9_.-]*)\s*\}\}")


class _Yaml12SafeLoader(yaml.SafeLoader):
    """Safe loader that does not coerce identity tokens such as yes/no/on/off."""


for first, resolvers in tuple(_Yaml12SafeLoader.yaml_implicit_resolvers.items()):
    _Yaml12SafeLoader.yaml_implicit_resolvers[first] = [
        (tag, pattern) for tag, pattern in resolvers if tag != "tag:yaml.org,2002:bool"
    ]
_Yaml12SafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


class MarkdownParser(Protocol):
    def parse(self, body: str) -> tuple[NarrativeBlock | QuestionBlock, ...]: ...


class DirectiveMarkdownParser:
    """Replaceable v0.1 parser for the documented question-directive syntax."""

    def parse(self, body: str) -> tuple[NarrativeBlock | QuestionBlock, ...]:
        blocks: list[NarrativeBlock | QuestionBlock] = []
        cursor = 0
        for match in DIRECTIVE_PATTERN.finditer(body):
            if match.start() > cursor:
                blocks.append(NarrativeBlock(body[cursor : match.start()]))
            blocks.append(QuestionBlock(match.group("id")))
            cursor = match.end()
        if cursor < len(body):
            blocks.append(NarrativeBlock(body[cursor:]))
        return tuple(blocks)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DefinitionError(f"`{name}` must be a mapping.")
    return value


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"true", "yes", "1", "on"}:
        return True
    if token in {"false", "no", "0", "off"}:
        return False
    raise DefinitionError(f"Invalid boolean value `{value}`.")


def _options(raw: Any) -> tuple[Option, ...]:
    built = []
    for item in raw or ():
        if isinstance(item, Mapping):
            built.append(Option(str(item.get("value") or ""), str(item.get("label") or "")))
        else:
            built.append(Option(str(item), str(item)))
    return tuple(built)


def _reject_unknown(raw: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(raw) - allowed
    if unknown:
        raise DefinitionError(f"Unsupported semantics in {context}: {', '.join(sorted(unknown))}.")


def _condition(raw: Any, context: str) -> Condition | None:
    if raw is None:
        return None
    value = _mapping(raw, context)
    _reject_unknown(value, {"field", "equals"}, context)
    if "equals" not in value:
        raise DefinitionError(f"`{context}` currently requires `equals`.")
    return Condition(str(value.get("field") or ""), "equals", value.get("equals"))


def _other(raw: Any, context: str) -> OtherControl:
    if raw is None:
        return OtherControl()
    value = _mapping(raw, context)
    _reject_unknown(value, {"enabled", "field", "label", "placeholder", "required"}, context)
    return OtherControl(
        enabled=_bool(value.get("enabled"), True),
        field_id=str(value.get("field") or ""),
        label=str(value.get("label") or ""),
        placeholder=str(value.get("placeholder") or ""),
        required=_bool(value.get("required"), False),
    )


def _input_type(raw_type: Any, context: str) -> InputType:
    aliases = {
        "single_choice": "single",
        "multiple_choice": "multiple",
        "multi": "multiple",
    }
    token = str(raw_type or "single")
    try:
        return InputType(aliases.get(token, token))
    except ValueError as exc:
        raise DefinitionError(f"Unsupported input type `{token}` in {context}.") from exc


_FIELD_KEYS = {
    "id",
    "revision",
    "prompt",
    "context",
    "type",
    "required",
    "options",
    "taxonomy",
    "suggestions",
    "presentation",
    "other",
    "min_select",
    "max_select",
    "min_items",
    "visible_if",
    "routing",
    "item",
    "skippable",
    "flaggable",
    "allow_comment",
    "shared_dimension",
    "status",
    "lineage",
    "metadata",
    "independently_answerable",
    "shortcuts",
    "capabilities",
    "companions",
    "option_groups",
    "free_text_field",
}


def _field_common(raw: Mapping[str, Any], *, nested: bool) -> dict[str, Any]:
    field_id = str(raw.get("id") or "").strip()
    context = f"field `{field_id or '?'}`"
    _reject_unknown(raw, _FIELD_KEYS, context)
    input_type = _input_type(raw.get("type"), context)
    item_fields: tuple[FieldDefinition, ...] = ()
    if input_type == InputType.REPEATABLE:
        item = _mapping(raw.get("item") or {}, f"{context}.item")
        _reject_unknown(item, {"fields"}, f"{context}.item")
        item_fields = tuple(
            _nested_field(_mapping(value, f"{context}.item.fields"))
            for value in item.get("fields") or ()
        )
    routes = []
    for route_raw in raw.get("routing") or ():
        route = _mapping(route_raw, f"{context}.routing")
        _reject_unknown(route, {"when", "action"}, f"{context}.routing")
        action = str(route.get("action") or "")
        if action == "end_session":
            action = "end"
        routes.append(
            TerminalRoute(
                _condition(route.get("when"), f"{context}.routing.when"),  # type: ignore[arg-type]
                action,
            )
        )
    return {
        "id": field_id,
        "revision": int(raw.get("revision") or 1),
        "prompt": str(raw.get("prompt") or "").strip(),
        "context": str(raw.get("context") or "").strip(),
        "input_type": input_type,
        "options": _options(raw.get("options")),
        "taxonomy_id": str(raw.get("taxonomy") or ""),
        "suggestions": _options(raw.get("suggestions")),
        "presentation": dict(_mapping(raw.get("presentation") or {}, f"{context}.presentation")),
        "other": _other(raw.get("other"), f"{context}.other"),
        "required": _bool(raw.get("required"), False),
        "min_select": int(raw["min_select"]) if raw.get("min_select") is not None else None,
        "max_select": int(raw["max_select"]) if raw.get("max_select") is not None else None,
        "min_items": int(raw["min_items"]) if raw.get("min_items") is not None else None,
        "visible_if": _condition(raw.get("visible_if"), f"{context}.visible_if"),
        "routes": tuple(routes),
        "item_fields": item_fields,
        "metadata": dict(_mapping(raw.get("metadata") or {}, f"{context}.metadata")),
        "independently_answerable": _bool(raw.get("independently_answerable"), not nested),
    }


def _nested_field(raw: Mapping[str, Any]) -> FieldDefinition:
    return FieldDefinition(**_field_common(raw, nested=True))


def _canonical_question(raw: Mapping[str, Any]) -> QuestionDefinition:
    common = _field_common(raw, nested=False)
    lineage_raw = _mapping(raw.get("lineage") or {}, f"field `{common['id']}`.lineage")
    common.pop("metadata")
    return QuestionDefinition(
        **common,
        skippable=_bool(raw.get("skippable"), True),
        flaggable=_bool(raw.get("flaggable"), True),
        allow_comment=_bool(raw.get("allow_comment"), False),
        shared_dimension=str(raw.get("shared_dimension") or ""),
        status=str(raw.get("status") or "active"),
        lineage=RevisionLineage(
            supersedes_revision=lineage_raw.get("supersedes_revision"),
            change_type=str(lineage_raw.get("change_type") or "initial"),
            reason=str(lineage_raw.get("reason") or ""),
            reask_if_answered=_bool(lineage_raw.get("reask_if_answered"), False),
        ),
        metadata=dict(raw.get("metadata") or {}),
    )


def _question(
    raw: Mapping[str, Any],
    *,
    fallback_id: str = "",
) -> QuestionDefinition:
    question_id = str(raw.get("id") or fallback_id).strip()
    revision = int(raw.get("revision") or 1)
    change = _mapping(raw.get("change") or raw.get("lineage") or {}, "change")
    raw_type = str(raw.get("input_type") or raw.get("mode") or "single")
    input_type = _input_type(raw_type, f"question `{question_id}`")
    return QuestionDefinition(
        id=question_id,
        revision=revision,
        prompt=str(raw.get("prompt") or raw.get("title") or "").strip(),
        context=str(raw.get("context") or raw.get("subtitle") or "").strip(),
        input_type=input_type,
        options=_options(raw.get("options")),
        required=_bool(raw.get("required"), False),
        skippable=_bool(raw.get("skippable"), True),
        flaggable=_bool(raw.get("flaggable"), True),
        allow_comment=_bool(raw.get("allow_comment"), False),
        shared_dimension=str(raw.get("shared_dimension") or ""),
        status=str(raw.get("status") or "active"),
        lineage=RevisionLineage(
            supersedes_revision=(
                int(raw.get("supersedes_revision"))
                if raw.get("supersedes_revision") is not None
                else change.get("supersedes_revision")
            ),
            change_type=str(change.get("type") or change.get("change_type") or "initial"),
            reason=str(change.get("reason") or ""),
            reask_if_answered=_bool(change.get("reask_if_answered"), False),
        ),
        metadata=dict(raw.get("metadata") or {}),
    )


def load_question_catalogue(
    source: str | Path | Mapping[str, Any],
) -> dict[str, QuestionDefinition]:
    payload = _load_yaml(source)
    entries = payload.get("questions") if "questions" in payload else payload
    entries = _mapping(entries, "questions")
    return {
        str(question_id): _question(_mapping(raw, str(question_id)), fallback_id=str(question_id))
        for question_id, raw in entries.items()
    }


def _load_yaml(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source)
    text = path.read_text(encoding="utf-8") if path.exists() else str(source)
    payload = yaml.load(text, Loader=_Yaml12SafeLoader) or {}
    return dict(_mapping(payload, "document"))


def _authored_options(raw: Any, context: str) -> tuple[Option, ...]:
    """Compile authored options, coalescing repeated declarations by stable value."""
    ordered: dict[str, str] = {}
    for value in raw or ():
        item = (
            _mapping(value, context)
            if isinstance(value, Mapping)
            else {"value": value, "label": value}
        )
        option_value = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        if not option_value:
            raise DefinitionError(f"{context} contains an option without a stable value.")
        if option_value not in ordered or (not ordered[option_value] and label):
            ordered[option_value] = label
    missing = [value for value, label in ordered.items() if not label]
    if missing:
        raise DefinitionError(f"{context} options require labels: {', '.join(missing)}.")
    return tuple(Option(value, label) for value, label in ordered.items())


def _authored_condition(raw: Any, *, default_field: str = "") -> Condition | None:
    if raw is None:
        return None
    item = _mapping(raw, "condition")
    if "any" in item:
        _reject_unknown(item, {"any"}, "condition")
        return Condition(
            operator="any",
            clauses=tuple(_authored_condition(value) for value in item.get("any") or ()),
        )  # type: ignore[arg-type]
    operators = [name for name in ("equals", "contains") if name in item]
    if len(operators) != 1:
        raise DefinitionError("Conditions require exactly one of `equals` or `contains`.")
    _reject_unknown(item, {"field", operators[0]}, "condition")
    return Condition(str(item.get("field") or default_field), operators[0], item[operators[0]])


def _authoring_taxonomies(payload: Mapping[str, Any]) -> tuple[Taxonomy, ...]:
    built = []
    for taxonomy_id, raw_value in _mapping(payload.get("taxonomies") or {}, "taxonomies").items():
        raw = _mapping(raw_value, f"taxonomy `{taxonomy_id}`")
        _reject_unknown(
            raw, {"revision", "options", "groups", "presentation"},
            f"taxonomy `{taxonomy_id}`"
        )
        options: list[Option] = []
        groups: list[OptionGroup] = []
        for group_value in raw.get("groups") or ():
            group = _mapping(group_value, f"taxonomy `{taxonomy_id}` group")
            _reject_unknown(group, {"id", "label", "options"}, f"taxonomy `{taxonomy_id}` group")
            group_options = _authored_options(
                group.get("options"), f"taxonomy `{taxonomy_id}` group"
            )
            options.extend(group_options)
            groups.append(
                OptionGroup(
                    str(group.get("id") or ""),
                    str(group.get("label") or ""),
                    tuple(item.value for item in group_options),
                )
            )
        options.extend(_authored_options(raw.get("options"), f"taxonomy `{taxonomy_id}`"))
        deduped = _authored_options(
            ({"value": item.value, "label": item.label} for item in options),
            f"taxonomy `{taxonomy_id}`",
        )
        built.append(
            Taxonomy(
                str(taxonomy_id), deduped, tuple(groups),
                int(raw.get("revision") or 1),
                dict(_mapping(raw.get("presentation") or {}, "taxonomy presentation")),
            )
        )
    return tuple(built)


def _authoring_subordinate(
    raw: Any,
    *,
    revision: int,
    kind: str,
) -> FieldDefinition | None:
    if raw is None:
        return None
    item = _mapping(raw, kind)
    _reject_unknown(item, {"field", "prompt", "show_if", "required"}, kind)
    return FieldDefinition(
        id=str(item.get("field") or ""),
        revision=revision,
        prompt=str(item.get("prompt") or item.get("field") or ""),
        input_type=InputType.TEXT,
        required=_bool(item.get("required"), False),
        visible_if=_authored_condition(item.get("show_if")),
        independently_answerable=False,
        metadata={"relationship": kind},
    )


def _authoring_field(
    raw: Mapping[str, Any], *, nested: bool = False, parent_revision: int = 1
) -> FieldDefinition | QuestionDefinition:
    allowed = {
        "step",
        "field",
        "id",
        "revision",
        "prompt",
        "context",
        "input_type",
        "required",
        "options",
        "groups",
        "taxonomy",
        "free_text",
        "companion",
        "fields",
        "suggestions",
        "show_if",
        "shortcuts",
        "capabilities",
        "min_select",
        "max_select",
        "min_items",
        "routing",
        "allow_skip",
        "selection_feedback",
        "suggestion_label",
        "detail_prompt",
        "detail_placeholder",
        "voice_note",
    }
    field_id = str(raw.get("id") or raw.get("field") or "").strip()
    _reject_unknown(raw, allowed, f"question `{field_id or '?'}`")
    revision = int(raw.get("revision") or parent_revision)
    input_type = _input_type(raw.get("input_type"), f"question `{field_id}`")
    options = list(_authored_options(raw.get("options"), f"question `{field_id}`"))
    option_groups = []
    for group_value in raw.get("groups") or ():
        group = _mapping(group_value, f"question `{field_id}` group")
        _reject_unknown(group, {"id", "label", "options"}, f"question `{field_id}` group")
        group_options = _authored_options(group.get("options"), f"question `{field_id}` group")
        options.extend(group_options)
        option_groups.append(
            OptionGroup(
                str(group.get("id") or ""),
                str(group.get("label") or ""),
                tuple(item.value for item in group_options),
            )
        )
    options = list(
        _authored_options(
            ({"value": item.value, "label": item.label} for item in options),
            f"question `{field_id}`",
        )
    )
    free_text = _authoring_subordinate(raw.get("free_text"), revision=revision, kind="free_text")
    companion = _authoring_subordinate(raw.get("companion"), revision=revision, kind="companion")
    other = OtherControl(
        enabled=free_text is not None,
        field_id=free_text.id if free_text else "",
        label=free_text.prompt if free_text else "",
        visible_if=free_text.visible_if if free_text else None,
    )
    item_fields = tuple(
        _authoring_field(
            _mapping(value, f"question `{field_id}` nested field"),
            nested=True,
            parent_revision=revision,
        )
        for value in raw.get("fields") or ()
    )
    shortcuts = tuple(
        SelectionShortcut(
            str(item.get("id") or ""),
            str(item.get("label") or ""),
            tuple(str(value) for value in item.get("select") or ()),
        )
        for item in (
            _mapping(value, f"question `{field_id}` shortcut")
            for value in raw.get("shortcuts") or ()
        )
    )
    capabilities = None
    if raw.get("capabilities") is not None:
        value = _mapping(raw.get("capabilities"), f"question `{field_id}` capabilities")
        _reject_unknown(
            value,
            {
                "manual_text", "geolocation_lookup",
                "geolocation_requires_user_action", "lookup_trigger",
                "lookup_behavior",
            },
            f"question `{field_id}` capabilities",
        )
        capabilities = LocationCapabilities(
            _bool(value.get("manual_text"), False),
            _bool(value.get("geolocation_lookup"), False),
            _bool(value.get("geolocation_requires_user_action"), True),
            str(value.get("lookup_trigger") or "explicit_action"),
            str(value.get("lookup_behavior") or "suggest_and_confirm_match"),
        )
    routes = []
    for action, route_value in _mapping(
        raw.get("routing") or {}, f"question `{field_id}` routing"
    ).items():
        route = _mapping(route_value, f"question `{field_id}` route")
        _reject_unknown(
            route, {"when", "toast", "scroll_to"},
            f"question `{field_id}` route"
        )
        routes.append(
            TerminalRoute(
                _authored_condition(route.get("when"), default_field=field_id),  # type: ignore[arg-type]
                "end" if str(action) == "end_session" else str(action),
                {
                    key: route[key]
                    for key in ("toast", "scroll_to")
                    if key in route
                },
            )
        )
    values = dict(
        id=field_id,
        revision=revision,
        prompt=str(raw.get("prompt") or "").strip(),
        context=str(raw.get("context") or "").strip(),
        input_type=input_type,
        required=_bool(raw.get("required"), False),
        options=tuple(options),
        taxonomy_id=str(raw.get("taxonomy") or ""),
        suggestions=_options(raw.get("suggestions")),
        other=other,
        min_select=int(raw["min_select"]) if raw.get("min_select") is not None else None,
        max_select=int(raw["max_select"]) if raw.get("max_select") is not None else None,
        min_items=int(raw["min_items"]) if raw.get("min_items") is not None else None,
        visible_if=_authored_condition(raw.get("show_if")),
        routes=tuple(routes),
        item_fields=item_fields,
        presentation={
            key: raw[key]
            for key in (
                "selection_feedback", "suggestion_label", "detail_prompt",
                "detail_placeholder", "voice_note"
            )
            if key in raw
        },
        independently_answerable=not nested,
        shortcuts=shortcuts,
        capabilities=capabilities,
        companions=(companion,) if companion else (),
        option_groups=tuple(option_groups),
        free_text_field=free_text,
    )
    if nested:
        return FieldDefinition(**values)
    return QuestionDefinition(
        **values,
        skippable=_bool(raw.get("allow_skip"), True),
        flaggable=True,
        metadata={
            "step_id": str(raw.get("step") or ""),
            "authored_field": str(raw.get("field") or field_id),
        },
    )


def _authoring_representation(raw_value: Any) -> RepresentationDefinition:
    item = _mapping(raw_value, "representation")
    _reject_unknown(
        item,
        {
            "id",
            "revision",
            "type",
            "scope",
            "title",
            "source",
            "sources",
            "projection",
            "components",
        },
        "representation",
    )
    sources_raw = item.get("sources")
    if sources_raw is None and item.get("source") is not None:
        sources_raw = [item.get("source")]
    sources = tuple(
        RepresentationSource(
            field_id=str(source.get("field") or ""),
            trajectory=str(source.get("trajectory") or ""),
            role=str(source.get("role") or ""),
            path=tuple(str(part) for part in source.get("path") or ()),
        )
        for source in (_mapping(value, "representation source") for value in sources_raw or ())
    )
    components: list[str | RepresentationComponent] = []
    for value in item.get("components") or ():
        if isinstance(value, str):
            components.append(value)
            continue
        component = _mapping(value, "representation component")
        if "representation" in component:
            _reject_unknown(component, {"representation"}, "representation component")
            components.append(str(component.get("representation") or ""))
            continue
        _reject_unknown(component, {"type", "source", "projection"}, "representation component")
        source = _mapping(component.get("source") or {}, "representation component source")
        components.append(
            RepresentationComponent(
                RepresentationType(str(component.get("type") or "")),
                RepresentationSource(
                    field_id=str(source.get("field") or ""),
                    trajectory=str(source.get("trajectory") or ""),
                ),
                dict(
                    _mapping(
                        component.get("projection") or {}, "representation component projection"
                    )
                ),
            )
        )
    return RepresentationDefinition(
        id=str(item.get("id") or ""),
        revision=int(item.get("revision") or 1),
        type=RepresentationType(str(item.get("type") or "")),
        scope=RepresentationScope(str(item.get("scope") or "")),
        sources=sources,
        projection=dict(_mapping(item.get("projection") or {}, "representation projection")),
        components=tuple(components),
        title=str(item.get("title") or ""),
    )


def _load_questionnaire_probe(payload: Mapping[str, Any]) -> ProbeDefinition:
    allowed = {
        "schema",
        "questionnaire",
        "step_order",
        "flow_modes",
        "sections",
        "step_copy",
        "taxonomies",
        "questions",
        "interaction",
        "profile_fields",
        "session_fields",
        "deferrable_fields",
        "fingerprint_axes",
        "representations",
        "editorial_review",
    }
    _reject_unknown(payload, allowed, "document")
    meta = _mapping(payload.get("questionnaire") or {}, "questionnaire")
    _reject_unknown(
        meta,
        {
            "id",
            "revision",
            "status",
            "language",
            "default_mode",
            "show_mode_selection",
            "show_welcome_step",
            "identity_position",
            "review",
        },
        "questionnaire",
    )
    questions = tuple(
        _authoring_field(_mapping(value, "question")) for value in payload.get("questions") or ()
    )
    by_step: dict[str, list[str]] = {}
    for question in questions:
        by_step.setdefault(str(question.metadata.get("step_id") or ""), []).append(question.id)
    step_copy = _mapping(payload.get("step_copy") or {}, "step_copy")
    step_order = tuple(str(value) for value in payload.get("step_order") or ())
    if set(step_copy) != set(step_order):
        raise DefinitionError("`step_copy` must define every and only `step_order` step.")
    built_steps = []
    for step_id in step_order:
        copy = _mapping(step_copy[step_id], f"step_copy.{step_id}")
        _reject_unknown(copy, {"title", "body", "cta"}, f"step_copy.{step_id}")
        built_steps.append(
            StepDefinition(
                step_id,
                str(copy.get("title") or ""),
                str(copy.get("body") or ""),
                str(copy.get("cta") or ""),
                tuple(by_step.get(step_id, ())),
            )
        )
    steps = tuple(built_steps)
    built_sections = []
    for item in (_mapping(value, "section") for value in payload.get("sections") or ()):
        _reject_unknown(item, {"id", "title", "steps", "process"}, "section")
        process = _mapping(item.get("process") or {}, "section process")
        _reject_unknown(process, {"checkpoint", "sync_point"}, "section process")
        built_sections.append(
            SectionDefinition(
                str(item.get("id") or ""),
                str(item.get("title") or ""),
                tuple(str(value) for value in item.get("steps") or ()),
                _bool(process.get("checkpoint"), False) or bool(process.get("sync_point")),
                str(process.get("sync_point") or ""),
            )
        )
    sections = tuple(built_sections)
    blocks = tuple(
        QuestionBlock(question_id)
        for step_id in step_order
        for question_id in by_step.get(step_id, ())
    )
    interaction = _mapping(payload.get("interaction") or {}, "interaction")
    _reject_unknown(
        interaction,
        {
            "nothing_substantively_mandatory",
            "question_resolution",
            "answer_before_meta_actions",
            "subordinate_fields_inherit_parent_resolution",
            "skip",
            "flag",
            "review_editable",
            "mobile",
            "validation",
            "submission_preview",
            "authentication",
        },
        "interaction",
    )
    skip = _mapping(interaction.get("skip") or {}, "interaction.skip")
    flag = _mapping(interaction.get("flag") or {}, "interaction.flag")
    _reject_unknown(
        skip, {"enabled", "reason_prompt", "reasons", "note_optional"}, "interaction.skip"
    )
    _reject_unknown(flag, {"enabled", "prompt", "options", "note_optional"}, "interaction.flag")
    resolution = ResolutionDefinition(
        skip_reasons=ReasonTaxonomy(
            "montreal_skip_reasons", 1, _authored_options(skip.get("reasons"), "skip reasons")
        ),
        flag_reasons=ReasonTaxonomy(
            "montreal_flag_reasons", 1, _authored_options(flag.get("options"), "flag reasons")
        ),
        actions=tuple(str(value) for value in interaction.get("question_resolution") or ()),
        nothing_substantively_mandatory=_bool(
            interaction.get("nothing_substantively_mandatory"), True
        ),
        answer_before_meta_actions=_bool(interaction.get("answer_before_meta_actions"), True),
        subordinate_fields_inherit_parent_resolution=_bool(
            interaction.get("subordinate_fields_inherit_parent_resolution"), True
        ),
        skip_enabled=_bool(skip.get("enabled"), True),
        skip_reason_prompt=str(skip.get("reason_prompt") or ""),
        skip_note_optional=_bool(skip.get("note_optional"), True),
        flag_enabled=_bool(flag.get("enabled"), True),
        flag_prompt=str(flag.get("prompt") or ""),
        flag_note_optional=_bool(flag.get("note_optional"), True),
        review_editable=_bool(interaction.get("review_editable"), True),
    )
    built_flow_modes = []
    for mode_id, value in _mapping(payload.get("flow_modes") or {}, "flow_modes").items():
        item = _mapping(value, f"flow mode `{mode_id}`")
        _reject_unknown(item, {"title", "detail", "steps"}, f"flow mode `{mode_id}`")
        built_flow_modes.append(
            FlowModeDefinition(
                str(mode_id),
                str(item.get("title") or ""),
                str(item.get("detail") or ""),
                tuple(str(value) for value in item.get("steps") or ()),
            )
        )
    flow_modes = tuple(built_flow_modes)
    fingerprint_axes = []
    for item in (
        _mapping(value, "fingerprint axis") for value in payload.get("fingerprint_axes") or ()
    ):
        _reject_unknown(item, {"id", "source", "taxonomy"}, "fingerprint axis")
        fingerprint_axes.append(
            FingerprintAxis(
                str(item.get("id") or ""),
                str(item.get("source") or ""),
                str(item.get("taxonomy") or ""),
            )
        )
    editorial_review = []
    for item in (
        _mapping(value, "editorial review") for value in payload.get("editorial_review") or ()
    ):
        _reject_unknown(item, {"id", "status", "note"}, "editorial review")
        editorial_review.append(
            EditorialReviewItem(
                str(item.get("id") or ""),
                str(item.get("status") or ""),
                str(item.get("note") or ""),
            )
        )
    authoring = AuthoringDefinition(
        language=str(meta.get("language") or ""),
        default_mode=str(meta.get("default_mode") or ""),
        show_mode_selection=_bool(meta.get("show_mode_selection"), False),
        show_welcome_step=_bool(meta.get("show_welcome_step"), False),
        identity_position=str(meta.get("identity_position") or ""),
        review=dict(_mapping(meta.get("review") or {}, "questionnaire.review")),
        step_order=step_order,
        flow_modes=flow_modes,
        profile_fields=tuple(str(value) for value in payload.get("profile_fields") or ()),
        session_fields=tuple(str(value) for value in payload.get("session_fields") or ()),
        deferrable_fields=tuple(str(value) for value in payload.get("deferrable_fields") or ()),
        fingerprint_axes=tuple(fingerprint_axes),
        editorial_review=tuple(editorial_review),
        presentation_hints={
            key: dict(_mapping(interaction.get(key) or {}, f"interaction.{key}"))
            for key in (
                "mobile", "validation", "submission_preview", "authentication"
            )
        },
    )
    title = str(
        _mapping(step_copy.get("welcome") or {}, "step_copy.welcome").get("title")
        or meta.get("id")
        or ""
    )
    return ProbeDefinition(
        id=str(meta.get("id") or ""),
        revision=int(meta.get("revision") or 1),
        title=title,
        status=str(meta.get("status") or "active"),
        blocks=blocks,
        questions=questions,
        sections=sections,
        steps=steps,
        taxonomies=_authoring_taxonomies(payload),
        representations=tuple(
            _authoring_representation(value) for value in payload.get("representations") or ()
        ),
        resolution=resolution,
        authoring=authoring,
    )


def load_yaml_probe(
    source: str | Path | Mapping[str, Any],
) -> ProbeDefinition:
    payload = _load_yaml(source)
    if payload.get("schema") != "probe-authoring/v1":
        raise DefinitionError(
            f"Unsupported authored Probe schema `{payload.get('schema')}`; "
            "expected `probe-authoring/v1`."
        )
    if "questionnaire" in payload:
        return _load_questionnaire_probe(payload)
    _reject_unknown(
        payload,
        {
            "schema",
            "probe",
            "taxonomies",
            "sections",
            "steps",
            "representations",
            "results",
            "resolution",
        },
        "document",
    )
    meta = _mapping(payload.get("probe") or {}, "probe")
    _reject_unknown(meta, {"id", "revision", "title", "status", "metadata"}, "probe")

    taxonomies = []
    for taxonomy_raw in payload.get("taxonomies") or ():
        item = _mapping(taxonomy_raw, "taxonomy")
        _reject_unknown(item, {"id", "revision", "options", "groups"}, "taxonomy")
        options = _options(item.get("options"))
        groups = tuple(
            OptionGroup(
                str(group.get("id") or ""),
                str(group.get("label") or ""),
                tuple(str(value) for value in group.get("option_values") or ()),
            )
            for group in (
                _mapping(value, f"taxonomy `{item.get('id')}` group")
                for value in item.get("groups") or ()
            )
        )
        taxonomies.append(
            Taxonomy(str(item.get("id") or ""), options, groups, int(item.get("revision") or 1))
        )

    sections = []
    for section_raw in payload.get("sections") or ():
        item = _mapping(section_raw, "section")
        _reject_unknown(item, {"id", "title", "steps", "process"}, "section")
        process = _mapping(item.get("process") or {}, f"section `{item.get('id')}` process")
        _reject_unknown(process, {"checkpoint", "sync_point"}, "section process")
        sync_point = str(process.get("sync_point") or "")
        sections.append(
            SectionDefinition(
                str(item.get("id") or ""),
                str(item.get("title") or ""),
                tuple(str(value) for value in item.get("steps") or ()),
                _bool(process.get("checkpoint"), False) or bool(sync_point),
                sync_point,
            )
        )

    questions: list[QuestionDefinition] = []
    steps = []
    for step_raw in payload.get("steps") or ():
        item = _mapping(step_raw, "step")
        _reject_unknown(item, {"id", "title", "body", "cta", "fields"}, "step")
        fields = tuple(
            _canonical_question(_mapping(value, f"step `{item.get('id')}` field"))
            for value in item.get("fields") or ()
        )
        questions.extend(fields)
        steps.append(
            StepDefinition(
                str(item.get("id") or ""),
                str(item.get("title") or ""),
                str(item.get("body") or ""),
                str(item.get("cta") or ""),
                tuple(field.id for field in fields),
            )
        )

    section_by_step = {step_id: section for section in sections for step_id in section.step_ids}
    blocks: list[SectionBlock | QuestionBlock] = []
    emitted_sections: set[str] = set()
    for step in steps:
        section = section_by_step.get(step.id)
        if section and section.id not in emitted_sections:
            blocks.append(
                SectionBlock(
                    section.id,
                    section.title,
                    section.step_ids,
                    {"checkpoint": section.checkpoint, "sync_point": section.sync_point},
                )
            )
            emitted_sections.add(section.id)
        blocks.extend(
            QuestionBlock(field.id)
            for field in questions
            if field.id in step.field_ids and field.status == "active"
        )
    representations = []
    for raw_value in payload.get("representations") or ():
        item = _mapping(raw_value, "representation")
        _reject_unknown(
            item,
            {"id", "revision", "type", "scope", "source", "sources", "projection", "components"},
            "representation",
        )
        raw_sources = item.get("sources")
        if raw_sources is None and item.get("source") is not None:
            raw_sources = [item.get("source")]
        sources = tuple(
            RepresentationSource(
                field_id=str(source.get("field") or ""),
                trajectory=str(source.get("trajectory") or ""),
                role=str(source.get("role") or ""),
                path=tuple(str(part) for part in source.get("path") or ()),
            )
            for source in (_mapping(value, "representation source") for value in raw_sources or ())
        )
        components = tuple(
            str(value.get("representation") if isinstance(value, Mapping) else value)
            for value in item.get("components") or ()
        )
        representations.append(
            RepresentationDefinition(
                id=str(item.get("id") or ""),
                revision=int(item.get("revision") or 1),
                type=RepresentationType(str(item.get("type") or "")),
                scope=RepresentationScope(str(item.get("scope") or "")),
                sources=sources,
                projection=dict(
                    _mapping(item.get("projection") or {}, "representation projection")
                ),
                components=components,
            )
        )
    results = None
    if payload.get("results") is not None:
        raw_results = _mapping(payload.get("results"), "results")
        _reject_unknown(raw_results, {"title", "intro", "blocks"}, "results")
        result_blocks = []
        for raw_value in raw_results.get("blocks") or ():
            item = _mapping(raw_value, "results block")
            kind = str(item.get("type") or "")
            if kind == "narrative":
                result_blocks.append(
                    ResultBlockDefinition(narrative=str(item.get("markdown") or ""))
                )
            elif kind == "representation":
                commentary = item.get("commentary")
                if isinstance(commentary, Mapping):
                    interpretation = Interpretation(
                        str(commentary.get("markdown") or ""),
                        str(commentary.get("kind") or "authored"),
                    )
                elif commentary:
                    interpretation = Interpretation(str(commentary))
                else:
                    interpretation = None
                result_blocks.append(
                    ResultBlockDefinition(
                        representation_id=str(item.get("representation") or ""),
                        commentary=interpretation,
                    )
                )
            else:
                raise DefinitionError(f"Unsupported results block type `{kind}`.")
        results = ResultsDefinition(
            str(raw_results.get("title") or ""),
            str(raw_results.get("intro") or ""),
            tuple(result_blocks),
        )
    resolution = ResolutionDefinition()
    if payload.get("resolution") is not None:
        raw_resolution = _mapping(payload.get("resolution"), "resolution")
        _reject_unknown(raw_resolution, {"skip_reasons", "flag_reasons"}, "resolution")

        def reasons(name: str, default: ReasonTaxonomy) -> ReasonTaxonomy:
            raw = raw_resolution.get(name)
            if raw is None:
                return default
            item = _mapping(raw, f"resolution.{name}")
            _reject_unknown(item, {"id", "revision", "options"}, f"resolution.{name}")
            return ReasonTaxonomy(
                str(item.get("id") or ""),
                int(item.get("revision") or 1),
                _options(item.get("options")),
            )

        resolution = ResolutionDefinition(
            reasons("skip_reasons", resolution.skip_reasons),
            reasons("flag_reasons", resolution.flag_reasons),
        )
    return ProbeDefinition(
        id=str(meta.get("id") or ""),
        revision=int(meta.get("revision") or 1),
        title=str(meta.get("title") or meta.get("id") or ""),
        status=str(meta.get("status") or "active"),
        blocks=tuple(blocks),
        questions=tuple(questions),
        sections=tuple(sections),
        steps=tuple(steps),
        taxonomies=tuple(taxonomies),
        representations=tuple(representations),
        results=results,
        resolution=resolution,
        metadata=dict(meta.get("metadata") or {}),
    )


def load_markdown_probe(
    source: str | Path,
    *,
    question_catalogue: Mapping[str, QuestionDefinition] | str | Path,
    parser: MarkdownParser | None = None,
) -> ProbeDefinition:
    path = Path(source)
    text = path.read_text(encoding="utf-8") if path.exists() else str(source)
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.DOTALL)
    if not match:
        raise DefinitionError("Markdown Probe must begin with YAML front matter.")
    meta = _mapping(yaml.load(match.group(1), Loader=_Yaml12SafeLoader) or {}, "front matter")
    catalogue = (
        dict(question_catalogue)
        if isinstance(question_catalogue, Mapping)
        else load_question_catalogue(question_catalogue)
    )
    blocks = (parser or DirectiveMarkdownParser()).parse(match.group(2))
    used = [block.question_id for block in blocks if isinstance(block, QuestionBlock)]
    questions = tuple(catalogue[question_id] for question_id in used if question_id in catalogue)
    missing = set(used) - set(catalogue)
    if missing:
        raise DefinitionError(f"Unresolved question references: {', '.join(sorted(missing))}.")
    unused = set(catalogue) - set(used)
    if unused:
        raise DefinitionError(f"Unused question definitions: {', '.join(sorted(unused))}.")
    return ProbeDefinition(
        id=str(meta.get("id") or ""),
        revision=int(meta.get("revision") or 1),
        title=str(meta.get("title") or meta.get("id") or ""),
        status=str(meta.get("status") or "active"),
        blocks=blocks,
        questions=questions,
        metadata={
            key: value
            for key, value in meta.items()
            if key not in {"id", "revision", "title", "status"}
        },
    )
