# Portable schemas

Probe Engine 0.3.0.dev2 writes three explicit schemas:

- `probe-definition/v1`: Probe identity/revision, ordered semantic blocks,
  exact question definitions/revisions, status, lineage, and metadata.
- `probe-trajectory/v1`: participation identity and scope plus ordered,
  append-only interaction events, including structured Skip/Flag reason codes
  and notes.
- `probe-representation-result/v1`: a neutral evaluated projection, explicit
  denominator, and Probe/field/taxonomy/representation/population provenance.

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

Composed answers use the authored field structure. For a choice field with an
`other` control, the canonical runtime value is a mapping with `selected` and
an `other.value`; repeatable item fields accept the same structure recursively.
The enclosing trajectory event preserves the parent field revision, while nested
field revisions remain in the canonical Probe definition referenced by result
provenance.

## Representation definitions

`ProbeDefinition` may contain revisioned representation definitions and an
ordered results composition. Definitions reference stable field, taxonomy, and
representation IDs. Loading fails on unresolved IDs, invalid nested paths,
incompatible source types, incompatible comparison sources, and composite cycles.
Results composition preserves narrative order and authored commentary without
encoding charts, grids, widths, or any renderer technology.

## Resolution

Top-level fields are independently answerable by definition. They are resolved
by Answer or Skip; `validate_resolution()` is the renderer-neutral CTA
gate. `required` applies only inside the Answer route. Nested fields inherit the
nearest answerable ancestor's state unless authored with
`independently_answerable: true`.

The default `ResolutionDefinition` contains two distinct revisioned taxonomies:
Prediction's seven Skip reasons and nine positive/critical Flag reasons. Events
store normalized `reason_codes` and an optional `reason_note`; the historical
`reason` string remains readable for trajectory compatibility. Flag remains
orthogonal, so answered+flagged and skipped+flagged are both representable.

Flag is orthogonal: a flag-only question remains unresolved/unanswered, while
answered+flagged and skipped+flagged remain representable.

Representation denominators expose `resolved` separately from `answered`,
`skipped`, `flagged`, `deferred`, and `unanswered`. Flag-only contributes to
`flagged` and `unanswered`, never to `resolved` or `answered`.
