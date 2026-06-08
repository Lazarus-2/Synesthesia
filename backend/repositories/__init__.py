"""Async repository layer over Motor collections (ID-01 / AURA).

Each repo wraps an ``AsyncIOMotorDatabase`` and centralizes the
collection-access patterns that previously lived inline in main.py. Ownership
checks (``user_id`` on the query filter) live here so callers can't forget
them.
"""

from backend.repositories.analysis_repo import AnalysisRepo
from backend.repositories.user_repo import UserRepo

__all__ = ["AnalysisRepo", "UserRepo"]
