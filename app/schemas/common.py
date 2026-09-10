# Shared identifier shapes for all OpenFGA-backed schemas. Identifiers
# become OpenFGA object ids (`<type>:<id>`), so they're restricted to a
# safe slug shape everywhere rather than loosened per-schema.
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,254}$"

# The fully-qualified OpenFGA user id supplied directly by the caller (no
# authentication in this PoC — see README), e.g. "user:parth".
USER_ID_PATTERN = r"^user:[a-z0-9][a-z0-9-]{0,254}$"
