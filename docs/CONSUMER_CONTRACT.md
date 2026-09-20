# Probe Engine consumer contract

Protocol Hack and other applications should import only names exported from
`probe_engine`. Parser helpers and model implementation modules are private.

## Load and inspect

```python
from probe_engine import load_yaml_probe

probe = load_yaml_probe("probe.yaml")

for section in probe.sections:
    for step_id in section.step_ids:
        step = probe.step(step_id)
        fields = tuple(probe.question(field_id) for field_id in step.field_ids)
```

Authored YAML must declare `schema: probe-authoring/v1`. Loading fails on
unknown authored schemas, unsupported semantics, unresolved references, or
invalid definitions.

Fields retain authored order within each Step. Sections and Steps retain their
authored order in `probe.sections` and `probe.steps`.

## Resolve shared taxonomies

```python
field = probe.question("knowledge_offer")
taxonomy = probe.taxonomy(field.taxonomy_id)
```

Applications render labels but submit stable option values. Multiple fields
that name one taxonomy resolve through `probe.taxonomy()` to the same canonical
taxonomy object.

## Validate and record answers

```python
from probe_engine import ProbeRuntime

runtime = ProbeRuntime(probe, participant_id="participant-1", scope_id="forum-1")
runtime.answer("knowledge_offer", ["data_governance_models"])
runtime.skip("friction", reason_codes=["not_relevant"])
runtime.flag(
    "future_outcome",
    reason_codes=["interesting_question"],
    note="Needs discussion.",
)
runtime.validate_resolution("future_outcome")
```

`answer()` is the public validation boundary. It validates choice membership,
selection constraints, repeatable item shape, stable item identity, and nested
fields before appending an answer event. `validate_resolution()` is the CTA
boundary: it accepts Answer, Skip, or Flag, so a substantive answer is not
mandatory. Skip and Flag remain distinct events with distinct controlled reason
taxonomies; neither is encoded as an answer value. Flag is orthogonal and can
coexist with Answer or Skip. Nested controls inherit parent resolution unless
explicitly declared `independently_answerable`.

## Canonical serialization

```python
from probe_engine import probe_from_dict, trajectory_from_dict

definition_value = probe.to_dict()
restored_probe = probe_from_dict(definition_value)

trajectory_value = runtime.trajectory.to_dict()
restored_trajectory = trajectory_from_dict(trajectory_value)
```

Consumers persist these JSON-compatible canonical values. They should not
serialize dataclass internals or reconstruct definitions through parser
helpers. `probe-definition/v1` and `probe-trajectory/v1` are explicit and fail
closed on unknown versions.

## Process boundaries

```python
runtime.reach_section_boundary("exchange", trajectory_store)
```

For a declared boundary this appends a checkpoint event, appends a named
`sync_point_reached` event when applicable, and calls the explicit store
checkpoint boundary. It does not wait for a cohort, calculate quorum, release
participants, or implement distributed coordination.

## Resume and reconcile

```python
runtime = ProbeRuntime.hydrate(
    current_probe,
    restored_trajectory,
    participant_id="participant-1",
    scope_id="forum-1",
)

pending = runtime.pending()
review = runtime.review()
reconciliation = runtime.reconciliation()
```

Hydration validates participant, Probe, and scope identity. Reconciliation uses
current field order and exact field revisions while retaining old events.

## Deliberate boundary

The public contract does not include Streamlit widgets, Protocol Hack models,
Host dashboards, analytics, fingerprints, generalized Boolean expressions,
taxonomy migration, privacy policy, or synchronization infrastructure. Add a
new semantic primitive only when a consumer integration demonstrates that the
current canonical values cannot represent required meaning without loss.
