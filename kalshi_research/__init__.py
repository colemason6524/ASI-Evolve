"""Lightweight market research framework for paper-trading binary markets."""

from .config import ResearchConfig
from .models import NormalizedSnapshot, WatchlistMarket

__all__ = ["ResearchConfig", "NormalizedSnapshot", "WatchlistMarket"]
