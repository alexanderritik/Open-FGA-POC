class ServiceError(Exception):
    """Base class for business-service errors (application DB layer)."""


class DuplicateResourceError(ServiceError):
    """Raised when a create would violate a uniqueness constraint
    (primary key or a unique business field, e.g. a client's name)."""

    def __init__(self, resource_type: str, field: str, value: str) -> None:
        self.resource_type = resource_type
        self.field = field
        self.value = value
        super().__init__(f"{resource_type} with {field}={value!r} already exists")


class ResourceNotFoundError(ServiceError):
    """Raised when a referenced resource does not exist."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(f"{resource_type} {resource_id!r} not found")


class CircularReferenceError(ServiceError):
    """Raised when creating a resource would make it its own ancestor
    (directly or transitively) in a hierarchy."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(
            f"circular {resource_type} relationship: {resource_id!r} would become its own ancestor"
        )
