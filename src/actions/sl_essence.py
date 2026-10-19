"""``sl_essence``：精华消息——设置 / 取消 / 查看。

对应 SnowLuma 的 ``set_essence_msg`` / ``delete_essence_msg`` /
``get_essence_msg_list``。设置与取消只需要 ``message_id``；查看需要群号，
群聊里默认当前群。
"""

from __future__ import annotations

from typing import Annotated, Literal

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, policy
from ..context import group_id_from_action

logger = get_logger("snowluma_full")

_OP_ACTION = {
    "set": "set_essence_msg",
    "unset": "delete_essence_msg",
    "list": "get_essence_msg_list",
}

_OP_LABEL = {"set": "设为精华", "unset": "取消精华", "list": "查看精华列表"}


class SlEssenceAction(BaseAction):
    """精华消息的设 / 取消 / 查看。"""

    name: str = "sl_essence"
    description: str = (
        "精华消息操作：op=set 设为精华、unset 取消精华（都需要 message_id）；"
        "op=list 查看当前群的精华列表（群聊里自动取当前群）。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        op: Annotated[Literal["set", "unset", "list"], "set=设为精华，unset=取消，list=查看列表"] = "set",
        message_id: Annotated[int | None, "消息 id；op=set/unset 时必填"] = None,
        group_id: Annotated[int | None, "群号；op=list 时可留空（默认当前群）"] = None,
    ) -> tuple[bool, str]:
        """执行精华消息操作。"""

        key = (str(op or "set")).strip().lower()
        action = _OP_ACTION.get(key)
        if action is None:
            return False, f"不支持的 op：{op}（可用 set / unset / list）。"

        params: dict[str, object] = {}
        if key in {"set", "unset"}:
            try:
                mid = int(message_id or 0)
            except (TypeError, ValueError):
                mid = 0
            if mid == 0:
                return False, f"op={key} 需要 message_id（消息 id 数字）。"
            params["message_id"] = mid
        else:
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
            if not gid:
                return False, "op=list 需要群号：本动作只能在群聊上下文用，或显式给 group_id。"
            params["group_id"] = gid

        ok, reason = await policy.ensure_allowed(
            self.plugin, self, action, is_action=True
        )
        if not ok:
            return False, reason

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            action, params, timeout=timeout, debug_log=debug_log
        )
        ok, detail = bridge.format_result(
            result, action=action, max_chars=max_chars * (2 if key == "list" else 1)
        )
        return (ok, f"已{_OP_LABEL[key]}。{detail}" if ok else detail)


__all__ = ["SlEssenceAction"]
