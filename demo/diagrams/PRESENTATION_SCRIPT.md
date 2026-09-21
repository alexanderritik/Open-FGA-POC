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

In a traditional role-based system, permissions attach to a role — admin, editor, viewer — and that role usually applies broadly, not to one specific resource. With ReBAC, a permission is a relationship between a user and one exact resource. A single grant at the right level in the hierarchy flows down automatically, without creating a new role for every case. And OpenFGA itself is our authorization source of truth here — it only ever stores relationship tuples and the model, never names, PII, or business data; that all stays in Postgres.

### 4. Gold Layer Database & Architecture

Clients, projects, and structures live in our Gold Layer database — that's our real business data. On top of that, we have two stores. Postgres holds this business data. OpenFGA holds who can see what. The application never connects to OpenFGA's internal database directly — it always goes through OpenFGA's API.

### 5. Database schema

Only one relationship here is a real foreign key — clients to projects. Everything below that — zones and structures — is a relationship that OpenFGA tracks, not something enforced by a table join.

### 6. Authentication → Authorization

Before we look at the hierarchy, here's the piece that sits in front of all of it. A caller first authenticates through Keycloak — that's SSO, and it could just as easily be Microsoft Entra ID or another identity provider depending on the client, this is just showing the pattern. That login gets us back a JWT. The app verifies that token locally against Keycloak's public keys — signature, issuer, audience, expiry. Once that's verified, the token's identity is what the app hands to OpenFGA for every authorization check from here on. This is exactly how we get "user:john" in the rest of the demo — it comes straight out of the verified token.

### 7. India Hierarchy

Here's the real hierarchy we're using for the demo — Govt of India, down to Indian Railway, into three zones, with Delhi nested under North, and bridges as the structures at the very bottom.

### 8. Security Tests — John, No Access

Before we grant anyone access, let's prove that denial works correctly. This is a brand-new user with zero grants anywhere. We check if he can view a specific structure — denied. We check the full tree — nothing comes back. No access means no access, everywhere.

### 9. Grant: Zone-Level Access to North, Verified

Now let's watch what happens when we grant access. We're granting this user viewer access at the North zone. Watch what falls inside that boundary — Delhi and its two bridges inherit access immediately, while South and Western stay completely untouched. Then, same user, we re-run the same two checks from before: the structure check now returns true, and the tree check comes back pruned — showing exactly what this user is allowed to see, and nothing else.

### 10. Every Change Traced, Every App Isolated

Every grant or revoke writes to two separate logs. Our own audit table answers who did what and whether it succeeded. OpenFGA's changelog answers exactly when a permission was granted or revoked, down to the tuple. And this same OpenFGA deployment can support multiple applications at once — each one gets its own store and its own model, fully isolated from ours.

### 11. Future Foreseeable Changes

This is built to handle change without rework — three scenarios. Scenario A: adding metadata to an existing table, like a new column, is just a migration, no OpenFGA change at all. Scenario B: a new hierarchy or client joining us — if it's the same shape, we reuse the existing model; if it's genuinely different, we design a new model and give it its own store. Scenario C: a whole new application joining us needs zero changes to OpenFGA itself — it just gets its own store and can define its own model.

### 12. Future Plans

Three things ahead: stress-testing this at scale, integrating it into datalake-api-core, and adding API version control on datalake-api-core.

---

### Closing

That's the full loop — deny by default, grant once at the right level, inherit correctly, and keep everything auditable. That's where we'd like this conversation to go next.
