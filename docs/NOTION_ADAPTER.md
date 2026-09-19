# Minimal Notion adapter boundary

Notion is not a Probe Engine dependency. A consumer may implement
`TrajectoryStore` using a minimal database containing participation identity,
Probe identity/revision, opaque scope, schema identifier, the complete
`probe-trajectory/v1` JSON payload, an idempotency key, and integration time.

`examples/notion_adapter/bootstrap_minimal.py` creates that database when run
inside an application environment that separately installs `notion-client`.
It does not define participant profiles, authentication, event routing, or
question databases. Adapters must reject missing canonical properties rather
than silently discard supplied trajectory fields.

