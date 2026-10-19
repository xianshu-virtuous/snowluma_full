"""``sl_poke``：戳一戳（拍一拍）。

对应 SnowLuma 的 ``send_poke``：群聊/私聊自动路由——给 ``group_id`` 就戳群成员，
不给就用当前会话的群；私聊里直接戳对方。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, policy
from ..context import group_id_from_action

logger = get_logger("snowluma_full")


class SlPokeAction(BaseAction):
    """戳一戳群成员或私聊对方。"""

    name: str = "sl_poke"
    description: str = (
        "戳一戳（拍一拍）一个人。群聊默认戳当前群的成员，私聊直接戳对方。"
        "参数：user_id 是被戳的 QQ 号（必填），group_id 一般不用填（默认当前群）。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        user_id: Annotated[int, "被戳的 QQ 号"],
        group_id: Annotated[int | None, "群号；留空=当前群（私聊留空即私聊戳）"] = None,
    ) -> tuple[bool, str]:
        """执行戳一戳。"""

        try:
            target = int(user_id)
        except (TypeError, ValueError):
            return False, "user_id 必须是 QQ 号数字。"
        if target <= 0:
            return False, "user_id 必须是正的 QQ 号。"

        gid: int | None = None
        if group_id:
            try:
                gid = int(group_id)
            except (TypeError, ValueError):
                gid = None
        if gid is None:
            current = group_id_from_action(self)
            if current:
                try:
                    gid = int(current)
                except ValueError:
                    gid = None

        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "send_poke", is_action=True
        )
        if not ok:
            return False, reason

        params: dict[str, object] = {"user_id": target}
        if gid:
            params["group_id"] = gid

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            "send_poke", params, timeout=timeout, debug_log=debug_log
        )
        return bridge.format_result(result, action="send_poke", max_chars=max_chars)


__all__ = ["SlPokeAction"]
