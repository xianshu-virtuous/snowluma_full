"""snowluma_full 插件入口：SnowLuma 全量接口扩展。

加载时读取随包分发的接口目录（``assets/sl_catalog.json``），向 LLM 暴露
两个组件：``sl_help``（查目录）与 ``sl_call``（调接口）。后续高频强化工具
会按需追加，但仍保持「少入口」原则。
"""

from __future__ import annotations

from src.core.components import BasePlugin, register_plugin
from src.kernel.logger import get_logger

from .config import SnowLumaFullConfig
from .src import fold, roles
from .src.actions.group_file_upload import GroupFileUploadAction
from .src.actions.qzone_interact import QzoneInteractAction
from .src.actions.qzone_post import QzonePostAction
from .src.actions.sl_call import SlCallAction
from .src.actions.sl_essence import SlEssenceAction
from .src.actions.sl_group_ban import SlGroupBanAction
from .src.actions.sl_group_card import SlGroupCardAction
from .src.actions.sl_group_kick import SlGroupKickAction
from .src.actions.sl_group_name import SlGroupNameAction
from .src.actions.sl_group_whole_ban import SlGroupWholeBanAction
from .src.actions.sl_poke import SlPokeAction
from .src.actions.sl_reaction import SlReactionAction
from .src.actions.sl_recall import SlRecallAction
from .src.catalog import Catalog, load_catalog
from .src.handlers.catalog_handler import CatalogHandler
from .src.handlers.fold_handler import FoldHandler
from .src.tools.group_file_list import GroupFileListTool
from .src.tools.msg_history import MsgHistoryTool
from .src.tools.qzone_read import QzoneReadTool
from .src.tools.sl_events import SlEventsTool
from .src.tools.sl_help import SlHelpTool
from .src.tools.sl_requests import SlRequestsTool
from .src.tools.sl_use import SlUseTool
from .src.tools.sl_user_info import SlUserInfoTool

logger = get_logger("snowluma_full")


@register_plugin
class SnowLumaFullPlugin(BasePlugin):
    """SnowLuma 全量接口扩展。"""

    plugin_name: str = "snowluma_full"
    plugin_description: str = (
        "把 SnowLuma 暴露的 OneBot v11 接口收进一个插件：一个目录检索 + 一个通用调用入口，"
        "覆盖好友请求、删除好友、QQ 空间、群文件、群相册、系统表情等；"
        "高危接口默认关闭，避免撑爆上下文"
    )
    plugin_version: str = "0.3.0"
    configs: list[type] = [SnowLumaFullConfig]

    def __init__(self, config=None) -> None:  # noqa: ANN001 - 与基类签名一致
        super().__init__(config)
        # 目录在 on_plugin_loaded 里加载；组件先拿到 None 也能安全降级
        self.catalog: Catalog | None = None

    def get_components(self) -> list[type]:
        """返回本插件提供的组件。"""

        config = self.config
        if isinstance(config, SnowLumaFullConfig) and not config.plugin.enabled:
            return []
        return [
            SlHelpTool,
            SlUseTool,
            SlRequestsTool,
            SlEventsTool,
            QzoneReadTool,
            GroupFileListTool,
            MsgHistoryTool,
            SlUserInfoTool,
            SlCallAction,
            QzonePostAction,
            QzoneInteractAction,
            GroupFileUploadAction,
            SlPokeAction,
            SlReactionAction,
            SlRecallAction,
            SlEssenceAction,
            SlGroupBanAction,
            SlGroupWholeBanAction,
            SlGroupKickAction,
            SlGroupCardAction,
            SlGroupNameAction,
            CatalogHandler,
            FoldHandler,
        ]

    async def on_plugin_loaded(self) -> None:
        """加载接口目录并打印统计。"""

        config = self.config
        if not isinstance(config, SnowLumaFullConfig):
            logger.error("snowluma_full：配置加载失败，插件不生效")
            return
        if not config.plugin.enabled:
            logger.info("snowluma_full：配置中已禁用，跳过初始化")
            return

        try:
            self.catalog = load_catalog()
        except Exception as exc:  # noqa: BLE001 - 目录缺失时插件仍可加载，只是不可用
            logger.error(f"snowluma_full：接口目录加载失败：{exc}")
            return

        risks = self.catalog.risk_counts()
        cats = self.catalog.categories()
        version = self.catalog.meta.get("sl_version", "?")
        logger.info(
            f"snowluma_full：接口目录已加载｜SnowLuma v{version}｜共 {self.catalog.total} 个"
            f"（只读 {risks.get('read', 0)} / 常规 {risks.get('write', 0)} / 高危 {risks.get('danger', 0)}）"
            f"｜分类 {len(cats)} 个"
            f"｜高危接口：{'开' if config.access.allow_danger else '关'}"
        )

    async def on_plugin_unloaded(self) -> None:
        """卸载时释放目录引用，并清空折叠/角色缓存。"""

        self.catalog = None
        # 展开状态与角色缓存都是模块级全局：不清的话重新加载后旧会话的展开会漏进来
        fold.reset()
        roles.reset()


__all__ = ["SnowLumaFullPlugin"]
