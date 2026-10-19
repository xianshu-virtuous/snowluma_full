"""从组件上下文里取当前群号 / 当前会话信息。

SnowLuma 适配器把群信息放在消息的 ``extra`` 里（``group_id`` /
``target_group_id``），Action 能直接拿到 ``chat_stream``，Tool 只能拿到
``trigger_message`` 与 ``stream_id``，所以这里两套入口。

思路参考 ``snowluma_extension`` 的上下文回溯做法，按本插件需要独立实现。
"""

from __future__ import annotations

from typing import Any

from src.app.plugin_system.api import stream_api
from src.kernel.logger import get_logger

logger = get_logger("snowluma_full")


def _group_id_of(message: Any) -> str | None:
    """从一条消息的 extra 里取群号。"""

    extra = getattr(message, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    value = extra.get("group_id") or extra.get("target_group_id")
    if value in (None, "", 0, "0"):
        return None
    return str(value)


def group_id_from_action(action: Any) -> str | None:
    """Action 场景：从聊天流上下文取当前群号。"""

    stream = getattr(action, "chat_stream", None)
    context = getattr(stream, "context", None) if stream is not None else None
    if context is not None:
        candidates: list[Any] = []
        try:
            for bucket in ("unread_messages", "history_messages", "message_cache"):
                items = getattr(context, bucket, None) or []
                try:
                    candidates.extend(list(items))
                except TypeError:
                    continue
            current = getattr(context, "current_message", None)
            if current is not None:
                candidates.append(current)
        except Exception as exc:  # noqa: BLE001 - 上下文异常时降级
            logger.debug(f"读取 Action 上下文失败：{exc}")
            candidates = []

        for message in reversed(candidates):
            gid = _group_id_of(message)
            if gid:
                return gid

    # 兜底：Action 的目标消息辅助方法（部分版本提供）
    try:
        message = action._get_context_message_for_target()  # type: ignore[attr-defined]
        gid = _group_id_of(message)
        if gid:
            return gid
    except Exception:  # noqa: BLE001
        pass
    return None


async def group_id_from_tool(tool: Any) -> str | None:
    """Tool 场景：从触发消息或当前流上下文取群号。"""

    message = getattr(tool, "trigger_message", None)
    gid = _group_id_of(message)
    if gid:
        return gid

    stream_id = ""
    try:
        stream_id = tool.get_current_stream_id()
    except Exception:  # noqa: BLE001
        stream_id = ""
    if not stream_id:
        return None

    try:
        stream = await stream_api.get_stream(stream_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"读取 Tool 上下文失败：{exc}")
        return None
    context = getattr(stream, "context", None) if stream is not None else None
    if context is None:
        return None

    candidates: list[Any] = []
    for bucket in ("unread_messages", "history_messages", "message_cache"):
        items = getattr(context, bucket, None) or []
        try:
            candidates.extend(list(items))
        except TypeError:
            continue
    current = getattr(context, "current_message", None)
    if current is not None:
        candidates.append(current)

    for item in reversed(candidates):
        gid = _group_id_of(item)
        if gid:
            return gid
    return None


async def collect_messages(tool: Any) -> list[Any]:
    """收集 Tool 可见的上下文消息（触发消息 + 当前流上下文）。"""

    messages: list[Any] = []
    trigger = getattr(tool, "trigger_message", None)
    if trigger is not None:
        messages.append(trigger)

    stream_id = ""
    try:
        stream_id = tool.get_current_stream_id()
    except Exception:  # noqa: BLE001 - 上下文不可用时静默降级
        stream_id = ""
    if not stream_id:
        return messages

    try:
        stream = await stream_api.get_stream(stream_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"读取上下文流失败：{exc}")
        return messages

    context = getattr(stream, "context", None) if stream is not None else None
    if context is None:
        return messages

    for bucket in ("unread_messages", "history_messages", "message_cache"):
        items = getattr(context, bucket, None) or []
        try:
            messages.extend(list(items))
        except TypeError:
            continue
    current = getattr(context, "current_message", None)
    if current is not None:
        messages.append(current)
    return messages


__all__ = ["collect_messages", "group_id_from_action", "group_id_from_tool"]
