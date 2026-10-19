"""``sl_qzone_interact``：对 QQ 空间说说的轻量互动——点赞、取消赞、评论。

合并三个动作到一个入口（op 枚举），避免为每个小操作各注册一个工具；
删除说说属于高危操作，不在这里做，走 ``sl_call(delete_qzone_msg)``。
"""

from __future__ import annotations

from typing import Annotated, Literal

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, policy

logger = get_logger("snowluma_full")

_ACTION_BY_OP = {
    "like": "like_qzone",
    "unlike": "unlike_qzone",
    "comment": "comment_qzone",
}

_OP_LABEL = {"like": "点赞", "unlike": "取消赞", "comment": "评论"}


class QzoneInteractAction(BaseAction):
    """对一条 QQ 空间说说点赞 / 取消赞 / 评论。"""

    name: str = "sl_qzone_interact"
    description: str = (
        "对 QQ 空间的一条说说做互动：op=like 点赞、unlike 取消赞、comment 评论（评论需 content）。"
        "tid 从 sl_qzone_read 的结果里取。删除说说属于高危操作，不在此工具范围。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        op: Annotated[
            Literal["like", "unlike", "comment"], "操作：like=点赞，unlike=取消赞，comment=评论"
        ],
        tid: Annotated[str, "说说的 tid（来自 sl_qzone_read 的返回）"],
        content: Annotated[str, "评论内容（op=comment 时必填）"] = "",
        target_uin: Annotated[int | None, "说说所属 QQ，留空=机器人自己"] = None,
    ) -> tuple[bool, str]:
        """执行空间互动。"""

        key = (op or "").strip().lower()
        action = _ACTION_BY_OP.get(key)
        if action is None:
            return False, f"不支持的 op：{op}（可用 like / unlike / comment）。"

        tid_text = (tid or "").strip()
        if not tid_text:
            return False, "tid 不能为空，先用 sl_qzone_read 查一条说说的 tid。"

        params: dict[str, object] = {"tid": tid_text}
        if target_uin:
            params["target_uin"] = int(target_uin)
        if key == "comment":
            text = (content or "").strip()
            if not text:
                return False, "评论内容不能为空。"
            params["content"] = text

        # 生效范围 + 精确屏蔽（blocked_actions）
        ok, reason = await policy.ensure_allowed(self.plugin, self, action, is_action=True)
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
        ok, detail = bridge.format_result(result, action=action, max_chars=max_chars)
        if not ok:
            return False, detail
        return True, f"已{_OP_LABEL[key]}（tid={tid_text}）。{detail}"


__all__ = ["QzoneInteractAction"]
