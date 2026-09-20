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
| REPRESENTATION | IceIceBaby questionnaire ordering, `fingerprint_axes`, and `fingerprint_labels` | ordered stable field references and authored labels | generic revisioned definitions and composite representations | Montréal representation conformance tests |
| REPRESENTATION | IceIceBaby collective distribution and response-field derivation | counts, proportions, response records, distinct answered/skipped/flagged state | neutral results with explicit denominators | evaluation and round-trip tests |
| CORE | IceIceBaby `conference/question_skips.py`, `question_flags.py`, and `question_state.py` | separate Skip/Flag vocabularies, optional notes, and orthogonal flag state | revisioned reason taxonomies, structured event reasons, and Answer/Skip/Flag resolution | resolution and hydration tests |
| REPRESENTATION | IceIceBaby timeline and participant/collective portraits | ordered events and semantically grouped projections | timeline and composite representations with explicit scope | projection tests |
| REPRESENTATION | IceIceBaby per-question ordering, opening copy, and commentary | authored scientific/editorial sequence and association | results composition with narrative and authored interpretation | composition test |
| APPLICATION | IceIceBaby bars, dots, cards, tables, two-column widths, Plotly/Streamlit/CSS | visual realization and interaction | none | remains consumer-owned |
| DO_NOT_EXTRACT | IceIceBaby historical chart-type names and event-specific fingerprint machinery | renderer/special-case vocabulary | none; expressed through generic distribution/composite algebra where meaningful | deliberately omitted |
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

The 0.3 classification is: stable question order/content and welcome/completion
copy are Probe semantics; projection definitions, explicit denominators,
participant/collective scope, and ordered commentary association are
representation semantics; screen nodes, columns, charts, CSS, privacy decisions,
and Host operations remain application presentation; historical widget/chart
names are not preserved. Fingerprints are generic composites rather than a new
canonical primitive. Welcome and completion are Probe content, review/finalise
remain trajectory semantics, and their screens remain application-owned.

The package depends on PyYAML only. Streamlit, Notion, `protocol-lab`, and
`trajectory-engine` remain outside the core.
