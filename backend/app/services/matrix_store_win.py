"""Windows-safe matrix-nio store — MXIDs contain ':' which breaks file paths."""

from __future__ import annotations

import os
from dataclasses import dataclass

from nio.store.database import DefaultStore, SqliteStore
from nio.store.file_trustdb import KeyStore


def _safe_prefix(user_id: str, device_id: str) -> str:
    safe_user = user_id.replace("@", "at_").replace(":", "_")
    return f"{safe_user}_{device_id}"


@dataclass
class WindowsSafeStore(DefaultStore):
    """DefaultStore with filesystem-safe names for Windows."""

    def __post_init__(self) -> None:
        prefix = _safe_prefix(self.user_id, self.device_id)
        self.database_name = self.database_name or f"{prefix}.db"
        SqliteStore.__post_init__(self)

        self.trust_db = KeyStore(os.path.join(self.store_path, f"{prefix}.trusted_devices"))
        self.blacklist_db = KeyStore(
            os.path.join(self.store_path, f"{prefix}.blacklisted_devices")
        )
        self.ignore_db = KeyStore(os.path.join(self.store_path, f"{prefix}.ignored_devices"))
