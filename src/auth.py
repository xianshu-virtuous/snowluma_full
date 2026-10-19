"""调用者判定：文件类 / 敏感接口只允许 owner 触发。

两道保险：
1. 配置里显式列出的 ``access.owner_uids``（平台 QQ 号）；
2. 框架自己的权限系统 ``permission_api.get_user_permission_level``
   （``PermissionLevel.OWNER`` 及以上）。
"""

from __future__ import annotations

from typing import Any

from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("snowluma_full.auth")


def sender_platform_id(message: Any) -> str:
    """从消息里取发送者的平台 ID（QQ 号）；拿不到返回空串。"""

    extra = getattr(message, "extra", None)
    if isinstance(extra, dict):
        for key in ("user_id", "sender_id", "sender_uin", "author_id"):
            value = extra.get(key)
            if value not in (None, "", 0, "0"):
                return str(value)
    return str(getattr(message, "sender_id", "") or "")


def context_message(component: Any) -> Any | None:
    """Action 场景：取本次调用的上下文消息。"""

    try:
        message = component._get_context_message_for_target()  # type: ignore[attr-defined]
        if message is not None:
            return message
    except Exception:  # noqa: BLE001 - 部分组件没有该方法
        pass

    stream = getattr(component, "chat_stream", None)
    context = getattr(stream, "context", None) if stream is not None else None
    if context is None:
        return None
    current = getattr(context, "current_message", None)
    if current is not None:
        return current
    for bucket in ("unread_messages", "history_messages", "message_cache"):
        items = getattr(context, bucket, None) or []
        try:
            for item in reversed(list(items)):
                return item
        except TypeError:
            continue
    return None


async def is_owner(plugin: Any, message: Any) -> bool:
    """判断消息发送者是不是 owner。"""

    user_id = sender_platform_id(message)
    if not user_id:
        return False

    config = getattr(plugin, "config", None)
    access = getattr(config, "access", None)
    whitelist = {
        str(item).strip()
        for item in (getattr(access, "owner_uids", None) or [])
        if str(item).strip()
    }
    if user_id in whitelist:
        return True

    # 框架权限系统兜底：owner 级别（4）及以上
    try:
        from src.app.plugin_system.api import permission_api
        from src.core.components.types import PermissionLevel

        person_id = permission_api.generate_person_id(platform="qq", user_id=user_id)
        level = await permission_api.get_user_permission_level(person_id)
        return level >= PermissionLevel.OWNER
    except Exception as error:  # noqa: BLE001 - 权限系统不可用时按非 owner 处理
        logger.debug(f"权限等级查询失败（按非 owner 处理）：{error}")
        return False


__all__ = ["context_message", "is_owner", "sender_platform_id"]
