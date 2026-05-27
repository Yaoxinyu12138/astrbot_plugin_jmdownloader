"""数据持久化管理器"""

from __future__ import annotations

from pathlib import Path

import msgspec
from boltons.fileutils import atomic_save

from ..core.data_models import GroupConfig, RestrictionConfig, UserData
from ..core.enums import GroupListMode


class DataManager:
    """插件数据管理器"""

    def __init__(
        self,
        data_dir: Path,
        default_user_limit: int,
        group_mode: GroupListMode,
    ):
        self._data_dir: Path = data_dir
        self._groups_dir: Path = data_dir / "groups"
        self._restriction_path: Path = data_dir / "restriction.json"
        self._user_path: Path = data_dir / "user.json"
        self.default_user_limit: int = default_user_limit
        self.group_mode: GroupListMode = group_mode

        data_dir.mkdir(parents=True, exist_ok=True)
        self._groups_dir.mkdir(parents=True, exist_ok=True)

        self._groups_cache: dict[str, GroupConfig] = {}

        self.restriction: RestrictionConfig = self._load(
            self._restriction_path, RestrictionConfig
        )
        self.users: UserData = self._load(self._user_path, UserData)

        if self.restriction.ensure_defaults():
            self.save_restriction()

    def _load(self, path: Path, cls: type):
        if path.exists():
            return msgspec.json.decode(path.read_bytes(), type=cls)
        return cls()

    def _save(self, path: Path, data) -> None:
        with atomic_save(str(path), text_mode=False) as f:
            f.write(msgspec.json.encode(data))

    def get_group(self, group_id: str | int) -> GroupConfig:
        group_id = str(group_id)
        if group_id not in self._groups_cache:
            path = self._groups_dir / f"{group_id}.json"
            self._groups_cache[group_id] = self._load(path, GroupConfig)
        return self._groups_cache[group_id]

    def save_group(self, group_id: str | int) -> None:
        group_id = str(group_id)
        config = self.get_group(group_id)
        path = self._groups_dir / f"{group_id}.json"
        self._save(path, config)

    def save_restriction(self) -> None:
        self._save(self._restriction_path, self.restriction)

    def save_users(self) -> None:
        self._save(self._user_path, self.users)