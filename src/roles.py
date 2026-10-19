"""查询 bot 自己在群里的角色（群主/管理员），带短缓存。

管理类动作只在 bot 是群主或管理员时暴露：普通成员群里调管理接口必然被平台
拒绝，暴露给模型只会浪费上下文。这里用 ``get_group_member_info`` 查 bot 自己
的角色，缓存 5 分钟，避免每次请求都打平台。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from src.app.plugin_system.api import adapter_api
from src.kernel.logger import get_logger

from . import bridge

logger = get_logger("snowluma_full.roles")

#: 角色缓存时长（秒）；失败（空角色）用更短 TTL，等权限变化后能较快重试。
_ROLE_TTL = 300.0
_ROLE_TTL_FAILED = 60.0

_role_cache: dict[str, tuple[str, float]] = {}
_role_locks: dict[str, asyncio.Lock] = {}
_bot_qq_cache: tuple[str, float] | None = None


async def bot_qq(plugin: Any) -> str:
    """取 bot 自己的 QQ 号：先用适配器配置（不联网），失败再查平台。"""

    global _bot_qq_cache
    now = time.monotonic()
    if _bot_qq_cache and _bot_qq_cache[1] > now:
        return _bot_qq_cache[0]

    value = ""
    try:
        info = await adapter_api.get_bot_info_by_platform("qq")
        if isinstance(info, dict):
            value = str(info.get("bot_id") or "").strip()
    except Exception as error:  # noqa: BLE001 - 适配器没实现时走平台查询
        logger.debug(f"roles：适配器取 bot 号失败：{error}")

    if not value:
        try:
            result = await bridge.call_action("get_login_info", {}, timeout=5.0)
            data = result.get("data")
            if isinstance(data, dict):
                value = str(data.get("user_id") or "").strip()
        except Exception as error:  # noqa: BLE001
            logger.debug(f"roles：get_login_info 失败：{error}")

    if value:
        _bot_qq_cache = (value, now + 3600.0)
    return value


async def _query_role(plugin: Any, group_id: str) -> str:
    """真正查一次 bot 在该群的角色（owner/admin/member/空串）。"""

    uid = await bot_qq(plugin)
    if not uid:
        return ""
    try:
        result = await bridge.call_action(
            "get_group_member_info",
            {"group_id": int(group_id), "user_id": int(uid)},
            timeout=3.0,
        )
    except Exception as error:  # noqa: BLE001
        logger.debug(f"roles：查询群 {group_id} 成员信息失败：{error}")
        return ""
    data = result.get("data")
    if isinstance(data, dict):
        role = str(data.get("role") or "").strip().lower()
        if role:
            return role
    return ""


async def bot_group_role(plugin: Any, group_id: str) -> str:
    """取 bot 在群里的角色（带缓存与并发去重）。"""

    key = str(group_id or "").strip()
    if not key:
        return ""
    now = time.monotonic()
    hit = _role_cache.get(key)
    if hit and hit[1] > now:
        return hit[0]

    lock = _role_locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _role_cache.get(key)
        if hit and hit[1] > now:
            return hit[0]
        role = await _query_role(plugin, key)
        ttl = _ROLE_TTL if role else _ROLE_TTL_FAILED
        _role_cache[key] = (role, now + ttl)
        return role


def reset() -> None:
    """清空缓存（插件卸载 / 自检用）。"""

    global _bot_qq_cache
    _role_cache.clear()
    _role_locks.clear()
    _bot_qq_cache = None


__all__ = ["bot_group_role", "bot_qq", "reset"]
