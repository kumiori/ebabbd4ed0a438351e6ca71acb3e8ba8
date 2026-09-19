"""Canonical, UI-neutral Probe instrument model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DefinitionError(ValueError):
    """A Probe definition violates a semantic invariant."""


class InputType(StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    REPEATABLE = "repeatable"


@dataclass(frozen=True)
class Option:
    value: str
    label: str

    def __post_init__(self) -> None:
        if not self.value or not self.label:
            raise DefinitionError("Question options require non-empty value and label.")

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True)
class OptionGroup:
    """A labelled subset of a taxonomy, expressed by stable option values."""

    id: str
    label: str
    option_values: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.label or not self.option_values:
            raise DefinitionError("Option groups require id, label, and option values.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "option_values": list(self.option_values),
        }


@dataclass(frozen=True)
class Taxonomy:
    id: str
    options: tuple[Option, ...]
    groups: tuple[OptionGroup, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.options:
            raise DefinitionError("Taxonomies require a stable id and options.")
        values = [option.value for option in self.options]
        if len(values) != len(set(values)):
            raise DefinitionError(f"Taxonomy `{self.id}` has duplicate option values.")
        unknown = {
            value for group in self.groups for value in group.option_values
        } - set(values)
        if unknown:
            raise DefinitionError(
                f"Taxonomy `{self.id}` groups reference unknown values: "
                f"{', '.join(sorted(unknown))}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "options": [option.to_dict() for option in self.options],
            "groups": [group.to_dict() for group in self.groups],
        }


@dataclass(frozen=True)
class Condition:
    field_id: str
    operator: str
    value: Any

    def __post_init__(self) -> None:
        if not self.field_id or self.operator not in {"equals"}:
            raise DefinitionError("Conditions require a field id and supported operator.")

    def to_dict(self) -> dict[str, Any]:
        return {"field_id": self.field_id, "operator": self.operator, "value": self.value}


@dataclass(frozen=True)
class TerminalRoute:
    when: Condition
    action: str

    def __post_init__(self) -> None:
        if self.action != "end":
            raise DefinitionError(f"Unsupported route action `{self.action}`.")

    def to_dict(self) -> dict[str, Any]:
        return {"when": self.when.to_dict(), "action": self.action}


@dataclass(frozen=True)
class OtherControl:
    enabled: bool = False
    field_id: str = ""
    label: str = ""
    placeholder: str = ""
    required: bool = False

    def __post_init__(self) -> None:
        if self.enabled and not self.field_id:
            raise DefinitionError("Enabled other controls require a stable field id.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "field_id": self.field_id,
            "label": self.label,
            "placeholder": self.placeholder,
            "required": self.required,
        }


@dataclass(frozen=True)
class FieldDefinition:
    """One renderer-neutral answer field, recursively composable for repeatables."""

    id: str
    revision: int
    prompt: str
    input_type: InputType
    context: str = ""
    required: bool = False
    options: tuple[Option, ...] = ()
    taxonomy_id: str = ""
    suggestions: tuple[Option, ...] = ()
    presentation: Mapping[str, Any] = field(default_factory=dict)
    other: OtherControl = field(default_factory=OtherControl)
    min_select: int | None = None
    max_select: int | None = None
    min_items: int | None = None
    visible_if: Condition | None = None
    routes: tuple[TerminalRoute, ...] = ()
    item_fields: tuple[FieldDefinition, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.prompt or self.revision < 1:
            raise DefinitionError("Fields require stable id, prompt, and positive revision.")
        if self.min_select is not None and self.min_select < 0:
            raise DefinitionError(f"Field `{self.id}` min_select cannot be negative.")
        if self.max_select is not None and self.max_select < 1:
            raise DefinitionError(f"Field `{self.id}` max_select must be positive.")
        if None not in {self.min_select, self.max_select} and self.min_select > self.max_select:
            raise DefinitionError(f"Field `{self.id}` min_select exceeds max_select.")
        if self.min_items is not None and self.min_items < 0:
            raise DefinitionError(f"Field `{self.id}` min_items cannot be negative.")
        if self.input_type == InputType.REPEATABLE and not self.item_fields:
            raise DefinitionError(f"Field `{self.id}` requires repeatable item fields.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "revision": self.revision,
            "prompt": self.prompt,
            "context": self.context,
            "input_type": self.input_type.value,
            "required": self.required,
            "options": [option.to_dict() for option in self.options],
            "taxonomy_id": self.taxonomy_id,
            "suggestions": [option.to_dict() for option in self.suggestions],
            "presentation": dict(self.presentation),
            "other": self.other.to_dict(),
            "min_select": self.min_select,
            "max_select": self.max_select,
            "min_items": self.min_items,
            "visible_if": self.visible_if.to_dict() if self.visible_if else None,
            "routes": [route.to_dict() for route in self.routes],
            "item_fields": [item.to_dict() for item in self.item_fields],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RevisionLineage:
    supersedes_revision: int | None = None
    change_type: str = "initial"
    reason: str = ""
    reask_if_answered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "supersedes_revision": self.supersedes_revision,
            "change_type": self.change_type,
            "reason": self.reason,
            "reask_if_answered": self.reask_if_answered,
        }


@dataclass(frozen=True)
class QuestionDefinition:
    id: str
    revision: int
    prompt: str
    input_type: InputType = InputType.SINGLE
    context: str = ""
    options: tuple[Option, ...] = ()
    taxonomy_id: str = ""
    suggestions: tuple[Option, ...] = ()
    presentation: Mapping[str, Any] = field(default_factory=dict)
    other: OtherControl = field(default_factory=OtherControl)
    min_select: int | None = None
    max_select: int | None = None
    min_items: int | None = None
    visible_if: Condition | None = None
    routes: tuple[TerminalRoute, ...] = ()
    item_fields: tuple[FieldDefinition, ...] = ()
    required: bool = False
    skippable: bool = True
    flaggable: bool = True
    allow_comment: bool = False
    shared_dimension: str = ""
    status: str = "active"
    lineage: RevisionLineage = field(default_factory=RevisionLineage)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.prompt:
            raise DefinitionError("Questions require stable `id` and non-empty `prompt`.")
        if self.revision < 1:
            raise DefinitionError(f"Question `{self.id}` revision must be positive.")
        if self.status not in {"active", "retired"}:
            raise DefinitionError(f"Question `{self.id}` has unsupported status `{self.status}`.")
        if self.input_type in {InputType.SINGLE, InputType.MULTIPLE} and not (
            self.options or self.taxonomy_id
        ):
            raise DefinitionError(f"Question `{self.id}` requires at least one option.")
        if self.input_type == InputType.REPEATABLE and not self.item_fields:
            raise DefinitionError(f"Question `{self.id}` requires repeatable item fields.")
        if (
            self.lineage.supersedes_revision is not None
            and self.lineage.supersedes_revision >= self.revision
        ):
            raise DefinitionError(
                f"Question `{self.id}` must supersede an earlier revision."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "revision": self.revision,
            "prompt": self.prompt,
            "context": self.context,
            "input_type": self.input_type.value,
            "options": [option.to_dict() for option in self.options],
            "taxonomy_id": self.taxonomy_id,
            "suggestions": [option.to_dict() for option in self.suggestions],
            "presentation": dict(self.presentation),
            "other": self.other.to_dict(),
            "min_select": self.min_select,
            "max_select": self.max_select,
            "min_items": self.min_items,
            "visible_if": self.visible_if.to_dict() if self.visible_if else None,
            "routes": [route.to_dict() for route in self.routes],
            "item_fields": [item.to_dict() for item in self.item_fields],
            "required": self.required,
            "skippable": self.skippable,
            "flaggable": self.flaggable,
            "allow_comment": self.allow_comment,
            "shared_dimension": self.shared_dimension,
            "status": self.status,
            "lineage": self.lineage.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NarrativeBlock:
    markdown: str
    kind: str = field(default="narrative", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "markdown": self.markdown}


@dataclass(frozen=True)
class QuestionBlock:
    question_id: str
    kind: str = field(default="question", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "question_id": self.question_id}


@dataclass(frozen=True)
class SectionBlock:
    id: str
    title: str
    steps: tuple[str, ...] = ()
    process: Mapping[str, Any] = field(default_factory=dict)
    kind: str = field(default="section", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "steps": list(self.steps),
            "process": dict(self.process),
        }


@dataclass(frozen=True)
class StepDefinition:
    id: str
    title: str
    body: str
    cta: str
    field_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.title:
            raise DefinitionError("Steps require stable id and title.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "cta": self.cta,
            "field_ids": list(self.field_ids),
        }


@dataclass(frozen=True)
class SectionDefinition:
    id: str
    title: str
    step_ids: tuple[str, ...]
    checkpoint: bool = False
    sync_point: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.step_ids:
            raise DefinitionError("Sections require stable id, title, and steps.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "step_ids": list(self.step_ids),
            "process": {"checkpoint": self.checkpoint, "sync_point": self.sync_point},
        }


Block = NarrativeBlock | QuestionBlock | SectionBlock


@dataclass(frozen=True)
class ProbeDefinition:
    id: str
    revision: int
    title: str
    blocks: tuple[Block, ...]
    questions: tuple[QuestionDefinition, ...]
    sections: tuple[SectionDefinition, ...] = ()
    steps: tuple[StepDefinition, ...] = ()
    taxonomies: tuple[Taxonomy, ...] = ()
    status: str = "active"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.title or self.revision < 1:
            raise DefinitionError("Probes require stable id, title, and positive revision.")
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise DefinitionError("A Probe cannot contain duplicate active question IDs.")
        known = set(ids)
        active = {question.id for question in self.questions if question.status == "active"}
        referenced = [
            block.question_id for block in self.blocks if isinstance(block, QuestionBlock)
        ]
        missing = set(referenced) - known
        retired_references = set(referenced) - active
        unused = active - set(referenced)
        if missing:
            raise DefinitionError(f"Unresolved question references: {', '.join(sorted(missing))}.")
        if retired_references:
            raise DefinitionError(
                f"Retired questions cannot be active blocks: {', '.join(sorted(retired_references))}."
            )
        if unused:
            raise DefinitionError(f"Unused question definitions: {', '.join(sorted(unused))}.")
        taxonomy_ids = [taxonomy.id for taxonomy in self.taxonomies]
        if len(taxonomy_ids) != len(set(taxonomy_ids)):
            raise DefinitionError("A Probe cannot contain duplicate taxonomy IDs.")
        known_taxonomies = set(taxonomy_ids)
        for question in self.questions:
            self._validate_field_taxonomies(question, known_taxonomies)
            if question.visible_if and question.visible_if.field_id not in known:
                raise DefinitionError(
                    f"Field `{question.id}` condition references unknown field "
                    f"`{question.visible_if.field_id}`."
                )
            for route in question.routes:
                if route.when.field_id not in known:
                    raise DefinitionError(
                        f"Field `{question.id}` route references unknown field "
                        f"`{route.when.field_id}`."
                    )
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise DefinitionError("A Probe cannot contain duplicate step IDs.")
        for step in self.steps:
            missing_fields = set(step.field_ids) - known
            if missing_fields:
                raise DefinitionError(
                    f"Step `{step.id}` references unknown fields: {', '.join(sorted(missing_fields))}."
                )
        known_steps = set(step_ids)
        for section in self.sections:
            missing_steps = set(section.step_ids) - known_steps
            if missing_steps:
                raise DefinitionError(
                    f"Section `{section.id}` references unknown steps: {', '.join(sorted(missing_steps))}."
                )

    @staticmethod
    def _validate_field_taxonomies(field: Any, known: set[str]) -> None:
        taxonomy_id = str(getattr(field, "taxonomy_id", "") or "")
        if taxonomy_id and taxonomy_id not in known:
            raise DefinitionError(
                f"Field `{field.id}` references unknown taxonomy `{taxonomy_id}`."
            )
        for nested in getattr(field, "item_fields", ()):
            ProbeDefinition._validate_field_taxonomies(nested, known)

    @property
    def active_questions(self) -> tuple[QuestionDefinition, ...]:
        return tuple(question for question in self.questions if question.status == "active")

    @property
    def question_order(self) -> tuple[str, ...]:
        active = {question.id for question in self.active_questions}
        return tuple(
            block.question_id
            for block in self.blocks
            if isinstance(block, QuestionBlock) and block.question_id in active
        )

    def question(self, question_id: str) -> QuestionDefinition:
        for question in self.questions:
            if question.id == question_id:
                return question
        raise KeyError(question_id)

    def taxonomy(self, taxonomy_id: str) -> Taxonomy:
        for taxonomy in self.taxonomies:
            if taxonomy.id == taxonomy_id:
                return taxonomy
        raise KeyError(taxonomy_id)

    def section(self, section_id: str) -> SectionDefinition:
        for section in self.sections:
            if section.id == section_id:
                return section
        raise KeyError(section_id)

    def step(self, step_id: str) -> StepDefinition:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "probe-definition/v1",
            "id": self.id,
            "revision": self.revision,
            "title": self.title,
            "status": self.status,
            "blocks": [block.to_dict() for block in self.blocks],
            "questions": [question.to_dict() for question in self.questions],
            "sections": [section.to_dict() for section in self.sections],
            "steps": [step.to_dict() for step in self.steps],
            "taxonomies": [taxonomy.to_dict() for taxonomy in self.taxonomies],
            "metadata": dict(self.metadata),
        }
