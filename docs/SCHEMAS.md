# Portable schemas

Probe Engine 0.2.0 writes two explicit schemas:

- `probe-definition/v1`: Probe identity/revision, ordered semantic blocks,
  exact question definitions/revisions, status, lineage, and metadata.
- `probe-trajectory/v1`: participation identity and scope plus ordered,
  append-only interaction events.

`ProbeDefinition.to_dict()` and `Trajectory.to_dict()` create portable values.
`probe_from_dict()` and `trajectory_from_dict()` accept only these exact schema
identifiers. Unknown schema identifiers fail with `SchemaError`; they are never
silently coerced.

Authored YAML has its own required discriminator: `probe-authoring/v1`.
`load_yaml_probe()` does not infer a dialect from keys such as `questionnaire`
or `questions`; unsupported dialects and keys fail explicitly.

## Authored interaction structures

The YAML authoring front end preserves renderer-neutral structures:

- A Probe owns ordered Sections, Steps, Fields, and Taxonomies. A Step may own
  multiple Fields.
- Sections declare `checkpoint` and an optional named `sync_point`.
- Ordinary `multi` fields reference a shared taxonomy and may request grouped
  presentation; the taxonomy object is not copied into each field.
- `other`, `suggestions`, and colocated text fields compose richer controls
  without new widget-shaped field types.
- `repeatable` recursively carries item fields. Answers are lists of mappings
  with unique stable item IDs.
- Equality conditions and terminal routes are explicit typed values designed
  to admit later operators without changing existing representations.

These values round-trip through `probe-definition/v1`. The additions are
optional, so existing v1 definitions remain readable.
