"""``sl_use``：按范围展开 SnowLuma 工具。

和目录注入配合：目录写进 prompt，模型要动手时用本工具展开对应范围，
**同一次回复的下一轮**这些工具就出现在工具列表里。

支持两种参数：工具名（``sl_qzone_post``）或范围名（``QQ空间``），
传范围名会一次展开整组——同一范围下的工具通常被同一次意图一起用到。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

from .. import fold

logger = get_logger("snowluma_full")

_SCOPE_HINT = "、".join(fold.SCOPE_ORDER)


class SlUseTool(BaseTool):
    """展开 SnowLuma 能力（工具或范围）。"""

    name: str = "sl_use"
    description: str = (
        "展开 SnowLuma 能力到你的工具列表。参数填工具名（如 sl_qzone_post、sl_events）"
        "或范围名（QQ空间 / 群管理 / 私信/群聊 / 通用入口），传范围名会一次展开整组。"
        "展开后下一轮即可直接调用；只展开确实要用的，展开越多越费上下文。"
    )

    async def execute(
        self,
        tools: Annotated[
            list[str],
            "要展开的工具名或范围名列表，如 [\"QQ空间\"] 或 [\"sl_qzone_post\", \"sl_msg_history\"]",
        ],
        reason: Annotated[str, "可选：为什么需要（只写进日志，便于排查）"] = "",
    ) -> tuple[bool, str]:
        """执行展开。"""

        names = [str(item).strip() for item in (tools or []) if str(item).strip()]
        if not names:
            return False, f"没有给出要展开的工具。可以填范围名（{_SCOPE_HINT}）或具体工具名。"

        try:
            stream_id = self.get_current_stream_id()
        except Exception:  # noqa: BLE001 - 拿不到流 ID 时按全局展开
            stream_id = ""

        added, already, unknown = fold.expand(stream_id, names)
        logger.info(
            f"[snowluma_full] sl_use 会话={str(stream_id)[:12] or '(空)'} "
            f"新增={len(added)} 已有={len(already)} 未知={len(unknown)}"
            + (f" 原因={str(reason)[:60]}" if reason else "")
        )
        text = fold.describe_expand(added, already, unknown)
        manage_tools = {
            "sl_group_ban",
            "sl_group_whole_ban",
            "sl_group_kick",
            "sl_group_card",
            "sl_group_name",
        }
        if manage_tools & set(added):
            text += (
                "\n（管理工具只有在 bot 自己是群主或管理员时才会真正出现在工具列表里；"
                "拿不准先问 OW 用户。）"
            )
        return True, text


__all__ = ["SlUseTool"]
