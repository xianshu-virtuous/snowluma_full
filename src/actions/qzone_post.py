"""``sl_qzone_post``：发表 QQ 空间说说。

SL 的 ``send_qzone_msg`` 支持纯文字或带图（images 可为本地路径 / http(s) /
base64://，平台侧会自动上传），并可按 ``ugc_right`` 控制可见范围。这里包一层
人类可读的 visibility，避免模型直接拼数字。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, guard, policy

logger = get_logger("snowluma_full")

# SL 的 ugc_right：1 所有人 / 4 好友 / 16 部分好友可见 / 64 仅自己 / 128 部分好友不可见
_VISIBILITY = {
    "public": (1, "所有人可见"),
    "friends": (4, "好友可见"),
    "private": (64, "仅自己可见"),
}


class QzonePostAction(BaseAction):
    """发表一条 QQ 空间说说。"""

    name: str = "sl_qzone_post"
    description: str = (
        "发表一条 QQ 空间说说（可以带图）。图片支持本地绝对路径、http(s) 链接或 base64://，"
        "平台侧会自动上传。可见范围默认所有人可见，也可设为好友可见或仅自己可见。"
        "只发文字、不带图时直接给 content 即可。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        content: Annotated[str, "说说正文（纯文字）"],
        images: Annotated[
            list[str] | None,
            "配图列表，可为本地绝对路径 / http(s) 链接 / base64://；不带图就不传",
        ] = None,
        visibility: Annotated[
            str,
            "可见范围：public=所有人（默认）、friends=好友、private=仅自己",
        ] = "public",
    ) -> tuple[bool, str]:
        """执行发表说说。"""

        text = (content or "").strip()
        if not text:
            return False, "说说正文不能为空。"

        key = (visibility or "public").strip().lower()
        if key not in _VISIBILITY:
            return False, f"不支持的可见范围：{visibility}（可用 public / friends / private）。"
        ugc_right, label = _VISIBILITY[key]

        params: dict[str, object] = {"content": text, "ugc_right": ugc_right}
        img_count = 0
        if images:
            cleaned = [str(item).strip() for item in images if str(item).strip()]
            if cleaned:
                params["images"] = cleaned
                img_count = len(cleaned)

        # 生效范围 + 精确屏蔽（blocked_actions）
        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "send_qzone_msg", is_action=True
        )
        if not ok:
            return False, reason

        # 配图同样会读本机文件：过路径白名单 + owner 判定
        ok, reason = await guard.guard_file_call(
            self.plugin, self, "send_qzone_msg", params
        )
        if not ok:
            return False, reason

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            "send_qzone_msg", params, timeout=timeout, debug_log=debug_log
        )
        ok, detail = bridge.format_result(result, action="send_qzone_msg", max_chars=max_chars)
        if not ok:
            return False, detail
        return True, f"说说已发表（{label}，配图 {img_count} 张）。{detail}"


__all__ = ["QzonePostAction"]
