# -*- coding: utf-8 -*-
"""自检：管理动作的暴露门（bot 是群主/管理员）与调用路径。

用法：
    & "F:\\Neo-MoFox-Aemeath\\.venv\\Scripts\\python.exe" tests\\check_manage.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_ROOT = Path(os.environ.get("NEO_ROOT", r"F:\Neo-MoFox-Aemeath"))
sys.path.insert(0, str(FRAMEWORK_ROOT))
sys.path.insert(0, str(ROOT.parent))

import importlib  # noqa: E402

bridge = importlib.import_module("snowluma_full.src.bridge")
roles = importlib.import_module("snowluma_full.src.roles")
ban_mod = importlib.import_module("snowluma_full.src.actions.sl_group_ban")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class FakeMessage:
    def __init__(self) -> None:
        self.message_id = "m1"
        self.sender_id = "3062887204"
        self.chat_type = "group"
        self.extra = {"group_id": "123456"}


class FakeContext:
    def __init__(self) -> None:
        message = FakeMessage()
        self.unread_messages = [message]
        self.history_messages = []
        self.message_cache = []
        self.current_message = message


class FakeStream:
    def __init__(self, chat_type: str = "group") -> None:
        self.chat_type = chat_type
        self.context = FakeContext()


class FakeConfig:
    scope = None
    access = types.SimpleNamespace(blocked_actions=[], owner_uids=[], allow_danger=False, allow_stream=False)
    limits = types.SimpleNamespace(timeout_seconds=20.0, max_result_chars=1500)
    plugin = types.SimpleNamespace(debug_log=False)


class FakePlugin:
    config = FakeConfig()
    catalog = None


plugin = FakePlugin()

captured: list[tuple[str, dict]] = []


async def fake_call(action: str, params: dict, **kwargs):  # noqa: ANN003
    captured.append((action, params))
    return {"status": "ok", "data": None}


bridge.call_action = fake_call  # type: ignore[assignment]


def make_action(chat_type: str = "group"):
    action = object.__new__(ban_mod.SlGroupBanAction)
    action.plugin = plugin
    action.chat_stream = FakeStream(chat_type)
    return action


async def main() -> None:
    role_holder = {"role": "admin"}

    async def fake_role(_plugin, _group_id):  # noqa: ANN001
        return role_holder["role"]

    roles.bot_group_role = fake_role  # type: ignore[assignment]

    role_holder["role"] = "admin"
    check("bot 是管理员 → 暴露", await make_action().go_activate())

    role_holder["role"] = "owner"
    check("bot 是群主 → 暴露", await make_action().go_activate())

    role_holder["role"] = "member"
    check("bot 是普通成员 → 不暴露", not await make_action().go_activate())

    role_holder["role"] = "admin"
    check("私聊 → 不暴露", not await make_action("private").go_activate())

    action = make_action()
    ok, reason = await action.execute(user_id=12345678, duration=0)
    check("管理员 bot 下禁言调用成功", ok, reason)
    check("调用参数正确", captured and captured[-1][0] == "set_group_ban"
          and captured[-1][1] == {"group_id": 123456, "user_id": 12345678, "duration": 0},
          str(captured[-1] if captured else None))


asyncio.run(main())

if failures:
    print(f"\n{len(failures)} 项失败")
    raise SystemExit(1)
print("\n全部通过")
