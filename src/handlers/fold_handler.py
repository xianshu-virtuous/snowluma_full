"""payload 层折叠：每次 LLM 请求前决定「本插件的工具哪些让模型看见」。

只动本插件自己的组件，其他插件的工具原样保留，不和别家折叠逻辑抢同一批工具。

为什么不在组件筛选事件里折：筛选结果同时决定 payload 和可执行注册表，
摘掉就再也调不动；payload 层每次请求前都能重算，展开后同一次回复内即生效。

为什么还要「回补」：框架会把 ``BEFORE_LLM_REQUEST`` 改过的 payload 回写进
``request.payloads``（``request_execution.py``），而 DFC/NDFC 一个会话只建一次
request —— 只做收窄的话，被摘掉的工具再也回不来，``sl_use`` 展开等于无效。
所以每次处理时先把自己认出来的组件登记进 ``fold``，再按登记表把
「常驻 ∪ 已展开」却不在 payload 里的组件补回去。
"""

from __future__ import annotations

from typing import Any

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BaseEventHandler
from src.app.plugin_system.types import EventType
from src.kernel.event import EventDecision
from src.kernel.llm import LLMPayload, ROLE

from .. import fold

logger = get_logger("snowluma_full.fold")

#: 本插件名（框架注入的 ``_plugin_`` 与组件签名前缀都用它）。
_PLUGIN_NAME = "snowluma_full"

#: 文件夹形态下的包名（开发态，模块形如 ``snowluma_full.src.tools.sl_help``）。
_PLUGIN_PACKAGE = _PLUGIN_NAME

#: ``.mfp`` 安装态的模块前缀（模块名是临时目录名，形如
#: ``mofox_plugin_snowluma_full_xxxx.src.tools.sl_help``）。
_MFP_PREFIX = f"mofox_plugin_{_PLUGIN_NAME}"


def _signature_of(component_cls: type) -> str:
    """取组件签名（拿不到就返回空串）。"""

    getter = getattr(component_cls, "get_signature", None)
    if not callable(getter):
        return ""
    try:
        return str(getter() or "")
    except Exception:  # noqa: BLE001 - 签名坏了就退回模块路径判定
        return ""


def _module_is_own(component_cls: type) -> bool:
    """模块路径兜底判定：只在拿不到 ``_plugin_`` 与签名时用。"""

    module = str(getattr(component_cls, "__module__", "") or "")
    if not module:
        return False
    # 文件夹形态：snowluma_full / snowluma_full.src.tools.sl_help
    if module == _PLUGIN_PACKAGE or module.startswith(_PLUGIN_PACKAGE + "."):
        return True
    # .mfp 安装形态：顶层模块名是临时目录名 mofox_plugin_snowluma_full_xxxx
    head = module.split(".", 1)[0]
    return head == _MFP_PREFIX or head.startswith(_MFP_PREFIX + "_")


def _is_own(component_cls: type) -> bool:
    """判断组件是否属于本插件。

    三级判定（从最可靠到兜底）：

    1. 框架注册组件时注入的 ``_plugin_``（插件名）—— 与模块名无关，.mfp 安装态也准；
    2. 组件签名 ``get_signature()`` 的前缀 ``snowluma_full:``；
    3. 当前模块路径（开发态文件夹形态 / .mfp 临时目录名）。
    """

    owner = str(getattr(component_cls, "_plugin_", "") or "").strip()
    if owner:
        return owner == _PLUGIN_NAME

    signature = _signature_of(component_cls)
    if signature:
        return signature.startswith(_PLUGIN_NAME + ":")

    return _module_is_own(component_cls)


def _short_name_of(component_cls: type) -> str:
    """取组件短名。"""

    short = str(getattr(component_cls, "name", "") or "").strip()
    if short:
        return short
    signature = _signature_of(component_cls)
    if signature:
        return signature.rsplit(":", 1)[-1]
    return ""


class FoldHandler(BaseEventHandler):
    """按范围折叠本插件工具（常驻 ∪ 已展开之外的收起来）。"""

    name: str = "fold"
    description: str = "payload 层折叠：只收窄本插件工具的可见面，注册表保持全量"
    weight: int = 0
    intercept_message: bool = False
    init_subscribe: list[EventType | str] = [EventType.BEFORE_LLM_REQUEST]

    async def execute(
        self,
        event_name: str,
        params: dict[str, Any],
    ) -> tuple[EventDecision, dict[str, Any]]:
        """处理 LLM 请求前事件。"""

        try:
            return await self._handle(params)
        except Exception as error:  # noqa: BLE001 - 折叠失败必须放行，不能拖累对话
            logger.warning(f"[snowluma_full] payload 折叠出错，本次不折叠：{error}")
            return EventDecision.SUCCESS, params

    async def _handle(self, params: dict[str, Any]) -> tuple[EventDecision, dict[str, Any]]:
        config = getattr(self.plugin, "config", None)
        fold_section = getattr(config, "fold", None)
        if fold_section is None or not bool(getattr(fold_section, "enabled", True)):
            return EventDecision.SUCCESS, params

        payloads = params.get("payloads")
        if not isinstance(payloads, list) or not payloads:
            return EventDecision.SUCCESS, params

        meta = params.get("meta_data")
        stream_id = ""
        if isinstance(meta, dict):
            stream_id = str(meta.get("stream_id") or "")

        mode = str(getattr(fold_section, "mode", "enforce") or "enforce").lower()
        resident = fold.RESIDENT | {
            str(item).strip()
            for item in (getattr(fold_section, "keep_always", None) or [])
            if str(item).strip()
        }
        open_now = fold.expanded(stream_id)

        total = 0
        hidden = 0
        restored = 0
        changed = False

        for index, payload in enumerate(payloads):
            if getattr(payload, "role", None) != ROLE.TOOL:
                continue
            content = getattr(payload, "content", None)
            if not isinstance(content, (list, tuple)) or not content:
                continue

            own_here = [component_cls for component_cls in content if _is_own(component_cls)]
            if own_here:
                # 登记全量：框架会把改过的 payload 回写进 request，之后只能靠登记表回补
                fold.remember_components(own_here)

            kept: list[type] = []
            kept_names: set[str] = set()
            for component_cls in content:
                if not _is_own(component_cls):
                    kept.append(component_cls)  # 别家插件：一个字都不动
                    continue
                short = _short_name_of(component_cls)
                if short in resident or short in open_now:
                    kept.append(component_cls)
                    if short:
                        kept_names.add(short)
                else:
                    hidden += 1

            # 回补：登记过、这次 payload 里没有（上次被摘掉了），但属于常驻 ∪ 已展开的
            for component_cls in fold.known_components():
                short = _short_name_of(component_cls)
                if not short or short in kept_names:
                    continue
                if short not in resident and short not in open_now:
                    continue
                kept_names.add(short)
                kept.append(component_cls)
                restored += 1

            total += len(content)

            if mode != "enforce":
                continue
            # 长度相同也可能「换了一个」，逐项比（类对象按同一性比较）
            if kept == list(content):
                continue
            payloads[index] = LLMPayload(ROLE.TOOL, kept)
            changed = True

        if changed:
            params["payloads"] = payloads

        debug = bool(getattr(getattr(config, "plugin", None), "debug_log", False))
        if debug and total:
            if mode == "enforce":
                logger.info(
                    f"[snowluma_full] 折叠：本插件工具 {total} 个中收 {hidden} 个"
                    f"，回补 {restored} 个"
                    f"（会话 {str(stream_id)[:12] or '(空)'}）"
                )
            else:
                logger.info(
                    f"[snowluma_full] [observe] 若切 enforce 会收起 {hidden} 个"
                    f"（会话 {str(stream_id)[:12] or '(空)'}）"
                )
        return EventDecision.SUCCESS, params


__all__ = ["FoldHandler"]
