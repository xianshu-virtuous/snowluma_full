"""``sl_requests``：从当前聊天上下文里收集待处理的好友/加群请求。

SnowLuma 适配器会把 request 事件包装成 ``[notice]`` 消息注入聊天上下文
（``extra.is_request = True``，并带 ``flag`` 等字段），但提示词里只有文本，
拿不到 ``flag``。本工具把上下文里的请求整理出来，让模型能接着用 ``sl_call``
调用 ``set_friend_add_request`` / ``set_group_add_request`` 完成审批。

不查平台、不产生副作用，只读本地上下文。
"""

from __future__ import annotations

from typing import Annotated, Any

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

from .. import scope
from ..context import collect_messages

logger = get_logger("snowluma_full")

_KIND_LABEL = {"friend": "好友申请", "group": "加群/入群申请"}


def _request_of(message: Any) -> dict[str, Any] | None:
    """把一条消息还原成请求信息；不是请求返回 None。"""

    extra = getattr(message, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    if not extra.get("is_request") and not extra.get("flag"):
        return None
    flag = str(extra.get("flag") or "").strip()
    if not flag:
        return None
    return {
        "flag": flag,
        "kind": str(extra.get("request_type") or "").strip() or "group",
        "sub_type": str(extra.get("sub_type") or "").strip(),
        "user_id": str(extra.get("user_id") or "").strip(),
        "nickname": str(extra.get("user_nickname") or "").strip(),
        "group_id": str(extra.get("group_id") or "").strip(),
        "group_name": str(extra.get("group_name") or "").strip(),
        "comment": str(extra.get("comment") or "").strip(),
        "qq_level": extra.get("qq_level"),
        "time": getattr(message, "time", None),
    }


class SlRequestsTool(BaseTool):
    """列出上下文里待处理的好友/加群请求。"""

    name: str = "sl_requests"
    description: str = (
        "列出当前会话上下文里收到的好友申请 / 加群申请（含审批所需的 flag）。"
        "好友/加群申请都交给 bot 自己判断：先看 QQ 等级和来源，等级高、来源熟悉"
        "（同群/有备注/留言可信）就可以同意；拿不准先用 sl_user_info 查资料，"
        "仍不确定就问 OW 用户，不要自行批准或删除。"
        "审批用 sl_call 调 set_friend_add_request / set_group_add_request。"
    )

    async def execute(
        self,
        kind: Annotated[
            str,
            "筛选类型：all=全部（默认）、friend=好友申请、group=加群/入群申请",
        ] = "all",
        limit: Annotated[int, "最多返回几条（默认 5，按时间从新到旧）"] = 5,
    ) -> tuple[bool, str]:
        """执行请求列表查询。"""

        wanted = (kind or "all").strip().lower()
        if wanted not in {"all", "friend", "group"}:
            wanted = "all"

        # 生效范围：群白/黑名单与私聊开关
        ok, reason = await scope.allowed(self.plugin, self, is_action=False)
        if not ok:
            return False, reason

        seen: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for message in await collect_messages(self):
            info = _request_of(message)
            if info is None:
                continue
            if wanted != "all" and info["kind"] != wanted:
                continue
            flag = info["flag"]
            if flag not in seen:
                order.append(flag)
            seen[flag] = info

        if not seen:
            return True, (
                "当前上下文里没有待处理的好友/加群请求。"
                "（若刚收到申请，等下一轮对话上下文同步后再查）"
            )

        # 上下文是旧→新/去重后按最后一次出现排序，取最新 N 条
        flags = order[-max(1, int(limit)):]
        lines = [f"共找到 {len(seen)} 条请求，按时间从新到旧显示最近 {len(flags)} 条："]
        for index, flag in enumerate(reversed(flags), start=1):
            info = seen[flag]
            label = _KIND_LABEL.get(info["kind"], info["kind"] or "请求")
            who = info["nickname"] or "未知用户"
            if info["user_id"]:
                who += f"（{info['user_id']}）"
            level = info.get("qq_level")
            level_text = f"，QQ 等级 {level}" if level not in (None, "", 0) else ""
            where = ""
            if info["group_id"]:
                where = f"，目标群 {info['group_name'] or info['group_id']}（{info['group_id']}）"
            comment = f"，留言：{info['comment']}" if info["comment"] else "，留言：无"
            lines.append(
                f"{index}. {label}｜{who}{level_text}{where}{comment}｜flag={flag}"
            )
        lines.append(
            "好友审批：等级高、来源熟悉（同群/有备注/留言可信）→ "
            "sl_call(action=\"set_friend_add_request\", params={\"flag\": \"...\", \"approve\": true})；"
            "拿不准先 sl_user_info 查资料，仍不确定就问 OW。"
        )
        lines.append(
            "加群审批：同样由 bot 按 QQ 等级/来源判断，拿不准先问 OW。"
        )
        return True, "\n".join(lines)


__all__ = ["SlRequestsTool"]
