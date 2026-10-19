"""文件类调用的统一闸门：路径白名单 + owner 身份判定。

``sl_call`` 与专用工具（上传群文件、发表带图说说）都从这里过一遍，避免
「专用工具忘了校验」这类口子。

闸门只在**真的会读本机文件**时生效：普通文本消息、网络图片、base64 不触发
owner 判定（否则 ``sl_call(send_group_msg)`` 这种正常发言会被误拦）。
"""

from __future__ import annotations

from typing import Any

from src.kernel.logger import get_logger

from . import auth, sandbox

logger = get_logger("snowluma_full.guard")


async def guard_file_call(
    plugin: Any,
    component: Any,
    action: str,
    params: dict,
) -> tuple[bool, str]:
    """检查一次「会把本机文件发出去」的调用。

    Returns:
        ``(是否放行, 拒绝原因)``；不涉及本机文件的调用直接放行。
    """

    if action not in sandbox.FILE_PARAMS and action not in sandbox.MESSAGE_ACTIONS:
        return True, ""

    # 消息段里的文本、http 图片、base64 不算读本机文件，不拦。
    if not sandbox.has_local_source(action, params):
        return True, ""

    config = getattr(plugin, "config", None)
    files_section = getattr(config, "files", None)
    allowed = list(getattr(files_section, "allowed_roots", None) or ["data"])

    ok, reason = sandbox.check_params(action, params, allowed)
    if not ok:
        logger.warning(f"[snowluma_full] 文件参数被拒：{action} {reason}")
        return False, reason

    access = getattr(config, "access", None)
    if not bool(getattr(access, "files_require_owner", True)):
        return True, ""

    message = auth.context_message(component)
    if message is None:
        return False, f"{action} 需要 owner 身份，但没能确认当前会话的发送者。"
    if not await auth.is_owner(plugin, message):
        logger.warning(f"[snowluma_full] 非 owner 触达文件类接口，已拒绝：{action}")
        return False, (
            f"{action} 会把本机文件发出去，只允许 owner 触发。"
            "请让主人来操作，或改用不发文件的接口。"
        )
    return True, ""


__all__ = ["guard_file_call"]
