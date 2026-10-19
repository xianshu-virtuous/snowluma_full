"""``sl_reaction``：给某条消息贴表情回应（表情回应/贴表情）。

对应 SnowLuma 的 ``set_msg_emoji_like``：``message_id`` + ``emoji_id``（QQ 表情 id，
字符串）+ 可选 ``set``（False 表示取消）。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, policy

logger = get_logger("snowluma_full")


class SlReactionAction(BaseAction):
    """给消息贴表情回应。"""

    name: str = "sl_reaction"
    description: str = (
        "给一条消息贴表情回应（QQ 的「表情回应」）。参数：message_id 是消息 id，"
        "emoji_id 是 QQ 表情 id（如 128512，字符串），set=false 表示取消回应。"
        "消息 id 一般从上下文消息行的方括号里取。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        message_id: Annotated[int, "目标消息 id（上下文消息行方括号里的数字）"],
        emoji_id: Annotated[str, "QQ 表情 id，字符串形式，如 \"128512\""],
        set: Annotated[bool, "True=贴表情（默认），False=取消"] = True,
    ) -> tuple[bool, str]:
        """执行贴表情。"""

        try:
            mid = int(message_id)
        except (TypeError, ValueError):
            return False, "message_id 必须是消息 id 数字。"
        if mid == 0:
            return False, "message_id 不能为 0。"

        emoji = str(emoji_id or "").strip()
        if not emoji:
            return False, "emoji_id 不能为空（QQ 表情 id，字符串）。"

        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "set_msg_emoji_like", is_action=True
        )
        if not ok:
            return False, reason

        params = {"message_id": mid, "emoji_id": emoji, "set": bool(set)}
        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            "set_msg_emoji_like", params, timeout=timeout, debug_log=debug_log
        )
        action_text = "已贴表情" if set else "已取消表情回应"
        ok, detail = bridge.format_result(
            result, action="set_msg_emoji_like", max_chars=max_chars
        )
        return (ok, f"{action_text}（message_id={mid}）。{detail}" if ok else detail)


__all__ = ["SlReactionAction"]
