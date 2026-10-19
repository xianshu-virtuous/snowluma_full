# -*- coding: utf-8 -*-
"""自检：插件能否被真实框架导入、组件是否齐全、内置目录是否可用。

用法（在插件目录下）：
    & "F:\\Neo-MoFox-Aemeath\\.venv\\Scripts\\python.exe" tests\\check_import.py
可用环境变量 NEO_ROOT 指定其它实例根。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_ROOT = Path(os.environ.get("NEO_ROOT", r"F:\Neo-MoFox-Aemeath"))
sys.path.insert(0, str(FRAMEWORK_ROOT))
sys.path.insert(0, str(ROOT.parent))

import importlib  # noqa: E402

plugin_mod = importlib.import_module("snowluma_full.plugin")
catalog_mod = importlib.import_module("snowluma_full.src.catalog")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


plugin = plugin_mod.SnowLumaFullPlugin()
components = plugin.get_components()
check("组件数量 = 23", len(components) == 23, str(len(components)))
check("组件名唯一", len({getattr(c, 'name', '') for c in components}) == len(components))

expected = {
    "sl_help", "sl_use", "sl_requests", "sl_events", "sl_qzone_read",
    "sl_group_file_list", "sl_msg_history", "sl_call", "sl_qzone_post",
    "sl_qzone_interact", "sl_group_file_upload", "sl_poke", "sl_reaction",
    "sl_recall", "sl_essence", "sl_group_ban", "sl_group_whole_ban",
    "sl_group_kick", "sl_group_card", "sl_group_name", "sl_user_info",
    "catalog", "fold",
}
check("新动作都在组件里", expected <= {getattr(c, 'name', '') for c in components},
      ",".join(sorted(expected - {getattr(c, 'name', '') for c in components})))

catalog = catalog_mod.load_catalog()
check("目录可加载", catalog is not None)
check("接口总数 = 198", catalog.total == 198, str(catalog.total))

for name in ("get_cookies", "get_credentials", "get_clientkey", "get_csrf_token"):
    info = catalog.get(name)
    check(f"{name} 标为 danger", info is not None and info.risk == "danger",
          info.risk if info else "missing")

counts = catalog.risk_counts()
check("危险档数量 = 49", counts.get("danger") == 49, str(counts))
check("删除好友默认可用（write）", catalog.get("delete_friend").risk == "write",
      catalog.get("delete_friend").risk)

if failures:
    print(f"\n{len(failures)} 项失败")
    raise SystemExit(1)
print("\n全部通过")
