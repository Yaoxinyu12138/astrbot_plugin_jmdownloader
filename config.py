"""插件配置"""

from typing import Self

from pydantic import BaseModel, Field

from .core.enums import GroupListMode, OutputFormat


class PluginConfig(BaseModel):
    """插件配置"""

    jmcomic_log: bool = Field(default=False, description="是否启用JMComic API日志")
    jmcomic_proxies: str = Field(default="system", description="代理配置")
    jmcomic_thread_count: int = Field(default=10, description="下载线程数量")
    jmcomic_username: str | None = Field(default=None, description="JM登录用户名")
    jmcomic_password: str | None = Field(default=None, description="JM登录密码")
    jmcomic_output_format: OutputFormat = Field(
        default=OutputFormat.PDF,
        description="输出格式：pdf 或 zip",
    )
    jmcomic_zip_password: str | None = Field(
        default=None, description="ZIP 压缩包密码（仅 ZIP 格式有效）"
    )
    jmcomic_modify_real_md5: bool = Field(
        default=False, description="是否修改PDF的MD5值（仅PDF格式有效）"
    )

    jmcomic_group_list_mode: GroupListMode = Field(
        default=GroupListMode.BLACKLIST,
        description="群列表模式：blacklist（默认禁用）/ whitelist（默认启用）",
    )
    jmcomic_allow_groups: bool | None = Field(
        default=None,
        description="[废弃] 请使用 jmcomic_group_list_mode",
    )
    jmcomic_allow_private: bool = Field(default=True, description="是否允许私聊功能")
    jmcomic_user_limits: int = Field(
        default=5, description="每位用户的每周下载限制次数"
    )
    jmcomic_punish_on_violation: bool = Field(
        default=True,
        description="当用户下载违规内容时是否惩罚（禁言+拉黑）",
    )
    jmcomic_allow_album_download: bool = Field(
        default=False, description="是否允许使用本子集下载功能"
    )

    jmcomic_results_per_page: int = Field(
        default=20, description="每页显示的搜索结果数量"
    )
    jmcomic_max_page_count: int = Field(
        default=150, description="单次下载最大页数限制，0表示不限制"
    )