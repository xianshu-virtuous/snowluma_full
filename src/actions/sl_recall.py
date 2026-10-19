"""``sl_recall``：撤回一条消息。

对应 SnowLuma 的 ``delete_msg``：只需 ``message_id``。撤回他人消息通常需要
管理员权限，平台会返回对应错误，原样回给模型即可。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, policy

logger = get_logger("snowluma_full")


class SlRecallAction(BaseAction):
    """撤回一条消息。"""

    name: str = "sl_recall"
    description: str = (
        "撤回一条消息。参数：message_id（上下文消息行方括号里的数字）。"
        "撤回他人消息一般需要管理员权限，平台不允许时会返回错误。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        message_id: Annotated[int, "要撤回的消息 id"],
    ) -> tuple[bool, str]:
        """执行撤回。"""

        try:
            mid = int(message_id)
        except (TypeError, ValueError):
            return False, "message_id 必须是消息 id 数字。"
        if mid == 0:
            return False, "message_id 不能为 0。"

        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "delete_msg", is_action=True
        )
        if not ok:
            return False, reason

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            "delete_msg", {"message_id": mid}, timeout=timeout, debug_log=debug_log
        )
        ok, detail = bridge.format_result(result, action="delete_msg", max_chars=max_chars)
        return (ok, f"已撤回（message_id={mid}）。{detail}" if ok else detail)


__all__ = ["SlRecallAction"]
