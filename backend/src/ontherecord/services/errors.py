"""Domain errors. Services raise these; `main.py` maps them to HTTP status codes,
so business rules never import FastAPI."""


class DomainError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    """The row doesn't exist, is deleted, or belongs to another user (all look the same)."""


class ConflictError(DomainError):
    """The request is valid but clashes with current state."""


class InvalidInputError(DomainError):
    """Well-formed input that breaks a business rule (e.g. a check dated in the future)."""


class UnauthorizedError(DomainError):
    """Missing, invalid, expired or revoked credentials. Deliberately vague to the caller."""
