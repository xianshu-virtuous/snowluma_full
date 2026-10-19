# -*- coding: utf-8 -*-
"""自检：能力折叠（常驻过滤 + 展开回补 + _is_own 判定）。

用法：
    & "F:\\Neo-MoFox-Aemeath\\.venv\\Scripts\\python.exe" tests\\check_fold.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_ROOT = Path(os.environ.get("NEO_ROOT", r"F:\Neo-MoFox-Aemeath"))
sys.path.insert(0, str(FRAMEWORK_ROOT))
sys.path.insert(0, str(ROOT.parent))

import importlib  # noqa: E402

from src.kernel.llm import LLMPayload, ROLE  # noqa: E402

config_mod = importlib.import_module("snowluma_full.config")
fold = importlib.import_module("snowluma_full.src.fold")
handler_mod = importlib.import_module("snowluma_full.src.handlers.fold_handler")
plugin_mod = importlib.import_module("snowluma_full.plugin")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class StubPlugin:
    def __init__(self) -> None:
        self.config = config_mod.SnowLumaFullConfig()


plugin = StubPlugin()
components = plugin_mod.SnowLumaFullPlugin().get_components()
for cls in components:
    cls._plugin_ = "snowluma_full"
    cls._signature_ = f"snowluma_full:component:{getattr(cls, 'name', '')}"

# 模拟「.mfp 安装」时的模块名（临时目录名），确认 _is_own 不再依赖模块路径
check(
    "_is_own 按 _plugin_ 判定（不受模块名影响）",
    all(handler_mod._is_own(cls) for cls in components),
    f"{sum(1 for c in components if handler_mod._is_own(c))}/{len(components)}",
)

handler = handler_mod.FoldHandler(plugin)  # type: ignore[arg-type]


def visible(payloads: list) -> list[str]:
    names: list[str] = []
    for payload in payloads:
        if payload.role == ROLE.TOOL:
            names.extend(getattr(c, "name", c.__name__) for c in payload.content)
    return names


async def main() -> None:
    payloads = [LLMPayload(ROLE.TOOL, list(components))]
    params = {"payloads": payloads, "meta_data": {"stream_id": "s-fold"}}
    _, params = await handler.execute("before_llm_request", params)
    first = visible(params["payloads"])
    check("首次请求只剩常驻", set(first) <= {"sl_help", "sl_use"}, str(first))
    check("sl_call 被折叠", "sl_call" not in first)
    check("消息操作被折叠", "sl_poke" not in first and "sl_reaction" not in first)
    check("群管理动作被折叠", "sl_group_ban" not in first)

    fold.expand("s-fold", ["私信/群聊"])
    params2 = {"payloads": params["payloads"], "meta_data": {"stream_id": "s-fold"}}
    _, params2 = await handler.execute("before_llm_request", params2)
    second = visible(params2["payloads"])
    check("展开后回补 sl_events", "sl_events" in second, str(second))
    check("展开后回补 sl_msg_history", "sl_msg_history" in second)
    check("未展开的 sl_qzone_post 仍折叠", "sl_qzone_post" not in second)

    fold.expand("s-fold2", ["消息操作"])
    params3 = {"payloads": params["payloads"], "meta_data": {"stream_id": "s-fold2"}}
    _, params3 = await handler.execute("before_llm_request", params3)
    third = visible(params3["payloads"])
    check("展开消息操作后 sl_poke 可见", "sl_poke" in third, str(third))
    check("展开消息操作后 sl_essence 可见", "sl_essence" in third)


asyncio.run(main())

if failures:
    print(f"\n{len(failures)} 项失败")
    raise SystemExit(1)
print("\n全部通过")
