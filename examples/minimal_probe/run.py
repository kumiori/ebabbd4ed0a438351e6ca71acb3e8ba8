from __future__ import annotations

import json
from pathlib import Path

from probe_engine import (
    InMemoryTrajectoryStore,
    ProbeRuntime,
    distributions,
    load_markdown_probe,
    operational_summary,
    project_response_field,
)

ROOT = Path(__file__).parent
probe = load_markdown_probe(
    ROOT / "probe.md", question_catalogue=ROOT / "questions.yaml"
)
store = InMemoryTrajectoryStore()

ada = ProbeRuntime(probe, participant_id="ada", scope_id="example")
ada.answer("confidence", "high")
ada.flag("confidence", reason="positive: useful scale")
ada.skip("challenge", reason="not enough context")
ada.finalise(store, idempotency_key="ada-v1")
ada.finalise(store, idempotency_key="ada-v1")

lin = ProbeRuntime(probe, participant_id="lin", scope_id="example")
lin.answer("confidence", "medium")
lin.answer("challenge", ["data", "assumptions"])
lin.finalise(store, idempotency_key="lin-v1")

hydrated = ProbeRuntime.hydrate(
    probe,
    store.load(ada.trajectory.participation.id),
    participant_id="ada",
    scope_id="example",
)
trajectories = [hydrated.trajectory, lin.trajectory]
result = {
    "probe": probe.id,
    "reviews": [[item.__dict__ for item in runtime.review()] for runtime in (hydrated, lin)],
    "operational": operational_summary(probe, trajectories).__dict__,
    "distributions": distributions(probe, trajectories),
    "response_field": [row.__dict__ for row in project_response_field(probe, trajectories)],
    "integration_calls": store.integration_calls,
}
print(json.dumps(result, indent=2, sort_keys=True))
