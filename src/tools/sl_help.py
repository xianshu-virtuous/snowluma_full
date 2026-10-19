"""``sl_help``：SnowLuma 接口目录检索工具。

工具而不是动作——它只查询本地目录、不产生副作用。目标是用一个工具替代
「每个接口注册一个工具」带来的上下文膨胀：模型先查、再调。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.tool import BaseTool
from src.kernel.logger import get_logger

logger = get_logger("snowluma_full")

_EMPTY_HINT = (
    "没找到匹配的接口。可以换关键词（如「空间」「群文件」「好友申请」「表情」），"
    "或直接传分类名：信息/消息/好友/群信息/群管理/群文件/请求/扩展/群相册/空间/系统表情/流式接口。"
)


class SlHelpTool(BaseTool):
    """检索 SnowLuma 暴露的接口目录。"""

    name: str = "sl_help"
    description: str = (
        "查询 SnowLuma 平台可用的接口（QQ 全量能力）。"
        "按关键词或分类检索，返回接口名、用途、必填/可选参数与风险等级。"
        "要调用平台接口但不确定接口名或参数时，先用本工具查，再用 sl_call 执行。"
        "常见关键词：好友申请、删除好友、空间说说、群文件、群相册、精华、公告、"
        "禁言、撤回、戳一戳、表情回应、消息历史、在线状态。"
    )

    async def execute(
        self,
        keyword: Annotated[str, "检索关键词，如「空间」「群文件」「好友」。留空则看分类总览"] = "",
        category: Annotated[
            str,
            "按分类过滤（可选）：信息/消息/好友/群信息/群管理/群文件/请求/扩展/群相册/空间/系统表情/流式接口",
        ] = "",
    ) -> tuple[bool, str]:
        """执行目录检索。"""

        plugin = self.plugin
        catalog = getattr(plugin, "catalog", None)
        if catalog is None:
            return False, "接口目录尚未加载（插件可能未完成初始化）。"

        config = getattr(plugin, "config", None)
        access = getattr(config, "access", None)
        allow_danger = bool(getattr(access, "allow_danger", False))
        allow_stream = bool(getattr(access, "allow_stream", False))
        # 配置里额外屏蔽的接口名（精确名）：检索、详情、提示里都不出现
        blocked_names = {
            str(name).strip()
            for name in (getattr(access, "blocked_actions", None) or [])
            if str(name).strip()
        }
        limits = getattr(config, "limits", None)
        limit = max(1, int(getattr(limits, "help_max_items", 12)))
        max_chars = int(getattr(limits, "help_max_chars", 6000))

        kw = (keyword or "").strip()
        cat = (category or "").strip()

        # 无任何条件：给总览
        if not kw and not cat:
            return True, catalog.overview(allow_danger=allow_danger, allow_stream=allow_stream)

        # 精确命中某个接口：返回详情（含参数）
        if kw and not cat:
            exact = catalog.get(kw)
            if exact is not None:
                if exact.name in blocked_names:
                    return False, f"{exact.name} 已被配置屏蔽（access.blocked_actions）。"
                if exact.risk == "danger" and not allow_danger:
                    return False, f"{exact.name} 是高危接口，当前配置未开启（access.allow_danger）。"
                if exact.stream and not allow_stream:
                    return False, f"{exact.name} 是流式接口，当前配置未开启（access.allow_stream）。"
                return True, exact.detail()

        # 多取一些再过滤：被屏蔽的接口不占条数上限
        fetch_limit = limit + len(blocked_names)
        results = catalog.search(
            keyword=kw,
            category=cat,
            allow_danger=allow_danger,
            allow_stream=allow_stream,
            limit=fetch_limit,
        )
        results = [item for item in results if item.name not in blocked_names][:limit]
        if not results:
            # 可能是命中的接口全被档位 / 屏蔽过滤了：再查一次全档位，给出明确提示
            hidden_hits = catalog.search(
                keyword=kw,
                category=cat,
                allow_danger=True,
                allow_stream=True,
                limit=fetch_limit,
            )
            hidden_hits = [item for item in hidden_hits if item.name not in blocked_names]
            if hidden_hits:
                names = "、".join(a.name for a in hidden_hits[:6])
                reasons = []
                if any(a.risk == "danger" for a in hidden_hits) and not allow_danger:
                    reasons.append("高危接口（access.allow_danger）")
                if any(a.stream for a in hidden_hits) and not allow_stream:
                    reasons.append("流式接口（access.allow_stream）")
                reason_text = " / ".join(reasons) if reasons else "当前档位"
                return False, f"命中 {names}，但都属于{reason_text}，当前配置未开放。"
            return False, _EMPTY_HINT

        lines = [catalog.overview(allow_danger=allow_danger, allow_stream=allow_stream), ""]
        for item in results:
            lines.append(item.one_line())
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "…（已截断，请缩小关键词范围）"
        if len(results) >= limit:
            text += f"\n（还有更多结果，已按上限显示 {limit} 条，可用更精确的关键词）"
        return True, text


__all__ = ["SlHelpTool"]
