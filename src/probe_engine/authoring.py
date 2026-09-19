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

DIRECTIVE_PATTERN = re.compile(
    r"\{\{\s*question\s*:\s*(?P<id>[a-zA-Z0-9][a-zA-Z0-9_.-]*)\s*\}\}"
)


class _Yaml12SafeLoader(yaml.SafeLoader):
    """Safe loader that does not coerce identity tokens such as yes/no/on/off."""


for first, resolvers in tuple(_Yaml12SafeLoader.yaml_implicit_resolvers.items()):
    _Yaml12SafeLoader.yaml_implicit_resolvers[first] = [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag != "tag:yaml.org,2002:bool"
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
        raise DefinitionError(
            f"Unsupported semantics in {context}: {', '.join(sorted(unknown))}."
        )


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
    _reject_unknown(
        value, {"enabled", "field", "label", "placeholder", "required"}, context
    )
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
        "text_with_suggestions": "text",
        "repeatable_group": "repeatable",
    }
    token = str(raw_type or "single")
    if token in {"grouped_multi", "multi_with_other", "companion"}:
        raise DefinitionError(
            f"Unsupported widget-shaped type `{token}` in {context}; use composed field semantics."
        )
    try:
        return InputType(aliases.get(token, token))
    except ValueError as exc:
        raise DefinitionError(f"Unsupported input type `{token}` in {context}.") from exc


_FIELD_KEYS = {
    "id", "revision", "prompt", "context", "type", "required", "options", "taxonomy",
    "suggestions", "presentation", "other", "min_select", "max_select", "min_items",
    "visible_if", "routing", "item", "skippable", "flaggable", "allow_comment",
    "shared_dimension", "status", "lineage", "metadata",
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


def load_yaml_probe(
    source: str | Path | Mapping[str, Any],
) -> ProbeDefinition:
    payload = _load_yaml(source)
    if payload.get("schema") != "probe-authoring/v1":
        raise DefinitionError(
            f"Unsupported authored Probe schema `{payload.get('schema')}`; "
            "expected `probe-authoring/v1`."
        )
    _reject_unknown(payload, {"schema", "probe", "taxonomies", "sections", "steps"}, "document")
    meta = _mapping(payload.get("probe") or {}, "probe")
    _reject_unknown(meta, {"id", "revision", "title", "status", "metadata"}, "probe")

    taxonomies = []
    for taxonomy_raw in payload.get("taxonomies") or ():
        item = _mapping(taxonomy_raw, "taxonomy")
        _reject_unknown(item, {"id", "options", "groups"}, "taxonomy")
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
        taxonomies.append(Taxonomy(str(item.get("id") or ""), options, groups))

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

    section_by_step = {
        step_id: section for section in sections for step_id in section.step_ids
    }
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
        metadata={key: value for key, value in meta.items() if key not in {"id", "revision", "title", "status"}},
    )
