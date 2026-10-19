"""生效范围（scope）闸门：按群白名单 / 群黑名单 / 私聊开关决定本插件能否在当前会话工作。

``config.py`` 里的 ``scope`` 配置节从一开始就写在配置模板里，但插件里没有任何
代码读它——README 宣称的「只在指定群生效」其实没落地（配置骗人）。本模块把这段
判定补上：四个平台动作（``sl_call`` / ``sl_qzone_post`` / ``sl_qzone_interact`` /
``sl_group_file_upload``）与五个工具（``sl_qzone_read`` / ``sl_group_file_list`` /
``sl_msg_history`` / ``sl_requests`` / ``sl_events``）在**参数校验通过之后、真正
调平台之前**过一遍 :func:`allowed`，命中限制就把原因直接返回给模型。

判定顺序（先拒后放）：

1. 群号命中 ``scope.group_blacklist`` → 拒；
2. 群聊且 ``scope.group_whitelist`` 非空、群号不在其中 → 拒；
3. 明确的私聊（没有群号、且 ``chat_type`` 就是 ``private``）且
   ``scope.private_enabled`` 为假 → 拒；
4. 其余（含上下文信息不足）→ 放行。

宁可漏拦也不误拦：拿不到群号、也拿不到明确 ``chat_type`` 时按「信息不足」放行，
避免把正常的群聊/私聊请求掐死。
"""

from __future__ import annotations

from typing import Any

from src.app.plugin_system.api import stream_api
from src.kernel.logger import get_logger

from . import context

logger = get_logger("snowluma_full.scope")


def _ids(raw: Any) -> set[str]:
    """把配置里的群号列表洗成字符串集合（容忍数字、空白、单个字符串、None）。"""

    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return set()
    result: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if text:
            result.add(text)
    return result


def _chat_type_text(value: Any) -> str:
    """把 ``chat_type`` 归一成小写字符串（框架里可能是 ``ChatType`` 枚举）。"""

    if value is None:
        return ""
    text = getattr(value, "value", value)
    if not isinstance(text, str):
        text = str(text)
    return text.strip().lower()


def _deny(explain: str) -> tuple[bool, str]:
    """统一的拒绝结果：文案由调用方原样返回给模型。"""

    return False, f"本插件在当前会话已被 scope 配置禁用（{explain}）。"


async def _group_id_of(component: Any, *, is_action: bool) -> str | None:
    """取当前会话群号；Action 与 Tool 走各自的上下文入口，异常一律降级为 None。"""

    try:
        if is_action:
            return context.group_id_from_action(component)
        return await context.group_id_from_tool(component)
    except Exception as exc:  # noqa: BLE001 - 取不到群号时按信息不足处理
        logger.debug(f"scope：读取群号失败：{exc}")
        return None


async def _chat_type_of(component: Any, *, is_action: bool) -> str:
    """取当前会话的 ``chat_type``（``group`` / ``private``）；取不到返回空串。

    Action 直接读 ``self.chat_stream.chat_type``（可能为空）；Tool 只有 stream_id，
    要通过 ``stream_api.get_stream`` 才能拿到 ChatStream。
    """

    if is_action:
        stream = getattr(component, "chat_stream", None)
        if stream is None:
            return ""
        return _chat_type_text(getattr(stream, "chat_type", None))

    try:
        stream_id = str(component.get_current_stream_id() or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"scope：读取当前 stream_id 失败：{exc}")
        return ""
    if not stream_id:
        return ""

    try:
        stream = await stream_api.get_stream(stream_id)
    except Exception as exc:  # noqa: BLE001 - 流不在缓存里时降级
        logger.debug(f"scope：读取 ChatStream 失败：{exc}")
        return ""
    if stream is None:
        return ""
    return _chat_type_text(getattr(stream, "chat_type", None))


async def allowed(
    plugin: Any,
    component: Any,
    *,
    is_action: bool,
) -> tuple[bool, str]:
    """判断本插件能否在当前会话生效（scope 配置）。

    Args:
        plugin: 插件实例，通过 ``plugin.config.scope`` 取生效范围配置；
            配置节缺失或字段缺失时按「未限制」放行。
        component: 当前组件实例。``is_action`` 为真时当作 ``BaseAction``
            （有 ``chat_stream``），否则当作 ``BaseTool``（有
            ``get_current_stream_id`` 与 ``trigger_message``）。
        is_action: 是否 Action 组件——决定用哪条上下文回溯入口。

    Returns:
        ``(是否放行, 拒绝原因)``。放行时原因为空串；拒绝时原因文案可以直接
        作为 ``execute`` 的返回内容给模型看。
    """

    config = getattr(plugin, "config", None)
    section = getattr(config, "scope", None)
    if section is None:
        # 老配置没有 scope 节，或配置未加载完成：不限制。
        return True, ""

    whitelist = _ids(getattr(section, "group_whitelist", None))
    blacklist = _ids(getattr(section, "group_blacklist", None))
    private_enabled = bool(getattr(section, "private_enabled", True))

    group_id = await _group_id_of(component, is_action=is_action)
    chat_type = await _chat_type_of(component, is_action=is_action)
    if not chat_type and group_id:
        # 拿不到 chat_type 但有群号：按群聊对待，让白/黑名单照常生效。
        chat_type = "group"

    if group_id and group_id in blacklist:
        logger.warning(f"[snowluma_full] scope 拒绝：群 {group_id} 在黑名单里")
        return _deny(f"群 {group_id} 在 group_blacklist 黑名单里")

    if group_id and whitelist and group_id not in whitelist:
        logger.warning(f"[snowluma_full] scope 拒绝：群 {group_id} 不在白名单里")
        return _deny(f"群 {group_id} 不在 group_whitelist 白名单里")

    if chat_type == "private" and not group_id and not private_enabled:
        logger.warning("[snowluma_full] scope 拒绝：私聊未开放")
        return _deny("私聊未开放，private_enabled 为 false")

    return True, ""


__all__ = ["allowed"]
