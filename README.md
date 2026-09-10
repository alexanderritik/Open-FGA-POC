# OpenFGA ReBAC Authorization PoC

A production-oriented proof of concept demonstrating Relationship-Based Access
Control (ReBAC) with [OpenFGA](https://openfga.dev/), fronted by a FastAPI
application.

## Architecture

```
                         FastAPI
                            |
              +-------------+-------------+
              |                           |
              v                           v
       Application DB                 OpenFGA
       PostgreSQL                         |
              |                           v
              |                    OpenFGA PostgreSQL
              |                           |
              |                    Authorization data
              |
       Business entities
```

**Application PostgreSQL** stores business/application data only:
`users`, `clients`, `projects`, `structures`, `audit_events`.

**OpenFGA** is the source of truth for authorization relationships and
hierarchy, including the entire `Zone` concept.

### Zone is not a database entity

`Zone` has **no table** in the application database. A Zone exists only as
an OpenFGA object connected via relationship tuples, e.g.:

```
zone:north#parent@project:indian-railway
zone:delhi#parent@zone:north
zone:central#parent@zone:delhi
structure:yamuna-bridge#parent@zone:central
```

This lets Zones nest recursively (Zone -> Zone -> Zone -> ...) without any
schema changes, and keeps OpenFGA as the single source of truth for the
authorization hierarchy.

### Hierarchy

```
Client -> Project -> Zone -> Zone -> ... -> Zone -> Structure
```

Access is inherited downward only:
- Viewing a Project grants viewing of all Zones/Structures beneath it.
- Viewing a Zone grants viewing of all child Zones/Structures beneath it.
- Viewing a Structure grants **no** access upward.
- Access to one Zone branch never grants access to a sibling branch.

## Authentication is out of scope

This PoC has **no JWT / login / OAuth / password hashing**. User identity is
supplied directly as a string (e.g. `user:parth`) to authorization-aware
endpoints. This keeps the PoC focused purely on the authorization model.

## Project layout

```
app/
├── main.py                  FastAPI app, lifespan, router registration
├── core/
│   ├── config.py             pydantic-settings configuration
│   └── logging.py            structured logging setup
├── db/
│   ├── database.py           SQLAlchemy engine/session
│   ├── models/                ORM models (user, client, project, structure, audit_event)
│   └── migrations/            Alembic migrations
├── authorization/
│   ├── client.py              OpenFGA SDK client lifecycle
│   ├── service.py              write/delete/check/list helpers (single choke point for SDK calls)
│   ├── models.py               typed request/response dataclasses
│   └── exceptions.py           authorization-specific exceptions
├── api/                        FastAPI routers (clients, projects, zones, structures, authorization, tree)
├── schemas/                     Pydantic request/response schemas
└── services/                    business logic orchestration per entity

tests/
├── unit/
├── integration/
└── security/

postman/                        Postman collection for manual/exploratory testing
docker-compose.yml               app db + openfga + openfga db + migration service
```

## Prerequisites

- Python 3.11+ (developed/tested against 3.14; `requirements.txt` pins
  versions with prebuilt wheels for 3.14 — see `requirements.lock.txt` for
  the exact resolved set used in development)
- Docker + Docker Compose
- (optional) `psql` client for debugging the application database directly

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment configuration
cp .env.example .env
# edit .env if needed (defaults work with docker-compose as-is)

# 4. Start infrastructure (application Postgres, OpenFGA, OpenFGA Postgres)
docker compose up -d

# 5. Run database migrations
alembic upgrade head

# 6. Bootstrap the OpenFGA store + authorization model
python scripts/bootstrap_openfga.py
# copy the printed FGA_STORE_ID / FGA_MODEL_ID into .env

# 7. Run the API
uvicorn app.main:app --reload --port 8002
```

Visit http://127.0.0.1:8002/docs for interactive API documentation.

## Running tests

```bash
pytest
```

## Demo data

```bash
python scripts/seed_demo_data.py
```

Seeds three scenarios (India / Emirates / Mexico) described in the project
specification, useful for exercising the Postman collection.

## Postman

Import `postman/OpenFGA-ReBAC-New-Architecture.postman_collection.json`.
Default `baseUrl` is `http://127.0.0.1:8002`. No authentication headers are
required.

## Operational notes

- The application PostgreSQL database and the OpenFGA PostgreSQL database are
  **logically separate** — the application never connects to, nor creates
  tables in, OpenFGA's internal datastore.
- If OpenFGA is unreachable, authorization checks **fail closed** (503), never
  defaulting to `allowed = true`.
- Audit events are recorded for hierarchy mutations and authorization
  decisions; see `app/services/audit_service.py`.
- This is a PoC: production hardening (secrets management, backup/restore
  drills, connection-pool tuning under load, model-version rollout strategy)
  is documented inline where relevant but not fully implemented.

## Implementation status

This project is being built step-by-step. See commit history / conversation
for progress. Current step: **Step 10 — Tree + Security + Audit**
(`GET /clients/{client_id}/tree`). Returns an authorization-pruned resource
tree: a node appears if the requesting user can view it directly/by
inheritance, or if any descendant can be viewed (so an ancestor the user
has no direct grant on can still render as a pass-through container on
the path to something they can see — e.g. a zone-level grant three levels
deep still needs the client/project nodes to attach to). Anti-enumeration:
a nonexistent client and a client the user has zero visibility into
produce an identical 404. Every access attempt is audited (`tree.access`,
`success`/`denied` with an internal-only reason, never exposed to the
caller) and OpenFGA outages fail closed (503, never a masked 200/404).
No Project CRUD API exists yet, so tests write the single
`project#parent@client` tuple directly, as in Steps 8–9.
