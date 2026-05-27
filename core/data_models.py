"""领域数据模型"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import msgspec

if TYPE_CHECKING:
    from .enums import GroupListMode


class GroupConfig(msgspec.Struct, omit_defaults=True):
    """单个群的配置数据"""

    folder_id: str | None = None
    enabled: bool | msgspec.UnsetType = msgspec.UNSET
    blacklist: set[str] = msgspec.field(default_factory=set)

    def is_enabled(self, mode: GroupListMode) -> bool:
        match (str(mode), self.enabled):
            case ("whitelist", False):
                return False
            case ("whitelist", _):
                return True
            case ("blacklist", True):
                return True
            case _:
                return False


class RestrictionConfig(msgspec.Struct, omit_defaults=True):
    """内容限制配置"""

    DEFAULT_RESTRICTED_TAGS: ClassVar[frozenset[str]] = frozenset(
        {
            "獵奇", "重口", "YAOI", "yaoi", "男同", "血腥", "猎奇", "虐杀", "恋尸癖",
        }
    )
    DEFAULT_RESTRICTED_IDS: ClassVar[frozenset[str]] = frozenset(
        {
            "136494", "323666", "350234", "363848", "405848", "454278", "481481",
            "559716", "611650", "629252", "69658", "626487", "400002", "208092",
            "253199", "382596", "418600", "279464", "565616", "222458",
        }
    )

    restricted_tags: set[str] = msgspec.field(default_factory=set)
    restricted_ids: set[str] = msgspec.field(default_factory=set)

    def ensure_defaults(self) -> bool:
        modified = False
        if not self.restricted_tags:
            self.restricted_tags = set(self.DEFAULT_RESTRICTED_TAGS)
            modified = True
        if not self.restricted_ids:
            self.restricted_ids = set(self.DEFAULT_RESTRICTED_IDS)
            modified = True
        return modified

    def is_photo_restricted(
        self,
        photo_id: str,
        photo_tags: list[str] | None = None,
    ) -> bool:
        if str(photo_id) in self.restricted_ids:
            return True
        if photo_tags:
            for tag_id in photo_tags:
                if tag_id in self.restricted_tags:
                    return True
        return False

    def find_restricted_tag(
        self,
        photo_tags: list[str] | None = None,
    ) -> str | None:
        if not photo_tags:
            return None
        for tag_id in photo_tags:
            if tag_id in self.restricted_tags:
                return tag_id
        return None


class UserData(msgspec.Struct, omit_defaults=True):
    """用户数据"""

    user_limits: dict[str, int] = msgspec.field(default_factory=dict)

    def get_limit(self, user_id: str | int, default: int = 5) -> int:
        return self.user_limits.get(str(user_id), default)

    def has_limit(self, user_id: str | int, default: int = 5) -> bool:
        return self.get_limit(user_id, default) > 0

    def decrease_limit(
        self, user_id: str | int, amount: int = 1, default: int = 5
    ) -> int:
        user_id = str(user_id)
        current = self.get_limit(user_id, default)
        new_limit = max(0, current - amount)
        self.user_limits[user_id] = new_limit
        return new_limit

    def reset_all(self, limit: int) -> int:
        count = len(self.user_limits)
        for user_id in self.user_limits:
            self.user_limits[user_id] = limit
        return count