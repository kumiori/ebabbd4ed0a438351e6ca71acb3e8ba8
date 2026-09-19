# Probe Engine

Probe Engine is a UI-independent engine for authored, versioned sensing
instruments that combine narrative and structured elicitation, preserve
participant response trajectories, and expose neutral projections for
collective sensing.

It has no dependency on Streamlit, Notion, IceIceBaby, Protocol Hack,
`protocol-lab`, or `trajectory-engine`.

## Install

```bash
python -m pip install \
  "probe-engine @ git+https://github.com/kumiori/ebabbd4ed0a438351e6ca71acb3e8ba8.git@v0.1.0"
```

For local development:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## A tiny YAML Probe

YAML questionnaires and authored documents converge on the same ordered
`ProbeDefinition` model:

```python
from probe_engine import ProbeRuntime, load_yaml_probe

probe = load_yaml_probe({
    "probe": {"id": "prediction", "revision": 1, "title": "Prediction"},
    "questions": [{
        "id": "confidence",
        "revision": 1,
        "prompt": "How confident are you?",
        "input_type": "single",
        "required": True,
        "options": ["low", "high"],
    }],
    "blocks": [
        {"kind": "narrative", "markdown": "Models meet observations."},
        {"kind": "question", "question_id": "confidence"},
    ],
})

runtime = ProbeRuntime(probe, participant_id="participant-1", scope_id="workshop-1")
runtime.answer("confidence", "high")
print(runtime.review())
```

The canonical classes can also be constructed directly for a Python-first Probe.

## Augmented Markdown

Authored prose remains readable. Directives carry stable question identity;
wording and configuration remain in an external catalogue:

```python
from probe_engine import load_markdown_probe, load_question_catalogue

document = """---
id: prediction-notes
revision: 1
title: Prediction notes
---
Models are calibrated against observations.

{{ question: confidence }}
"""

catalogue = load_question_catalogue({
    "confidence": {
        "revision": 1,
        "title": "How confident are you?",
        "mode": "single_choice",
        "options": ["low", "high"],
    }
})
probe = load_markdown_probe(document, question_catalogue=catalogue)
```

The v0.1 syntax is `{{ question: stable_id }}`. Its parser is replaceable and
does not contain rendering logic.

## Revision reconciliation

Reconciliation compares an existing trajectory with current question
revisions. It never rewrites the old response:

```python
from probe_engine import ProbeRuntime, load_yaml_probe

rev1 = load_yaml_probe({
    "probe": {"id": "prediction", "revision": 1, "title": "Prediction"},
    "questions": [{
        "id": "confidence", "revision": 1, "prompt": "Confidence?",
        "input_type": "single", "required": True, "options": ["low", "high"],
    }],
})
first_visit = ProbeRuntime(rev1, participant_id="p1", scope_id="course-1")
first_visit.answer("confidence", "high")

rev2 = load_yaml_probe({
    "probe": {"id": "prediction", "revision": 2, "title": "Prediction"},
    "questions": [{
        "id": "confidence", "revision": 2, "supersedes_revision": 1,
        "prompt": "Confidence after discussion?", "input_type": "single",
        "required": True, "options": ["low", "high"],
        "change": {
            "type": "semantic_change",
            "reason": "The question now follows discussion.",
            "reask_if_answered": True,
        },
    }],
})
returning = ProbeRuntime.hydrate(
    rev2, first_visit.trajectory, participant_id="p1", scope_id="course-1"
)

assert returning.pending() == ("confidence",)
assert returning.reconciliation().first_pending_question == "confidence"
```

After the participant answers revision 2, both revision-1 and revision-2
events remain in the trajectory.

## Interaction is local; persistence is coarse-grained

`answer()`, `skip()`, `flag()`, `review()`, and `reconciliation()` perform no
persistence calls. Storage happens only at explicit boundaries:

```python
from probe_engine import InMemoryTrajectoryStore

runtime.flag("confidence", reason="positive: useful distinction")
store = InMemoryTrajectoryStore()
runtime.checkpoint(store)
runtime.finalise(store, idempotency_key="submission-p1-v1")
```

Finalisation is explicit, retryable, and idempotent at the store boundary.
Adapters can implement `TrajectoryStore` for a database, filesystem, or remote
service without changing Probe semantics.

## Schemas and projections

Probe Engine serialises `probe-definition/v1` and `probe-trajectory/v1` and
fails explicitly on unknown schemas. Neutral projections include completion,
operational counts, response fields, distributions, and timeline-ready events.
Applications provide visualisation and interpretation.

See [docs/SCHEMAS.md](docs/SCHEMAS.md) and run:

```bash
python examples/minimal_probe/run.py
```

## Origins

Probe Engine emerged from two experimental lineages:

- IceIceBaby contributed versioned-question, response-trajectory, Flag/Skip,
  review/resume, scope, and coarse-persistence semantics proven during Udine.
- Protocol Hack's Markdown Aperture experiment at commit `6f09cb5` contributed
  readable Markdown, stable references, and document/question composition.

Neither source application is a package dependency. See
[docs/PROBE_EXTRACTION_MAP.md](docs/PROBE_EXTRACTION_MAP.md).
