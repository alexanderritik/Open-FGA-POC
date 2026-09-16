# Presentation Script

Plain script to read aloud, slide by slide. Just read it as-is.

---

### Opening (before slide 1)

Good [morning/afternoon] everyone, thank you for joining.

Today I'll be walking you through our proof of concept for the Business Hierarchy Suite, built on OpenFGA using relationship-based access control, or ReBAC.

The core question we set out to answer: can we grant access at any level of a business hierarchy — client, project, zone, or structure — and have that access inherit correctly, deny correctly, and stay fully auditable.

I'll first cover the foundations, then walk through a live example end to end, and close with how this scales and what's next.

Let's get started.

---

### 1. Cover

Permissions that follow the hierarchy, not a role name. That's the whole idea, and everything after this is proof.

### 2. What we're going to cover

We'll go through this in three parts: the foundations, a live walkthrough with a real user, and then how this scales going forward.

### 3. What is ReBAC?

In a traditional role-based system, permissions attach to a role — admin, editor, viewer — and that role usually applies broadly, not to one specific resource. With ReBAC, a permission is a relationship between a user and one exact resource. A single grant at the right level in the hierarchy flows down automatically, without creating a new role for every case.

### 4. Gold Layer Database

This is our real business data — clients, projects, and structures.

### 5. Architecture

We have two stores here. Postgres holds our business data. OpenFGA holds who can see what. The application never connects to OpenFGA's internal database directly — it always goes through OpenFGA's API.

### 6. Database schema

Only one relationship here is a real foreign key — clients to projects. Everything below that — zones and structures — is a relationship that OpenFGA tracks, not something enforced by a table join.

### 7. OpenFGA = Authorization Source of Truth

OpenFGA only ever stores relationship tuples and the authorization model. No names, no personal data, nothing from our business schema. That separation is deliberate.

### 8. India Hierarchy

Here's the real hierarchy we're using for the demo — Govt of India, down to Indian Railway, into three zones, with Delhi nested under North, and bridges as the structures at the very bottom.

### 9. Security Tests

Before we grant anyone access, let's prove that denial works correctly.

### 10. John — No Access

This is a brand-new user with zero grants anywhere. We check if he can view a specific structure — denied. We check the full tree — nothing comes back. No access means no access, everywhere.

### 11. Grant: Client-Level Viewer Access

Now let's watch what happens when we grant access.

### 12. Grant — Zone North

We're granting this user viewer access at the North zone. Watch what falls inside that boundary — Delhi and its two bridges inherit access immediately. South and Western are completely untouched.

### 13. Checks After Grant

Same two checks as before, same user, only the grant has changed. The structure check now returns true. The tree check comes back pruned — showing exactly what this user is allowed to see, and nothing else.

### 14. Core APIs

These are the four calls behind everything we just saw — seeding the hierarchy, granting access, and checking it. We've also run a full suite of security tests covering cross-client and cross-branch access, which all deny correctly.

### 15. Audit & Logging

We keep two separate logs. Our own audit table answers who did what and whether it succeeded. OpenFGA's changelog answers exactly when a permission was granted or revoked. And this same OpenFGA setup can support multiple applications, each fully isolated.

### 16. Future Foreseeable Changes

This is built to handle change without rework. New data on an existing table is just a migration. A new client with the same hierarchy shape reuses the same model. A genuinely new hierarchy shape gets its own model — none of it disrupts what's already running.

### 17. Future Plans

Next, we integrate this into datalake-api-core using real production data, and after that, we introduce API versioning so this can keep evolving safely. Then we want to stress-test it at scale — runtime permission writes, multiple roles, large-scale reverse lookups, high-volume checks, and complex cross-resource relationships — so we have real numbers on latency, size, and volume, not just correctness.

### 18. Integration Pattern

This is the open decision for the room. We keep the centralized OpenFGA service as it is today. We avoid running it as a sidecar. And we want to add two things — middleware so checks happen automatically, and a shared client library so no team has to build this integration on their own.

---

### Closing

That's the full loop — deny by default, grant once at the right level, inherit correctly, and keep everything auditable. The open question for this room is the last slide — how we want services to call this going forward.
