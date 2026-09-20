# Changelog

## 0.3.0.dev2 - 2026-09-20

- Compile the exact Montréal v2 questionnaire authoring contract through
  `load_yaml_probe()` without requiring consumer-side normalization.
- Add explicit authoring models for questionnaire metadata, ordered step copy,
  flow modes, profile/session classification, deferral, fingerprint axes, and
  editorial review.
- Add canonical URL and location primitives, grouped/Other field types,
  shortcuts, companions, conditional expressions, and repeatable groups.
- Preserve inline authored representation components and grouped distributions.
- Correct resolution semantics so Flag remains orthogonal and does not by itself
  resolve an unanswered question.
- Add the exact 1,142-line Montréal source as a conformance fixture and exercise
  parsing, canonical round trips, structured answers, hydration, editing, and persistence.

## 0.3.0.dev1 - 2026-09-20

Integration build for application consumption and consolidation toward 0.3.0.
This build is intentionally untagged.

- Make Answer/CTA, Skip, and Flag explicit resolution routes for every top-level
  interaction; substantive answers are not mandatory by default.
- Preserve Prediction's distinct revisioned Skip and Flag reason taxonomies,
  optional notes, and structured reason codes on canonical trajectory events.
- Let subordinate fields inherit parent resolution unless explicitly declared
  `independently_answerable`.
- Record flag-only interactions separately from Answer and Skip. This dev1
  behavior was corrected in dev2 so Flag remains unresolved until Answer or Skip.
- Add canonical representation definitions for distributions, responses, records,
  comparisons, timelines, and composites with participant/collective/cohort scope.
- Add neutral, serialisable representation results with explicit denominators and
  revision/population provenance.
- Add authored results composition with ordered narratives, representations, and
  epistemically distinct authored commentary.
- Preserve composed multi-select + Other answers, including recursively inside
  repeatable records, through trajectory hydration.
- Add static reference, capability, nested-path, compatibility, and composite-cycle
  validation.
- Add a distinct deferred trajectory disposition and denominator category.
- Extend the frozen Montréal fixture with four representation conformance specimens.

## 0.2.0 - 2026-09-19

- Require the explicit `probe-authoring/v1` discriminator for authored YAML.
- Add canonical Section → Step → Field structure with multiple fields per step.
- Add shared taxonomy objects with stable option and optional group identities.
- Compose grouped multi-select, other controls, suggestions, and companion fields from generic fields.
- Add equality conditions, selection/item constraints, terminal routes, and recursive repeatables.
- Record declared checkpoints and named synchronization-point arrivals without coordination behavior.
- Parse YAML 1.2 boolean tokens so option identities such as `yes` and `no` remain strings.

## 0.1.0 - 2026-09-19

- Establish canonical ordered Probe, block, and versioned question model.
- Add YAML and augmented-Markdown authoring front ends.
- Add append-only local trajectory runtime with Answer, Skip, and Flag events.
- Add revision-aware reconciliation, review, hydration, and pending work.
- Add explicit coarse-grained persistence and idempotent finalisation boundary.
- Add portable definition and trajectory schemas.
- Add operational and collective neutral projections.
- Add independent non-Streamlit consumer example.
