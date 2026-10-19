"""``sl_group_name``：修改群名。

底层 ``set_group_name``。
"""

from __future__ import annotations

from typing import Annotated

from .manage_base import ManageActionBase


class SlGroupNameAction(ManageActionBase):
    """修改当前群的群名。"""

    name: str = "sl_group_name"
    platform_action: str = "set_group_name"
    description: str = (
        "修改当前群的群名。参数：group_name 是新群名。"
        "只在 bot 是群主/管理员时可用；拿不准先问 OW 用户。"
    )

    async def execute(
        self,
        group_name: Annotated[str, "新的群名"],
    ) -> tuple[bool, str]:
        """执行改群名。"""

        ok, reason, group_id = await self._guard()
        if not ok:
            return False, reason
        name = str(group_name or "").strip()
        if not name:
            return False, "group_name 不能为空。"

        params = {"group_id": int(group_id or 0), "group_name": name}
        ok, detail = await self._call(self.platform_action, params)
        if not ok:
            return False, detail
        return True, f"群名已改为「{name}」（群 {group_id}）。{detail}"


__all__ = ["SlGroupNameAction"]
