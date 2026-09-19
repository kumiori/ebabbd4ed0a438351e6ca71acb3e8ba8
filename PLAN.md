# Probe Engine extraction plan

## Completed in the 0.1.0 candidate

- Audited and classified both source lineages.
- Established canonical ordered Probe/block/question model.
- Added YAML, Python, and augmented-Markdown authoring convergence.
- Added local append-only trajectory runtime and explicit Answer/Skip/Flag.
- Added revision-aware reconciliation, review, hydration, and pending order.
- Added explicit persistence protocol, in-memory store, and idempotent integration.
- Added portable schemas, projections, tests, and independent example.
- Added optional consumer-side minimal Notion bootstrap example.

## Release gates

- [x] Focused package tests.
- [x] Independent example.
- [x] Ruff validation.
- [x] Isolated wheel and source-distribution build.
- [x] Twine validation and archive inspection.
- [ ] Independent repository `main` push and remote verification.
- [ ] Annotated `v0.1.0` tag and remote verification.
- [ ] Clean installation from the remote tag.
- [ ] Unrelated remote-installed consumer proof.

## Post-release consumer migration

- [ ] Migrate IceIceBaby capability-by-capability after equivalence tests.
- [ ] Migrate Protocol Hack Markdown Aperture after equivalence tests.

The package must not be tagged while a release gate above remains unchecked.
Consumer migrations begin only after the remote-install proof succeeds.
