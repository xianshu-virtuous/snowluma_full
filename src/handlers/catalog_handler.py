"""把「SnowLuma 能力目录」写进 user prompt 末尾。

模型不会主动检索它不知道存在的东西，所以目录要直接摆在眼前；而目录本身
很便宜（4 个范围 + 工具名，约 200 字符），换掉的是 8 个工具的完整 schema。
只往 ``*_user_prompt`` 模板末尾追加，不碰 system prompt。
"""

from __future__ import annotations

from typing import Any

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BaseEventHandler
from src.app.plugin_system.types import EventType
from src.kernel.event import EventDecision

from .. import fold

logger = get_logger("snowluma_full.catalog")

#: 注入标记：模板里已经有它就别再加（不带右括号，群聊/私聊两种标题都认）。
MARK = "【SnowLuma 能力目录"

#: 目录还没加载时按这个数报（SnowLuma v11 接口总数）。
DEFAULT_TOTAL = 198


def _current_chat_type(params: dict[str, Any]) -> str:
    """从 prompt 模板的占位符值里取当前聊天流类型。

    ``default_chatter`` / ``neo_default_chatter`` 的 user prompt 模板里都有
    ``{chat_type}`` 占位符，构建时会把 ``chat_stream.chat_type`` 填进 values；
    取不到（别的 chatter、模板没这个占位符）时返回空串，目录按默认顺序输出。
    """

    values = params.get("values")
    if isinstance(values, dict):
        return fold.chat_kind(values.get("chat_type"))
    return ""


def _catalog_total(plugin: Any) -> int:
    """取目录里实际加载到的接口总数；目录未加载时退回 ``DEFAULT_TOTAL``。"""

    catalog = getattr(plugin, "catalog", None)
    total = getattr(catalog, "total", None)
    try:
        value = int(total)  # type: ignore[arg-type] - 目录属性可能是任何东西
    except (TypeError, ValueError):
        return DEFAULT_TOTAL
    return value if value > 0 else DEFAULT_TOTAL


def _danger_open(config: Any) -> bool:
    """高危接口是否已开放；配置取不到一律按关闭处理。"""

    access = getattr(config, "access", None)
    return bool(getattr(access, "allow_danger", False))


class CatalogHandler(BaseEventHandler):
    """在 user prompt 末尾内联能力目录。"""

    name: str = "catalog"
    description: str = "在 user prompt 末尾内联按范围分组的能力目录"
    weight: int = 0
    intercept_message: bool = False
    init_subscribe: list[EventType | str] = [EventType.ON_PROMPT_BUILD]

    async def execute(
        self,
        event_name: str,
        params: dict[str, Any],
    ) -> tuple[EventDecision, dict[str, Any]]:
        """处理 prompt 构建事件。"""

        try:
            config = getattr(self.plugin, "config", None)
            fold_section = getattr(config, "fold", None)
            if fold_section is None or not bool(getattr(fold_section, "enabled", True)):
                return EventDecision.SUCCESS, params
            if not bool(getattr(fold_section, "inline_catalog", True)):
                return EventDecision.SUCCESS, params

            template_name = str(params.get("name") or "")
            if not template_name.endswith("_user_prompt"):
                return EventDecision.SUCCESS, params

            template = str(params.get("template") or "")
            if MARK in template:
                return EventDecision.SUCCESS, params

            text = fold.catalog_text(
                total=_catalog_total(self.plugin),
                danger_open=_danger_open(config),
                chat_type=_current_chat_type(params),
            )
            if not text:
                return EventDecision.SUCCESS, params
            params["template"] = f"{template}\n\n{text}"
        except Exception as error:  # noqa: BLE001 - 注入失败不能影响对话
            logger.warning(f"[snowluma_full] 目录注入失败：{error}")

        return EventDecision.SUCCESS, params


__all__ = ["MARK", "CatalogHandler"]
