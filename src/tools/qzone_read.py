"""``sl_qzone_read``：读 QQ 空间——自己的说说列表或好友动态。

对应 SL 的 ``get_qzone_msg_list``（按 QQ 号读说说）与 ``get_qzone_feeds``
（好友动态）。结果整理成「时间 + 内容摘要 + tid + 点赞/评论数」，方便模型
接着用 tid 去点赞/评论（``sl_qzone_interact``）。
"""

from __future__ import annotations

from typing import Annotated, Any

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

from .. import bridge, policy

logger = get_logger("snowluma_full")


def _fmt_time(value: Any) -> str:
    """把时间戳/字符串统一成可读文本。"""

    if value in (None, "", 0):
        return "时间未知"
    try:
        import datetime as _dt

        ts = int(value)
        return _dt.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


def _summarize_msglist(items: list[dict[str, Any]]) -> str:
    """整理 ``get_qzone_msg_list`` 的说说列表。"""

    if not items:
        return "说说列表：没有取到内容。"

    lines = [f"自己的说说（{len(items)} 条）："]
    for index, item in enumerate(items, start=1):
        content = str(item.get("content") or item.get("summary") or "").strip().replace("\n", " ")
        if len(content) > 80:
            content = content[:80] + "…"
        when = _fmt_time(item.get("time") or item.get("create_time") or item.get("abstime"))
        tid = str(item.get("tid") or "").strip()
        comments = item.get("comment_num")
        images = item.get("images")
        img_count = len(images) if isinstance(images, list) else 0
        private = "（私密）" if item.get("is_private") else ""
        meta = []
        if comments is not None:
            meta.append(f"评论 {comments}")
        if img_count:
            meta.append(f"图 {img_count} 张")
        if tid:
            meta.append(f"tid={tid}")
        meta_text = f"（{'，'.join(meta)}）" if meta else ""
        lines.append(f"{index}. {when}{private} {content or '（无文字）'}{meta_text}")
    lines.append("要点赞/取消赞/评论，用上面的 tid 调 sl_qzone_interact。")
    return "\n".join(lines)


def _strip_html(raw: str) -> str:
    """把动态里的 html 片段压成纯文本摘要。"""

    import re

    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _summarize_feeds(items: list[dict[str, Any]]) -> str:
    """整理 ``get_qzone_feeds`` 的好友动态（注意：没有 tid、没有结构化正文）。"""

    if not items:
        return "好友动态：没有取到内容。"

    lines = [f"好友动态（{len(items)} 条）："]
    for index, item in enumerate(items, start=1):
        nickname = str(item.get("nickname") or "").strip() or "未知"
        uin = item.get("uin") or item.get("user_id") or ""
        who = f"{nickname}（{uin}）" if uin else nickname
        when = _fmt_time(item.get("time") or item.get("create_time"))
        summary = _strip_html(str(item.get("html") or item.get("content") or ""))
        if len(summary) > 100:
            summary = summary[:100] + "…"
        lines.append(f"{index}. {when} {who}：{summary or '（无文字内容）'}")
    lines.append(
        "注：好友动态接口只提供上述字段，没有 tid 也没有结构化正文；"
        "点赞/评论只能用自己空间说说（kind=self）里的 tid。"
    )
    return "\n".join(lines)


class QzoneReadTool(BaseTool):
    """读 QQ 空间的说说或好友动态。"""

    name: str = "sl_qzone_read"
    description: str = (
        "读 QQ 空间：kind=self 看某个 QQ 号的说说列表（默认机器人自己），"
        "kind=feeds 看好友动态。说说列表会给出 tid、评论数、配图数，"
        "可以接着用 sl_qzone_interact 点赞/评论；好友动态只有摘要与作者，没有 tid。"
    )

    async def execute(
        self,
        kind: Annotated[str, "self=读说说列表（默认），feeds=读好友动态"] = "self",
        target_uin: Annotated[
            int | None, "kind=self 时指定读哪个 QQ 的说说；留空=机器人自己"
        ] = None,
        num: Annotated[int, "读取条数（1~20，默认 5）"] = 5,
    ) -> tuple[bool, str]:
        """执行空间读取。"""

        mode = (kind or "self").strip().lower()
        if mode not in {"self", "feeds"}:
            return False, f"不支持的 kind：{kind}（可用 self / feeds）。"

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        count = max(1, min(20, int(num or 5)))

        if mode == "feeds":
            ok, reason = await policy.ensure_allowed(
                self.plugin, self, "get_qzone_feeds", is_action=False
            )
            if not ok:
                return False, reason
            result = await bridge.call_action(
                "get_qzone_feeds",
                {"page_num": 1, "count": count},
                timeout=timeout,
                debug_log=debug_log,
            )
            ok, detail = bridge.format_result(
                result, action="get_qzone_feeds", max_chars=max_chars * 4
            )
            if not ok:
                return False, detail
            data = result.get("data")
            payload = data if isinstance(data, dict) else {}
            raw = payload.get("feeds")
            items = (
                [item for item in raw if isinstance(item, dict)][:count]
                if isinstance(raw, list)
                else []
            )
            return True, _summarize_feeds(items)

        params: dict[str, Any] = {"pos": 0, "num": count}
        if target_uin:
            params["target_uin"] = int(target_uin)
        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "get_qzone_msg_list", is_action=False
        )
        if not ok:
            return False, reason
        result = await bridge.call_action(
            "get_qzone_msg_list", params, timeout=timeout, debug_log=debug_log
        )
        ok, detail = bridge.format_result(
            result, action="get_qzone_msg_list", max_chars=max_chars * 4
        )
        if not ok:
            return False, detail
        data = result.get("data")
        payload = data if isinstance(data, dict) else {}
        raw = payload.get("msglist") or payload.get("msgList") or payload.get("list") or []
        items = (
            [item for item in raw if isinstance(item, dict)]
            if isinstance(raw, list)
            else []
        )
        return True, _summarize_msglist(items[:count])


__all__ = ["QzoneReadTool"]
