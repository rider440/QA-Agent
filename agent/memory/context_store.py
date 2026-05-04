from __future__ import annotations
 
import json
import logging
from pathlib import Path
from typing import Any
 
logger = logging.getLogger(__name__)
 
 
class ContextStore:
    """
    Simple in-memory key-value store with optional JSON persistence.
 
    Usage
    -----
    store = ContextStore()
    store.set("codebase_summary", "...")
    store.set("test_plan", plan.model_dump())
 
    summary = store.get("codebase_summary")
    """
 
    def __init__(self, persist_path: str | None = None):
        """
        Parameters
        ----------
        persist_path:
            If provided, the store is saved to this JSON file after every
            `set` call and loaded on initialisation (enables crash recovery).
        """
        self._data: dict[str, Any] = {}
        self._persist_path: Path | None = Path(persist_path) if persist_path else None
 
        if self._persist_path and self._persist_path.exists():
            self._load()
 
    # ── Private ──────────────────────────────────────────────────────────────
 
    def _save(self) -> None:
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        with self._persist_path.open("w") as fh:
            json.dump(self._data, fh, indent=2, default=str)
        logger.debug("ContextStore saved to %s", self._persist_path)
 
    def _load(self) -> None:
        with self._persist_path.open("r") as fh:  # type: ignore[arg-type]
            self._data = json.load(fh)
        logger.info("ContextStore loaded from %s (%d keys)", self._persist_path, len(self._data))
 
    # ── Public ───────────────────────────────────────────────────────────────
 
    def set(self, key: str, value: Any) -> None:
        """Store a value under `key` and persist if configured."""
        self._data[key] = value
        self._save()
 
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key; returns `default` if missing."""
        return self._data.get(key, default)
 
    def delete(self, key: str) -> None:
        """Remove a key from the store."""
        self._data.pop(key, None)
        self._save()
 
    def all(self) -> dict[str, Any]:
        """Return a shallow copy of all stored data."""
        return dict(self._data)
 
    def clear(self) -> None:
        """Wipe all data from the store."""
        self._data = {}
        self._save()
 
    def __repr__(self) -> str:
        return f"ContextStore(keys={list(self._data.keys())})"