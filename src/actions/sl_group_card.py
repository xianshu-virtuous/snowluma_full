"""``sl_group_card``：修改群名片。

底层 ``set_group_card``。空字符串表示清除群名片。
"""

from __future__ import annotations

from typing import Annotated

from .manage_base import ManageActionBase


class SlGroupCardAction(ManageActionBase):
    """修改群成员的群名片。"""

    name: str = "sl_group_card"
    platform_action: str = "set_group_card"
    description: str = (
        "修改群名片。参数：user_id 必填（QQ 号），card 是新名片（空字符串=清除群名片）。"
        "只在 bot 是群主/管理员时可用；拿不准先问 OW 用户。"
    )

    async def execute(
        self,
        user_id: Annotated[int, "要改群名片的 QQ 号"],
        card: Annotated[str, "新群名片；空字符串表示清除"] = "",
    ) -> tuple[bool, str]:
        """执行改群名片。"""

        ok, reason, group_id = await self._guard()
        if not ok:
            return False, reason
        try:
            target = int(user_id)
        except (TypeError, ValueError):
            return False, "user_id 必须是 QQ 号数字。"
        if target <= 0:
            return False, "user_id 必须是正的 QQ 号。"

        params = {
            "group_id": int(group_id or 0),
            "user_id": target,
            "card": str(card or ""),
        }
        ok, detail = await self._call(self.platform_action, params)
        if not ok:
            return False, detail
        shown = str(card or "").strip() or "（已清除）"
        return True, f"已改群名片为 {shown}（群 {group_id}，用户 {target}）。{detail}"


__all__ = ["SlGroupCardAction"]
