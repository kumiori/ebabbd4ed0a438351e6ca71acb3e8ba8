# Probe Engine extraction map

This audit precedes extraction. Behaviour was derived into a clean package
contract; neither source implementation was mechanically copied.

| Classification | Source | Responsibility and dependencies | Probe target | Protection / maturity |
|---|---|---|---|---|
| CORE | IceIceBaby `conference/question_sets/__init__.py` | Stable IDs, revisions, lineage, reask policy; Python only | `model.py`, `runtime.py` | YAML/revision tests; Udine production lineage |
| CORE | IceIceBaby `conference/question_state.py` | Distinct answered/skipped/flagged state; Python only | append-only events in `runtime.py` | interaction semantics tests; production lineage |
| CORE | IceIceBaby `conference/question_sets/yaml_loader.py` | YAML loading, shared definitions, explicit validation; PyYAML | `authoring.py` | YAML-first tests; production lineage |
| CORE | IceIceBaby `conference/wg2_schema.py` | revision comparison and retained provenance; application bundles | `reconcile()` and trajectory history | schema evolution tests; exercised lineage |
| CORE | IceIceBaby `conference/flow.py` | ordered steps, review/payload semantics; Streamlit session state | ordered blocks, review projection | flow tests; production lineage |
| ADAPTER | IceIceBaby `repositories/interaction_repo.py` | Notion response/checkpoint storage | consumer-side `TrajectoryStore` adapter | repository tests; production |
| APPLICATION | IceIceBaby `conference/questionnaire.py` | Streamlit UI, identity, recovery, routing, event copy | none | route/App tests; production |
| APPLICATION | IceIceBaby Host/Results modules | operational/scientific rendering | consumes neutral projections | projection/host tests; production |
| PROTOTYPE | Protocol Hack `protocol/aperture/directives.py` at `6f09cb5` | front matter and `{{ question: id }}` splitting; regex/PyYAML | replaceable parser in `authoring.py` | aperture contract tests; experimental |
| CORE | Protocol Hack `protocol/aperture/registry.py` | separate question catalogue and reference resolution | catalogue loader | aperture tests; experimental concept |
| ADAPTER | Protocol Hack `protocol/aperture/responses.py` | append-only JSONL trace | example store may be consumer code | aperture tests; experimental |
| APPLICATION | Protocol Hack `protocol/aperture/renderer.py` | native Streamlit widgets and trace rendering | none | aperture tests; experimental |
| DO_NOT_EXTRACT | Both applications | event prose, questionnaires, CSS, charts, routes, credentials, profiles, deployment, secrets | none | application-owned |

## Lineage result

IceIceBaby contributes the revision, trajectory, scope, local interaction,
review/resume, integration, and projection semantics. Protocol Hack contributes
readable augmented Markdown, stable embedded references, external catalogue
resolution, and source-ordered narrative/question composition.

The package depends on PyYAML only. Streamlit, Notion, `protocol-lab`, and
`trajectory-engine` remain outside the core.

