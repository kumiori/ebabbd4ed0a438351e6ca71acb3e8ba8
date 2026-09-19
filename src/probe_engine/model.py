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
        if self.input_type in {InputType.SINGLE, InputType.MULTIPLE} and not self.options:
            raise DefinitionError(f"Question `{self.id}` requires at least one option.")
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
    kind: str = field(default="section", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "title": self.title}


Block = NarrativeBlock | QuestionBlock | SectionBlock


@dataclass(frozen=True)
class ProbeDefinition:
    id: str
    revision: int
    title: str
    blocks: tuple[Block, ...]
    questions: tuple[QuestionDefinition, ...]
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "probe-definition/v1",
            "id": self.id,
            "revision": self.revision,
            "title": self.title,
            "status": self.status,
            "blocks": [block.to_dict() for block in self.blocks],
            "questions": [question.to_dict() for question in self.questions],
            "metadata": dict(self.metadata),
        }
