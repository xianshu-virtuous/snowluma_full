"""能力折叠：按「使用范围」分组管理本插件自己的工具有没有出现在模型工具列表里。

折叠放在 payload 层（每次 LLM 请求前重算），只改发给模型的那份
``ROLE.TOOL`` payload，注册表始终全量：展开后同一会话内的下一次请求就能回补。

范围是「模型想干什么」的维度，不是代码组织维度：同一范围下的工具往往被
同一次意图一起用到，展开一次就够。
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 展开/目录里展示的范围顺序。
SCOPE_ORDER: tuple[str, ...] = ("QQ空间", "群管理", "消息操作", "私信/群聊", "通用入口")

#: 按聊天流类型调整的展示顺序：当前会话最可能用到的范围放最前。
SCOPE_ORDER_BY_CHAT: dict[str, tuple[str, ...]] = {
    "group": ("群管理", "消息操作", "私信/群聊", "QQ空间", "通用入口"),
    "private": ("QQ空间", "私信/群聊", "消息操作", "通用入口", "群管理"),
    "discuss": ("私信/群聊", "消息操作", "群管理", "QQ空间", "通用入口"),
}

#: 目录标题后缀与首句措辞（按聊天流类型）。
_CHAT_HEAD: dict[str, tuple[str, str]] = {
    "group": (
        "·群聊",
        "【SnowLuma 能力目录·群聊】当前在群聊里，群相关能力优先列出。"
        "不在你工具列表里的，先调 `sl_use([\"工具名或范围名\"])` 展开，"
        "**同一会话内的下一次请求**就能直接调用（一次可展开整组）。",
    ),
    "private": (
        "·私聊",
        "【SnowLuma 能力目录·私聊】当前是私聊，群管理类用不上已排到最后。"
        "不在你工具列表里的，先调 `sl_use([\"工具名或范围名\"])` 展开，"
        "**同一会话内的下一次请求**就能直接调用（一次可展开整组）。",
    ),
}

#: 范围介绍按聊天流类型改写的说法（没有覆盖时用默认介绍）。
_SCOPE_INTRO_BY_CHAT: dict[str, dict[str, str]] = {
    "group": {
        "私信/群聊": "群历史消息回溯、群通知事件（撤回/戳一戳/禁言/文件上传/贴表情）",
    },
    "private": {
        "私信/群聊": "私聊历史消息、通知事件（撤回/戳一戳）",
        "QQ空间": "发说说、看自己的说说/好友动态、点赞·取消赞·评论",
    },
}


def chat_kind(chat_type: object) -> str:
    """把 ``chat_type`` 归一成 ``group`` / ``private`` / ``discuss``（取不到返回空串）。"""

    text = getattr(chat_type, "value", chat_type)
    if not isinstance(text, str):
        text = str(text or "")
    text = text.strip().lower()
    return text if text in ("group", "private", "discuss") else ""


@dataclass(frozen=True)
class Scope:
    """一个使用范围。"""

    name: str
    intro: str
    tools: tuple[str, ...] = field(default_factory=tuple)


SCOPES: dict[str, Scope] = {
    "QQ空间": Scope(
        name="QQ空间",
        intro="发说说、看自己的说说/好友动态、点赞·取消赞·评论",
        tools=("sl_qzone_post", "sl_qzone_read", "sl_qzone_interact"),
    ),
    "群管理": Scope(
        name="群管理",
        intro="群文件、申请审批；禁言/踢人/群名片/群名（bot 是群主或管理员时才出现）",
        tools=(
            "sl_group_file_list",
            "sl_group_file_upload",
            "sl_requests",
            "sl_user_info",
            "sl_group_ban",
            "sl_group_whole_ban",
            "sl_group_kick",
            "sl_group_card",
            "sl_group_name",
        ),
    ),
    "消息操作": Scope(
        name="消息操作",
        intro="戳一戳、贴表情回应、撤回消息、精华消息（设/取消/查看）",
        tools=("sl_poke", "sl_reaction", "sl_recall", "sl_essence"),
    ),
    "私信/群聊": Scope(
        name="私信/群聊",
        intro="历史消息回溯、通知事件（撤回/戳一戳/禁言/文件上传/贴表情）",
        tools=("sl_msg_history", "sl_events"),
    ),
    "通用入口": Scope(
        name="通用入口",
        intro="查询平台接口目录、调用任意平台接口",
        tools=("sl_help", "sl_call"),
    ),
}

#: 永远在手的工具（折叠不动的底线）：目录检索 + 展开入口。
RESIDENT: frozenset[str] = frozenset({"sl_help", "sl_use"})

#: 展开状态：``{stream_id: {工具短名}}``；空 stream_id 视为全局。
_expanded: dict[str, set[str]] = {}

#: 本插件自己的组件类（首次在 payload 里见到时登记）。
#:
#: 框架会把 ``BEFORE_LLM_REQUEST`` 改过的 payload 回写进 ``request.payloads``
#: （``request_execution.py``），而 DFC/NDFC 一个会话只建一次 request —— 只做
#: 「过滤」的话，被摘掉的工具再也回不来，``sl_use`` 展开等于无效。这里留一份
#: 全量登记表，折叠处理器每次按它把「常驻 ∪ 已展开」补回去。
_own_components: dict[str, type] = {}


def remember_components(classes: list[type] | tuple[type, ...]) -> None:
    """登记本插件组件类（按短名去重，保持首次出现顺序）。"""

    for component_cls in classes:
        short = str(getattr(component_cls, "name", "") or "").strip()
        if not short:
            continue
        _own_components.setdefault(short, component_cls)


def known_components() -> list[type]:
    """已登记的本插件组件类。"""

    return list(_own_components.values())


def reset() -> None:
    """清空展开状态与组件登记（插件卸载 / 自检用）。"""

    _expanded.clear()
    _own_components.clear()


def scope_of(tool: str) -> str:
    """工具 → 所属范围；未声明返回空串。"""

    for scope in SCOPES.values():
        if tool in scope.tools:
            return scope.name
    return ""


def all_tools() -> list[str]:
    """全部可折叠工具（含常驻）。"""

    result: list[str] = []
    for name in SCOPE_ORDER:
        result.extend(SCOPES[name].tools)
    return result


def expandable_tools() -> list[str]:
    """可被展开的工具（排除常驻）。"""

    return [name for name in all_tools() if name not in RESIDENT]


def expanded(stream_id: str) -> set[str]:
    """当前会话已展开的工具集合。"""

    return set(_expanded.get(str(stream_id or ""), set()))


def expand(stream_id: str, names: list[str]) -> tuple[list[str], list[str], list[str]]:
    """展开工具。

    Args:
        stream_id: 会话流 ID（空串视为全局）。
        names: 工具短名或范围名（范围名展开整组）。

    Returns:
        ``(新展开, 本来就有, 没认出来)``
    """

    key = str(stream_id or "")
    bucket = _expanded.setdefault(key, set())

    targets: list[str] = []
    unknown: list[str] = []
    known = set(all_tools())
    for raw in names:
        item = str(raw or "").strip()
        if not item:
            continue
        if item in SCOPES:
            targets.extend(SCOPES[item].tools)
        elif item in known:
            targets.append(item)
        elif item.startswith("snowluma_full:"):
            short = item.rsplit(":", 1)[-1]
            if short in known:
                targets.append(short)
            else:
                unknown.append(item)
        else:
            unknown.append(item)

    added: list[str] = []
    already: list[str] = []
    seen: set[str] = set()
    for tool in targets:
        if tool in seen:
            continue
        seen.add(tool)
        if tool in RESIDENT or tool in bucket:
            already.append(tool)
            continue
        bucket.add(tool)
        added.append(tool)
    return added, already, unknown


def describe_expand(added: list[str], already: list[str], unknown: list[str]) -> str:
    """把展开结果转成给模型看的文本。"""

    lines: list[str] = []
    if added:
        scope_map: dict[str, list[str]] = {}
        for tool in added:
            scope_map.setdefault(scope_of(tool) or "其它", []).append(tool)
        parts = "；".join(f"{scope}：{'、'.join(tools)}" for scope, tools in scope_map.items())
        lines.append(f"已展开 {len(added)} 个工具，同一会话内下一次请求即可直接调用（{parts}）。")
    if already:
        lines.append(f"这些本来就能用：{'、'.join(already[:8])}")
    if unknown:
        lines.append(f"没认出来：{'、'.join(unknown[:6])}（照目录里的名字填，或直接给范围名如「QQ空间」）。")
    if not lines:
        lines.append("没有需要展开的工具。")
    return "\n".join(lines)


def catalog_text(
    resident: frozenset[str] = RESIDENT,
    *,
    total: int = 198,
    danger_open: bool = False,
    chat_type: object = "",
) -> str:
    """生成写进 prompt 的能力目录（按范围分组，并按当前聊天流类型分流）。

    Args:
        resident: 常驻工具集合。
        total: 目录里的接口总数（从加载后的目录取，别写死）。
        danger_open: 高危档位是否已开放。
        chat_type: 当前聊天流类型（``group`` / ``private`` / ``discuss``）；
            群聊把群相关范围提到最前，私聊把群管理排到最后；未知时用默认顺序。
    """

    kind = chat_kind(chat_type)
    order = SCOPE_ORDER_BY_CHAT.get(kind, SCOPE_ORDER)
    intro_overrides = _SCOPE_INTRO_BY_CHAT.get(kind, {})

    tail = (
        "高危接口已开放（access.allow_danger = true），调用前请确认不可逆后果。"
        if danger_open
        else "高危接口默认不开放，需要时请在插件配置里逐项评估后开启。"
    )

    if kind in _CHAT_HEAD:
        head = _CHAT_HEAD[kind][1]
    else:
        head = (
            f"【SnowLuma 能力目录】平台接口共 {total} 个，按**用途范围**分组；"
            "不在你工具列表里的，先调 `sl_use([\"工具名或范围名\"])` 展开，"
            "**同一会话内的下一次请求**就能直接调用（一次可展开整组）。"
        )

    lines = [head]
    for name in order:
        scope = SCOPES.get(name)
        if scope is None:
            continue
        pending = [tool for tool in scope.tools if tool not in resident]
        if not pending:
            continue
        intro = intro_overrides.get(name, scope.intro)
        lines.append(f"- [{scope.name}] {intro}：{'、'.join(pending)}")

    if kind == "private":
        lines.append("（群文件、群管理这类能力只在群聊会话里可用。）")
    lines.append(
        f"常驻在手：`sl_help`（查 {total} 个接口的说明与参数）。"
        "平台接口本身还分风险档位，" + tail
    )
    lines.append(
        "回复/发消息请用正常的发送能力（适配器），不要用 `sl_call` 调 "
        "send_group_msg / send_private_msg / send_msg——直发不会写聊天历史。"
    )
    lines.append(
        "审批、踢人、禁言这类有后果的操作由你自己判断；拿不准先在对话里问 OW 用户，不要硬来。"
    )
    return "\n".join(lines)


__all__ = [
    "RESIDENT",
    "SCOPES",
    "SCOPE_ORDER",
    "SCOPE_ORDER_BY_CHAT",
    "Scope",
    "all_tools",
    "catalog_text",
    "chat_kind",
    "describe_expand",
    "expand",
    "expandable_tools",
    "expanded",
    "known_components",
    "remember_components",
    "reset",
    "scope_of",
]
