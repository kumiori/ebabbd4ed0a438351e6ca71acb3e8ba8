# Montréal authoring contract

`tests/fixtures/montreal_communs_2.yaml` is the exact Montréal v2 conformance
document. `load_yaml_probe()` recognises its `probe-authoring/v1` dialect and
compiles it to a runtime `ProbeDefinition`; consumers do not pre-normalise the
document. Canonical definition serialization preserves every accepted construct
needed to rehydrate that compiled meaning.

## Top-level classification

| Construct | Classification | Compiled meaning |
| --- | --- | --- |
| `questionnaire` | Canonical authoring metadata | Identity, revision, status, language, flow defaults, welcome/review policy |
| `step_order` | Canonical Probe semantics | Exact ordered `StepDefinition` sequence |
| `flow_modes` | Canonical authoring metadata | Named, ordered subsets of authored steps |
| `sections` | Canonical Probe semantics | Section-to-step membership plus checkpoint and sync-point declarations |
| `step_copy` | Canonical authoring metadata | Lossless title, body, and CTA copy on every compiled step |
| `taxonomies` | Canonical Probe semantics | Revisioned stable options and option groups |
| `questions` | Canonical Probe semantics | Versioned fields, composition, conditions, routes, and constraints |
| `interaction` | Canonical Probe semantics | Answer/Skip resolution, orthogonal Flag annotations, review and inheritance policy |
| `profile_fields` | Canonical authoring metadata | Explicit authored profile classification; no identity or storage behaviour |
| `session_fields` | Canonical authoring metadata | Explicit authored session classification; no persistence behaviour |
| `deferrable_fields` | Canonical Probe semantics | Fields on which the distinct Deferred event is permitted |
| `fingerprint_axes` | Canonical representation semantics | Stable participant portrait axes and their sources/taxonomies |
| `representations` | Canonical representation semantics | Neutral participant/collective projections and ordered composition |
| `editorial_review` | Canonical authoring metadata | Explicitly accepted editorial status and notes |

`interaction.mobile` is the sole application-presentation declaration accepted
by this fixture. It is preserved explicitly as an authoring presentation hint;
Probe Engine assigns it no rendering behaviour. Unknown keys at the document or
nested construct boundaries fail compilation. There is no `extra=allow` path.

## Runtime boundaries

- Location is a semantic primitive. Its canonical value can contain display
  label, locality, region, country, country code, stable place identifier,
  latitude, and longitude. Capabilities declare manual text, lookup support, and
  whether lookup requires user action. Lookup adapters, HTTP, OpenCage, and UI
  concerns stay in consuming applications.
- Answer and Skip resolve an eligible question. Flag records one or more authored
  flag values and an optional note, but is orthogonal and cannot resolve a
  question by itself. Deferred remains a separate trajectory disposition where
  the authoring declaration permits it.
- Subordinate fields inherit their parent's resolution unless explicitly marked
  independently answerable. The rule applies recursively inside repeatable
  groups.
- Representation denominators count Answer, Skip, Deferred, Flag, and Unanswered
  independently: a flag-only interaction increments both Flagged and Unanswered,
  never Resolved.

## Source anomaly policy

The supplied `future_outcome` option list declares `unexpected_initiative`
twice: first without a label, then with its label. Stable option identity is
canonical, so compilation coalesces duplicate declarations in source order and
uses the later non-empty label. Any stable option still lacking a label fails
explicitly.
