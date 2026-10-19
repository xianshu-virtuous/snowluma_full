"""``sl_user_info``：查一个 QQ 的资料（昵称、等级、来源线索）。

给好友审批用：好友申请只有 QQ 号和留言时，先查资料再决定——
等级高、来源熟悉（同群/有备注/留言可信）就批；拿不准就先问 OW。
底层 ``get_stranger_info``（只读）。
"""

from __future__ import annotations

from typing import Annotated, Any

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

from .. import bridge, policy

logger = get_logger("snowluma_full")


def _fmt_time(value: Any) -> str:
    if not value:
        return ""
    try:
        import datetime as _dt

        return _dt.datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


def _summarize(data: dict[str, Any]) -> str:
    """把 get_stranger_info 的返回整理成给人看的几行。"""

    def pick(*keys: str) -> Any:
        for key in keys:
            value = data.get(key)
            if value not in (None, "", 0, []):
                return value
        return None

    lines: list[str] = []
    nickname = pick("nickname")
    if nickname:
        lines.append(f"昵称：{nickname}")
    qid = pick("qid")
    if qid:
        lines.append(f"账号标识：{qid}")
    remark = pick("remark")
    if remark:
        lines.append(f"备注：{remark}")
    level = pick("qq_level", "qqLevel", "level")
    if level is not None:
        lines.append(f"QQ 等级：{level}")
    sex = pick("sex")
    age = pick("age")
    if sex or age:
        lines.append(f"性别/年龄：{sex or '未知'}/{age if age is not None else '未知'}")
    signature = pick("long_nick")
    if signature:
        lines.append(f"个性签名：{str(signature)[:120]}")
    reg_time = _fmt_time(pick("reg_time"))
    if reg_time:
        lines.append(f"注册时间：{reg_time}")
    if pick("is_vip") or pick("is_years_vip"):
        lines.append(f"会员：{'年费' if pick('is_years_vip') else '超级会员'}（等级 {pick('vip_level') or '?'}）")
    return "\n".join(lines) if lines else "没有查到更多资料。"


class SlUserInfoTool(BaseTool):
    """查询一个 QQ 的资料与等级。"""

    name: str = "sl_user_info"
    description: str = (
        "查一个 QQ 号的资料：昵称、QQ 等级、备注、签名、注册时间等。"
        "好友审批前建议先查一下：等级高且来源熟悉（同群/有备注/留言可信）就可以批；"
        "拿不准就先问 OW 用户，不要自行批准或删除。"
    )

    async def execute(
        self,
        user_id: Annotated[int, "要查的 QQ 号"],
    ) -> tuple[bool, str]:
        """执行资料查询。"""

        try:
            target = int(user_id)
        except (TypeError, ValueError):
            return False, "user_id 必须是 QQ 号数字。"
        if target <= 0:
            return False, "user_id 必须是正的 QQ 号。"

        # 生效范围 + 精确屏蔽（blocked_actions）
        ok, reason = await policy.ensure_allowed(
            self.plugin, self, "get_stranger_info", is_action=False
        )
        if not ok:
            return False, reason

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            "get_stranger_info",
            {"user_id": target},
            timeout=timeout,
            debug_log=debug_log,
        )
        ok, detail = bridge.format_result(
            result, action="get_stranger_info", max_chars=1500
        )
        if not ok:
            return False, detail
        data = result.get("data")
        if not isinstance(data, dict):
            return True, f"QQ {target}：没有查到资料。"
        return True, f"QQ {target} 的资料：\n{_summarize(data)}"


__all__ = ["SlUserInfoTool"]
