"""群管理动作的公共底座。

两条门：
1. **暴露**：``go_activate()`` 看 **bot 自己**在当前群是不是群主/管理员，
   不是就根本不把这个工具发给模型（普通群里调管理接口必被平台拒）。
2. **调用**：交给 LLM 决策——bot 身份够了就允许调用；操作是否有分寸由模型
   按上下文判断，**拿不准就先问 OW 用户**（写进工具描述与目录提醒里）。
   这里不硬卡 OW 权限，也不看 ``access.allow_danger``（授权由「bot 是管理 +
   LLM 决策」承担），``allow_danger`` 仍然只管 ``sl_call`` 通用入口。
"""

from __future__ import annotations

from typing import Any

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, policy, roles
from ..context import group_id_from_action

logger = get_logger("snowluma_full.manage")

#: 视为「有管理身份」的 bot 群角色。
_MANAGE_ROLES = frozenset({"owner", "admin", "administrator", "operator"})


def _as_bool(value: Any) -> bool:
    """把模型可能传进来的 "true"/"false" 字符串也解析成布尔。"""

    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return bool(value)


class ManageActionBase(BaseAction):
    """管理动作基类：``platform_action`` 为底层 SnowLuma 接口名。"""

    platform_action: str = ""
    primary_action: bool = False
    associated_types = ["text"]

    # ---------- 上下文 ----------

    def _group_id(self) -> str | None:
        try:
            return group_id_from_action(self)
        except Exception:  # noqa: BLE001
            return None

    def _chat_type(self) -> str:
        stream = getattr(self, "chat_stream", None)
        value = getattr(stream, "chat_type", "") if stream is not None else ""
        text = getattr(value, "value", value)
        return str(text or "").strip().lower()

    # ---------- 暴露：bot 必须是群主/管理员 ----------

    async def go_activate(self) -> bool:
        """bot 不是群主/管理员时不暴露本工具。"""

        try:
            group_id = self._group_id()
            if not group_id:
                return False
            chat_type = self._chat_type()
            if chat_type and chat_type != "group":
                return False
            access = getattr(getattr(self.plugin, "config", None), "access", None)
            blocked = {
                str(item).strip()
                for item in (getattr(access, "blocked_actions", None) or [])
                if str(item).strip()
            }
            if self.platform_action in blocked:
                return False
            role = await roles.bot_group_role(self.plugin, group_id)
            return role in _MANAGE_ROLES
        except Exception as error:  # noqa: BLE001 - 判定失败按不暴露处理
            logger.debug(f"管理动作暴露判定失败（按不暴露处理）：{error}")
            return False

    # ---------- 调用：bot 身份够了就交给 LLM 决策 ----------

    async def _guard(self) -> tuple[bool, str, str | None]:
        """返回 ``(是否放行, 拒绝原因, 群号)``。

        只做会话范围与配置屏蔽检查；具体要不要做，由模型按上下文判断，
        拿不准时应在对话里先问 OW 用户。
        """

        group_id = self._group_id()
        if not group_id:
            return False, "本功能只能在群聊里用。", None

        ok, reason = await policy.ensure_allowed(
            self.plugin,
            self,
            self.platform_action,
            is_action=True,
            check_danger=False,
        )
        if not ok:
            return False, reason, None
        return True, "", group_id

    async def _call(self, action: str, params: dict) -> tuple[bool, str]:
        """统一调用 + 结果格式化。"""

        config = getattr(self.plugin, "config", None)
        limits = getattr(config, "limits", None)
        timeout = float(getattr(limits, "timeout_seconds", 20.0))
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))
        result = await bridge.call_action(
            action, params, timeout=timeout, debug_log=debug_log
        )
        return bridge.format_result(result, action=action, max_chars=max_chars)


__all__ = ["ManageActionBase", "_as_bool"]
