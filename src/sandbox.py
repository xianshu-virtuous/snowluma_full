"""文件参数沙箱：本机路径只能出自允许的目录。

SnowLuma 的若干接口接受「本地路径」作为文件来源（``f.file()`` /
``images`` 数组），平台侧会直接 ``fs.readFileSync`` 读走再上传。如果不拦，
模型被一句话带偏就能把 ``config/model.toml`` 这类文件传出去——所以这里在
**调用参数层**做白名单，而不是只靠"风险档位"。

覆盖两类入口：
1. **文件参数**（``FILE_PARAMS``）：``upload_group_file`` 这类显式吃路径的接口；
2. **消息段**（``MESSAGE_ACTIONS``）：``send_group_msg`` 的 ``message`` 里
   ``{type: image, data: {file: "F:\\..."}}`` 这种段——SnowLuma 的
   ``pickMediaSource`` 会把含斜杠/盘符的 ``file`` 当本地路径读，属于同一条外泄通道。

规则：
- ``http(s)://`` / ``base64://``：不碰本机文件，放行；
- ``file://``：解析成本地路径后检查；
- 裸路径（盘符 / UNC / 相对路径）：解析绝对路径后检查；
- 只有落在 ``files.allowed_roots``（默认实例 ``data`` 目录）里的文件才放行。
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

#: 哪些接口的哪些参数直接接受「本地文件来源」。
FILE_PARAMS: dict[str, tuple[str, ...]] = {
    "create_flash_task": ("files", "thumb_path"),
    "upload_group_file": ("file",),
    "upload_private_file": ("file",),
    "upload_image_to_qun_album": ("file",),
    "upload_video_to_qun_album": ("file",),
    "send_qzone_msg": ("images",),
    "comment_qzone": ("images",),
}

#: 哪些接口的 message 段里也可能藏本地路径（SnowLuma 会把 file 段读成本机文件）。
MESSAGE_ACTIONS: frozenset[str] = frozenset(
    {
        "send_group_msg",
        "send_private_msg",
        "send_msg",
        "send_group_forward_msg",
        "send_private_forward_msg",
    }
)

#: 消息段里可能放文件来源的键。
_SOURCE_KEYS: frozenset[str] = frozenset({"file", "path", "file_path", "media", "url"})

#: 这些前缀的取值不读本机文件。
_REMOTE_PREFIXES = ("http://", "https://", "base64://", "data:")


def instance_root() -> Path:
    """定位实例根目录（含 ``config`` 的那一层）。

    优先用框架 ``src`` 包的位置反推（实例内 ``src/`` 与 ``config/`` 同级，
    ``src.__file__`` 的父目录就是实例根）；退回「从本文件向上找」，
    最后才用 cwd。``.mfp`` 安装时插件在临时目录里，前两种方式都不会命中，
    此时 cwd 通常是 bot 的启动目录（实例根），与旧行为一致。
    """

    module = sys.modules.get("src")
    module_file = getattr(module, "__file__", None)
    if module_file:
        try:
            root = Path(module_file).resolve().parent.parent
            if (root / "config").is_dir():
                return root
        except OSError:
            pass

    for parent in Path(__file__).resolve().parents:
        if (parent / "config").is_dir() and (parent / "src").is_dir():
            return parent
    return Path.cwd()


def resolve_roots(raw_roots: list[str] | None) -> list[Path]:
    """把配置里的允许目录解析成绝对路径列表。"""

    root = instance_root()
    result: list[Path] = []
    for item in raw_roots or []:
        text = str(item or "").strip()
        if not text:
            continue
        candidate = Path(text)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            result.append(candidate.resolve())
        except OSError:
            continue
    if not result:
        result.append((root / "data").resolve())
    return result


def _to_local_path(value: str) -> str | None:
    """把文件来源转成本地路径；不是本地来源返回 None。"""

    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith(_REMOTE_PREFIXES):
        return None
    if lowered.startswith("file://"):
        parsed = urlparse(text)
        path = unquote(parsed.path or "")
        # file:///F:/xxx -> /F:/xxx（去掉开头多余的斜杠）
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return path or None
    return text


def _looks_like_path(text: str) -> bool:
    """判断一个字符串像不像路径（用于消息段：避免把 file_id 当路径）。"""

    if not text:
        return False
    if text.lower().startswith("file://"):
        return True
    if "/" in text or "\\" in text:
        return True
    return len(text) >= 2 and text[1] == ":" and text[0].isalpha()


def _collect_sources(value: object, out: list[str], *, strict: bool) -> None:
    """递归收集参数里的文件来源字符串。

    Args:
        value: 任意参数值（str / list / dict）。
        out: 收集结果。
        strict: True 时把任何非远程字符串都当本地路径（文件参数用）；
            False 时只收「看起来像路径」的（消息段用，避开 file_id）。
    """

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return
        if strict or _looks_like_path(text):
            out.append(text)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_sources(item, out, strict=strict)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in _SOURCE_KEYS:
                _collect_sources(item, out, strict=strict)
            elif isinstance(item, (dict, list, tuple)):
                # 转发节点的 data/content 里还可能继续嵌段
                _collect_sources(item, out, strict=strict)


def collect_local_sources(action: str, params: dict) -> list[str]:
    """取出一次调用里所有「会读本机文件」的来源字符串。"""

    if not isinstance(params, dict):
        return []
    sources: list[str] = []
    fields = FILE_PARAMS.get(action)
    if fields:
        for field in fields:
            _collect_sources(params.get(field), sources, strict=True)
    if action in MESSAGE_ACTIONS:
        for field in ("message", "messages"):
            _collect_sources(params.get(field), sources, strict=False)
    return sources


def has_local_source(action: str, params: dict) -> bool:
    """这次调用是否真的会读本机文件（网络地址 / base64 不算）。"""

    for text in collect_local_sources(action, params):
        if _to_local_path(text) is not None:
            return True
    return False


def _is_under(path: Path, roots: list[Path]) -> bool:
    """判断路径是否落在任一根目录下。"""

    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def check_params(
    action: str,
    params: dict,
    allowed_roots: list[str] | None,
) -> tuple[bool, str]:
    """检查一次调用里的文件参数。

    Returns:
        ``(是否放行, 拒绝原因)``；不放行时原因会原样回给模型。
    """

    sources = collect_local_sources(action, params)
    if not sources:
        return True, ""

    roots = resolve_roots(allowed_roots)
    root_text = "、".join(str(root) for root in roots)

    for field in sources:
        local = _to_local_path(field)
        if local is None:
            continue  # 网络地址 / base64，不涉及本机文件

        candidate = Path(local)
        if not candidate.is_absolute():
            candidate = instance_root() / candidate

        if not _is_under(candidate, roots):
            return False, (
                f"{action} 的文件参数指向允许目录之外：{field}。"
                f"只能使用这些目录里的文件：{root_text}。"
                f"需要上传别处的文件请先复制进允许目录。"
            )
        if not candidate.exists():
            return False, f"{action} 的文件不存在：{field}"
        if candidate.is_dir():
            return False, f"{action} 的文件参数是目录而不是文件：{field}"
    return True, ""


__all__ = [
    "FILE_PARAMS",
    "MESSAGE_ACTIONS",
    "check_params",
    "collect_local_sources",
    "has_local_source",
    "instance_root",
    "resolve_roots",
]
