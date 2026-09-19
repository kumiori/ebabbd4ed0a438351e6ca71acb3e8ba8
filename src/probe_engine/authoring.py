"""YAML and augmented-Markdown front ends for canonical Probe definitions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import yaml

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

DIRECTIVE_PATTERN = re.compile(
    r"\{\{\s*question\s*:\s*(?P<id>[a-zA-Z0-9][a-zA-Z0-9_.-]*)\s*\}\}"
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


def _question(raw: Mapping[str, Any], *, fallback_id: str = "") -> QuestionDefinition:
    question_id = str(raw.get("id") or fallback_id).strip()
    revision = int(raw.get("revision") or 1)
    change = _mapping(raw.get("change") or raw.get("lineage") or {}, "change")
    raw_type = str(raw.get("input_type") or raw.get("mode") or "single")
    aliases = {"single_choice": "single", "multiple_choice": "multiple", "multi": "multiple"}
    try:
        input_type = InputType(aliases.get(raw_type, raw_type))
    except ValueError as exc:
        raise DefinitionError(f"Question `{question_id}` has unsupported input type `{raw_type}`.") from exc
    options: list[Option] = []
    for item in raw.get("options") or ():
        if isinstance(item, Mapping):
            options.append(Option(str(item.get("value") or ""), str(item.get("label") or "")))
        else:
            options.append(Option(str(item), str(item)))
    return QuestionDefinition(
        id=question_id,
        revision=revision,
        prompt=str(raw.get("prompt") or raw.get("title") or "").strip(),
        context=str(raw.get("context") or raw.get("subtitle") or "").strip(),
        input_type=input_type,
        options=tuple(options),
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
    payload = yaml.safe_load(text) or {}
    return dict(_mapping(payload, "document"))


def _resolve_shared(
    raw: Mapping[str, Any], shared: Mapping[str, QuestionDefinition]
) -> QuestionDefinition:
    reference = str(raw.get("use") or "")
    if not reference:
        return _question(raw)
    if reference not in shared:
        raise DefinitionError(f"Unknown shared question reference `{reference}`.")
    if set(raw) - {"use"}:
        raise DefinitionError(
            f"Shared question `{reference}` cannot be overridden in v0.1; version it instead."
        )
    return shared[reference]


def load_yaml_probe(
    source: str | Path | Mapping[str, Any],
    *,
    shared_catalogue: Mapping[str, QuestionDefinition] | None = None,
) -> ProbeDefinition:
    payload = _load_yaml(source)
    meta = _mapping(payload.get("probe") or payload.get("questionnaire") or {}, "probe")
    questions = tuple(
        _resolve_shared(_mapping(raw, "question"), shared_catalogue or {})
        for raw in payload.get("questions") or ()
    )
    blocks_raw = payload.get("blocks")
    if blocks_raw is None:
        blocks = tuple(QuestionBlock(question.id) for question in questions)
    else:
        built = []
        for raw in blocks_raw:
            item = _mapping(raw, "block")
            kind = str(item.get("kind") or "")
            if kind == "narrative":
                built.append(NarrativeBlock(str(item.get("markdown") or "")))
            elif kind == "question":
                built.append(QuestionBlock(str(item.get("question_id") or item.get("id") or "")))
            elif kind == "section":
                built.append(SectionBlock(str(item.get("id") or ""), str(item.get("title") or "")))
            else:
                raise DefinitionError(f"Unsupported block kind `{kind}`.")
        blocks = tuple(built)
    return ProbeDefinition(
        id=str(meta.get("id") or ""),
        revision=int(meta.get("revision") or 1),
        title=str(meta.get("title") or meta.get("id") or ""),
        status=str(meta.get("status") or "active"),
        blocks=blocks,
        questions=questions,
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
    meta = _mapping(yaml.safe_load(match.group(1)) or {}, "front matter")
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
