# Montréal questionnaire: validation and rendering boundary

`tests/fixtures/montreal.yaml` is the demanding conformance fixture for the
canonical `probe-authoring/v1` contract. It is intentionally not flattened to
an application questionnaire or widget vocabulary.

## Cardinality accounting

The authored application questionnaire previously reported 16 flow steps:

`welcome` + 13 interaction steps + `review` + `done`.

The canonical Probe contains the 13 interaction steps. `welcome`, `review`,
and `done` are application flow/chrome states rather than authored answer
screens, so they are intentionally outside `ProbeDefinition.steps`.

The source contained 24 question records. The canonical Probe contains 26
fields because two former `companion` controls are now ordinary, independently
identified fields colocated with their parent step:

- `knowledge_offer_example` in `exchange_offer`;
- `knowledge_need_example` in `exchange_need`.

Thus `16 → 13` removes three non-answer flow states, while `24 → 26` promotes
two authored answer controls. Neither change drops answer semantics.

## Machinery now represented by Probe Engine

| YAML construct | Canonical representation | Renderer obligation |
| --- | --- | --- |
| Section process | `SectionDefinition.checkpoint` and `sync_point` | Call the explicit process-boundary operation; coordination remains external. |
| Grouped choice | `type: multi`, a taxonomy reference, and `presentation.group_by` | Render group labels without changing option identity. |
| Other answer | `OtherControl` on an ordinary field | Render associated text without inventing a new input type. |
| Companion answer | Another ordinary field in the same Step | Render fields together while preserving independent field identity and revision. |
| Suggested text | `type: text` with `suggestions` | Offer suggestions while preserving a text answer. |
| Repeatable structure | `type: repeatable` with recursive `item_fields` | Keep each action and its actors in one stable-ID item. |
| Conditions and constraints | Typed condition, route, and constraint values | Apply the declared semantics without inspecting opaque metadata. |

The loader also uses YAML 1.2 boolean rules. This is semantic, not cosmetic:
unquoted option values `yes` and `no` remain those exact string identities.

## Machinery deliberately not supplied by this package

Probe Engine remains UI- and infrastructure-neutral. A consumer renderer still
has to implement the following:

1. **Widget rendering and local draft state.** There is no Streamlit, browser,
   form, add/remove-row, conditional visibility, or pill component here.
2. **Condition and route execution.** The canonical model validates and
   preserves conditions/routes; a consuming flow controller evaluates them.
3. **Checkpoint storage.** `process.checkpoint` identifies when a checkpoint is
   wanted, but only the application's explicit `TrajectoryStore` call persists
   it.
4. **Synchronisation coordination.** A `sync_point` records participant arrival.
   Cohort waiting/release, quorum, timeouts,
   operator override, and recovery need an application-level coordinator and
   durable shared state.
5. **Welcome/review/done and mode chrome.** `step_copy`, `flow_modes`, identity
   placement, and profile/session projections are application composition and
   presentation concerns, not Probe primitives.

Consumers should adapt the canonical Sections, Steps, Fields, and Taxonomies;
they should not fork or flatten the questionnaire YAML.
