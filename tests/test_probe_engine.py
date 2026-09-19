from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

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
        load_markdown_probe(MARKDOWN, question_catalogue={**load_question_catalogue(CATALOGUE), "extra": next(iter(load_question_catalogue(CATALOGUE).values()))})


def test_montreal_fixture_is_lossless_canonical_probe():
    source = Path(__file__).parent / "fixtures" / "montreal.yaml"
    value = load_yaml_probe(source)

    assert value.id == "montreal_communs_data_ai_2026"
    assert value.revision == 1
    assert len(value.questions) == 26
    assert [section.id for section in value.sections] == [
        "participation", "portrait", "exchange", "future"
    ]
    assert [step.id for step in value.steps] == [
        "consent", "participation", "portrait", "project", "exchange_offer",
        "exchange_need", "friction", "inspiration", "future_outcome",
        "future_effects", "future_conditions", "future_contribution", "scenario_role",
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
        "governance", "access", "infrastructure", "collective_action"
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


def test_authored_yaml_requires_schema_and_rejects_widget_ontology():
    with pytest.raises(DefinitionError, match="probe-authoring/v1"):
        load_yaml_probe({"probe": {"id": "implicit"}})
    invalid = {
        "schema": "probe-authoring/v1",
        "probe": {"id": "invalid", "revision": 1, "title": "Invalid"},
        "steps": [{
            "id": "s", "title": "S", "body": "", "cta": "Next",
            "fields": [{
                "id": "q", "revision": 1, "prompt": "Q?", "type": "grouped_multi"
            }],
        }],
    }
    with pytest.raises(DefinitionError, match="composed field semantics"):
        load_yaml_probe(invalid)


def test_repeatable_answers_validate_recursively_and_keep_item_identity():
    value = load_yaml_probe(Path(__file__).parent / "fixtures" / "montreal.yaml")
    runtime = ProbeRuntime(value, participant_id="p1", scope_id="montreal")
    answer = [{
        "id": "condition-1",
        "action": "Former une coalition",
        "actors": ["cultural_institution", "commons_movement"],
    }]
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
        "checkpoint", "sync_point_reached"
    ]
    assert runtime.trajectory.events[-1].metadata["sync_point"] == "knowledge_exchange"
    assert store.checkpoint_calls == 1


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
        "answered", "flagged", "skipped"
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
    resumed = ProbeRuntime.hydrate(current, runtime.trajectory, participant_id="p1", scope_id="scope")
    assert resumed.reconciliation().questions[0].state == ReconciliationState.RESKIP_OR_ANSWER_REQUIRED


def test_new_question_and_current_order_drive_pending():
    old = probe()
    runtime = ProbeRuntime(old, participant_id="p1", scope_id="scope")
    runtime.answer("confidence", "high")
    runtime.skip("challenge")
    catalogue = deepcopy(CATALOGUE)
    catalogue["new"] = {"title": "New?", "revision": 1, "mode": "single_choice", "required": True, "options": ["yes", "no"]}
    markdown = MARKDOWN.replace("{{ question: confidence }}", "{{ question: new }}\n\n{{ question: confidence }}").replace("revision: 1", "revision: 2", 1)
    current = load_markdown_probe(markdown, question_catalogue=load_question_catalogue(catalogue))
    resumed = ProbeRuntime.hydrate(current, runtime.trajectory, participant_id="p1", scope_id="scope")
    assert resumed.pending() == ("new",)
    assert resumed.reconciliation().currently_complete is False


def test_retired_question_is_historical_but_not_pending():
    current = load_yaml_probe(
        {
            "schema": "probe-authoring/v1",
            "probe": {"id": "retirement", "revision": 2, "title": "Retirement"},
            "steps": [{
                "id": "questions", "title": "Questions", "body": "", "cta": "Next",
                "fields": [
                    {
                        "id": "confidence", "revision": 1, "prompt": "Confidence?",
                        "type": "single", "options": ["low", "high"],
                    },
                    {
                        "id": "challenge", "revision": 1, "prompt": "Challenge?",
                        "type": "multi", "options": ["data", "assumptions"],
                        "status": "retired",
                    },
                ],
            }],
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
        MARKDOWN.replace("revision: 1", "revision: 2", 1).replace("Readable prose", "Revised prose"),
        question_catalogue=load_question_catalogue(CATALOGUE),
    )
    resumed = ProbeRuntime.hydrate(current, runtime.trajectory, participant_id="p1", scope_id="scope")
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
