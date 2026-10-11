"""FastAPI dependency providers for account deletion (DIP)."""

from functools import lru_cache

from .account_deletion_service import AccountDeletionService


@lru_cache
def get_account_deletion_service() -> AccountDeletionService:
    return AccountDeletionService()
