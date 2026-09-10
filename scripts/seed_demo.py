"""Idempotent demo data seeder.

Seeds three scenarios (India, Emirates, Mexico) entirely through the
running API — clients and projects via their CRUD endpoints, the
recursive Zone hierarchy and Structures via their endpoints — plus a set
of demo users at every access level (client/project/zone/structure) via
POST /authorization/grant.

Safe to re-run: a 409 ("already exists") from /clients, /projects, or
/structures is treated as "already seeded" rather than a failure; zone
creation and grants are already idempotent at the API level (Steps 8-9).

Requires the docker-compose stack and the FastAPI app to already be
running (see README.md "Setup"), and FGA_STORE_ID/FGA_MODEL_ID to be
configured in .env (scripts/bootstrap_openfga.py).

Usage:
    python scripts/seed_demo.py
    SEED_BASE_URL=http://127.0.0.1:8002 python scripts/seed_demo.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE_URL = os.environ.get("SEED_BASE_URL", "http://127.0.0.1:8002")

# Statuses treated as "this already exists, nothing to do" for a repeatable
# seed run: 201 (created now), 200 (idempotent no-op, e.g. a zone with an
# unchanged parent), 409 (a client/project/structure with this id already
# exists from a prior run).
_OK_STATUSES = {200, 201, 409}


def _post(client: httpx.Client, path: str, json: dict) -> httpx.Response:
    response = client.post(path, json=json)
    if response.status_code not in _OK_STATUSES:
        response.raise_for_status()
    return response


def seed_client(client: httpx.Client, id_: str, name: str) -> None:
    r = _post(client, "/clients", {"id": id_, "name": name})
    print(f"  client      {id_:<28} {r.status_code}")


def seed_project(client: httpx.Client, id_: str, client_id: str, name: str) -> None:
    r = _post(client, "/projects", {"id": id_, "client_id": client_id, "name": name})
    print(f"  project     {id_:<28} {r.status_code}")


def seed_zone(client: httpx.Client, id_: str, parent_type: str, parent_id: str) -> None:
    r = _post(client, "/zones", {"id": id_, "parent_type": parent_type, "parent_id": parent_id})
    print(f"  zone        {id_:<28} {r.status_code}  (parent {parent_type}:{parent_id})")


def seed_structure(client: httpx.Client, id_: str, name: str, parent_id: str) -> None:
    r = _post(client, "/structures", {"id": id_, "name": name, "parent_type": "zone", "parent_id": parent_id})
    print(f"  structure   {id_:<28} {r.status_code}  (zone:{parent_id})")


def seed_grant(client: httpx.Client, user: str, resource_type: str, resource_id: str) -> None:
    r = _post(
        client, "/authorization/grant", {"user": user, "resource_type": resource_type, "resource_id": resource_id}
    )
    print(f"  grant       {user:<20} -> {resource_type}:{resource_id:<20} {r.status_code}")


def seed_india(client: httpx.Client) -> None:
    print("\n=== Scenario 1: India ===")
    seed_client(client, "govt-of-india", "Govt of India")
    seed_project(client, "indian-railway", "govt-of-india", "Indian Railway")
    seed_zone(client, "north", "project", "indian-railway")
    seed_zone(client, "south", "project", "indian-railway")
    seed_zone(client, "western", "project", "indian-railway")
    seed_zone(client, "delhi", "zone", "north")
    seed_zone(client, "central", "zone", "delhi")
    seed_structure(client, "yamuna-bridge", "Yamuna Bridge", "central")
    seed_structure(client, "agra-bridge", "Agra Bridge", "central")
    seed_structure(client, "delhi-bridge", "Delhi Bridge", "delhi")
    seed_structure(client, "north-bridge", "North Bridge", "north")
    seed_structure(client, "south-bridge", "South Bridge", "south")
    seed_structure(client, "western-bridge", "Western Bridge", "western")


def seed_emirates(client: httpx.Client) -> None:
    print("\n=== Scenario 2: Emirates ===")
    seed_client(client, "emirates", "Emirates")
    seed_project(client, "etihad-high-speed-railway", "emirates", "Etihad High Speed Railway")
    # Track 1 / Track 2 have no business attributes of their own, so they
    # are represented purely as Zones (no Structures beneath them) per the
    # project's demo-data specification.
    seed_zone(client, "track-1", "project", "etihad-high-speed-railway")
    seed_zone(client, "track-2", "project", "etihad-high-speed-railway")


def seed_mexico(client: httpx.Client) -> None:
    print("\n=== Scenario 3: Mexico ===")
    seed_client(client, "mexican-government", "Mexican Government")
    seed_project(client, "mexican-railway", "mexican-government", "Mexican Railway")
    seed_zone(client, "chihuahua", "project", "mexican-railway")
    seed_zone(client, "queretaro", "project", "mexican-railway")
    seed_structure(client, "structure-1", "Structure 1", "chihuahua")
    seed_structure(client, "structure-2", "Structure 2", "queretaro")


# (user, resource_type, resource_id, description) — one demo user per
# access level, spanning all three scenarios. user:nobody is intentionally
# absent: it has zero grants, used in Postman/tests to demonstrate denial.
DEMO_USERS = [
    ("user:parth", "client", "govt-of-india", "client-level access to all of India"),
    ("user:alice", "project", "indian-railway", "project-level access to Indian Railway"),
    ("user:carlos", "zone", "north", "zone-level access to North (and Delhi, Central beneath it)"),
    ("user:deepa", "structure", "yamuna-bridge", "structure-only access to Yamuna Bridge"),
    ("user:etihad-admin", "client", "emirates", "client-level access to Emirates"),
    ("user:mx-admin", "client", "mexican-government", "client-level access to Mexican Government"),
]


def seed_demo_users(client: httpx.Client) -> None:
    print("\n=== Demo users / access levels ===")
    for user, resource_type, resource_id, description in DEMO_USERS:
        print(f"  {description}")
        seed_grant(client, user, resource_type, resource_id)
    print("\n  user:nobody has no grants anywhere -- use it to demonstrate zero-access denial.")


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        health = client.get("/health")
        health.raise_for_status()

        seed_india(client)
        seed_emirates(client)
        seed_mexico(client)
        seed_demo_users(client)

    print("\nDemo data seeded successfully (idempotent -- safe to re-run).")


if __name__ == "__main__":
    main()
