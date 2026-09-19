"""Optional consumer-side bootstrap for a minimal Notion trajectory store.

This file is deliberately excluded from the Probe Engine import graph. Install
`notion-client` in the consuming application and provide a parent page ID.
"""

from __future__ import annotations

import argparse

PROPERTIES = {
    "Name": {"title": {}},
    "participation_id": {"rich_text": {}},
    "participant_id": {"rich_text": {}},
    "probe_id": {"rich_text": {}},
    "probe_revision": {"number": {"format": "number"}},
    "scope_id": {"rich_text": {}},
    "schema": {"select": {"options": [{"name": "probe-trajectory/v1"}]}},
    "trajectory_json": {"rich_text": {}},
    "idempotency_key": {"rich_text": {}},
    "integrated_at": {"date": {}},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--parent-page-id", required=True)
    parser.add_argument("--title", default="Probe Trajectories")
    args = parser.parse_args()
    try:
        from notion_client import Client
    except ImportError as exc:
        raise SystemExit("Install notion-client in the consuming application.") from exc
    client = Client(auth=args.token)
    database = client.databases.create(
        parent={"type": "page_id", "page_id": args.parent_page_id},
        title=[{"type": "text", "text": {"content": args.title}}],
        properties=PROPERTIES,
    )
    print(database["id"])


if __name__ == "__main__":
    main()

