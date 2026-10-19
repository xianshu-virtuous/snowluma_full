"""``sl_group_file_list``：浏览当前群的文件（根目录 / 子目录）。

对应 SL 的 ``get_group_root_files`` / ``get_group_files_by_folder``。
输出文件名、大小、上传者、file_id 与子文件夹 id，方便接着上传、下载或
用 ``sl_call`` 做删除/重命名/移动。
"""

from __future__ import annotations

from typing import Annotated, Any

from src.core.components.base.tool import BaseTool
from src.core.components.types import ChatType
from src.kernel.logger import get_logger

from .. import bridge, policy
from ..context import group_id_from_tool

logger = get_logger("snowluma_full")


def _size_text(value: Any) -> str:
    """文件大小转可读文本。"""

    try:
        size = int(value)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return "0B"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}GB"


def _format_files(data: Any) -> tuple[list[str], int, int]:
    """整理文件/文件夹列表，返回（行文本，文件数，文件夹数）。"""

    payload = data if isinstance(data, dict) else {}
    files = payload.get("files") or []
    folders = payload.get("folders") or []
    if not isinstance(files, list):
        files = []
    if not isinstance(folders, list):
        folders = []

    lines: list[str] = []
    for folder in folders:
        if not isinstance(folder, dict):
            continue
        name = folder.get("folder_name") or folder.get("name") or "（未命名）"
        folder_id = folder.get("folder_id") or folder.get("id") or ""
        count = folder.get("total_file_count")
        count_text = f"，{count} 个文件" if count is not None else ""
        lines.append(f"📁 {name}｜folder_id={folder_id}{count_text}")

    for item in files:
        if not isinstance(item, dict):
            continue
        name = item.get("file_name") or item.get("name") or "（未命名）"
        size = _size_text(item.get("file_size") or item.get("size"))
        uploader = item.get("uploader_name") or item.get("uploader") or ""
        file_id = item.get("file_id") or item.get("id") or ""
        extra = []
        if size:
            extra.append(size)
        if uploader:
            extra.append(f"上传者 {uploader}")
        if file_id:
            extra.append(f"file_id={file_id}")
        suffix = f"（{'，'.join(extra)}）" if extra else ""
        lines.append(f"📄 {name}{suffix}")

    return lines, len(files), len(folders)


class GroupFileListTool(BaseTool):
    """浏览当前群文件。"""

    name: str = "sl_group_file_list"
    description: str = (
        "浏览当前群的文件：默认列出根目录，传 folder_id 看某个子文件夹。"
        "返回文件名、大小、上传者、file_id 与子文件夹 id；"
        "要下载用 get_group_file_url（走 sl_call），要删除/重命名/移动也用 sl_call。"
    )
    chat_type: ChatType = ChatType.GROUP

    async def execute(
        self,
        folder_id: Annotated[str, "子文件夹 id（来自列表里的 folder_id）；留空看根目录"] = "",
    ) -> tuple[bool, str]:
        """执行群文件浏览。"""

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        group_id = await group_id_from_tool(self)
        if not group_id:
            return False, "没能从当前会话拿到群号：本工具只能在群聊上下文里用。"

        folder = (folder_id or "").strip()
        if folder:
            action = "get_group_files_by_folder"
            params: dict[str, Any] = {"group_id": int(group_id), "folder_id": folder}
        else:
            action = "get_group_root_files"
            params = {"group_id": int(group_id)}

        # 生效范围 + 精确屏蔽（blocked_actions）
        ok, reason = await policy.ensure_allowed(self.plugin, self, action, is_action=False)
        if not ok:
            return False, reason

        result = await bridge.call_action(action, params, timeout=timeout, debug_log=debug_log)
        ok, detail = bridge.format_result(result, action=action, max_chars=4000)
        if not ok:
            return False, detail

        lines, file_count, folder_count = _format_files(result.get("data"))
        where = f"子目录 {folder}" if folder else "根目录"
        if not lines:
            return True, f"群 {group_id} 的{where}是空的（没有文件也没有子文件夹）。"
        header = f"群 {group_id} · {where}：{file_count} 个文件、{folder_count} 个子文件夹"
        return True, "\n".join([header, *lines[:60]])


__all__ = ["GroupFileListTool"]
