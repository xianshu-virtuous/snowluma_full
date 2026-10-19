# -*- coding: utf-8 -*-
"""自检：文件参数沙箱与 owner 闸门（含消息段本地路径）。

用法：
    & "F:\\Neo-MoFox-Aemeath\\.venv\\Scripts\\python.exe" tests\\check_guard.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_ROOT = Path(os.environ.get("NEO_ROOT", r"F:\Neo-MoFox-Aemeath"))
sys.path.insert(0, str(FRAMEWORK_ROOT))
sys.path.insert(0, str(ROOT.parent))

import importlib  # noqa: E402

sandbox = importlib.import_module("snowluma_full.src.sandbox")
guard = importlib.import_module("snowluma_full.src.guard")

TMP = Path(tempfile.mkdtemp(prefix="sl_guard_"))
ALLOWED = TMP / "data"
ALLOWED.mkdir()
INSIDE = ALLOWED / "inside.txt"
INSIDE.write_text("ok", encoding="utf-8")
SECRET = TMP / "secret.toml"
SECRET.write_text("token=xxx", encoding="utf-8")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def allowed(action: str, params: dict, want: bool, label: str) -> None:
    ok, reason = sandbox.check_params(action, params, [str(ALLOWED)])
    check(label, ok == want, reason[:90] if not ok else "")


allowed("upload_group_file", {"file": str(SECRET)}, False, "直传白名单外被拒")
allowed("upload_group_file", {"file": str(INSIDE)}, True, "直传白名单内放行")
allowed("create_flash_task", {"files": [{"file": str(SECRET), "name": "x"}]}, False, "闪传 dict 白名单外被拒")
allowed("create_flash_task", {"files": [{"file": str(INSIDE), "name": "x"}]}, True, "闪传 dict 白名单内放行")
allowed("send_group_msg", {"message": [{"type": "text", "data": {"text": "hi"}}]}, True, "纯文本消息放行")
allowed(
    "send_group_msg",
    {"message": [{"type": "image", "data": {"file": str(SECRET)}}]},
    False,
    "消息段塞本机文件被拒",
)
allowed(
    "send_group_msg",
    {"message": [{"type": "image", "data": {"file": "abc123fileid"}}]},
    True,
    "消息段 file_id 不误拦",
)


class FakeMessage:
    def __init__(self, sender_id: str) -> None:
        self.sender_id = sender_id
        self.extra = {"group_id": "1"}


class FakeComponent:
    def __init__(self, sender_id: str) -> None:
        self._message = FakeMessage(sender_id)

    def _get_context_message_for_target(self, reply_to=None):  # noqa: ANN001
        return self._message


class Config:
    class files:
        allowed_roots = [str(ALLOWED)]
        files_require_owner = True

    class access:
        owner_uids = ["3062887204"]


class Plugin:
    config = Config()


async def main() -> None:
    text_msg = {"message": [{"type": "text", "data": {"text": "hi"}}]}
    ok, _ = await guard.guard_file_call(Plugin(), FakeComponent("99999"), "send_group_msg", text_msg)
    check("非 owner 发纯文本消息放行", ok)

    secret_msg = {"message": [{"type": "image", "data": {"file": str(SECRET)}}]}
    ok, _ = await guard.guard_file_call(Plugin(), FakeComponent("3062887204"), "send_group_msg", secret_msg)
    check("owner 也不能传白名单外文件", not ok)

    ok, _ = await guard.guard_file_call(Plugin(), FakeComponent("99999"), "upload_group_file", {"file": str(INSIDE)})
    check("非 owner 传白名单内文件被拒", not ok)

    ok, _ = await guard.guard_file_call(Plugin(), FakeComponent("3062887204"), "upload_group_file", {"file": str(INSIDE)})
    check("owner 传白名单内文件放行", ok)


asyncio.run(main())

if failures:
    print(f"\n{len(failures)} 项失败")
    raise SystemExit(1)
print("\n全部通过")
