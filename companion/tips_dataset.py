"""
tips_dataset.py - Dynamic tip dataset with online fetch and local cache

Fetches a JSON tip bank from a configurable URL. Falls back to local cache if
offline or on error. Provides an API to retrieve tips per label.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List
import requests

logger = logging.getLogger(__name__)


class TipsDataset:
    """
    Manages a dynamic tip bank loaded from a remote JSON or local cache.
    
    JSON format expected:
    {
      "version": "1.0",
      "labels": {
        "low_health": [
          {"text": "...", "spoiler_level": 0, "priority": 10},
          ...
        ],
        "low_food": [...],
        ...
      }
    }
    """
    
    def __init__(
        self,
        url: str = "",
        cache_path: str = "data/tips_cache.json",
        fallback_path: str = "companion/tips_default.json",
        refresh_seconds: int = 3600,
    ) -> None:
        self.url = url
        self.cache_path = cache_path
        self.fallback_path = fallback_path
        self.refresh_seconds = refresh_seconds
        
        self.tips: Dict[str, List[Dict[str, Any]]] = {}
        self.last_fetch: float = 0.0
        
        self._load()
    
    def _load(self) -> None:
        """Try to load from cache, then fallback; optionally fetch fresh."""
        now = time.time()
        needs_refresh = (now - self.last_fetch) > self.refresh_seconds
        
        # Check if URL is a local path (no http/https scheme)
        is_local_path = self.url and not self.url.startswith(('http://', 'https://'))
        
        # If local path, load directly
        if is_local_path:
            if self._load_from_file(self.url):
                logger.info(f"Loaded tips from local path: {self.url}")
                return
        
        # Attempt online fetch if URL provided and refresh needed
        if self.url and not is_local_path and needs_refresh:
            if self._fetch_from_url():
                return
        
        # Load from cache if present
        if os.path.exists(self.cache_path):
            if self._load_from_file(self.cache_path):
                logger.info("Loaded tips from cache.")
                return
        
        # Fallback to bundled default
        if os.path.exists(self.fallback_path):
            if self._load_from_file(self.fallback_path):
                logger.info("Loaded tips from fallback default.")
                return
        
        logger.warning("No tips dataset available; using minimal stub.")
        self._stub()
    
    def _fetch_from_url(self) -> bool:
        """Fetch tips JSON from URL and cache locally."""
        try:
            logger.info(f"Fetching tips from {self.url}...")
            r = requests.get(self.url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self._parse(data)
                self._save_cache(data)
                self.last_fetch = time.time()
                logger.info(f"Fetched {len(self.tips)} label categories from URL.")
                return True
        except Exception as e:
            logger.warning(f"Failed to fetch tips from URL: {e}")
        return False
    
    def _load_from_file(self, path: str) -> bool:
        """Load tips from a local JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._parse(data)
            return True
        except Exception as e:
            logger.warning(f"Failed to load tips from {path}: {e}")
            return False
    
    def _parse(self, data: Dict[str, Any]) -> None:
        """Parse JSON structure into internal tips dict."""
        labels_block = data.get("labels", {})
        self.tips = {k: v for k, v in labels_block.items() if isinstance(v, list)}
    
    def _save_cache(self, data: Dict[str, Any]) -> None:
        """Write fetched data to cache file."""
        try:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save cache: {e}")
    
    def _stub(self) -> None:
        """Minimal fallback if all else fails."""
        self.tips = {
            "low_health": [{"text": "Your health is low—eat food or find shelter.", "spoiler_level": 0, "priority": 10}],
            "low_food": [{"text": "You're hungry—hunt animals or harvest crops.", "spoiler_level": 0, "priority": 9}],
            "exploring": [{"text": "Exploring? Mark your base coordinates.", "spoiler_level": 0, "priority": 5}],
        }
    
    def get_tips_for_label(self, label: str) -> List[Dict[str, Any]]:
        """Return all tip dicts for a given label."""
        return self.tips.get(label, [])
    
    def reload(self) -> None:
        """Force a refresh from the URL or cache."""
        self.last_fetch = 0.0
        self._load()
