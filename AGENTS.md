# Probe Engine agent instructions

Probe Engine extracts semantic engines, never application surfaces.

- Keep the package independent of Streamlit, Notion, application identity,
  deployment, styling, and event-specific content.
- Preserve stable Probe and question identities, exact revisions, scope, and
  append-only response provenance.
- Never encode Skip as null or Flag as an answer option.
- Keep interaction local. Persistence occurs only through explicit load,
  checkpoint, or finalise boundaries.
- Reconciliation must use question revisions and current instrument order.
- Parsing, rendering, persistence, and interpretation are separate concerns.
- Invalid definitions, unresolved references, schema incompatibility, scope
  mismatch, and invalid answers fail explicitly.
- Every public semantic change requires tests and a changelog entry.
- Build and inspect both wheel and sdist; prove installation in a clean venv.

