from __future__ import annotations

from copy import deepcopy

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


def test_yaml_and_shared_questions_converge_on_canonical_model():
    shared = load_question_catalogue({"questions": {"shared.role": CATALOGUE["confidence"]}})
    value = load_yaml_probe(
        {
            "probe": {"id": "yaml-probe", "revision": 2, "title": "YAML Probe"},
            "questions": [{"use": "shared.role"}],
            "blocks": [
                {"kind": "section", "id": "s1", "title": "Start"},
                {"kind": "narrative", "markdown": "Read this."},
                {"kind": "question", "question_id": "shared.role"},
            ],
        },
        shared_catalogue=shared,
    )
    assert value.revision == 2
    assert value.question_order == ("shared.role",)
    assert value.question("shared.role").revision == 1


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
            "probe": {"id": "retirement", "revision": 2, "title": "Retirement"},
            "questions": [
                {**CATALOGUE["confidence"], "id": "confidence"},
                {**CATALOGUE["challenge"], "id": "challenge", "status": "retired"},
            ],
            "blocks": [{"kind": "question", "question_id": "confidence"}],
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
