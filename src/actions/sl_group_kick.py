"""``sl_group_kick``：踢出群成员。

底层 ``set_group_kick``。同上：bot 是群主/管理员才暴露，调用者需 OW。
"""

from __future__ import annotations

from typing import Annotated

from .manage_base import ManageActionBase, _as_bool


class SlGroupKickAction(ManageActionBase):
    """踢出一个群成员。"""

    name: str = "sl_group_kick"
    platform_action: str = "set_group_kick"
    description: str = (
        "把群成员踢出群。参数：user_id 必填（QQ 号），reject_add_request=true 表示"
        "同时拒绝对方再次加群（默认 false）。只在 bot 是群主/管理员时可用；拿不准先问 OW 用户。"
    )

    async def execute(
        self,
        user_id: Annotated[int, "要踢出的 QQ 号"],
        reject_add_request: Annotated[bool, "是否同时拒绝对方再次加群"] = False,
    ) -> tuple[bool, str]:
        """执行踢人。"""

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
            "reject_add_request": _as_bool(reject_add_request),
        }
        ok, detail = await self._call(self.platform_action, params)
        if not ok:
            return False, detail
        return True, f"已踢出（群 {group_id}，用户 {target}）。{detail}"


__all__ = ["SlGroupKickAction"]
