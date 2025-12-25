from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any
import yaml

class ProfileManager:
    """Encapsulates profile storage and management logic."""
    def __init__(self, config_path: Path, test_mode: bool = False):
        self.config_path = config_path
        self.test_mode = test_mode
        self.profiles_dir = config_path.parent / "multirig.config.profiles"
        self.active_profile_path = config_path.parent / "multirig.config.active_profile"
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    def persist_active_name(self, name: str) -> None:
        """Persist the active profile name to disk.

        Args:
            name: The name of the profile to save as active.
        """
        if self.test_mode: return
        try:
            if not name:
                if self.active_profile_path.exists(): self.active_profile_path.unlink()
                return
            self.active_profile_path.write_text(name)
        except Exception: pass

    def get_active_name(self) -> str:
        """Retrieve the currently active profile name.

        Returns:
            The name of the active profile, or an empty string if none is set.
        """
        try:
            if self.active_profile_path.exists():
                return self.active_profile_path.read_text().strip()
        except Exception: pass
        return ""

    def list_names(self) -> List[str]:
        """List all available profile names.

        Returns:
            A sorted list of profile names available in storage.
        """
        if self.test_mode: return sorted(list(self._memory_store.keys()))
        if not self.profiles_dir.exists(): return []
        names = {p.stem for p in self.profiles_dir.glob("*.y*ml") if p.is_file()}
        return sorted(list(names))

    def exists(self, name: str) -> bool:
        """Check if a profile exists.

        Args:
            name: The name of the profile to check.

        Returns:
            True if the profile exists, False otherwise.
        """
        if self.test_mode: return name in self._memory_store
        return (self.profiles_dir / f"{name}.yaml").exists() or (self.profiles_dir / f"{name}.yml").exists()

    def load_data(self, name: str) -> Dict[str, Any]:
        """Load profile data by name.

        Args:
            name: The name of the profile to load.

        Returns:
            A dictionary containing the profile configuration.

        Raises:
            FileNotFoundError: If the profile does not exist.
            ValueError: If the profile data is invalid.
        """
        if self.test_mode:
            if name not in self._memory_store: raise FileNotFoundError(name)
            return self._memory_store[name]
        p1, p2 = self.profiles_dir / f"{name}.yaml", self.profiles_dir / f"{name}.yml"
        path = p1 if p1.exists() else p2
        if not path.exists(): raise FileNotFoundError(name)
        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict): raise ValueError("invalid profile")
        return raw

    def save_data(self, name: str, data: Dict[str, Any]) -> None:
        """Save configuration data to a profile.

        Args:
            name: The name of the profile.
            data: The configuration dictionary to save.
        """
        if self.test_mode:
            self._memory_store[name] = data
            return
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        (self.profiles_dir / f"{name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False))

    def delete(self, name: str) -> bool:
        """Delete a profile.

        Args:
            name: The name of the profile to delete.

        Returns:
            True if the profile was deleted, False if it was not found.
        """
        if self.test_mode:
            if name in self._memory_store:
                del self._memory_store[name]
                return True
            return False
        removed = False
        for ext in ("yaml", "yml"):
            p = self.profiles_dir / f"{name}.{ext}"
            if p.exists():
                try:
                    p.unlink()
                    removed = True
                except Exception: pass
        return removed

    def rename(self, old_name: str, new_name: str) -> None:
        if self.test_mode:
            if old_name not in self._memory_store: raise FileNotFoundError(old_name)
            if new_name in self._memory_store: raise FileExistsError(new_name)
            self._memory_store[new_name] = self._memory_store.pop(old_name)
            return
        p1, p2 = self.profiles_dir / f"{old_name}.yaml", self.profiles_dir / f"{old_name}.yml"
        src = p1 if p1.exists() else p2
        if not src.exists(): raise FileNotFoundError(old_name)
        dst = self.profiles_dir / f"{new_name}{src.suffix}"
        if dst.exists() or (self.profiles_dir / f"{new_name}.yaml").exists() or (self.profiles_dir / f"{new_name}.yml").exists():
            raise FileExistsError(new_name)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

    def is_valid_name(self, name: str) -> bool:
        if not name or len(name) > 100: return False
        return re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None
