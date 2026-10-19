"""``sl_events``：整理上下文里的通知事件（撤回 / 戳 / 禁言 / 上传 / 精华 / 贴表情…）。

SnowLuma 适配器把 notice 事件包装成 ``[notice]`` 消息注入聊天上下文，
``extra`` 里带 ``notice_type`` 等结构化字段；直接读提示词只能看到一行文本，
本工具把这些事件按类型整理出来，方便模型判断「刚才发生了什么」。

只读本地上下文，不查平台、不产生副作用。
"""

from __future__ import annotations

from typing import Annotated, Any

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

from .. import scope
from ..context import collect_messages

logger = get_logger("snowluma_full")

# 工具侧的筛选词 → notice_type 集合
_KIND_TYPES: dict[str, set[str]] = {
    "poke": {"poke", "friend_poke", "group_poke"},
    # 适配器实测发的是 "recall"（好友/群撤回都走它），旧实现只认 friend_recall / group_recall
    "recall": {"recall", "friend_recall", "group_recall"},
    "ban": {"group_ban", "group_lift_ban", "group_whole_ban", "group_whole_lift_ban"},
    "upload": {"group_upload"},
    "emoji": {"emoji_like", "group_msg_emoji_like"},
    "essence": {"essence"},
    "member": {"group_increase", "group_decrease", "group_admin"},
    "title": {"title"},
}

_LABEL = {
    "poke": "戳一戳",
    "recall": "撤回",
    "ban": "禁言/解禁",
    "upload": "文件上传",
    "emoji": "贴表情",
    "essence": "精华消息",
    "member": "群成员变动",
    "title": "头衔变更",
    "request": "申请",
    "other": "其它通知",
}


def _notice_of(message: Any) -> dict[str, Any] | None:
    """把消息还原成通知事件；不是通知返回 None。"""

    extra = getattr(message, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    if extra.get("is_request"):
        kind = "request"
        title = str(extra.get("request_type") or "request")
    elif extra.get("is_notice"):
        raw_type = str(extra.get("notice_type") or "other")
        kind = "other"
        for candidate, types in _KIND_TYPES.items():
            if raw_type in types:
                kind = candidate
                break
        title = raw_type
    else:
        return None

    content = str(
        getattr(message, "processed_plain_text", "")
        or getattr(message, "content", "")
        or ""
    ).strip()
    for prefix in ("[notice]", "[NOTICE]"):
        if content.startswith(prefix):
            content = content[len(prefix):].strip()

    return {
        "kind": kind,
        "title": title,
        "content": content,
        "time": getattr(message, "time", None),
        "sender": str(getattr(message, "sender_name", "") or ""),
        "message_id": str(getattr(message, "message_id", "") or ""),
    }


def _fmt_time(value: Any) -> str:
    if value in (None, "", 0):
        return "??:??"
    try:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(float(value)).strftime("%H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


class SlEventsTool(BaseTool):
    """整理上下文里的 QQ 通知事件。"""

    name: str = "sl_events"
    description: str = (
        "查看当前会话里最近发生的通知事件：撤回消息、戳一戳、禁言/解禁、群文件上传、"
        "贴表情、精华消息、群成员进出、头衔变更、好友/加群申请等。"
        "返回时间、类型和内容摘要，适合判断「刚刚发生了什么」。"
        "需要审批申请时用 sl_requests 拿 flag。"
    )

    async def execute(
        self,
        kind: Annotated[
            str,
            "筛选类型：all=全部（默认）、request=申请、poke=戳一戳、recall=撤回、"
            "ban=禁言/解禁、upload=文件上传、emoji=贴表情、essence=精华、"
            "member=群成员变动、title=头衔、other=其它",
        ] = "all",
        limit: Annotated[int, "最多返回几条（默认 8，从新到旧）"] = 8,
    ) -> tuple[bool, str]:
        """执行通知事件整理。"""

        wanted = (kind or "all").strip().lower()
        allowed = {"all", "request", "other", *_KIND_TYPES}
        if wanted not in allowed:
            wanted = "all"

        # 生效范围：群白/黑名单与私聊开关
        ok, reason = await scope.allowed(self.plugin, self, is_action=False)
        if not ok:
            return False, reason

        events: list[dict[str, Any]] = []
        for message in await collect_messages(self):
            info = _notice_of(message)
            if info is None:
                continue
            if wanted != "all" and info["kind"] != wanted:
                continue
            events.append(info)

        if not events:
            scope_text = "全部" if wanted == "all" else _LABEL.get(wanted, wanted)
            return True, f"当前上下文里没有「{scope_text}」类通知事件。"

        keep = max(1, int(limit or 8))
        events = events[-keep:]
        lines = [f"最近通知事件（{len(events)} 条，从新到旧）："]
        for index, info in enumerate(reversed(events), start=1):
            label = _LABEL.get(info["kind"], info["kind"])
            when = _fmt_time(info["time"])
            content = info["content"].replace("\n", " ")
            if len(content) > 90:
                content = content[:90] + "…"
            sender = f" {info['sender']}：" if info["sender"] else "："
            lines.append(f"{index}. [{when}] {label}{sender}{content}")
        return True, "\n".join(lines)


__all__ = ["SlEventsTool"]
