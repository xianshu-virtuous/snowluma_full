"""平台调用薄封装：通过框架公共接口把 OneBot 动作发给当前 QQ 适配器。

这里**不直接依赖** ``snowluma_adapter`` 的实现，只使用框架的
``src.app.plugin_system.api.adapter_api``：

- ``get_all_adapters()`` 找已启动的 QQ 适配器（优先 ``snowluma_adapter``）；
- ``send_adapter_command()`` 下发 ``adapter_command`` 信封并等待 ``adapter_response``。

SnowLuma 适配器侧对 ``action`` 名**不做白名单校验**（实测 2.2.12 直接把名称与
参数透传给平台），因此本插件可以调用平台侧声明的全部接口；真正的门控在
本插件配置里做（高危/流式/黑名单）。
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.app.plugin_system.api import adapter_api
from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("snowluma_full")

_PREFERRED_PREFIX = "snowluma_adapter"


class BridgeError(RuntimeError):
    """桥接层错误（适配器缺失、调用异常等）。"""


def resolve_adapter() -> str | None:
    """挑一个可用的 QQ 适配器签名。"""

    adapters = adapter_api.get_all_adapters()
    candidates = [
        signature
        for signature, adapter in adapters.items()
        if getattr(adapter, "platform", "") == "qq"
    ]
    if not candidates:
        return None
    for signature in candidates:
        if signature.split(":", 1)[0] == _PREFERRED_PREFIX:
            return signature
    return candidates[0]


def _normalize(raw: Any) -> dict[str, Any]:
    """把适配器返回统一成 ``{status, retcode, data, message}``。"""

    if not isinstance(raw, dict):
        return {"status": "error", "message": f"平台返回了非字典结果：{type(raw).__name__}"}

    # 适配器透传回来的通常是平台原始响应；个别适配器会再包一层 data
    payload = raw
    if "response" in raw and isinstance(raw["response"], dict):
        payload = raw["response"]

    status = str(payload.get("status") or raw.get("status") or "").lower()
    if not status:
        # 没有 status 字段时按 retcode 推断
        retcode = payload.get("retcode", raw.get("retcode"))
        status = "ok" if retcode in (0, None) else "failed"

    return {
        "status": status,
        "retcode": payload.get("retcode", raw.get("retcode")),
        "data": payload.get("data", raw.get("data")),
        "message": payload.get("message") or raw.get("message") or "",
        "wording": payload.get("wording") or raw.get("wording") or "",
    }


async def call_action(
    action: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 20.0,
    adapter_sign: str = "",
    debug_log: bool = False,
) -> dict[str, Any]:
    """调用一个 OneBot 动作。

    Args:
        action: 接口名（如 ``send_group_msg``）。
        params: 接口参数。
        timeout: 超时秒数。
        adapter_sign: 指定适配器签名；留空自动选择。
        debug_log: 是否输出调试日志（只记键名与耗时，不记敏感值）。

    Returns:
        dict: ``{status, retcode, data, message, wording}``；调用异常时 ``status=error``。
    """

    signature = adapter_sign or resolve_adapter()
    if not signature:
        return {
            "status": "error",
            "message": "没有可用的 QQ 适配器（请先启用 snowluma_adapter 或其它兼容适配器）",
            "data": None,
        }

    args = dict(params or {})
    started = time.monotonic()
    try:
        raw = await adapter_api.send_adapter_command(
            adapter_sign=signature,
            command_name=action,
            command_data=args,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - 桥接层兜底，错误要回给 LLM
        logger.error(f"调用平台接口异常：action={action} err={exc}")
        return {"status": "error", "message": f"调用异常：{exc}", "data": None}

    elapsed = time.monotonic() - started
    result = _normalize(raw)
    if debug_log:
        logger.info(
            f"平台调用：action={action} keys={sorted(args)} "
            f"status={result.get('status')} retcode={result.get('retcode')} {elapsed:.2f}s"
        )
    return result


def format_result(
    result: dict[str, Any],
    *,
    action: str,
    max_chars: int = 1500,
) -> tuple[bool, str]:
    """把调用结果格式化为给 LLM 的文本。"""

    status = str(result.get("status") or "").lower()
    data = result.get("data")
    detail = str(result.get("wording") or result.get("message") or "").strip()

    if status in {"ok", "async"}:
        if data is None or data == "" or data == [] or data == {}:
            return True, f"{action} 调用成功。"
        try:
            text = json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(data)
        if len(text) > max_chars:
            text = text[:max_chars] + f"…（结果过长已截断，原长 {len(text)} 字符）"
        return True, f"{action} 调用成功，返回：{text}"

    retcode = result.get("retcode")
    hint = f"（retcode={retcode}）" if retcode is not None else ""
    return False, f"{action} 调用失败{hint}：{detail or '平台未返回原因'}"


__all__ = ["BridgeError", "call_action", "format_result", "resolve_adapter"]
