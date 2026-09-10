# OpenFGA ReBAC Authorization PoC

A production-oriented proof of concept demonstrating Relationship-Based Access
Control (ReBAC) with [OpenFGA](https://openfga.dev/), fronted by a FastAPI
application.

**Status: feature-complete (Steps 1–11).** All planned endpoints, the demo
data set, the Postman collection, and the test suite are implemented and
verified. See [Known limitations](#known-limitations) before treating this
as anything beyond a PoC.

## Table of contents

- [Architecture](#architecture)
- [Authentication is out of scope](#authentication-is-out-of-scope)
- [Project layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Docker infrastructure](#docker-infrastructure)
- [OpenFGA authorization model](#openfga-authorization-model)
- [API reference](#api-reference)
- [Demo data](#demo-data)
- [Testing](#testing)
- [Postman](#postman)
- [Security model](#security-model)
- [Audit logging](#audit-logging)
- [Backups and disaster recovery](#backups-and-disaster-recovery)
- [Production considerations](#production-considerations)
- [Known limitations](#known-limitations)

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
`users`, `clients`, `projects`, `structures`, `audit_events`. Nothing about
*who can see what* is stored here.

**OpenFGA** is the single source of truth for authorization relationships
and hierarchy: `client`, `project`, `zone` (including arbitrarily nested
zones), and `structure` all exist there as relationship tuples. There is
**no permissions-mirror table** in the application database — every
authorization decision is answered by calling OpenFGA, never by querying
Postgres.

### Zone is not a database entity

`Zone` has **no table** in the application database and **no SQLAlchemy
model**. A Zone exists only as an OpenFGA object connected via relationship
tuples, e.g.:

```
zone:north#parent@project:indian-railway
zone:delhi#parent@zone:north
zone:central#parent@zone:delhi
structure:yamuna-bridge#parent@zone:central
```

This lets Zones nest recursively (Zone → Zone → Zone → ...) to arbitrary
depth without any schema changes, and keeps OpenFGA as the single source of
truth for the authorization hierarchy. Because Zone has no business data,
a zone node's only identity anywhere in this system is its `id` — API
responses for a zone never include a `name` field (see
[Tree](#get-clientsclient_idtree)).

### Hierarchy

```
Client -> Project -> Zone -> Zone -> ... -> Zone -> Structure
```

- **Client** and **Project** and **Structure** have both a business row
  (application DB) and an OpenFGA object with a `parent` tuple establishing
  where they sit in the hierarchy.
- **Zone** has only the OpenFGA object/tuples — no business row.
- Access is inherited **downward only**: viewing a Client grants viewing of
  every Project/Zone/Structure beneath it; viewing a Zone grants viewing of
  every nested child Zone and Structure beneath it.
- Viewing a Structure grants **no** access upward (not to its Zone, Project,
  or Client).
- Access to one Zone branch never grants access to a sibling branch, and
  access within one Client's tree never grants access to another Client's
  tree.

## Authentication is out of scope

This PoC has **no JWT / login / OAuth / password hashing / auth middleware**.
User identity is supplied directly as a string (e.g. `user:parth`) to
authorization-aware endpoints (`/authorization/*`, `/clients/{id}/tree`).
This keeps the PoC focused purely on the authorization *model and
architecture* — a real deployment would put a real authentication layer in
front of the API and derive the caller's identity from a verified token
rather than a client-supplied query parameter. Endpoints that don't need a
caller identity (e.g. `GET /structures/{id}`) have no user-scoped access
control at all; see [Known limitations](#known-limitations).

## Project layout

```
app/
├── main.py                     FastAPI app, lifespan (OpenFGA client connect/close), router registration
├── core/
│   ├── config.py                pydantic-settings configuration (env vars / .env)
│   └── logging.py                structured stdout logging
├── db/
│   ├── database.py               SQLAlchemy engine/session, Base, get_db dependency
│   ├── models/                   ORM models: User, Client, Project, Structure, AuditEvent (NO Zone model)
│   └── migrations/                Alembic migrations
├── authorization/
│   ├── client.py                  OpenFgaClientManager: process-wide async OpenFGA SDK client lifecycle
│   ├── service.py                  AuthorizationService: write_tuple/delete_tuple/check/list_relationships/
│   │                               read_parent/tuple_exists — the ONLY place OpenFGA SDK calls happen
│   ├── model.fga                   human-readable reference copy of the loaded authorization model
│   └── exceptions.py                AuthorizationServiceUnavailableError (fail-closed), InvalidAuthorizationRequestError
├── api/                          FastAPI routers: clients, projects, zones, structures, authorization, tree
├── schemas/                       Pydantic request/response schemas (+ common.py for shared id patterns)
└── services/                      Business logic per entity; only these call app/authorization/service.py
    ├── client_service.py / project_service.py / structure_service.py   (app DB + OpenFGA parent tuple)
    ├── zone_service.py             entirely OpenFGA — no Zone table to touch
    ├── access_service.py           /authorization/{check,grant} orchestration
    ├── tree_service.py             authorization-pruned tree traversal
    └── audit_service.py            append-only audit_events writer

tests/
├── unit/                          pure-logic tests (config, zone cycle-detection walk)
├── integration/                   one file per feature area, against the real app-postgres + OpenFGA stack
└── security/                      (reserved; security scenarios currently live alongside their feature's
                                     integration tests — see test_full_scenarios.py for the consolidated view)

scripts/
├── bootstrap_openfga.py           creates/reuses the OpenFGA store, writes the authorization model
├── verify_openfga_model.py        standalone recursive-zone-inheritance verification against live OpenFGA
├── seed_demo.py                   idempotent demo data seeder (India/Emirates/Mexico + demo users)
└── _build_postman.py              generator for postman/*.json (not part of the runtime app)

postman/                          Postman collection for manual/exploratory testing
docker-compose.yml                 app db + openfga + openfga db + migration service
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

# 8. (optional) seed demo data -- see "Demo data" below
python scripts/seed_demo.py
```

Visit http://127.0.0.1:8002/docs for interactive API documentation.

## Docker infrastructure

`docker compose up -d` starts four services:

| Service | Purpose | Host port |
|---|---|---|
| `postgres` (`rebac-poc-app-postgres`) | Application business data | `5436` (see note below) |
| `openfga-postgres` (`rebac-poc-openfga-postgres`) | OpenFGA's own internal datastore | `5434` |
| `openfga-migrate` (`rebac-poc-openfga-migrate`) | One-shot schema migration for OpenFGA's datastore | — |
| `openfga` (`rebac-poc-openfga`) | The authorization server | `8080` (HTTP), `8081` (gRPC), `3000` (Playground) |

The two Postgres instances use **separate named volumes**
(`openfga-rebac-poc_app_postgres_data`, `openfga-rebac-poc_openfga_postgres_data`)
and are never cross-connected — the application never opens a connection to
`openfga-postgres`, and nothing but OpenFGA's own migration job ever writes
to it.

`docker compose ps` should show all three long-running services `Up
(healthy)`/`Up`; check with:

```bash
docker compose ps
curl http://localhost:8080/healthz   # {"status":"SERVING"}
```

Note: `openfga` has no Docker-level healthcheck (the image is distroless —
no shell, `curl`, or `wget` inside it to run one), so liveness is checked
externally via `/healthz` instead, exactly as shown above and as the
application itself does at startup.

Non-default host ports (`5436`, `5434` instead of the Postgres/OpenFGA
defaults) were chosen because this development machine already had other,
unrelated services bound to `5432`/`5433`/`8080`'s usual neighbors —
adjust `.env` if your ports differ.

## OpenFGA authorization model

Schema 1.1, defined in [`app/authorization/model.fga`](app/authorization/model.fga)
and loaded via `scripts/bootstrap_openfga.py` (the Python SDK has no
DSL-to-JSON compiler, so the loader builds it from SDK model classes —
kept in sync with the `.fga` file, which is the human-readable reference):

```
type user

type client
  relations
    define viewer: [user]

type project
  relations
    define parent: [client]
    define viewer: [user] or viewer from parent

type zone
  relations
    define parent: [project, zone]
    define viewer: [user] or viewer from parent

type structure
  relations
    define parent: [zone]
    define viewer: [user] or viewer from parent
```

`zone#parent` accepting both `project` and `zone` is what gives Zones
arbitrary-depth recursion. Every type's `viewer` is `[user] or viewer from
parent` — downward-only inheritance, with no path back upward anywhere in
the model.

## API reference

No authentication on any endpoint. `user` fields/params are the caller-
supplied OpenFGA identity (e.g. `user:parth`); `resource_type` is one of
`client`, `project`, `zone`, `structure`.

| Method & path | Notes |
|---|---|
| `GET /health` | Liveness probe |
| `POST /clients` | `{id, name}`. Business row only — no OpenFGA object |
| `GET /clients` | List |
| `GET /clients/{client_id}` | Get |
| `POST /projects` | `{id, client_id, name}`. Business row **and** writes `project:<id>#parent@client:<client_id>` |
| `GET /projects` | List |
| `GET /projects/{project_id}` | Get |
| `POST /zones` | `{id, parent_type: "project"\|"zone", parent_id}`. **OpenFGA only** — no table, idempotent for an unchanged id+parent |
| `GET /zones/{zone_id}` | Returns `{id, parent_type, parent_id}` from OpenFGA |
| `GET /zones/{zone_id}/children` | Immediate child zones and structures |
| `GET /projects/{project_id}/zones` | Immediate child zones of a project |
| `POST /structures` | `{id, name, parent_type: "zone", parent_id}`. Business row **and** writes `structure:<id>#parent@zone:<parent_id>` |
| `GET /structures` | List (business data only) |
| `GET /structures/{structure_id}` | Get, including the OpenFGA-recorded parent zone |
| `GET /authorization/check` | `?user&resource_type&resource_id&permission=viewer` → `{allowed: bool}`. Delegates entirely to OpenFGA; fails closed |
| `POST /authorization/grant` | `{user, resource_type, resource_id, permission}`. Idempotent (`200` if already granted, `201` if new) |
| `DELETE /authorization/grant` | Same fields as query params. Idempotent (`204` even if nothing was granted) |
| `GET /clients/{client_id}/tree` | `?user=...` → authorization-pruned resource tree, see below |

### `GET /clients/{client_id}/tree`

Returns a tree rooted at the client, containing only what `user` can view.
A node appears if the user can view it directly/by inheritance, **or** if
at least one descendant can be viewed — the latter lets an ancestor the
user has no direct grant on still render as a "pass-through" container on
the path to something they can see (a zone-level grant three levels deep
still needs the client/project nodes to attach to).

```json
{
  "type": "client", "id": "govt-of-india", "name": "Govt of India",
  "children": [
    { "type": "project", "id": "indian-railway", "name": "Indian Railway",
      "children": [
        { "type": "zone", "id": "north", "name": null,
          "children": [
            { "type": "zone", "id": "delhi", "name": null, "children": [
              { "type": "zone", "id": "central", "name": null, "children": [
                { "type": "structure", "id": "yamuna-bridge", "name": "Yamuna Bridge", "children": [] },
                { "type": "structure", "id": "agra-bridge", "name": "Agra Bridge", "children": [] }
              ]}
            ]}
          ]}
      ]}
  ]
}
```

Zone nodes always have `"name": null` — Zone has no business data anywhere
in this system (see [Architecture](#architecture)).

A client that doesn't exist and a client the user has zero visibility into
both return an identical `404` (see [Security model](#security-model)).

## Demo data

```bash
python scripts/seed_demo.py
# or against a non-default host:
SEED_BASE_URL=http://127.0.0.1:8002 python scripts/seed_demo.py
```

Requires the Docker stack and the FastAPI app to already be running.
Seeds three scenarios through the real API (Client → Project → Zone →
Structure), plus a set of demo users spanning every access level:

```
Client: Govt of India                       Client: Emirates
└── Project: Indian Railway                 └── Project: Etihad High Speed Railway
    ├── Zone: North                             ├── Zone: Track 1
    │   ├── Zone: Delhi                         └── Zone: Track 2
    │   │   ├── Zone: Central                       (no Structures --
    │   │   │   ├── Structure: Yamuna Bridge          no business attributes)
    │   │   │   └── Structure: Agra Bridge
    │   │   └── Structure: Delhi Bridge         Client: Mexican Government
    │   └── Structure: North Bridge             └── Project: Mexican Railway
    ├── Zone: South                                 ├── Zone: Chihuahua
    │   └── Structure: South Bridge                 │   └── Structure: Structure 1
    └── Zone: Western                               └── Zone: Queretaro
        └── Structure: Western Bridge                   └── Structure: Structure 2
```

| Demo user | Access level | Grant |
|---|---|---|
| `user:parth` | Client | `client:govt-of-india` |
| `user:alice` | Project | `project:indian-railway` |
| `user:carlos` | Zone | `zone:north` (reaches Delhi, Central beneath it) |
| `user:deepa` | Structure | `structure:yamuna-bridge` only |
| `user:etihad-admin` | Client | `client:emirates` |
| `user:mx-admin` | Client | `client:mexican-government` |
| `user:nobody` | — | No grants anywhere — demonstrates zero-access denial |

**Idempotent / safe to re-run**: a `409` from `/clients`, `/projects`, or
`/structures` (id already exists) is treated as "already seeded"; zone
creation and grants are themselves idempotent at the API level. Verified
by running the script twice in a row with no errors and no duplicate data.

## Testing

```bash
pytest
```

Organized by feature area (one integration test file roughly per API
surface added in each build step), plus:

- `tests/unit/test_zone_cycle_detection.py` — the zone ancestor-walk cycle
  guard, tested in isolation with a fake `AuthorizationService` (so a real
  multi-level cycle can be exercised even though it's unreachable through
  the public API once created — see the code comments for why).
- `tests/integration/test_full_scenarios.py` — the capstone end-to-end
  suite: builds a full Client → Project → Zone → nested Zone → Structure
  hierarchy through nothing but public HTTP calls, then verifies every
  axis in one place — client/project/zone/nested-zone/structure-level
  access, cross-client and cross-branch denial, no-upward inheritance,
  zero-grant denial, fail-closed, anti-enumeration, tree pruning, and
  audit-trail coverage.

Every integration test cleans up its own rows (application DB) and tuples
(OpenFGA) in a fixture teardown; tests use randomly-suffixed ids so they
never collide with each other, with demo data from `scripts/seed_demo.py`,
or with each other across repeated runs. Verified: running the entire
suite with the demo data already seeded produces the same pass count as
running it against an empty database.

**A real bug this discipline caught**: two test files (from Steps 5 and
10) originally hardcoded literal ids/names — e.g. `"govt-of-india"` and
`"Govt of India"` — matching what `scripts/seed_demo.py` also uses. Once
the demo seed script existed and both could be present in the same
database, those tests failed on a unique-constraint / "tuple already
exists" collision. Fixed by switching them to test-only ids never used by
real demo data, matching the convention already used everywhere else.

## Postman

Import `postman/OpenFGA-ReBAC-New-Architecture.postman_collection.json`.
Default `baseUrl` is `http://127.0.0.1:8002`. No authentication headers.

Folders: `01 Health`, `02 Clients`, `03 Projects`, `04 Zones`,
`05 Structures`, `06 Authorization`, `07 Tree`, `08 Demo Scenarios`,
`09 Security Tests`. The last two assume `scripts/seed_demo.py` has already
been run. Collection variables: `baseUrl`, `clientId`, `projectId`,
`zoneId`, `nestedZoneId`, `structureId`, `userId`.

Regenerate with `python scripts/_build_postman.py` if the collection needs
updating (it's a plain generator script, not part of the running app).

## Security model

- **Fail closed.** Any OpenFGA error or timeout raises
  `AuthorizationServiceUnavailableError` (`app/authorization/exceptions.py`),
  mapped to HTTP `503` everywhere it can occur. `check()` never returns
  `True` as a side effect of a failure, and no code path anywhere falls
  back to "allow" when OpenFGA is unreachable. Verified against a
  genuinely stopped OpenFGA container and against a real network timeout
  (an unroutable test address), not just a mocked exception.
- **Anti-enumeration.** `GET /clients/{id}/tree` returns an identical `404`
  (same status, same detail shape) whether the client doesn't exist or the
  user simply has no visibility into it anywhere in its tree — verified
  directly in tests. Other endpoints (`GET /clients/{id}`, `/projects/{id}`,
  `/structures/{id}`) are plain resource lookups with **no user-scoped
  visibility check** (see [Known limitations](#known-limitations)) and
  return a plain `404` for a missing id.
- **No SQL-based authorization.** Nothing in `app/services/*` or `app/api/*`
  queries Postgres to make an access decision. The only SQL touched by
  authorization-adjacent code is read-only existence checks (does this
  client/project/structure row exist?) needed to validate that a Zone's or
  grant's target actually exists — never to decide who can see it.
- **Downward-only inheritance, no cross-branch, no cross-client** — see
  [Architecture](#architecture) and the tests in
  `test_full_scenarios.py`/`test_tree_api.py`/`test_authorization_api.py`.
- **No JWT/authentication** anywhere (deliberate, see above).
- **No secrets in logs.** Audit metadata is restricted to small,
  non-sensitive fields (a permission name, a reason code); `.env` (with
  real credentials) is gitignored, only `.env.example` is committed.

## Audit logging

`app/services/audit_service.py` appends to `audit_events` (id, event_type,
actor, resource_type, resource_id, action, result, metadata, created_at).
Recorded today: `client.created`, `project.created`,
`zone.relationship.created`, `structure.created`,
`authorization.grant.created`, `authorization.grant.deleted`, and
`tree.access` (`success`/`denied`, with an internal-only `reason` —
`not_found` vs `unauthorized` — that is **never** exposed to the API
caller, preserving anti-enumeration at the response layer while still
giving operators a real audit trail). A create's business row and its
audit row are written in the same DB transaction, so a rollback (e.g. a
duplicate-id conflict) never leaves an orphaned audit event — verified
directly in tests.

Not implemented: a dedicated audit event for every single
`/authorization/check` call (would be one row per permission check,
overwhelming for a PoC) or for OpenFGA engine failures specifically (those
are logged via the application logger — see `AuthorizationService._handle_error`
— rather than written to the DB, since writing to Postgres in the middle of
handling an OpenFGA outage adds a second failure mode for little benefit).

## Backups and disaster recovery

This PoC does not implement backup/restore tooling. For a production
deployment built on this architecture:

- **Application PostgreSQL** is a standard Postgres instance — use your
  usual backup strategy (`pg_dump`/`pg_basebackup`, managed-service
  snapshots, PITR via WAL archiving). It contains only business data;
  losing it loses names and audit history, not the authorization model.
- **OpenFGA's PostgreSQL** is equally a standard Postgres instance and
  needs the same treatment — it is the source of truth for every
  relationship tuple and the authorization model itself. Losing it without
  a backup means the entire hierarchy and every grant would need to be
  rebuilt (e.g. by replaying `scripts/seed_demo.py`-style provisioning
  calls from an external system of record, if one exists).
- The two datastores are **independent** and not transactionally
  consistent with each other (see [Known limitations](#known-limitations)),
  so a restore of one without a coordinated restore of the other can leave
  orphaned business rows (no OpenFGA parent) or orphaned tuples (no
  business row) — the compensating-delete logic in
  `structure_service.py`/`project_service.py` only handles a failure
  *during* the original write, not a later restore-time skew.
- OpenFGA's authorization model is versioned and immutable once written
  (`scripts/bootstrap_openfga.py` always creates a new model version); keep
  that script (and `FGA_MODEL_ID` history) under version control so a
  disaster recovery rebuild can reproduce the exact model that was live.

## Production considerations

Documented here rather than implemented, consistent with this being a PoC:

- **Connection pooling**: SQLAlchemy's default pool is used as-is; tune
  `pool_size`/`max_overflow` in `app/db/database.py` for real load.
- **Timeouts/retries**: the OpenFGA client has a 3s timeout and 2 bounded
  retries (`app/authorization/client.py`); tune per your latency budget.
- **Idempotent writes**: zone creation and authorization grants/revokes are
  idempotent by design (see [API reference](#api-reference)); client,
  project, and structure creation are **not** (a duplicate id is a `409`,
  since silently accepting a different `name` for an existing id would be
  surprising).
- **Model versioning**: OpenFGA authorization models are immutable and
  versioned; `FGA_MODEL_ID` pins the app to one version. A model change
  requires writing a new version and updating `.env` — there is no
  automated migration/rollout strategy here.
- **Dual-write consistency**: see [Known limitations](#known-limitations) —
  there is no distributed transaction between the application DB and
  OpenFGA.
- **Observability**: structured stdout logging only; no metrics/tracing
  wired up.
- **Secrets**: `.env` holds plaintext credentials for local/dev use; a
  real deployment should source these from a secrets manager, not a file.

## Known limitations

- **No Project CRUD API was present through Step 10.** It was added in
  Step 11 (`POST/GET /projects`, `GET /projects/{id}` —
  `app/api/projects.py`, `app/services/project_service.py`) specifically
  because `scripts/seed_demo.py` needed a real way to create the
  Client → Project relationship rather than writing that one OpenFGA tuple
  directly, as Steps 8–10's tests had been doing as a stand-in. This is a
  deliberate, documented scope addition for this step, following the same
  pattern already established for Structure (business row + compensating
  OpenFGA write on failure) — not a silent architecture change.
- **No dual-write transaction** between the application DB and OpenFGA.
  Project/Structure creation commits the DB row first, then writes the
  OpenFGA tuple; if that second write fails, the code compensates by
  deleting the DB row it just committed (see `structure_service.py`,
  `project_service.py`) rather than leaving an orphan — but this is
  best-effort, not a two-phase commit, and a crash between those two steps
  (as opposed to a clean exception) could still leave one without the
  other.
- **No user-scoped visibility check on plain resource reads.** `GET
  /clients/{id}`, `/projects/{id}`, `/structures/{id}`, and the `list`
  endpoints do not take a `user` parameter and are not access-controlled
  per caller — only `/authorization/check` and `/clients/{id}/tree` are
  user-aware. A real deployment would put an authentication/authorization
  layer in front of all business-data reads; that's out of scope for this
  PoC (see [Authentication is out of scope](#authentication-is-out-of-scope)).
- **No authentication anywhere** (by design — see above). Anyone who can
  reach the API can supply any `user:` identity string.
- **No per-check audit row** and **no DB-persisted "engine failure" audit
  event** — see [Audit logging](#audit-logging).
- **No backup/restore tooling implemented** — see
  [Backups and disaster recovery](#backups-and-disaster-recovery).
- **Zone has no rename/move/delete endpoint.** Once created, a zone's
  parent is immutable through this API (by design — this is also what
  makes the cycle-prevention argument in `zone_service.py` hold); there is
  no way to re-parent or delete a zone, project, or client through the API.

This project has been built step-by-step; a full architecture/security
review is recommended as the next activity before adding further features.
