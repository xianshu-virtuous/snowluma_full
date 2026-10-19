"""``sl_group_whole_ban``：全员禁言开关。

底层 ``set_group_whole_ban``。属于高危接口，但本动作不走 ``allow_danger``：
授权由「bot 是群主/管理员 + 调用者 OW」承担。
"""

from __future__ import annotations

from typing import Annotated

from .manage_base import ManageActionBase, _as_bool


class SlGroupWholeBanAction(ManageActionBase):
    """开启 / 关闭全员禁言。"""

    name: str = "sl_group_whole_ban"
    platform_action: str = "set_group_whole_ban"
    description: str = (
        "开启或关闭全员禁言。参数：enable=true 开启（默认），false 关闭。"
        "只在 bot 是群主/管理员时可用；拿不准先问 OW 用户。"
    )

    async def execute(
        self,
        enable: Annotated[bool, "True=开启全员禁言，False=关闭"] = True,
    ) -> tuple[bool, str]:
        """执行全员禁言开关。"""

        ok, reason, group_id = await self._guard()
        if not ok:
            return False, reason

        params = {"group_id": int(group_id or 0), "enable": _as_bool(enable)}
        ok, detail = await self._call(self.platform_action, params)
        if not ok:
            return False, detail
        label = "已开启全员禁言" if enable else "已关闭全员禁言"
        return True, f"{label}（群 {group_id}）。{detail}"


__all__ = ["SlGroupWholeBanAction"]
