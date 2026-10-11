"""Account deletion package."""

__all__ = ["AccountDeletionService", "get_account_deletion_service"]


def __getattr__(name: str):
    if name == "AccountDeletionService":
        from .account_deletion_service import AccountDeletionService

        return AccountDeletionService
    if name == "get_account_deletion_service":
        from .dependencies import get_account_deletion_service

        return get_account_deletion_service
    raise AttributeError(name)
