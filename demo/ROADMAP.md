# Integration roadmap: this PoC → `api-python-infinitus`

## Current state (verified, not assumed)

`api-python-infinitus` is presently an **empty scaffold**: the only file
under `app/` is `app/api/v1/structure_routes.py`, and its entire content
is the single word `placeholder`. There is no database layer, no
authorization, no services, no auth/identity integration — nothing to
build *around* yet. That changes the shape of this roadmap: it isn't
"here's how to bolt OpenFGA onto your existing structure_routes.py" — it's
"here's the pattern this PoC already validated; use it as the reference
implementation while `api-python-infinitus` gets built out."

## Recommendation: port the pattern, don't redesign it

This PoC's layering has been exercised by 103 passing tests and a working
demo across four scenarios (India/Emirates/Mexico/Argentina). Re-deriving
an authorization architecture from scratch for the new repo would be
redoing work that's already been validated here. Concretely, carry over:

| This PoC | → | `api-python-infinitus` |
|---|---|---|
| `app/authorization/service.py`, `app/authorization/model.fga` | → | Copy near-verbatim. It's a generic choke point over the OpenFGA SDK (validation, fail-closed error handling) with no PoC-specific logic in it. |
| `app/db/models/{client,project,structure,zone,audit_event}.py` | → | Starting schema. `zone.py` is a **metadata mirror only** (see its docstring) — OpenFGA stays the source of truth for hierarchy, cycle detection, and every authorization decision. |
| `app/services/*.py` | → | The create/get/list pattern: DB row committed first with a compensating rollback if the OpenFGA write then fails (`project_service.py`, `structure_service.py`), or OpenFGA-write-first with a best-effort DB mirror where OpenFGA alone is authoritative (`zone_service.py`). |
| `app/api/*.py` | → | Direct template for `api-python-infinitus/app/api/v1/{client,project,zone,structure,authorization,tree}_routes.py` — replacing the current placeholder in `structure_routes.py` and adding its siblings. |
| `docker-compose.yml`, `scripts/bootstrap_openfga.py`, `scripts/seed_demo.py` | → | Reusable as-is for standing up OpenFGA (app Postgres, OpenFGA, OpenFGA's own Postgres) in every environment the new repo runs in. |

## Phased rollout

1. **Scaffold + infra.** Bring in the DB models, `docker-compose.yml`, and
   `bootstrap_openfga.py`. Get a real store + authorization model running
   in dev before writing any route.
2. **Implement routes behind a new API version.** Fill in
   `structure_routes.py` and add the client/project/zone/authorization/tree
   routes, following this PoC's `app/api/*.py` + `app/services/*.py` split.
3. **Backfill.** If `api-python-infinitus` inherits any pre-existing data
   (from another system, or from a prior non-OpenFGA-backed version), write
   a one-off script — generalize `scripts/seed_demo.py`'s tuple-writing
   pattern — to populate OpenFGA tuples for everything that already exists
   in Postgres before enforcement turns on.
4. **Shadow mode.** Call `AuthorizationService.check(...)` and log what it
   *would* decide, without actually blocking anything yet. Compare against
   whatever access behavior exists today (if any) to catch mismatches
   before they become incidents.
5. **Enforce.** Flip authorization checks from logged-only to blocking.

## Open decisions to raise with the team

These are genuinely unresolved and shouldn't be decided unilaterally by
copying this PoC's choices:

- **Id scheme.** This PoC uses human-readable slug strings (`"north"`,
  `"indian-railway"`) as both the DB primary key and the OpenFGA object
  id. If `api-python-infinitus`'s conventions favor UUIDs instead, the
  OpenFGA object id would become `f"{type}:{uuid}"` instead — mechanically
  simple, but worth deciding explicitly rather than defaulting.
- **Does "Client" map to anything real?** This PoC's hierarchy is
  `Client → Project → Zone* → Structure`. Confirm whether `api-python-infinitus`
  actually has (or wants) a "Client" concept above Project, or whether
  Project is the real top-level entity and the Client layer should be
  dropped or renamed.
- **Identity source.** `AuthorizationService` takes a plain `user:<id>`
  string — it doesn't care where that id comes from. `api-python-infinitus`
  has no auth/identity layer yet, so this needs to be decided as part of
  building one: whichever user-id field that layer settles on (Keycloak
  subject, internal user id, etc.) is what gets passed as `user:<id>` here.
