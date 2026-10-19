"""``sl_msg_history``：读群聊 / 私聊的历史消息。

对应 SL 的 ``get_group_msg_history`` / ``get_friend_msg_history``。
整理成「时间 + 发送者 + 内容摘要 + message_id」，方便模型回溯上下文、
找被撤回/被引用的消息，或拿 message_id 去做引用/精华/撤回。
"""

from __future__ import annotations

from typing import Annotated, Any

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

from .. import bridge
from .. import policy  # execute 形参也叫 scope，这里避免同名覆盖
from ..context import group_id_from_tool

logger = get_logger("snowluma_full")


def _fmt_time(value: Any) -> str:
    if value in (None, "", 0):
        return "??:??"
    try:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(int(value)).strftime("%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


def _sender_of(message: dict[str, Any]) -> str:
    sender = message.get("sender")
    if isinstance(sender, dict):
        name = sender.get("card") or sender.get("nickname") or ""
        uid = sender.get("user_id") or ""
        if name and uid:
            return f"{name}({uid})"
        return str(name or uid or "未知")
    uid = message.get("user_id") or message.get("sender_id")
    name = message.get("sender_name") or message.get("nickname") or ""
    if name and uid:
        return f"{name}({uid})"
    return str(name or uid or "未知")


def _content_of(message: dict[str, Any]) -> str:
    for key in ("raw_message", "message", "content", "text"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.replace("\n", " ")
        if isinstance(value, list):
            parts: list[str] = []
            for seg in value:
                if not isinstance(seg, dict):
                    continue
                data = seg.get("data") or {}
                seg_type = seg.get("type")
                if seg_type == "text":
                    parts.append(str(data.get("text") or ""))
                elif seg_type == "image":
                    parts.append("[图片]")
                elif seg_type == "record":
                    parts.append("[语音]")
                elif seg_type == "video":
                    parts.append("[视频]")
                elif seg_type == "at":
                    parts.append(f"@{data.get('qq') or ''}")
                elif seg_type == "face":
                    parts.append("[表情]")
                elif seg_type == "file":
                    parts.append("[文件]")
            if parts:
                return "".join(parts).replace("\n", " ")
    return "（无文本内容）"


def _extract_messages(data: Any) -> list[dict[str, Any]]:
    """从平台返回里取出消息数组。"""

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("messages", "message_list", "list", "history"):
            raw = data.get(key)
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
    return []


class MsgHistoryTool(BaseTool):
    """读取群聊/私聊历史消息。"""

    name: str = "sl_msg_history"
    description: str = (
        "读取历史消息：scope=group 读当前群，scope=user 读与指定用户的私聊（需 user_id）。"
        "返回时间、发送者、内容摘要与 message_id。适合回溯上下文、找被撤回或被引用的消息。"
        "群聊上下文可省略 group_id（自动取当前群）。"
    )

    async def execute(
        self,
        scope: Annotated[str, "group=当前群（默认），user=指定用户的私聊"] = "group",
        user_id: Annotated[int | None, "scope=user 时的对方 QQ 号"] = None,
        count: Annotated[int, "读取条数（1~50，默认 20）"] = 20,
    ) -> tuple[bool, str]:
        """执行历史消息读取。"""

        mode = (scope or "group").strip().lower()
        if mode not in {"group", "user"}:
            return False, f"不支持的 scope：{scope}（可用 group / user）。"

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))
        size = max(1, min(50, int(count or 20)))

        if mode == "group":
            group_id = await group_id_from_tool(self)
            if not group_id:
                return False, "没能从当前会话拿到群号：scope=group 只能在群聊上下文用。"
            action = "get_group_msg_history"
            params: dict[str, Any] = {"group_id": int(group_id), "count": size}
            where = f"群 {group_id}"
        else:
            if not user_id:
                return False, "scope=user 时必须给 user_id。"
            action = "get_friend_msg_history"
            params = {"user_id": int(user_id), "count": size}
            where = f"与 {user_id} 的私聊"

        # 生效范围 + 精确屏蔽（blocked_actions）
        ok, reason = await policy.ensure_allowed(self.plugin, self, action, is_action=False)
        if not ok:
            return False, reason

        result = await bridge.call_action(action, params, timeout=timeout, debug_log=debug_log)
        ok, detail = bridge.format_result(result, action=action, max_chars=6000)
        if not ok:
            return False, detail

        messages = _extract_messages(result.get("data"))
        if not messages:
            return True, f"{where}：没有取到历史消息。"

        lines = [f"{where} · 最近 {len(messages)} 条："]
        for message in messages[-size:]:
            when = _fmt_time(message.get("time"))
            sender = _sender_of(message)
            content = _content_of(message)
            if len(content) > 70:
                content = content[:70] + "…"
            mid = message.get("message_id") or message.get("id") or ""
            mid_text = f"｜id={mid}" if mid else ""
            lines.append(f"{when} {sender}：{content}{mid_text}")
        return True, "\n".join(lines)


__all__ = ["MsgHistoryTool"]
