"""``sl_group_file_upload``：把本地文件/图片上传到当前群文件。

对应 SL 的 ``upload_group_file``。file 支持本地绝对路径（bot 与 SnowLuma
同机时可直接读）或 http(s) 链接；上传成功返回 file_id，之后可用
``get_group_file_url`` 取下载链接，或用 ``sl_call`` 删除/重命名/移动。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.action import BaseAction
from src.core.components.types import ChatType
from src.kernel.logger import get_logger

from .. import bridge, guard, policy
from ..context import group_id_from_action

logger = get_logger("snowluma_full")


class GroupFileUploadAction(BaseAction):
    """上传文件到当前群文件。"""

    name: str = "sl_group_file_upload"
    description: str = (
        "把文件上传到当前群文件（群共享文件区）。file 可传本地绝对路径或 http(s) 链接；"
        "可选指定显示名 name、目标子文件夹 folder_id。"
        "只在群聊上下文可用。发普通群消息附件不要用这个，用发消息能力。"
    )
    primary_action: bool = False
    chat_type: ChatType = ChatType.GROUP
    associated_types = ["text"]

    async def execute(
        self,
        file: Annotated[str, "要上传的文件：本地绝对路径或 http(s) 链接"],
        name: Annotated[str, "上传后的显示文件名（留空=用原文件名）"] = "",
        folder_id: Annotated[str, "目标子文件夹 id（留空=根目录）"] = "",
    ) -> tuple[bool, str]:
        """执行上传。"""

        path = (file or "").strip()
        if not path:
            return False, "file 不能为空：给本地绝对路径或 http(s) 链接。"

        group_id = group_id_from_action(self)
        if not group_id:
            return False, "没能从当前会话拿到群号：本动作只能在群聊上下文里用。"

        # 生效范围 + 精确屏蔽（blocked_actions）
        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "upload_group_file", is_action=True
        )
        if not ok:
            return False, reason

        params: dict[str, object] = {"group_id": int(group_id), "file": path}
        show_name = (name or "").strip()
        if show_name:
            params["name"] = show_name
        folder = (folder_id or "").strip()
        if folder:
            params["folder_id"] = folder

        # 文件参数闸门：只能读白名单目录 + 只允许 owner 触发
        ok, reason = await guard.guard_file_call(
            self.plugin, self, "upload_group_file", params
        )
        if not ok:
            return False, reason

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        # 上传可能比普通接口慢，给 1.5 倍超时
        result = await bridge.call_action(
            "upload_group_file", params, timeout=timeout * 1.5, debug_log=debug_log
        )
        ok, detail = bridge.format_result(
            result, action="upload_group_file", max_chars=max_chars
        )
        if not ok:
            return False, detail
        return True, f"已上传到群 {group_id}{'（' + folder + '）' if folder else ''}。{detail}"


__all__ = ["GroupFileUploadAction"]
