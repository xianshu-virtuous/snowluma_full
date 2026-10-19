"""平台调用前的统一策略闸门：scope（生效范围）+ blocked_actions（精确屏蔽）。

专用动作/工具原本各自调 ``scope.allowed``，但 ``blocked_actions`` 只在 ``sl_call``
里检查，导致「配置里屏蔽了 send_poke，专用工具照样能戳」这类不一致。这里收口成
一个入口，所有要调平台的组件都过它。
"""

from __future__ import annotations

from typing import Any

from . import scope


def _blocked_names(plugin: Any) -> set[str]:
    access = getattr(getattr(plugin, "config", None), "access", None)
    return {
        str(item).strip()
        for item in (getattr(access, "blocked_actions", None) or [])
        if str(item).strip()
    }


async def ensure_allowed(
    plugin: Any,
    component: Any,
    action: str = "",
    *,
    is_action: bool,
    check_danger: bool = True,
) -> tuple[bool, str]:
    """判断本次平台调用是否被 scope / blocked_actions / 风险档位允许。

    Args:
        plugin: 插件实例（读 config / catalog）。
        component: 当前组件实例（scope 判定需要会话上下文）。
        action: 要调用的平台接口名；留空表示纯本地工具（不查 blocked）。
        is_action: 组件是否为 Action。
        check_danger: 是否按目录的风险档位再检查一次（管理动作由
            「bot 是管理 + 调用者是 OW」把关，传 False 跳过 allow_danger）。

    Returns:
        ``(是否放行, 拒绝原因)``；拒绝原因可以直接回给模型。
    """

    ok, reason = await scope.allowed(plugin, component, is_action=is_action)
    if not ok:
        return False, reason

    access = getattr(getattr(plugin, "config", None), "access", None)

    if action and action in _blocked_names(plugin):
        return False, f"{action} 已被配置屏蔽（access.blocked_actions）。"

    if check_danger and action:
        catalog = getattr(plugin, "catalog", None)
        info = catalog.get(action) if catalog is not None else None
        if info is not None:
            if info.risk == "danger" and not bool(getattr(access, "allow_danger", False)):
                return False, (
                    f"{action} 是高危接口，当前配置未开启 access.allow_danger，已拒绝执行。"
                )
            if info.stream and not bool(getattr(access, "allow_stream", False)):
                return False, (
                    f"{action} 是流式接口，当前通道是单请求-单响应，"
                    "开启 access.allow_stream 也可能超时。"
                )
    return True, ""


__all__ = ["ensure_allowed"]
