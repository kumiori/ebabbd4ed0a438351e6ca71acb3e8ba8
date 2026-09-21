from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from probe_engine import (
    DefinitionError,
    InMemoryTrajectoryStore,
    NarrativeBlock,
    ProbeRuntime,
    ReconciliationState,
    RuntimeError,
    SchemaError,
    distributions,
    load_markdown_probe,
    load_question_catalogue,
    load_yaml_probe,
    operational_summary,
    probe_from_dict,
    project_response_field,
    trajectory_from_dict,
    evaluate_representation,
    evaluate_results,
    representation_result_from_dict,
    ResolutionState,
)

CATALOGUE = {
    "confidence": {
        "title": "Confidence?",
        "revision": 1,
        "mode": "single_choice",
        "required": True,
        "options": ["low", "high"],
    },
    "challenge": {
        "title": "Challenge?",
        "revision": 1,
        "mode": "multiple_choice",
        "options": ["data", "assumptions"],
    },
}

MARKDOWN = """---
id: prediction
revision: 1
title: Prediction
---
# Predict

Readable prose before.

{{ question: confidence }}

Prose between questions.

{{ question: challenge }}

Prose after.
"""


def probe(revision: int = 1, confidence_revision: int = 1, reask: bool = False):
    catalogue = deepcopy(CATALOGUE)
    catalogue["confidence"]["revision"] = confidence_revision
    if confidence_revision > 1:
        catalogue["confidence"]["supersedes_revision"] = confidence_revision - 1
        catalogue["confidence"]["change"] = {
            "type": "semantic_change",
            "reason": "Scale changed.",
            "reask_if_answered": reask,
        }
    return load_markdown_probe(
        MARKDOWN.replace("revision: 1", f"revision: {revision}", 1),
        question_catalogue=load_question_catalogue(catalogue),
    )


def test_markdown_preserves_readable_chunks_and_source_order():
    value = probe()
    assert value.id == "prediction"
    assert value.question_order == ("confidence", "challenge")
    narratives = [block.markdown for block in value.blocks if isinstance(block, NarrativeBlock)]
    assert "Readable prose before" in narratives[0]
    assert "Prose between questions" in narratives[1]
    assert "Prose after" in narratives[2]


def test_markdown_requires_front_matter_and_complete_references():
    with pytest.raises(DefinitionError, match="front matter"):
        load_markdown_probe("hello", question_catalogue={})
    with pytest.raises(DefinitionError, match="Unresolved"):
        load_markdown_probe(MARKDOWN, question_catalogue={})
    with pytest.raises(DefinitionError, match="Unused"):
        load_markdown_probe(
            MARKDOWN,
            question_catalogue={
                **load_question_catalogue(CATALOGUE),
                "extra": next(iter(load_question_catalogue(CATALOGUE).values())),
            },
        )


def test_montreal_fixture_is_lossless_canonical_probe():
    source = Path(__file__).parent / "fixtures" / "montreal.yaml"
    value = load_yaml_probe(source)

    assert value.id == "montreal_communs_data_ai_2026"
    assert value.revision == 1
    assert len(value.questions) == 26
    assert [section.id for section in value.sections] == [
        "participation",
        "portrait",
        "exchange",
        "future",
    ]
    assert [step.id for step in value.steps] == [
        "consent",
        "participation",
        "portrait",
        "project",
        "exchange_offer",
        "exchange_need",
        "friction",
        "inspiration",
        "future_outcome",
        "future_effects",
        "future_conditions",
        "future_contribution",
        "scenario_role",
    ]
    participation = next(step for step in value.steps if step.id == "participation")
    assert value.step("participation") is participation
    assert participation.field_ids == ("availability", "dietary_preferences")
    assert participation.title == "Votre participation"
    assert participation.cta == "Continuer"

    offer = value.question("knowledge_offer")
    need = value.question("knowledge_need")
    assert offer.taxonomy_id == need.taxonomy_id == "commons_ai_topics"
    assert value.taxonomy(offer.taxonomy_id) is value.taxonomy(need.taxonomy_id)
    assert [group.id for group in value.taxonomy("commons_ai_topics").groups] == [
        "governance",
        "access",
        "infrastructure",
        "collective_action",
    ]
    assert offer.presentation == {"group_by": "taxonomy_group"}
    assert offer.other.field_id == "knowledge_offer_other"
    assert "knowledge_offer_example" in next(
        step.field_ids for step in value.steps if step.id == "exchange_offer"
    )

    organization_size = value.question("organization_size")
    assert organization_size.visible_if.field_id == "participation_capacity"
    assert organization_size.visible_if.value == "organization_representative"
    assert value.question("friction").max_select == 4
    assert value.question("consent").routes[0].action == "end"

    repeatable = value.question("future_conditions")
    assert repeatable.input_type.value == "repeatable"
    assert repeatable.min_items == 0
    assert [field.id for field in repeatable.item_fields] == ["action", "actors"]
    assert repeatable.item_fields[0].suggestions[0].value == "consultation"
    assert repeatable.item_fields[1].taxonomy_id == "actor_types"
    assert repeatable.item_fields[1].min_select == 1
    assert repeatable.item_fields[0].revision == 1

    assert value.sections[2].checkpoint is True
    assert value.sections[2].sync_point == "knowledge_exchange"
    assert value.sections[3].sync_point == "future_action"
    assert probe_from_dict(value.to_dict()) == value


def test_authored_yaml_requires_schema_and_valid_grouped_fields():
    with pytest.raises(DefinitionError, match="probe-authoring/v1"):
        load_yaml_probe({"probe": {"id": "implicit"}})
    invalid = {
        "schema": "probe-authoring/v1",
        "probe": {"id": "invalid", "revision": 1, "title": "Invalid"},
        "steps": [
            {
                "id": "s",
                "title": "S",
                "body": "",
                "cta": "Next",
                "fields": [{"id": "q", "revision": 1, "prompt": "Q?", "type": "grouped_multi"}],
            }
        ],
    }
    with pytest.raises(DefinitionError, match="requires at least one option"):
        load_yaml_probe(invalid)


def test_repeatable_answers_validate_recursively_and_keep_item_identity():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    answer = [
        {
            "id": "condition-1",
            "action": "Former une coalition",
            "actors": ["cultural_institution", "commons_movement"],
        }
    ]
    runtime.answer("future_conditions", answer)
    assert runtime.review()[value.question_order.index("future_conditions")].value == answer

    with pytest.raises(RuntimeError, match="unique stable id"):
        runtime.answer("future_conditions", [{"action": "Agir", "actors": ["government"]}])
    with pytest.raises(RuntimeError, match="lacks required fields: actors"):
        runtime.answer(
            "future_conditions",
            [{"id": "condition-2", "action": "Agir", "actors": []}],
        )


def test_section_boundary_records_checkpoint_and_named_sync_point_only():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    store = InMemoryTrajectoryStore()
    runtime.reach_section_boundary("exchange", store)
    assert [event.kind.value for event in runtime.trajectory.events] == [
        "checkpoint",
        "sync_point_reached",
    ]
    assert runtime.trajectory.events[-1].metadata["sync_point"] == "knowledge_exchange"
    assert store.checkpoint_calls == 1


def test_private_checkpoint_and_sync_arrival_are_separate_operations():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    store = InMemoryTrajectoryStore()

    runtime.reach_checkpoint("exchange", store)
    assert [event.kind.value for event in runtime.trajectory.events] == ["checkpoint"]

    runtime.reach_sync_point("exchange", store)
    assert [event.kind.value for event in runtime.trajectory.events] == [
        "checkpoint",
        "sync_point_reached",
    ]
    assert store.checkpoint_calls == 2


def test_prepared_checkpoint_is_exactly_the_draft_sent_to_storage():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    store = InMemoryTrajectoryStore()
    prepared = runtime.prepare_checkpoint("portrait")

    runtime.commit_checkpoint("portrait", store, prepared=prepared)

    assert runtime.trajectory == prepared
    assert store.load(prepared.participation.id) == prepared


def test_authored_skip_action_can_end_without_becoming_an_answer():
    payload = yaml.safe_load(
        (Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml").read_text()
    )
    consent = payload["questions"][0]
    consent["allow_skip"] = True
    consent["skip_action"] = "end"

    value = load_yaml_probe(payload)
    question = value.question(consent["id"])
    assert question.skippable is True
    assert question.skip_action == "end"
    assert probe_from_dict(value.to_dict()) == value

    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    runtime.skip(question.id, reason_codes=["prefer_not"])
    resolution = runtime.resolution(question.id)
    assert resolution.state == ResolutionState.SKIPPED
    assert resolution.event is not None
    assert resolution.event.value is None


def test_grouped_distribution_without_taxonomy_keeps_values_and_empty_groups():
    payload = yaml.safe_load(
        (Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml").read_text()
    )
    payload["representations"][0]["components"][1]["type"] = "grouped_distribution"
    value = load_yaml_probe(payload)
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    runtime.answer("availability", ["oct28_am_online"])

    result = evaluate_representation(
        value,
        value.representation("participation_overview"),
        [runtime.trajectory],
    )

    component = result.data["components"][1]
    assert component["data"]["values"]["oct28_am_online"]["count"] == 1
    assert component["data"]["groups"] == {}


def test_checkpoint_capabilities_round_trip_and_remain_distinct_from_sync():
    payload = yaml.safe_load(
        (Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml").read_text()
    )
    payload["sections"][0]["process"]["checkpoint"] = {
        "enabled": True,
        "review": True,
        "draft_save": True,
        "export": {"yaml": True},
    }

    value = load_yaml_probe(payload)
    section = value.sections[0]
    assert section.checkpoint is True
    assert section.sync_point == ""
    assert section.checkpoint_config.review is True
    assert section.checkpoint_config.draft_save is True
    assert section.checkpoint_config.export_yaml is True
    assert probe_from_dict(value.to_dict()) == value


def test_validation_errors_have_codes_and_other_skip_requires_detail():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")

    with pytest.raises(RuntimeError) as over_limit:
        runtime.answer("inspiration", ["tool", "group", "project", "community"])
    assert over_limit.value.code == "max_select"

    with pytest.raises(RuntimeError) as missing_detail:
        runtime.skip("dietary_preferences", reason_codes=["other"])
    assert missing_detail.value.code == "other_detail_required"

    runtime.skip("dietary_preferences", reason_codes=["other"], note="Mon motif")


def test_definition_and_trajectory_schema_round_trip_and_fail_closed():
    value = probe()
    assert probe_from_dict(value.to_dict()) == value
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    restored = trajectory_from_dict(runtime.trajectory.to_dict())
    assert restored == runtime.trajectory
    with pytest.raises(SchemaError):
        probe_from_dict({"schema": "probe-definition/v999"})


def test_answer_skip_flag_and_review_are_distinct_and_append_only():
    runtime = ProbeRuntime(probe(), participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    runtime.flag("confidence", reason="positive")
    runtime.skip("challenge", reason="not applicable")
    assert [event.kind.value for event in runtime.trajectory.events] == [
        "answered",
        "flagged",
        "skipped",
    ]
    review = runtime.review()
    assert review[0].value == "high" and review[0].flags == ("positive",)
    assert review[1].state == "skipped_current" and review[1].value is None


def test_answer_validation_and_skip_capability_fail_explicitly():
    runtime = ProbeRuntime(probe(), participant_id="p1", scope_id="scope")
    with pytest.raises(RuntimeError, match="Invalid option"):
        runtime.answer("confidence", "unknown")
    required = deepcopy(CATALOGUE)
    required["confidence"]["skippable"] = False
    value = load_markdown_probe(MARKDOWN, question_catalogue=load_question_catalogue(required))
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="scope")
    with pytest.raises(RuntimeError, match="cannot be skipped"):
        runtime.skip("confidence")


@pytest.mark.parametrize(
    ("reask", "expected"),
    [
        (False, ReconciliationState.ANSWERED_PREVIOUS_VALID),
        (True, ReconciliationState.REANSWER_REQUIRED),
    ],
)
def test_revision_reconciliation_retains_old_provenance(reask, expected):
    old = probe()
    runtime = ProbeRuntime(old, participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    old_event = runtime.trajectory.events[0]
    current = probe(revision=2, confidence_revision=2, reask=reask)
    resumed = ProbeRuntime.hydrate(
        current, runtime.trajectory, participant_id="p1", scope_id="scope"
    )
    assert resumed.reconciliation().questions[0].state == expected
    assert resumed.trajectory.events[0] == old_event
    if reask:
        assert resumed.pending()[0] == "confidence"
        resumed.answer("confidence", "low")
        assert [event.question_revision for event in resumed.trajectory.events] == [1, 2]


def test_previous_skip_is_revision_aware():
    runtime = ProbeRuntime(probe(), participant_id="p1", scope_id="scope")
    runtime.skip("confidence")
    current = probe(revision=2, confidence_revision=2, reask=True)
    resumed = ProbeRuntime.hydrate(
        current, runtime.trajectory, participant_id="p1", scope_id="scope"
    )
    assert (
        resumed.reconciliation().questions[0].state == ReconciliationState.RESKIP_OR_ANSWER_REQUIRED
    )


def test_new_question_and_current_order_drive_pending():
    old = probe()
    runtime = ProbeRuntime(old, participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    runtime.skip("challenge")
    catalogue = deepcopy(CATALOGUE)
    catalogue["new"] = {
        "title": "New?",
        "revision": 1,
        "mode": "single_choice",
        "required": True,
        "options": ["yes", "no"],
    }
    markdown = MARKDOWN.replace(
        "{{ question: confidence }}", "{{ question: new }}\n\n{{ question: confidence }}"
    ).replace("revision: 1", "revision: 2", 1)
    current = load_markdown_probe(markdown, question_catalogue=load_question_catalogue(catalogue))
    resumed = ProbeRuntime.hydrate(
        current, runtime.trajectory, participant_id="p1", scope_id="scope"
    )
    assert resumed.pending() == ("new",)
    assert resumed.reconciliation().currently_complete is False


def test_retired_question_is_historical_but_not_pending():
    current = load_yaml_probe(
        {
            "schema": "probe-authoring/v1",
            "probe": {"id": "retirement", "revision": 2, "title": "Retirement"},
            "steps": [
                {
                    "id": "questions",
                    "title": "Questions",
                    "body": "",
                    "cta": "Next",
                    "fields": [
                        {
                            "id": "confidence",
                            "revision": 1,
                            "prompt": "Confidence?",
                            "type": "single",
                            "options": ["low", "high"],
                        },
                        {
                            "id": "challenge",
                            "revision": 1,
                            "prompt": "Challenge?",
                            "type": "multi",
                            "options": ["data", "assumptions"],
                            "status": "retired",
                        },
                    ],
                }
            ],
        }
    )
    runtime = ProbeRuntime(current, participant_id="p1", scope_id="scope")
    assert current.question("challenge").status == "retired"
    assert runtime.pending() == ("confidence",)


def test_narrative_only_revision_creates_no_pending_work():
    runtime = ProbeRuntime(probe(), participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    runtime.skip("challenge")
    current = load_markdown_probe(
        MARKDOWN.replace("revision: 1", "revision: 2", 1).replace(
            "Readable prose", "Revised prose"
        ),
        question_catalogue=load_question_catalogue(CATALOGUE),
    )
    resumed = ProbeRuntime.hydrate(
        current, runtime.trajectory, participant_id="p1", scope_id="scope"
    )
    assert resumed.pending() == ()


def test_hydration_rejects_participant_probe_and_scope_mismatch():
    value = probe()
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="production")
    with pytest.raises(RuntimeError, match="Participant"):
        ProbeRuntime.hydrate(value, runtime.trajectory, participant_id="p2", scope_id="production")
    with pytest.raises(RuntimeError, match="Scope"):
        ProbeRuntime.hydrate(value, runtime.trajectory, participant_id="p1", scope_id="test")


def test_interactions_review_and_reconciliation_make_zero_store_calls():
    store = InMemoryTrajectoryStore()
    runtime = ProbeRuntime(probe(), participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    runtime.flag("confidence", reason="critical")
    runtime.skip("challenge")
    runtime.review()
    runtime.reconciliation()
    assert (store.load_calls, store.checkpoint_calls, store.integration_calls) == (0, 0, 0)


def test_checkpoint_is_explicit_and_finalisation_is_retryable_and_idempotent():
    store = InMemoryTrajectoryStore()
    runtime = ProbeRuntime(probe(), participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    runtime.checkpoint(store)
    runtime.finalise(store, idempotency_key="p1-v1")
    runtime.finalise(store, idempotency_key="p1-v1")
    assert store.checkpoint_calls == 1
    assert store.integration_calls == 2
    assert sum(event.kind.value == "integrated" for event in runtime.trajectory.events) == 1
    stored = store.load(runtime.trajectory.participation.id)
    assert stored is not None
    assert stored.events[-1].kind.value == "integrated"
    assert runtime.reconciliation().previously_completed is True


def test_projections_are_deterministic_and_do_not_mutate_trajectories():
    value = probe()
    first = ProbeRuntime(value, participant_id="p1", scope_id="scope")
    first.answer("confidence", "high")
    first.skip("challenge")
    second = ProbeRuntime(value, participant_id="p2", scope_id="scope")
    second.answer("confidence", "low")
    second.answer("challenge", ["data"])
    trajectories = [first.trajectory, second.trajectory]
    before = deepcopy(trajectories)
    assert operational_summary(value, trajectories).answered == 3
    assert distributions(value, trajectories) == {
        "confidence": {"high": 1, "low": 1},
        "challenge": {"data": 1, "skipped": 1},
    }
    assert len(project_response_field(value, trajectories)) == 4
    assert trajectories == before


def test_composed_other_answer_survives_trajectory_round_trip():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    answer = {"selected": ["other"], "other": {"value": "Sans gluten"}}
    runtime.answer("dietary_preferences", answer)
    restored = trajectory_from_dict(runtime.trajectory.to_dict())
    assert restored.events[-1].value == answer
    runtime.answer("dietary_preferences", {"selected": ["other"]})


def test_representation_definitions_and_results_round_trip():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    assert [item.id for item in value.representations] == [
        "exchange_landscape",
        "friction_landscape",
        "future_action_map",
        "participant_portrait",
    ]
    assert probe_from_dict(value.to_dict()) == value
    first = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    first.answer("knowledge_offer", ["data_governance_models"])
    first.answer("knowledge_need", ["ai_dataset_structuring"])
    first.answer("friction", ["funding"])
    first.answer("future_conditions", [{"id": "a1", "action": "Convene", "actors": ["government"]}])
    first.flag("friction", reason="important")
    second = ProbeRuntime(value, participant_id="p2", scope_id="montreal")
    second.skip("friction")
    third = ProbeRuntime(value, participant_id="p3", scope_id="montreal")
    third.defer("friction", reason="answer later")

    distribution = evaluate_representation(
        value, "friction_landscape", [first.trajectory, second.trajectory, third.trajectory]
    )
    assert distribution.denominator.to_dict() == {
        "cohort": 3,
        "eligible": 3,
        "resolved": 3,
        "answered": 1,
        "selected": 1,
        "skipped": 1,
        "flagged": 1,
        "deferred": 1,
        "unanswered": 0,
    }
    assert distribution.data["values"] == {"funding": {"count": 1, "proportion": 1.0}}
    assert representation_result_from_dict(distribution.to_dict()) == distribution

    comparison = evaluate_representation(value, "exchange_landscape", [first.trajectory])
    assert comparison.data["roles"]["offer"]["data_governance_models"] == 1
    assert comparison.data["roles"]["need"]["ai_dataset_structuring"] == 1
    records = evaluate_representation(value, "future_action_map", [first.trajectory])
    assert records.data["records"][0]["value"][0]["actors"] == ["government"]


def test_results_composition_keeps_authored_commentary_distinct():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    runtime.answer("friction", ["funding"])
    projection = evaluate_results(value, [runtime.trajectory])
    assert projection.title == "Ce que nous voyons"
    block = next(
        item for item in projection.blocks if item.representation_id == "friction_landscape"
    )
    assert block.commentary.kind == "authored"
    assert "frictions" in block.commentary.markdown.lower()
    assert block.result.representation_id == "friction_landscape"


def test_representation_validation_fails_closed():
    source = Path(__file__).parent / "fixtures" / "montreal.yaml"
    payload = __import__("yaml").safe_load(source.read_text())
    payload["representations"][0]["sources"][0]["field"] = "missing"
    with pytest.raises(DefinitionError, match="unknown field"):
        load_yaml_probe(payload)


def test_continue_validates_resolution_not_a_mandatory_answer():
    value = probe()
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="scope")
    with pytest.raises(RuntimeError, match="unresolved"):
        runtime.validate_resolution("confidence")

    runtime.skip(
        "confidence",
        reason_codes=["dont_know"],
        note="Not enough evidence yet.",
    )
    assert runtime.validate_resolution("confidence").state == ResolutionState.SKIPPED
    runtime.flag(
        "challenge",
        reason_codes=["interesting_question", "missing_option"],
        note="Worth revisiting.",
    )
    with pytest.raises(RuntimeError, match="unresolved"):
        runtime.validate_resolution("challenge")
    runtime.answer("challenge", ["data"])
    assert runtime.validate_resolution("challenge").flagged is True
    assert runtime.pending() == ()
    assert runtime.reconciliation().currently_complete is True

    restored = trajectory_from_dict(runtime.trajectory.to_dict())
    assert restored.events[0].reason_codes == ("dont_know",)
    assert restored.events[0].reason_note == "Not enough evidence yet."
    assert restored.events[1].reason_codes == ("interesting_question", "missing_option")


def test_resolution_reason_taxonomies_preserve_prediction_vocabulary():
    value = probe()
    assert [item.value for item in value.resolution.skip_reasons.options] == [
        "not_relevant",
        "dont_know",
        "prefer_not_to_answer",
        "dont_understand",
        "no_option_fits",
        "too_difficult_briefly",
        "other",
    ]
    assert [item.value for item in value.resolution.flag_reasons.options] == [
        "interesting_question",
        "useful_for_coordination",
        "thought_provoking",
        "well_framed",
        "incomplete",
        "misleading",
        "too_narrow",
        "unclear",
        "missing_option",
    ]
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="scope")
    with pytest.raises(RuntimeError, match="Unknown skip reason"):
        runtime.skip("confidence", reason_codes=["interesting_question"])


def test_nested_fields_inherit_parent_resolution_unless_independent():
    payload = __import__("yaml").safe_load(
        (Path(__file__).parent / "fixtures" / "montreal.yaml").read_text()
    )
    actors = payload["steps"][10]["fields"][0]["item"]["fields"][1]
    actors["independently_answerable"] = True
    value = load_yaml_probe(payload)
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    runtime.skip("future_conditions", reason_codes=["prefer_not_to_answer"])
    assert runtime.resolution("action").inherited_from == "future_conditions"
    assert runtime.resolution("actors").state == ResolutionState.UNRESOLVED
    runtime.flag("actors", reason_codes=["unclear"])
    with pytest.raises(RuntimeError, match="unresolved"):
        runtime.validate_resolution("actors")
    runtime.skip("actors", reason_codes=["prefer_not_to_answer"])
    assert runtime.validate_resolution("actors").state == ResolutionState.SKIPPED


def test_flag_only_state_remains_unanswered_and_orthogonal():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    runtime.flag("friction", reason_codes=["interesting_question"])
    result = evaluate_representation(value, "friction_landscape", [runtime.trajectory])
    assert result.denominator.resolved == 0
    assert result.denominator.answered == 0
    assert result.denominator.flagged == 1
    assert result.denominator.unanswered == 1
    row = next(
        item
        for item in project_response_field(value, [runtime.trajectory])
        if item.question_id == "friction"
    )
    assert row.state == "flagged" and row.value is None


def test_conditional_fields_are_not_resolution_obligations_or_denominator_eligible():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    runtime.answer("participation_capacity", "individual")
    assert runtime.resolution("organization_size").state == ResolutionState.INELIGIBLE
    assert "organization_size" not in runtime.pending()


def test_montreal_v2_authored_contract_compiles_and_round_trips():
    source = Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml"
    authored = __import__("yaml").safe_load(source.read_text())
    value = load_yaml_probe(source)

    assert value.id == "montreal_communs_data_ai_short_2026"
    assert value.revision == 2
    assert value.authoring.step_order == (
        "welcome",
        "participation_information",
        "participation",
        "portrait",
        "organisation",
        "project",
        "exchange_offer",
        "exchange_need",
        "friction",
        "inspiration",
        "future_intro",
        "future_outcome",
        "future_effects",
        "future_conditions",
        "future_contribution",
        "scenario_position",
        "review",
        "done",
    )
    assert len(value.steps) == 18
    assert {
        step.id: {"title": step.title, "body": step.body, "cta": step.cta} for step in value.steps
    } == authored["step_copy"]
    assert len(value.questions) == 24
    assert [question.id for question in value.questions] == [
        question["field"] for question in authored["questions"]
    ]
    assert [taxonomy.id for taxonomy in value.taxonomies] == list(authored["taxonomies"])
    assert [(section.id, section.step_ids) for section in value.sections] == [
        (section["id"], tuple(section["steps"])) for section in authored["sections"]
    ]
    assert value.sections[2].sync_point == "knowledge_exchange"
    assert value.sections[3].sync_point == "future_action"
    assert value.authoring.profile_fields == (
        "name",
        "participation_position",
        "base_location",
        "sectors",
        "functions",
        "organisation_name",
        "organisation_size",
        "organisation_territory",
    )
    assert len(value.authoring.editorial_review) == 2
    assert probe_from_dict(value.to_dict()) == value


def test_montreal_v2_nested_authoring_grammar_rejects_unknown_semantics():
    source = Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml"
    payload = __import__("yaml").safe_load(source.read_text())
    payload["step_copy"]["welcome"]["renderer_magic"] = True
    with pytest.raises(DefinitionError, match="Unsupported semantics in step_copy.welcome"):
        load_yaml_probe(payload)


def test_montreal_v2_field_and_interaction_grammar_is_explicit():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml")

    assert {question.input_type.value for question in value.questions} == {
        "text",
        "url",
        "location",
        "single",
        "single_with_other",
        "grouped_multi",
        "multi_with_other",
        "repeatable_group",
    }
    availability = value.question("availability")
    assert [group.id for group in availability.option_groups] == ["oct28", "oct29"]
    assert availability.shortcuts[0].id == "both_full_days"
    assert availability.shortcuts[0].select == (
        "oct28_am_online",
        "oct28_pm_inrs",
        "oct29_am_inrs",
        "oct29_pm_inrs",
    )
    dietary = value.question("dietary_preferences")
    assert dietary.free_text_field.id == "dietary_preferences_detail"
    assert dietary.free_text_field.visible_if.operator == "any"
    assert dietary.other.field_id == "dietary_preferences_detail"
    offer = value.question("knowledge_offer")
    assert offer.taxonomy_id == "commons_ai_topics"
    assert offer.companions[0].id == "knowledge_offer_example"
    assert offer.companions[0].independently_answerable is False
    repeatable = value.question("future_conditions")
    assert repeatable.input_type.value == "repeatable_group"
    assert [field.id for field in repeatable.item_fields] == ["action", "actors"]
    assert repeatable.item_fields[0].input_type.value == "text_with_suggestions"
    assert repeatable.item_fields[1].free_text_field.id == "actors_other"
    location = value.question("base_location")
    assert location.capabilities.to_dict() == {
        "manual_text": True,
        "geolocation_lookup": True,
        "geolocation_requires_user_action": True,
        "lookup_trigger": "explicit_action",
        "lookup_behavior": "suggest_and_confirm_match",
    }
    organisation = value.question("organisation_name")
    assert organisation.visible_if.operator == "any"
    assert {clause.value for clause in organisation.visible_if.clauses} == {"organisation", "both"}
    assert value.question("participation_acknowledgement").routes[0].action == "end"

    assert value.resolution.actions == ("answer", "skip", "flag")
    assert [item.value for item in value.resolution.skip_reasons.options] == [
        "not_applicable",
        "dont_know",
        "prefer_not",
        "cannot_answer",
        "other",
    ]
    assert [item.value for item in value.resolution.flag_reasons.options][:4] == [
        "interesting",
        "useful",
        "thought_provoking",
        "well_framed",
    ]
    assert value.authoring.deferrable_fields[-1] == "scenario_position"
    assert [axis.id for axis in value.authoring.fingerprint_axes] == [
        "sectors",
        "functions",
        "offers",
        "needs",
        "frictions",
    ]
    assert [item.id for item in value.representations] == [
        "participation_overview",
        "participant_portrait",
        "knowledge_exchange",
        "future_landscape",
    ]
    assert value.representations[0].title == "Notre participation"


def test_montreal_v3_presentation_and_resolution_contract_is_canonical():
    source = Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml"
    payload = __import__("yaml").safe_load(source.read_text())
    payload["taxonomies"]["functions"]["presentation"] = {
        "groups": "expanders",
        "default_state": "collapsed",
        "show_selected_count": True,
    }
    consent = next(item for item in payload["questions"] if item["id"] == "participation_acknowledgement")
    consent["allow_skip"] = False
    consent["routing"]["show_contact"] = {
        "when": {"equals": "read_understood"},
        "toast": "Contact us",
    }
    location = next(item for item in payload["questions"] if item["id"] == "base_location")
    location["capabilities"].update({
        "geolocation_requires_user_action": False,
        "lookup_trigger": "after_text_input",
        "lookup_behavior": "suggest_and_confirm_match",
    })
    offer = next(item for item in payload["questions"] if item["id"] == "knowledge_offer")
    offer["companion"]["required"] = False
    inspiration = next(item for item in payload["questions"] if item["id"] == "inspiration")
    inspiration["selection_feedback"] = {
        "at_limit": "3 selected",
        "over_limit": "spectacular_soft_block",
        "message": "Choose at most three",
    }
    repeatable = next(item for item in payload["questions"] if item["id"] == "future_conditions")
    repeatable["fields"][0].update({
        "suggestion_label": "Start from a suggestion",
        "detail_prompt": "Add details",
        "detail_placeholder": "Who? What?",
        "voice_note": {"enabled": False, "disabled_note": "Soon"},
    })
    payload["interaction"].update({
        "validation": {"optional_companions_do_not_block": True},
        "submission_preview": {"enabled": True, "show_exact_payload": True},
        "authentication": {"required_for_production_write": True},
    })

    value = load_yaml_probe(payload)

    assert value.question("participation_acknowledgement").skippable is False
    assert value.taxonomy("functions").presentation["groups"] == "expanders"
    assert value.question("base_location").capabilities.lookup_trigger == "after_text_input"
    assert value.question("knowledge_offer").companions[0].required is False
    assert value.question("dietary_preferences").other.required is True
    action = value.question("future_conditions").item_fields[0]
    assert action.presentation["detail_prompt"] == "Add details"
    assert value.authoring.presentation_hints["submission_preview"]["enabled"] is True
    assert probe_from_dict(value.to_dict()) == value


def test_prepared_finalisation_is_the_exact_trajectory_sent_to_storage():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    prepared = runtime.prepare_finalisation(idempotency_key="commit-1")

    class CaptureStore:
        received = None

        def integrate(self, trajectory, *, idempotency_key):
            self.received = trajectory
            return trajectory

    store = CaptureStore()
    runtime.finalise(store, idempotency_key="commit-1", prepared=prepared)

    assert store.received == prepared
    assert runtime.trajectory == prepared


def test_montreal_v2_representative_answers_and_recursive_resolution():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal-2026")

    runtime.answer("availability", ["oct28_am_online", "oct29_am_inrs"])
    runtime.answer(
        "dietary_preferences",
        {"selected": ["vegetarian", "other"], "other": {"value": "Sans noix"}},
    )
    runtime.answer(
        "knowledge_offer",
        {
            "selected": ["commons_principles"],
            "companions": {"knowledge_offer_example": {"value": "Un registre partagé"}},
        },
    )
    runtime.answer(
        "base_location",
        {
            "display_label": "Montréal, Québec, Canada",
            "locality": "Montréal",
            "region": "Québec",
            "country": "Canada",
            "country_code": "CA",
            "place_id": "opencage:montreal-qc-ca",
            "latitude": 45.5019,
            "longitude": -73.5674,
        },
    )
    runtime.skip("frictions", reason_codes=["not_applicable"], note="Pas dans ce contexte")
    runtime.answer("future_outcome", ["shared_resource"])
    runtime.flag("future_outcome", reason_codes=["interesting", "well_framed"])
    runtime.answer(
        "future_conditions",
        [
            {
                "id": "action-1",
                "action": "Former une coalition",
                "actors": {
                    "selected": ["government", "other"],
                    "other": {"value": "Bibliothèque municipale"},
                },
            }
        ],
    )
    runtime.answer("participation_position", "organisation")
    runtime.answer("organisation_name", "Communs Montréal")

    assert runtime.resolution("knowledge_offer_example").inherited_from == "knowledge_offer"
    assert runtime.resolution("actors_other").inherited_from == "future_conditions"
    assert runtime.resolution("future_outcome").state == ResolutionState.ANSWERED
    assert runtime.resolution("future_outcome").flagged is True
    assert runtime.resolution("organisation_name").state == ResolutionState.ANSWERED
    future = evaluate_representation(value, "future_landscape", [runtime.trajectory])
    assert len(future.data["components"]) == 5
    outcome = future.data["components"][0]
    assert outcome["denominator"]["answered"] == 1
    assert outcome["denominator"]["flagged"] == 1
    restored = trajectory_from_dict(runtime.trajectory.to_dict())
    assert restored == runtime.trajectory


def test_montreal_v2_review_edit_hydrate_modify_and_persist():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal_communs_2.yaml")
    store = InMemoryTrajectoryStore()
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal-2026")
    runtime.answer("name", "Ada")
    runtime.checkpoint(store)

    resumed = ProbeRuntime.hydrate(
        value,
        trajectory_from_dict(runtime.trajectory.to_dict()),
        participant_id="p1",
        scope_id="montreal-2026",
    )
    resumed.answer("name", "Ada Lovelace")
    resumed.finalise(store, idempotency_key="montreal-p1-r2")
    saved = store.load(resumed.trajectory.participation.id)

    assert [event.value for event in saved.events if event.question_id == "name"] == [
        "Ada",
        "Ada Lovelace",
    ]
    assert resumed.review()[value.answerable_order.index("name")].value == "Ada Lovelace"
