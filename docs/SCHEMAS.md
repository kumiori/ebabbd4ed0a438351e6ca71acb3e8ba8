# Portable schemas

Probe Engine 0.1.0 writes two explicit schemas:

- `probe-definition/v1`: Probe identity/revision, ordered semantic blocks,
  exact question definitions/revisions, status, lineage, and metadata.
- `probe-trajectory/v1`: participation identity and scope plus ordered,
  append-only interaction events.

`ProbeDefinition.to_dict()` and `Trajectory.to_dict()` create portable values.
`probe_from_dict()` and `trajectory_from_dict()` accept only these exact schema
identifiers. Unknown schema identifiers fail with `SchemaError`; they are never
silently coerced.

