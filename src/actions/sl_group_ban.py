"""``sl_group_ban``：禁言 / 解禁群成员。

底层 ``set_group_ban``。暴露与调用条件由 ``ManageActionBase`` 统一处理：
bot 是群主/管理员才暴露，调用者需 OW 权限。
"""

from __future__ import annotations

from typing import Annotated

from .manage_base import ManageActionBase


class SlGroupBanAction(ManageActionBase):
    """禁言或解禁一个群成员。"""

    name: str = "sl_group_ban"
    platform_action: str = "set_group_ban"
    description: str = (
        "禁言/解禁群成员。参数：user_id 必填（QQ 号），duration 是禁言秒数"
        "（默认 60，传 0 表示解除禁言）。只在 bot 是群主/管理员时可用；拿不准先问 OW 用户。"
    )

    async def execute(
        self,
        user_id: Annotated[int, "要禁言/解禁的 QQ 号"],
        duration: Annotated[int, "禁言秒数，0=解除禁言"] = 60,
    ) -> tuple[bool, str]:
        """执行禁言/解禁。"""

        ok, reason, group_id = await self._guard()
        if not ok:
            return False, reason
        try:
            target = int(user_id)
        except (TypeError, ValueError):
            return False, "user_id 必须是 QQ 号数字。"
        if target <= 0:
            return False, "user_id 必须是正的 QQ 号。"
        try:
            seconds = max(0, int(duration))
        except (TypeError, ValueError):
            seconds = 60

        params = {"group_id": int(group_id or 0), "user_id": target, "duration": seconds}
        ok, detail = await self._call(self.platform_action, params)
        if not ok:
            return False, detail
        label = "已解除禁言" if seconds == 0 else f"已禁言 {seconds} 秒"
        return True, f"{label}（群 {group_id}，用户 {target}）。{detail}"


__all__ = ["SlGroupBanAction"]
