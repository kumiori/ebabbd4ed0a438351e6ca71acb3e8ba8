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
    SINGLE_WITH_OTHER = "single_with_other"
    GROUPED_MULTIPLE = "grouped_multi"
    MULTIPLE_WITH_OTHER = "multi_with_other"
    TEXT = "text"
    TEXT_WITH_SUGGESTIONS = "text_with_suggestions"
    EMAIL = "email"
    URL = "url"
    LOCATION = "location"
    NUMBER = "number"
    BOOLEAN = "boolean"
    REPEATABLE = "repeatable"
    REPEATABLE_GROUP = "repeatable_group"


class RepresentationType(StrEnum):
    DISTRIBUTION = "distribution"
    GROUPED_DISTRIBUTION = "grouped_distribution"
    RESPONSES = "responses"
    RECORDS = "records"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    COMPOSITE = "composite"


class RepresentationScope(StrEnum):
    PARTICIPANT = "participant"
    COLLECTIVE = "collective"
    COHORT = "cohort"


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
    revision: int = 1
    presentation: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.options or self.revision < 1:
            raise DefinitionError("Taxonomies require a stable id and options.")
        values = [option.value for option in self.options]
        if len(values) != len(set(values)):
            raise DefinitionError(f"Taxonomy `{self.id}` has duplicate option values.")
        unknown = {value for group in self.groups for value in group.option_values} - set(values)
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
            "revision": self.revision,
            "presentation": dict(self.presentation),
        }


@dataclass(frozen=True)
class Condition:
    field_id: str = ""
    operator: str = "equals"
    value: Any = None
    clauses: tuple[Condition, ...] = ()

    def __post_init__(self) -> None:
        if self.operator == "any":
            if not self.clauses:
                raise DefinitionError("Any conditions require clauses.")
        elif not self.field_id or self.operator not in {"equals", "contains"}:
            raise DefinitionError("Conditions require a field id and supported operator.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "operator": self.operator,
            "value": self.value,
            "clauses": [clause.to_dict() for clause in self.clauses],
        }


@dataclass(frozen=True)
class TerminalRoute:
    when: Condition
    action: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action:
            raise DefinitionError("Terminal routes require an action.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when.to_dict(),
            "action": self.action,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class OtherControl:
    enabled: bool = False
    field_id: str = ""
    label: str = ""
    placeholder: str = ""
    required: bool = False
    visible_if: Condition | None = None

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
            "visible_if": self.visible_if.to_dict() if self.visible_if else None,
        }


@dataclass(frozen=True)
class SelectionShortcut:
    id: str
    label: str
    select: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.id or not self.label or not self.select:
            raise DefinitionError("Selection shortcuts require id, label, and selections.")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "select": list(self.select)}


@dataclass(frozen=True)
class LocationCapabilities:
    manual_text: bool = False
    geolocation_lookup: bool = False
    geolocation_requires_user_action: bool = True
    lookup_trigger: str = "explicit_action"
    lookup_behavior: str = "suggest_and_confirm_match"

    def to_dict(self) -> dict[str, bool]:
        return {
            "manual_text": self.manual_text,
            "geolocation_lookup": self.geolocation_lookup,
            "geolocation_requires_user_action": self.geolocation_requires_user_action,
            "lookup_trigger": self.lookup_trigger,
            "lookup_behavior": self.lookup_behavior,
        }


@dataclass(frozen=True)
class LocationValue:
    display_label: str
    locality: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""
    place_id: str = ""
    latitude: float | None = None
    longitude: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_label": self.display_label,
            "locality": self.locality,
            "region": self.region,
            "country": self.country,
            "country_code": self.country_code,
            "place_id": self.place_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass(frozen=True)
class ReasonTaxonomy:
    id: str
    revision: int
    options: tuple[Option, ...]

    def __post_init__(self) -> None:
        values = [option.value for option in self.options]
        if not self.id or self.revision < 1 or not values or len(values) != len(set(values)):
            raise DefinitionError("Reason taxonomies require stable identity and unique options.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "revision": self.revision,
            "options": [item.to_dict() for item in self.options],
        }


def _default_skip_reasons() -> ReasonTaxonomy:
    return ReasonTaxonomy(
        "prediction_skip_reasons",
        1,
        (
            Option("not_relevant", "Not relevant to me"),
            Option("dont_know", "I don't know"),
            Option("prefer_not_to_answer", "I prefer not to answer"),
            Option("dont_understand", "I don't understand the question"),
            Option("no_option_fits", "None of the options fit"),
            Option("too_difficult_briefly", "Too difficult to answer briefly"),
            Option("other", "Other"),
        ),
    )


def _default_flag_reasons() -> ReasonTaxonomy:
    return ReasonTaxonomy(
        "prediction_flag_reasons",
        1,
        (
            Option("interesting_question", "Interesting"),
            Option("useful_for_coordination", "Useful"),
            Option("thought_provoking", "Thought-provoking"),
            Option("well_framed", "Well framed"),
            Option("incomplete", "Incomplete"),
            Option("misleading", "Misleading"),
            Option("too_narrow", "Too narrow"),
            Option("unclear", "Unclear"),
            Option("missing_option", "Missing option"),
        ),
    )


@dataclass(frozen=True)
class ResolutionDefinition:
    skip_reasons: ReasonTaxonomy = field(default_factory=_default_skip_reasons)
    flag_reasons: ReasonTaxonomy = field(default_factory=_default_flag_reasons)
    actions: tuple[str, ...] = ("answer", "skip", "flag")
    nothing_substantively_mandatory: bool = True
    answer_before_meta_actions: bool = True
    subordinate_fields_inherit_parent_resolution: bool = True
    skip_enabled: bool = True
    skip_reason_prompt: str = ""
    skip_note_optional: bool = True
    flag_enabled: bool = True
    flag_prompt: str = ""
    flag_note_optional: bool = True
    review_editable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "skip_reasons": self.skip_reasons.to_dict(),
            "flag_reasons": self.flag_reasons.to_dict(),
            "actions": list(self.actions),
            "nothing_substantively_mandatory": self.nothing_substantively_mandatory,
            "answer_before_meta_actions": self.answer_before_meta_actions,
            "subordinate_fields_inherit_parent_resolution": self.subordinate_fields_inherit_parent_resolution,
            "skip_enabled": self.skip_enabled,
            "skip_reason_prompt": self.skip_reason_prompt,
            "skip_note_optional": self.skip_note_optional,
            "flag_enabled": self.flag_enabled,
            "flag_prompt": self.flag_prompt,
            "flag_note_optional": self.flag_note_optional,
            "review_editable": self.review_editable,
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
    independently_answerable: bool = False
    shortcuts: tuple[SelectionShortcut, ...] = ()
    capabilities: LocationCapabilities | None = None
    companions: tuple[FieldDefinition, ...] = ()
    option_groups: tuple[OptionGroup, ...] = ()
    free_text_field: FieldDefinition | None = None

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
        if self.input_type == InputType.REPEATABLE_GROUP and not self.item_fields:
            raise DefinitionError(f"Field `{self.id}` requires repeatable item fields.")
        if self.input_type == InputType.LOCATION and self.capabilities is None:
            raise DefinitionError(f"Location field `{self.id}` requires capabilities.")

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
            "independently_answerable": self.independently_answerable,
            "shortcuts": [item.to_dict() for item in self.shortcuts],
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
            "companions": [item.to_dict() for item in self.companions],
            "option_groups": [item.to_dict() for item in self.option_groups],
            "free_text_field": self.free_text_field.to_dict() if self.free_text_field else None,
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
    skip_action: str = "continue"
    flaggable: bool = True
    allow_comment: bool = False
    shared_dimension: str = ""
    status: str = "active"
    lineage: RevisionLineage = field(default_factory=RevisionLineage)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    independently_answerable: bool = True
    shortcuts: tuple[SelectionShortcut, ...] = ()
    capabilities: LocationCapabilities | None = None
    companions: tuple[FieldDefinition, ...] = ()
    option_groups: tuple[OptionGroup, ...] = ()
    free_text_field: FieldDefinition | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.prompt:
            raise DefinitionError("Questions require stable `id` and non-empty `prompt`.")
        if self.revision < 1:
            raise DefinitionError(f"Question `{self.id}` revision must be positive.")
        if self.status not in {"active", "retired"}:
            raise DefinitionError(f"Question `{self.id}` has unsupported status `{self.status}`.")
        if self.skip_action not in {"continue", "end"}:
            raise DefinitionError(f"Question `{self.id}` has unsupported skip action `{self.skip_action}`.")
        if self.input_type in {
            InputType.SINGLE,
            InputType.MULTIPLE,
            InputType.SINGLE_WITH_OTHER,
            InputType.GROUPED_MULTIPLE,
            InputType.MULTIPLE_WITH_OTHER,
        } and not (self.options or self.taxonomy_id):
            raise DefinitionError(f"Question `{self.id}` requires at least one option.")
        if (
            self.input_type in {InputType.REPEATABLE, InputType.REPEATABLE_GROUP}
            and not self.item_fields
        ):
            raise DefinitionError(f"Question `{self.id}` requires repeatable item fields.")
        if self.input_type == InputType.LOCATION and self.capabilities is None:
            raise DefinitionError(f"Location field `{self.id}` requires capabilities.")
        if (
            self.lineage.supersedes_revision is not None
            and self.lineage.supersedes_revision >= self.revision
        ):
            raise DefinitionError(f"Question `{self.id}` must supersede an earlier revision.")

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
            "skip_action": self.skip_action,
            "flaggable": self.flaggable,
            "allow_comment": self.allow_comment,
            "shared_dimension": self.shared_dimension,
            "status": self.status,
            "lineage": self.lineage.to_dict(),
            "metadata": dict(self.metadata),
            "independently_answerable": self.independently_answerable,
            "shortcuts": [item.to_dict() for item in self.shortcuts],
            "capabilities": self.capabilities.to_dict() if self.capabilities else None,
            "companions": [item.to_dict() for item in self.companions],
            "option_groups": [item.to_dict() for item in self.option_groups],
            "free_text_field": self.free_text_field.to_dict() if self.free_text_field else None,
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
class CheckpointDefinition:
    """UI-neutral capabilities authored for a private section checkpoint."""

    enabled: bool = False
    review: bool = False
    draft_save: bool = False
    export_yaml: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "review": self.review,
            "draft_save": self.draft_save,
            "export": {"yaml": self.export_yaml},
        }


@dataclass(frozen=True)
class SectionDefinition:
    id: str
    title: str
    step_ids: tuple[str, ...]
    checkpoint: bool = False
    sync_point: str = ""
    checkpoint_config: CheckpointDefinition = field(default_factory=CheckpointDefinition)

    def __post_init__(self) -> None:
        if not self.id or not self.title or not self.step_ids:
            raise DefinitionError("Sections require stable id, title, and steps.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "step_ids": list(self.step_ids),
            "process": {
                "checkpoint": self.checkpoint_config.to_dict()
                if self.checkpoint_config != CheckpointDefinition()
                else self.checkpoint,
                "sync_point": self.sync_point,
            },
        }


@dataclass(frozen=True)
class FlowModeDefinition:
    id: str
    title: str
    detail: str
    step_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "detail": self.detail,
            "step_ids": list(self.step_ids),
        }


@dataclass(frozen=True)
class FingerprintAxis:
    id: str
    source_field_id: str
    taxonomy_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "source_field_id": self.source_field_id,
            "taxonomy_id": self.taxonomy_id,
        }


@dataclass(frozen=True)
class EditorialReviewItem:
    id: str
    status: str
    note: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status, "note": self.note}


@dataclass(frozen=True)
class AuthoringDefinition:
    language: str = ""
    default_mode: str = ""
    show_mode_selection: bool = False
    show_welcome_step: bool = False
    identity_position: str = ""
    review: Mapping[str, Any] = field(default_factory=dict)
    step_order: tuple[str, ...] = ()
    flow_modes: tuple[FlowModeDefinition, ...] = ()
    profile_fields: tuple[str, ...] = ()
    session_fields: tuple[str, ...] = ()
    deferrable_fields: tuple[str, ...] = ()
    fingerprint_axes: tuple[FingerprintAxis, ...] = ()
    editorial_review: tuple[EditorialReviewItem, ...] = ()
    presentation_hints: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "default_mode": self.default_mode,
            "show_mode_selection": self.show_mode_selection,
            "show_welcome_step": self.show_welcome_step,
            "identity_position": self.identity_position,
            "review": dict(self.review),
            "step_order": list(self.step_order),
            "flow_modes": [item.to_dict() for item in self.flow_modes],
            "profile_fields": list(self.profile_fields),
            "session_fields": list(self.session_fields),
            "deferrable_fields": list(self.deferrable_fields),
            "fingerprint_axes": [item.to_dict() for item in self.fingerprint_axes],
            "editorial_review": [item.to_dict() for item in self.editorial_review],
            "presentation_hints": dict(self.presentation_hints),
        }


@dataclass(frozen=True)
class RepresentationSource:
    field_id: str = ""
    trajectory: str = ""
    role: str = ""
    path: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.field_id:
            result["field"] = self.field_id
        if self.trajectory:
            result["trajectory"] = self.trajectory
        if self.role:
            result["role"] = self.role
        if self.path:
            result["path"] = list(self.path)
        return result


@dataclass(frozen=True)
class RepresentationComponent:
    type: RepresentationType
    source: RepresentationSource
    projection: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "source": self.source.to_dict(),
            "projection": dict(self.projection),
        }


@dataclass(frozen=True)
class RepresentationDefinition:
    id: str
    revision: int
    type: RepresentationType
    scope: RepresentationScope
    sources: tuple[RepresentationSource, ...] = ()
    projection: Mapping[str, Any] = field(default_factory=dict)
    components: tuple[str | RepresentationComponent, ...] = ()
    title: str = ""

    def __post_init__(self) -> None:
        if not self.id or self.revision < 1:
            raise DefinitionError("Representations require stable id and positive revision.")
        if self.type == RepresentationType.COMPOSITE and not self.components:
            raise DefinitionError(f"Composite representation `{self.id}` requires components.")
        if self.type != RepresentationType.COMPOSITE and not self.sources:
            raise DefinitionError(f"Representation `{self.id}` requires a source.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "revision": self.revision,
            "type": self.type.value,
            "scope": self.scope.value,
            "sources": [source.to_dict() for source in self.sources],
            "projection": dict(self.projection),
            "components": [
                {"representation": item} if isinstance(item, str) else item.to_dict()
                for item in self.components
            ],
            "title": self.title,
        }


@dataclass(frozen=True)
class Interpretation:
    markdown: str
    kind: str = "authored"

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "markdown": self.markdown}


@dataclass(frozen=True)
class ResultBlockDefinition:
    representation_id: str = ""
    narrative: str = ""
    commentary: Interpretation | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.representation_id:
            return {
                "type": "representation",
                "representation": self.representation_id,
                "commentary": self.commentary.to_dict() if self.commentary else None,
            }
        return {"type": "narrative", "markdown": self.narrative}


@dataclass(frozen=True)
class ResultsDefinition:
    title: str
    intro: str = ""
    blocks: tuple[ResultBlockDefinition, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "intro": self.intro,
            "blocks": [b.to_dict() for b in self.blocks],
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
    representations: tuple[RepresentationDefinition, ...] = ()
    results: ResultsDefinition | None = None
    resolution: ResolutionDefinition = field(default_factory=ResolutionDefinition)
    authoring: AuthoringDefinition = field(default_factory=AuthoringDefinition)

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
            condition_fields = self._condition_fields(question.visible_if)
            if condition_fields - known:
                raise DefinitionError(
                    f"Field `{question.id}` condition references unknown field "
                    f"`{', '.join(sorted(condition_fields - known))}`."
                )
            for route in question.routes:
                route_fields = self._condition_fields(route.when)
                if route_fields - known:
                    raise DefinitionError(
                        f"Field `{question.id}` route references unknown field "
                        f"`{', '.join(sorted(route_fields - known))}`."
                    )
        nested_ids = [
            field.id for question in self.questions for field in self._nested_fields(question)
        ]
        if len(nested_ids) != len(set(nested_ids)) or set(nested_ids) & known:
            raise DefinitionError(
                "Nested field IDs must be globally unique and distinct from questions."
            )
        all_known = known | set(nested_ids)
        for question in self.questions:
            for nested_field in (question, *self._nested_fields(question)):
                condition_fields = self._condition_fields(nested_field.visible_if)
                if condition_fields - all_known:
                    raise DefinitionError(
                        f"Field `{nested_field.id}` condition references unknown fields: "
                        f"{', '.join(sorted(condition_fields - all_known))}."
                    )
                allowed_options = {option.value for option in nested_field.options}
                if nested_field.taxonomy_id:
                    allowed_options = {
                        option.value for option in self.taxonomy(nested_field.taxonomy_id).options
                    }
                for shortcut in nested_field.shortcuts:
                    unknown_selections = set(shortcut.select) - allowed_options
                    if unknown_selections:
                        raise DefinitionError(
                            f"Shortcut `{shortcut.id}` selects unknown values: "
                            f"{', '.join(sorted(unknown_selections))}."
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
        if self.authoring.step_order:
            if self.authoring.step_order != tuple(step.id for step in self.steps):
                raise DefinitionError("Authoring step order must match canonical steps exactly.")
            for mode in self.authoring.flow_modes:
                missing_mode_steps = set(mode.step_ids) - known_steps
                if missing_mode_steps:
                    raise DefinitionError(
                        f"Flow mode `{mode.id}` references unknown steps: "
                        f"{', '.join(sorted(missing_mode_steps))}."
                    )
            classified = set(self.authoring.profile_fields) | set(self.authoring.session_fields)
            if classified - known:
                raise DefinitionError(
                    f"Authoring field classifications reference unknown fields: "
                    f"{', '.join(sorted(classified - known))}."
                )
            overlap = set(self.authoring.profile_fields) & set(self.authoring.session_fields)
            if overlap:
                raise DefinitionError(
                    f"Fields cannot be both profile and session fields: {', '.join(sorted(overlap))}."
                )
            unknown_deferrable = set(self.authoring.deferrable_fields) - known
            if unknown_deferrable:
                raise DefinitionError(
                    f"Deferrable fields are unknown: {', '.join(sorted(unknown_deferrable))}."
                )
            for axis in self.authoring.fingerprint_axes:
                if axis.source_field_id not in known:
                    raise DefinitionError(f"Fingerprint axis `{axis.id}` references unknown field.")
                if axis.taxonomy_id and axis.taxonomy_id not in known_taxonomies:
                    raise DefinitionError(
                        f"Fingerprint axis `{axis.id}` references unknown taxonomy."
                    )
        allowed_actions = {"answer", "skip", "flag", "defer"}
        if not self.resolution.actions or set(self.resolution.actions) - allowed_actions:
            raise DefinitionError("Resolution actions contain unsupported semantics.")
        self._validate_representations()

    def _validate_representations(self) -> None:
        ids = [item.id for item in self.representations]
        if len(ids) != len(set(ids)):
            raise DefinitionError("A Probe cannot contain duplicate representation IDs.")
        known_fields = {question.id: question for question in self.questions}
        known_representations = set(ids)
        for representation in self.representations:
            component_sources = tuple(
                component.source
                for component in representation.components
                if isinstance(component, RepresentationComponent)
            )
            for source in (*representation.sources, *component_sources):
                if source.field_id and source.field_id not in known_fields:
                    raise DefinitionError(
                        f"Representation `{representation.id}` references unknown field `{source.field_id}`."
                    )
                if source.trajectory and source.trajectory != "events":
                    raise DefinitionError(f"Unsupported trajectory source `{source.trajectory}`.")
                if source.path and source.field_id:
                    current = known_fields[source.field_id].item_fields
                    for part in source.path:
                        match = next((field for field in current if field.id == part), None)
                        if match is None:
                            raise DefinitionError(
                                f"Representation `{representation.id}` has invalid nested path."
                            )
                        current = match.item_fields
            taxonomy_id = str(representation.projection.get("taxonomy") or "")
            if taxonomy_id and taxonomy_id not in {item.id for item in self.taxonomies}:
                raise DefinitionError(
                    f"Representation `{representation.id}` references unknown taxonomy `{taxonomy_id}`."
                )
            source_fields = [
                known_fields[source.field_id]
                for source in representation.sources
                if source.field_id
            ]
            if representation.type in {
                RepresentationType.DISTRIBUTION,
                RepresentationType.GROUPED_DISTRIBUTION,
            } and any(
                source.input_type
                not in {
                    InputType.SINGLE,
                    InputType.MULTIPLE,
                    InputType.SINGLE_WITH_OTHER,
                    InputType.GROUPED_MULTIPLE,
                    InputType.MULTIPLE_WITH_OTHER,
                }
                for source in source_fields
            ):
                raise DefinitionError(f"Distribution `{representation.id}` requires choice fields.")
            if representation.type == RepresentationType.RESPONSES and any(
                source.input_type != InputType.TEXT for source in source_fields
            ):
                raise DefinitionError(f"Responses `{representation.id}` requires text fields.")
            if representation.type == RepresentationType.RECORDS and any(
                source.input_type not in {InputType.REPEATABLE, InputType.REPEATABLE_GROUP}
                for source in source_fields
            ):
                raise DefinitionError(f"Records `{representation.id}` requires repeatable fields.")
            if representation.type == RepresentationType.COMPARISON:
                roles = [source.role for source in representation.sources]
                if (
                    len(roles) < 2
                    or any(not role for role in roles)
                    or len(roles) != len(set(roles))
                ):
                    raise DefinitionError(
                        f"Comparison `{representation.id}` requires distinct source roles."
                    )
                taxonomies = {source.taxonomy_id for source in source_fields}
                if len(taxonomies) != 1:
                    raise DefinitionError(
                        f"Comparison `{representation.id}` requires compatible sources."
                    )
            for component in representation.components:
                if isinstance(component, str) and component not in known_representations:
                    raise DefinitionError(
                        f"Representation `{representation.id}` references unknown representation `{component}`."
                    )
        graph = {
            item.id: tuple(component for component in item.components if isinstance(component, str))
            for item in self.representations
        }

        def visit(node: str, stack: set[str]) -> None:
            if node in stack:
                raise DefinitionError("Circular composite representation reference.")
            for child in graph.get(node, ()):
                visit(child, {*stack, node})

        for node in graph:
            visit(node, set())
        if self.results:
            for block in self.results.blocks:
                if block.representation_id and block.representation_id not in known_representations:
                    raise DefinitionError(
                        f"Results reference unknown representation `{block.representation_id}`."
                    )

    @staticmethod
    def _condition_fields(condition: Condition | None) -> set[str]:
        if condition is None:
            return set()
        if condition.operator == "any":
            return set().union(
                *(ProbeDefinition._condition_fields(item) for item in condition.clauses)
            )
        return {condition.field_id}

    @staticmethod
    def _validate_field_taxonomies(field: Any, known: set[str]) -> None:
        taxonomy_id = str(getattr(field, "taxonomy_id", "") or "")
        if taxonomy_id and taxonomy_id not in known:
            raise DefinitionError(
                f"Field `{field.id}` references unknown taxonomy `{taxonomy_id}`."
            )
        for nested in (
            *getattr(field, "item_fields", ()),
            *getattr(field, "companions", ()),
            *(
                (getattr(field, "free_text_field", None),)
                if getattr(field, "free_text_field", None)
                else ()
            ),
        ):
            ProbeDefinition._validate_field_taxonomies(nested, known)

    @staticmethod
    def _nested_fields(field: Any) -> tuple[FieldDefinition, ...]:
        return tuple(
            nested
            for child in (
                *getattr(field, "item_fields", ()),
                *getattr(field, "companions", ()),
                *(
                    (getattr(field, "free_text_field", None),)
                    if getattr(field, "free_text_field", None)
                    else ()
                ),
            )
            for nested in (child, *ProbeDefinition._nested_fields(child))
        )

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

    def field(self, field_id: str) -> QuestionDefinition | FieldDefinition:
        try:
            return self.question(field_id)
        except KeyError:
            for question in self.questions:
                for nested in self._nested_fields(question):
                    if nested.id == field_id:
                        return nested
        raise KeyError(field_id)

    def resolution_parent(self, field_id: str) -> str:
        for question in self.active_questions:
            if question.id == field_id:
                return field_id

            def walk(field: FieldDefinition, inherited: str) -> str | None:
                current = field.id if field.independently_answerable else inherited
                if field.id == field_id:
                    return current
                for child in (
                    *field.item_fields,
                    *field.companions,
                    *((field.free_text_field,) if field.free_text_field else ()),
                ):
                    found = walk(child, current)
                    if found:
                        return found
                return None

            for nested in (
                *question.item_fields,
                *question.companions,
                *((question.free_text_field,) if question.free_text_field else ()),
            ):
                found = walk(nested, question.id)
                if found:
                    return found
        raise KeyError(field_id)

    @property
    def answerable_order(self) -> tuple[str, ...]:
        ordered: list[str] = []

        def append_nested(field: FieldDefinition) -> None:
            if field.independently_answerable:
                ordered.append(field.id)
            for child in field.item_fields:
                append_nested(child)

        for question_id in self.question_order:
            question = self.question(question_id)
            ordered.append(question_id)
            for nested in question.item_fields:
                append_nested(nested)
        return tuple(ordered)

    def taxonomy(self, taxonomy_id: str) -> Taxonomy:
        for taxonomy in self.taxonomies:
            if taxonomy.id == taxonomy_id:
                return taxonomy
        raise KeyError(taxonomy_id)

    def representation(self, representation_id: str) -> RepresentationDefinition:
        for representation in self.representations:
            if representation.id == representation_id:
                return representation
        raise KeyError(representation_id)

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
            "representations": [item.to_dict() for item in self.representations],
            "results": self.results.to_dict() if self.results else None,
            "resolution": self.resolution.to_dict(),
            "authoring": self.authoring.to_dict(),
            "metadata": dict(self.metadata),
        }
