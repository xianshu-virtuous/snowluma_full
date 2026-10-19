"""内置接口目录的加载、检索与风险标注。

目录数据来自 SnowLuma WebUI 的 ``/api/debug/actions`` 实时导出，经
``tools/build_sl_catalog.py`` 精简后随插件分发（``assets/sl_catalog.json``，
旧位置 ``data/sl_catalog.json`` 保留作回退），不依赖运行时联网或 WebUI 登录。

加载顺序见 ``_CATALOG_CANDIDATES``：先 ``assets/``（随 ``.mfp`` 分发的正式数据），
再 ``data/``（打包脚本把 ``data`` 当运行产物排除，只用于本地回退）。

每条记录字段：
- ``name``：OneBot v11 接口名；
- ``category``：SnowLuma 侧分类（信息/消息/好友/群信息/群管理/群文件/请求/
  扩展/群相册/空间/系统表情/流式接口）；
- ``summary``：一句话说明；
- ``params``：参数列表（含必填标记与角色标记）；
- ``read_only``：是否只读；
- ``stream``：是否流式接口（多帧传输，单请求通道不适用）；
- ``aliases``：别名（如 ``upload_foward_msg`` 这种历史拼写）；
- ``risk``：``read`` / ``write`` / ``danger``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# 内置目录的候选位置，按优先级排列：
# - ``assets/sl_catalog.json``：正式位置，会随 .mfp 一起分发；
# - ``data/sl_catalog.json``：旧位置（打包脚本把 data/ 当运行产物排除），
#   仅作本地回退，避免旧部署或未迁移时直接不可用。
_CATALOG_CANDIDATES: tuple[Path, ...] = (
    _PLUGIN_ROOT / "assets" / "sl_catalog.json",
    _PLUGIN_ROOT / "data" / "sl_catalog.json",
)

RISK_LABEL = {
    "read": "只读",
    "write": "常规",
    "danger": "高危",
}

# 用户常说的词 → 接口名。纯子串检索对「好友申请 / 说说 / 踢人」这类说法命中率低，
# 这里补一层同义映射，让 sl_help 更接近人类检索习惯。
SEARCH_HINTS: dict[str, list[str]] = {
    "好友申请": ["set_friend_add_request", "get_doubt_friends_add_request", "set_doubt_friends_add_request"],
    "同意好友": ["set_friend_add_request"],
    "加好友": ["set_friend_add_request", "get_friend_list", "get_stranger_info"],
    "删好友": ["delete_friend"],
    "好友列表": ["get_friend_list", "get_friends_with_category"],
    "群文件": [
        "upload_group_file",
        "get_group_root_files",
        "get_group_files_by_folder",
        "delete_group_file",
        "get_group_file_url",
        "create_group_file_folder",
        "rename_group_file",
        "move_group_file",
    ],
    "群相册": [
        "get_group_album_list",
        "get_group_album_media_list",
        "upload_image_to_qun_album",
        "upload_video_to_qun_album",
        "del_group_album_media",
    ],
    "说说": [
        "send_qzone_msg",
        "get_qzone_msg_list",
        "get_qzone_feeds",
        "like_qzone",
        "unlike_qzone",
        "comment_qzone",
        "delete_qzone_msg",
    ],
    "空间": [
        "send_qzone_msg",
        "get_qzone_msg_list",
        "get_qzone_feeds",
        "like_qzone",
        "unlike_qzone",
        "comment_qzone",
        "delete_qzone_msg",
        "set_qzone_msg_right",
        "set_qzone_ban",
    ],
    "踢人": ["set_group_kick", "set_group_kick_members"],
    "禁言": ["set_group_ban", "get_group_shut_list", "set_group_anonymous_ban"],
    "撤回": ["delete_msg"],
    "精华": ["set_essence_msg", "delete_essence_msg", "get_essence_msg_list"],
    "公告": ["_send_group_notice", "_get_group_notice", "_del_group_notice"],
    "群名片": ["set_group_card"],
    "头衔": ["set_group_special_title"],
    "签到": ["set_group_sign", "get_group_signed_list"],
    "待办": ["set_group_todo", "cancel_group_todo", "complete_group_todo", "get_group_todo_list"],
    "表情回应": ["set_msg_emoji_like", "get_msg_emoji_likes", "get_emoji_likes", "fetch_emoji_like", "set_group_reaction"],
    "贴表情": ["set_msg_emoji_like", "get_msg_emoji_likes"],
    "戳一戳": ["send_poke", "group_poke", "friend_poke"],
    "消息历史": ["get_group_msg_history", "get_friend_msg_history", "get_msg", "get_forward_msg"],
    "在线状态": ["set_online_status", "set_diy_online_status", "nc_get_user_status", "get_online_clients"],
    "闪传": ["create_flash_task", "download_fileset", "get_fileset_id", "get_fileset_info", "get_flash_file_url", "list_filesets"],
    "收藏表情": ["fetch_custom_face", "fetch_custom_face_detail", "add_custom_face", "delete_custom_face", "modify_custom_face"],
    "群成员": ["get_group_member_list", "get_group_member_info"],
    "群列表": ["get_group_list"],
    "群信息": ["get_group_info", "get_group_info_ex", "get_group_detail_info"],
    "点赞": ["send_like", "like_qzone", "get_profile_like", "friend_profile_like"],
    "翻译": ["translate_en2zh"],
    "识别": ["ocr_image", "fetch_ptt_text"],
    "头像": ["set_qq_avatar", "set_group_portrait"],
    "禁言列表": ["get_group_shut_list"],
    "打卡": ["get_group_signed_list"],
    "文件上传": ["upload_group_file", "upload_private_file", "upload_file_stream"],
    "下载": ["download_file", "download_file_stream", "get_group_file_url", "get_private_file_url"],
}


def _hint_names(keyword: str) -> set[str]:
    """关键词命中的同义接口集合。"""

    if not keyword:
        return set()
    hits: set[str] = set()
    for key, names in SEARCH_HINTS.items():
        if keyword in key or key in keyword:
            hits.update(names)
    return hits


@dataclass
class ActionParam:
    """接口参数。"""

    name: str
    required: bool = False
    role: str = ""


@dataclass
class ActionInfo:
    """单个接口的元数据。"""

    name: str
    category: str = "未分类"
    summary: str = ""
    params: list[ActionParam] = field(default_factory=list)
    read_only: bool = False
    stream: bool = False
    aliases: list[str] = field(default_factory=list)
    risk: str = "write"

    @property
    def risk_label(self) -> str:
        return RISK_LABEL.get(self.risk, self.risk)

    def required_params(self) -> list[str]:
        return [p.name for p in self.params if p.required]

    def optional_params(self) -> list[str]:
        return [p.name for p in self.params if not p.required]

    def one_line(self) -> str:
        """给 LLM 看的一行摘要（不含参数细节）。"""

        return f"{self.name}｜{self.category}｜{self.risk_label}｜{self.summary or '（无说明）'}"

    def detail(self) -> str:
        """给 LLM 看的完整说明（含参数）。"""

        head = f"{self.name}（{self.category}，{self.risk_label}）"
        body = self.summary or "（无说明）"
        req = self.required_params()
        opt = self.optional_params()
        lines = [head, f"  说明：{body}"]
        if req:
            lines.append(f"  必填参数：{', '.join(req)}")
        if opt:
            lines.append(f"  可选参数：{', '.join(opt)}")
        if self.aliases:
            lines.append(f"  别名：{', '.join(self.aliases)}")
        if self.stream:
            lines.append("  注意：流式接口，走多帧传输")
        return "\n".join(lines)


class Catalog:
    """接口目录。"""

    def __init__(self, actions: list[ActionInfo], meta: dict) -> None:
        self._actions = {a.name: a for a in actions}
        self._order = [a.name for a in actions]
        self.meta = meta

    # ---------- 基础访问 ----------

    @property
    def total(self) -> int:
        return len(self._order)

    def names(self) -> list[str]:
        return list(self._order)

    def get(self, name: str) -> ActionInfo | None:
        """按名称或别名取接口。"""

        info = self._actions.get(name)
        if info is not None:
            return info
        lowered = name.lower()
        if lowered in self._actions:
            return self._actions[lowered]
        for action in self._actions.values():
            if lowered in (a.lower() for a in action.aliases):
                return action
        return None

    def categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name in self._order:
            cat = self._actions[name].category
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def risk_counts(self) -> dict[str, int]:
        counts = {"read": 0, "write": 0, "danger": 0}
        for name in self._order:
            risk = self._actions[name].risk
            counts[risk] = counts.get(risk, 0) + 1
        return counts

    # ---------- 检索 ----------

    def search(
        self,
        keyword: str = "",
        category: str = "",
        *,
        allow_danger: bool = False,
        allow_stream: bool = False,
        limit: int = 12,
    ) -> list[ActionInfo]:
        """按关键词 / 分类检索，自动过滤未开放的档位。"""

        kw = (keyword or "").strip()
        kw_lower = kw.lower()
        hints = _hint_names(kw)
        cat = (category or "").strip()

        primary: list[ActionInfo] = []
        secondary: list[ActionInfo] = []
        for name in self._order:
            action = self._actions[name]
            if action.risk == "danger" and not allow_danger:
                continue
            if action.stream and not allow_stream:
                continue
            if cat and action.category != cat:
                continue
            if kw:
                haystack = " ".join(
                    [action.name, action.category, action.summary, *action.aliases]
                ).lower()
                matched_by_hint = action.name in hints
                matched_by_text = kw_lower in haystack
                if not (matched_by_hint or matched_by_text):
                    continue
                (primary if matched_by_hint else secondary).append(action)
            else:
                primary.append(action)

        return (primary + secondary)[: max(1, limit)]

    def overview(self, *, allow_danger: bool = False, allow_stream: bool = False) -> str:
        """目录总览（给 LLM 的开场说明）。"""

        cats = self.categories()
        hidden = []
        if not allow_danger:
            hidden.append("高危")
        if not allow_stream:
            hidden.append("流式")
        lines = [
            f"SnowLuma 接口目录：共 {self.total} 个（v{self.meta.get('sl_version', '?')}，"
            f"{self.meta.get('protocol', 'OneBot v11')}）",
            "分类：" + "、".join(f"{c}{n}" for c, n in cats.items()),
        ]
        if hidden:
            lines.append(f"当前未开放：{'、'.join(hidden)}（可在插件配置开启）")
        return "\n".join(lines)


def load_catalog(path: Path | None = None) -> Catalog:
    """加载内置目录；找不到任何候选文件时抛 ``FileNotFoundError``（插件仍可加载，但功能不可用）。

    未显式给 ``path`` 时按 ``_CATALOG_CANDIDATES`` 顺序取第一个存在的文件：
    ``assets/sl_catalog.json`` 优先，缺失时回退 ``data/sl_catalog.json``。
    """

    if path is not None:
        targets = [Path(path)]
    else:
        targets = list(_CATALOG_CANDIDATES)

    payload = None
    tried: list[str] = []
    for target in targets:
        tried.append(str(target))
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        break
    if payload is None:
        raise FileNotFoundError(f"找不到接口目录文件，已尝试：{'; '.join(tried)}")

    actions: list[ActionInfo] = []
    for raw in payload.get("actions", []):
        actions.append(
            ActionInfo(
                name=raw["name"],
                category=raw.get("category", "未分类"),
                summary=raw.get("summary", ""),
                params=[
                    ActionParam(
                        name=p.get("name", ""),
                        required=bool(p.get("required")),
                        role=p.get("role", ""),
                    )
                    for p in raw.get("params", [])
                ],
                read_only=bool(raw.get("read_only")),
                stream=bool(raw.get("stream")),
                aliases=[a for a in raw.get("aliases", []) if a],
                risk=raw.get("risk", "write"),
            )
        )
    return Catalog(actions, payload.get("_meta", {}))


__all__ = [
    "ActionInfo",
    "ActionParam",
    "Catalog",
    "RISK_LABEL",
    "SEARCH_HINTS",
    "load_catalog",
]
