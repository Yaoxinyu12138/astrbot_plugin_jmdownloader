"""AstrBot JMComic 插件

JMComic搜索、下载插件，支持全局屏蔽jm号和tag。
"""

import asyncio
import random
from pathlib import Path
from typing import Annotated

from jmcomic import JmAlbumDetail, JmPhotoDetail, MissingAlbumPhotoException

from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.message_components import Comp
from astrbot.api.star import Context, Star
from astrbot.api import logger

from .config import PluginConfig
from .infra.data_manager import DataManager
from .infra.jm_service import JMService, JMOptionContext
from .infra.search_session import SessionCache
from .core.search_session import SearchSession
from .core.enums import GroupListMode, OutputFormat


# 全局配置实例
_plugin_config: PluginConfig | None = None
_jm_service: JMService | None = None
_data_manager: DataManager | None = None
_session_cache: SessionCache | None = None


def init_services(config: AstrBotConfig):
    """初始化服务实例"""
    global _plugin_config, _jm_service, _data_manager, _session_cache

    _plugin_config = PluginConfig(
        jmcomic_log=config.get("jmcomic_log", False),
        jmcomic_proxies=config.get("jmcomic_proxies", "system"),
        jmcomic_thread_count=config.get("jmcomic_thread_count", 10),
        jmcomic_username=config.get("jmcomic_username"),
        jmcomic_password=config.get("jmcomic_password"),
        jmcomic_output_format=OutputFormat(config.get("jmcomic_output_format", "pdf")),
        jmcomic_zip_password=config.get("jmcomic_zip_password"),
        jmcomic_modify_real_md5=config.get("jmcomic_modify_real_md5", False),
        jmcomic_group_list_mode=GroupListMode(config.get("jmcomic_group_list_mode", "blacklist")),
        jmcomic_allow_private=config.get("jmcomic_allow_private", True),
        jmcomic_user_limits=config.get("jmcomic_user_limits", 5),
        jmcomic_punish_on_violation=config.get("jmcomic_punish_on_violation", True),
        jmcomic_allow_album_download=config.get("jmcomic_allow_album_download", False),
        jmcomic_results_per_page=config.get("jmcomic_results_per_page", 20),
        jmcomic_max_page_count=config.get("jmcomic_max_page_count", 150),
    )

    # 数据管理器
    data_dir = Path("data/plugins/astrbot_plugin_jmdownloader")
    data_dir.mkdir(parents=True, exist_ok=True)
    _data_manager = DataManager(
        data_dir=data_dir,
        default_user_limit=_plugin_config.jmcomic_user_limits,
        group_mode=_plugin_config.jmcomic_group_list_mode,
    )

    # JM服务
    jm_config = JMOptionContext(
        cache_dir=str(data_dir / "cache"),
        output_format=_plugin_config.jmcomic_output_format,
        zip_password=_plugin_config.jmcomic_zip_password,
        log=_plugin_config.jmcomic_log,
        proxies=_plugin_config.jmcomic_proxies,
        thread_count=_plugin_config.jmcomic_thread_count,
        username=_plugin_config.jmcomic_username,
        password=_plugin_config.jmcomic_password,
        modify_md5=_plugin_config.jmcomic_modify_real_md5,
    )
    _jm_service = JMService(jm_config, logger)

    # 搜索会话缓存
    _session_cache = SessionCache(
        default_page_size=_plugin_config.jmcomic_results_per_page,
    )

    # 预热JM客户端
    asyncio.create_task(_jm_service.warmup())


def get_jm_service() -> JMService:
    return _jm_service


def get_data_manager() -> DataManager:
    return _data_manager


def get_session_cache() -> SessionCache:
    return _session_cache


def get_plugin_config() -> PluginConfig:
    return _plugin_config


class AstrbotPluginJmdownloader(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config

        # 初始化服务
        if _plugin_config is None:
            init_services(config)

        self.jm = get_jm_service()
        self.dm = get_data_manager()
        self.sessions = get_session_cache()
        self.plugin_config = get_plugin_config()

    # region 辅助方法

    def _get_random_nickname(self) -> str:
        nicknames = getattr(self.config, "nickname", set()) or {"猫猫"}
        return random.choice(tuple(nicknames))

    async def _send_forward_msg(self, event: AstrMessageEvent, messages: list):
        """发送合并转发消息"""
        chain = []
        for msg in messages:
            if hasattr(msg, 'data') and msg.type == 'node_custom':
                # Convert MessageSegment.node_custom to Node format
                node_data = msg.data
                content = node_data.get('content', [])
                if not isinstance(content, list):
                    content = [content]
                chain.append(Comp.Node(
                    uin=int(node_data.get('uin', 0)),
                    name=node_data.get('name', 'jm搜索结果'),
                    content=content
                ))
        if chain:
            yield event.chain_result(chain)
        else:
            yield event.chain_result(messages)

    async def _build_search_result_messages(self, event: AstrMessageEvent, photo_ids: list[str], blocked_message: str):
        """构建搜索结果消息"""
        from .infra import blur_image_async

        photos = await asyncio.gather(
            *(self.jm.get_photo(photo_id) for photo_id in photo_ids),
            return_exceptions=True,
        )
        avatars = await asyncio.gather(
            *(self.jm.download_avatar(photo_id) for photo_id in photo_ids),
            return_exceptions=True,
        )

        messages = []
        nickname = self._get_random_nickname()

        for photo, avatar in zip(photos, avatars, strict=True):
            if photo is None or isinstance(photo, BaseException):
                continue

            if not self.dm.restriction.restricted_tags.isdisjoint(photo.tags or []):
                messages.append(Comp.Node(
                    uin=int(event.get_self_id() or 0),
                    name="jm搜索结果",
                    content=[Comp.Plain(blocked_message)]
                ))
            else:
                node_content = [Comp.Plain(self.jm.format_photo_info(photo))]

                if not isinstance(avatar, BaseException):
                    try:
                        blurred_avatar = await blur_image_async(avatar)
                        import io
                        avatar_bytes = blurred_avatar.getvalue() if hasattr(blurred_avatar, 'getvalue') else blurred_avatar
                        node_content.append(Comp.Image.fromFileSystem(io.BytesIO(avatar_bytes)))
                    except Exception:
                        pass

                messages.append(Comp.Node(
                    uin=int(event.get_self_id() or 0),
                    name="jm搜索结果",
                    content=node_content
                ))

        return messages

    # endregion

    # region 搜索命令

    @filter.command("jm搜索")
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def jm_search(self, event: AstrMessageEvent, message: str = ""):
        '''jm搜索 [关键词]：搜索包含关键词的本子'''
        if not message:
            yield event.plain_result("请输入要搜索的内容")
            return

        # 私聊功能开关检查
        if not self.plugin_config.jmcomic_allow_private and not event.get_group_id():
            yield event.plain_result("私聊功能已禁用")
            return

        # 群聊启用检查
        group_id = event.get_group_id()
        if group_id:
            group = self.dm.get_group(str(group_id))
            if not group.is_enabled(self.dm.group_mode):
                yield event.plain_result("当前群聊未开启该功能")
                return

        yield event.plain_result("正在搜索中...")

        try:
            page = await self.jm.search(message)
        except Exception as e:
            logger.warning(f"搜索失败: query={message}", exc_info=True)
            yield event.plain_result("搜索失败")
            return

        # 创建搜索会话
        session = self.sessions.create(
            user_id=event.get_sender_id(),
            query=message,
            results=list(page.iter_id()),
        )

        if not session.results:
            yield event.plain_result("未搜索到本子")
            return

        current_results = session.get_current_page()
        blocked_message = f"{self._get_random_nickname()}吃掉了一个不豪吃的本子"

        messages = await self._build_search_result_messages(event, current_results, blocked_message)
        yield event.chain_result(messages)

        # 前进到下一页并保存会话
        session.advance_page()
        if session.has_next_page():
            self.sessions.set(event.get_sender_id(), session)
            yield event.plain_result("搜索有更多结果，使用'jm下一页'指令查看更多")
        else:
            yield event.plain_result("已发送所有搜索结果")

    @filter.command("jm下一页")
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def jm_next_page(self, event: AstrMessageEvent):
        '''jm下一页：查看搜索结果的下一页'''
        # 私聊功能开关检查
        if not self.plugin_config.jmcomic_allow_private and not event.get_group_id():
            yield event.plain_result("私聊功能已禁用")
            return

        # 群聊启用检查
        group_id = event.get_group_id()
        if group_id:
            group = self.dm.get_group(str(group_id))
            if not group.is_enabled(self.dm.group_mode):
                yield event.plain_result("当前群聊未开启该功能")
                return

        user_id = event.get_sender_id()
        session = self.sessions.get(user_id)
        if not session:
            yield event.plain_result("没有进行中的搜索，请先使用'jm搜索'命令")
            return

        yield event.plain_result("正在搜索更多内容...")

        # 如果需要获取更多 API 数据
        if session.needs_fetch_more():
            try:
                next_page = await self.jm.search(session.query, page=session.api_page + 1)
                session.append_results(list(next_page.iter_id()))
            except Exception:
                logger.warning(f"获取搜索下一页失败", exc_info=True)

        current_results = session.get_current_page()
        blocked_message = f"{self._get_random_nickname()}吃掉了一个不豪吃的本子"

        messages = await self._build_search_result_messages(event, current_results, blocked_message)
        yield event.chain_result(messages)

        # 前进到下一页
        session.advance_page()

        # 检查是否还有更多
        if session.is_last_page():
            self.sessions.remove(user_id)
            yield event.plain_result("已显示所有搜索结果")
        else:
            yield event.plain_result("搜索有更多结果，使用'jm下一页'指令查看更多")

    # endregion

    # region 查询命令

    @filter.command("jm查询")
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def jm_query(self, event: AstrMessageEvent, photo_id: str = ""):
        '''jm查询 [jm号]：查询指定jm号的本子'''
        if not photo_id:
            yield event.plain_result("请输入要查询的jm号")
            return

        # 私聊功能开关检查
        if not self.plugin_config.jmcomic_allow_private and not event.get_group_id():
            yield event.plain_result("私聊功能已禁用")
            return

        # 群聊启用检查
        group_id = event.get_group_id()
        if group_id:
            group = self.dm.get_group(str(group_id))
            if not group.is_enabled(self.dm.group_mode):
                yield event.plain_result("当前群聊未开启该功能")
                return

        if not photo_id.isdigit():
            yield event.plain_result("请输入有效的jm号")
            return

        try:
            photo = await self.jm.get_photo(photo_id)
        except MissingAlbumPhotoException:
            yield event.plain_result("未查找到本子")
            return
        except Exception:
            logger.warning(f"获取本子信息失败: photo_id={photo_id}", exc_info=True)
            yield event.plain_result("查询时发生错误")
            return

        album = None
        if not getattr(photo, 'is_single_album', True):
            try:
                album = await self.jm.get_album_from_photo(photo)
            except Exception:
                pass

        chain = [Comp.Plain(self.jm.format_photo_info(photo, album))]

        try:
            avatar = await self.jm.download_avatar(photo.id)
            from .infra import blur_image_async
            blurred = await blur_image_async(avatar)
            import io
            chain.append(Comp.Image.fromFileSystem(io.BytesIO(blurred.getvalue())))
        except Exception:
            pass

        yield event.chain_result(chain)

    # endregion

    # region 下载命令

    @filter.command("jm下载")
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def jm_download(self, event: AstrMessageEvent, photo_id: str = ""):
        '''jm下载 [jm号]：下载指定jm号的本子'''
        if not photo_id:
            yield event.plain_result("请输入要下载的jm号")
            return

        # 私聊功能开关检查
        if not self.plugin_config.jmcomic_allow_private and not event.get_group_id():
            yield event.plain_result("私聊功能已禁用")
            return

        # 群聊启用检查
        group_id = event.get_group_id()
        if group_id:
            group = self.dm.get_group(str(group_id))
            if not group.is_enabled(self.dm.group_mode):
                yield event.plain_result("当前群聊未开启该功能")
                return
            # 黑名单检查
            if str(event.get_sender_id()) in group.blacklist:
                yield event.plain_result("你已被拉入本群黑名单，无法使用此功能")
                return

        # 下载次数检查
        if not self.dm.users.has_limit(event.get_sender_id(), self.dm.default_user_limit):
            yield event.plain_result("你的下载次数已经用完了！")
            return

        if not photo_id.isdigit():
            yield event.plain_result("请输入有效的jm号")
            return

        # 页数限制检查
        max_pages = self.plugin_config.jmcomic_max_page_count
        try:
            photo = await self.jm.get_photo(photo_id)
        except MissingAlbumPhotoException:
            yield event.plain_result("未查找到本子")
            return
        except Exception:
            logger.warning(f"获取本子信息失败: photo_id={photo_id}", exc_info=True)
            yield event.plain_result("查询时发生错误")
            return

        if max_pages > 0 and hasattr(photo, 'page_arr') and photo.page_arr:
            page_count = len(photo.page_arr)
            if page_count > max_pages:
                yield event.plain_result(f"该本子共 {page_count} 页，超过单次下载限制({max_pages}页)")
                return

        # 内容限制检查
        photo_tags = list(photo.tags or [])
        if self.dm.restriction.is_photo_restricted(photo.id, photo_tags):
            yield event.plain_result("该本子（或其tag）被禁止下载！")
            return

        # 查询剩余次数
        remaining = self.dm.users.get_limit(event.get_sender_id(), self.dm.default_user_limit)
        info = self.jm.format_photo_info(photo)
        yield event.plain_result(f"你本周还有 {remaining} 次下载次数，开始下载...\n{info}")

        # 下载
        try:
            result = await self.jm.prepare_photo_file(photo)
        except Exception:
            logger.warning(f"下载本子失败: photo_id={photo_id}", exc_info=True)
            yield event.plain_result("下载失败")
            return

        if result is None:
            yield event.plain_result("下载失败")
            return

        file_path, ext = result

        # 上传
        try:
            if group_id:
                group_config = self.dm.get_group(str(group_id))
                params = {
                    "group_id": int(group_id),
                    "file": file_path,
                    "name": f"{photo.id}{ext}",
                }
                if group_config.folder_id:
                    params["folder_id"] = group_config.folder_id
                # For AstrBot, we use file sending via context
                chain = [Comp.File(file=file_path, name=f"{photo.id}{ext}")]
                yield event.chain_result(chain)
            else:
                chain = [Comp.File(file=file_path, name=f"{photo.id}{ext}")]
                yield event.chain_result(chain)
        except Exception as e:
            logger.warning(f"发送文件失败: {e}")
            yield event.plain_result("发送文件失败")

        # 扣减额度
        self.dm.users.decrease_limit(event.get_sender_id(), 1, self.dm.default_user_limit)
        self.dm.save_users()

    # endregion

    # region 管理命令

    @filter.command("jm拉黑")
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def jm_ban_user(self, event: AstrMessageEvent):
        '''jm拉黑 [@用户]：将用户加入当前群的黑名单'''
        # 获取 at 的用户
        target_id = None
        for seg in event.message_obj.message:
            if seg.type == "at":
                target_id = seg.data.get("qq")
                if target_id and target_id != "all":
                    target_id = int(target_id)
                    break

        if not target_id:
            yield event.plain_result("请使用@指定目标用户")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令仅限群聊使用")
            return

        group_config = self.dm.get_group(str(group_id))
        group_config.blacklist.add(str(target_id))
        self.dm.save_group(str(group_id))
        yield event.plain_result(f"<at qq='{target_id}'/>已加入本群jm黑名单")

    @filter.command("jm解除拉黑")
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def jm_unban_user(self, event: AstrMessageEvent):
        '''jm解除拉黑 [@用户]：将用户移出当前群的黑名单'''
        target_id = None
        for seg in event.message_obj.message:
            if seg.type == "at":
                target_id = seg.data.get("qq")
                if target_id and target_id != "all":
                    target_id = int(target_id)
                    break

        if not target_id:
            yield event.plain_result("请使用@指定目标用户")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令仅限群聊使用")
            return

        group_config = self.dm.get_group(str(group_id))
        group_config.blacklist.discard(str(target_id))
        self.dm.save_group(str(group_id))
        yield event.plain_result(f"<at qq='{target_id}'/>已移出本群jm黑名单")

    @filter.command("jm黑名单")
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def jm_blacklist(self, event: AstrMessageEvent):
        '''jm黑名单：列出当前群的黑名单列表'''
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令仅限群聊使用")
            return

        group_config = self.dm.get_group(str(group_id))
        if not group_config.blacklist:
            yield event.plain_result("当前群的jm黑名单列表为空")
            return

        msg = "当前群的jm黑名单列表：\n"
        for user_id in group_config.blacklist:
            msg += f"<at qq='{user_id}'/>"

        yield event.plain_result(msg)

    # endregion

    # region 群控制命令

    @filter.command("jm设置文件夹")
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def jm_set_folder(self, event: AstrMessageEvent, folder_name: str = ""):
        '''jm设置文件夹 [文件夹名]：设置本群的本子储存文件夹'''
        if not folder_name:
            yield event.plain_result("请输入要设置的文件夹名称")
            return

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令仅限群聊使用")
            return

        group_config = self.dm.get_group(str(group_id))
        # 在 AstrBot 中通过 platform 获取客户端
        try:
            from astrbot.api.platform import AiocqhttpAdapter
            platform = self.context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
            if platform:
                client = platform.get_client()
                # 尝试获取文件夹
                root_data = await client.api.call_action('get_group_root_files', group_id=group_id)
                found_folder_id = None
                for folder_item in root_data.get("folders", []):
                    if folder_item.get("folder_name") == folder_name:
                        found_folder_id = folder_item.get("folder_id")
                        break

                if found_folder_id:
                    group_config.folder_id = found_folder_id
                    self.dm.save_group(str(group_id))
                    yield event.plain_result("已设置本子储存文件夹")
                    return
        except Exception as e:
            logger.warning(f"获取群根目录文件夹信息失败：{e}")

        yield event.plain_result("未找到该文件夹")

    @filter.command("开启jm")
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def jm_enable_here(self, event: AstrMessageEvent):
        '''开启jm：启用当前群的功能'''
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令仅限群聊使用")
            return

        group = self.dm.get_group(str(group_id))
        group.enabled = True
        self.dm.save_group(str(group_id))
        yield event.plain_result("已启用本群jm功能！")

    @filter.command("关闭jm")
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def jm_disable_here(self, event: AstrMessageEvent, confirm: str = ""):
        '''关闭jm：禁用当前群的功能'''
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此命令仅限群聊使用")
            return

        if confirm != "确认":
            yield event.plain_result("禁用后只能请求神秘存在再次开启该功能！发送'确认'关闭")
            return

        group = self.dm.get_group(str(group_id))
        group.enabled = False
        self.dm.save_group(str(group_id))
        yield event.plain_result("已禁用本群jm功能！")

    @filter.command("jm启用群")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def jm_enable_group(self, event: AstrMessageEvent, text: str = ""):
        '''jm启用群 [群号]：启用指定群的功能'''
        group_ids = [g for g in text.split() if g.isdigit()]
        if not group_ids:
            yield event.plain_result("请输入有效的群号")
            return

        for group_id_str in group_ids:
            self.dm.get_group(group_id_str).enabled = True
            self.dm.save_group(group_id_str)

        yield event.plain_result("以下群已启用jm插件功能：\n" + " ".join(group_ids))

    @filter.command("jm禁用群")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def jm_disable_group(self, event: AstrMessageEvent, text: str = ""):
        '''jm禁用群 [群号]：禁用指定群的功能'''
        group_ids = [g for g in text.split() if g.isdigit()]
        if not group_ids:
            yield event.plain_result("请输入有效的群号")
            return

        for group_id_str in group_ids:
            self.dm.get_group(group_id_str).enabled = False
            self.dm.save_group(group_id_str)

        yield event.plain_result("以下群已禁用jm插件功能：\n" + " ".join(group_ids))

    # endregion

    # region 内容过滤命令

    @filter.command("jm禁用id")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def jm_forbid_id(self, event: AstrMessageEvent, text: str = ""):
        '''jm禁用id [jm号]：禁用指定的jm号'''
        jm_ids = [t for t in text.split() if t.isdigit()]
        if not jm_ids:
            yield event.plain_result("请输入有效的jm号")
            return

        for jm_id in jm_ids:
            self.dm.restriction.restricted_ids.add(jm_id)
        self.dm.save_restriction()

        yield event.plain_result("以下jm号已加入禁止下载列表：\n" + " ".join(jm_ids))

    @filter.command("jm禁用tag")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def jm_forbid_tag(self, event: AstrMessageEvent, text: str = ""):
        '''jm禁用tag [tag]：禁用指定的tag'''
        tags = [t for t in text.split() if t]
        if not tags:
            yield event.plain_result("请输入有效的tag")
            return

        for tag in tags:
            self.dm.restriction.restricted_tags.add(tag)
        self.dm.save_restriction()

        yield event.plain_result("以下tag已加入禁止下载列表：\n" + " ".join(tags))

    # endregion

    async def terminate(self):
        '''插件卸载时调用'''
        pass