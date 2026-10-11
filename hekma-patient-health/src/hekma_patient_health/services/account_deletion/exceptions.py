"""Domain exceptions for permanent account deletion."""


class AccountDeletionError(Exception):
    """Base class for account deletion failures."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class AccountNotFoundError(AccountDeletionError):
    """No matching patient / auth account for the given identity."""

    def __init__(self, message: str = "Account not found."):
        super().__init__("ACCOUNT_NOT_FOUND", message)


class AccountAlreadyDeletedError(AccountDeletionError):
    """Account was already permanently deleted."""

    def __init__(self, message: str = "Account is already deleted."):
        super().__init__("ACCOUNT_ALREADY_DELETED", message)


class InvalidCredentialsError(AccountDeletionError):
    """Email/password check failed for external deletion."""

    def __init__(self, message: str = "Invalid email or password."):
        super().__init__("INVALID_CREDENTIALS", message)


class OtpError(AccountDeletionError):
    """OTP send/verify failures (rate limit, expired, mismatch)."""

    def __init__(self, code: str, message: str, retry_after: int | None = None):
        self.retry_after = retry_after
        super().__init__(code, message)


class ConfirmationRequiredError(AccountDeletionError):
    """Caller did not type the required confirmation phrase."""

    def __init__(self, message: str = 'Type "DELETE" to confirm permanent deletion.'):
        super().__init__("CONFIRMATION_REQUIRED", message)


class DeletionFailedError(AccountDeletionError):
    """Unexpected failure while purging account data."""

    def __init__(self, message: str = "Failed to delete account. Please try again."):
        super().__init__("DELETION_FAILED", message)
