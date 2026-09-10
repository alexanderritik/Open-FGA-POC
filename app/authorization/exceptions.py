class AuthorizationError(Exception):
    """Base class for all authorization-layer errors."""


class AuthorizationServiceUnavailableError(AuthorizationError):
    """Raised when OpenFGA cannot be reached or fails unexpectedly.

    Callers MUST treat this as "access denied" (fail closed) — never
    interpret its absence as "allowed". A future API layer should map this
    to HTTP 503, not to `allowed=false`, so the distinction between "denied"
    and "authorization engine unavailable" is preserved for the caller and
    for audit logging.
    """


class InvalidAuthorizationRequestError(AuthorizationError):
    """Raised for malformed input to the authorization layer (bad tuple key
    shape, empty identifiers, etc.) — a client/programming error, distinct
    from an authorization engine failure."""
