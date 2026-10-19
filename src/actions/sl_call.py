"""``sl_call``：SnowLuma 通用接口调用动作。

一个入口覆盖平台全部已开放接口：先按目录校验（存在性、风险档位、流式、
黑名单、必填参数），再通过框架适配器命令通道透传调用。

为什么不拆成 198 个动作：每个动作的 schema 都会进每轮提示词，198 个的
常驻开销约为一个通用入口的 10~20 倍；模型不确定接口名时用 ``sl_help`` 查。
"""

from __future__ import annotations

from typing import Annotated

from src.core.components.base.action import BaseAction
from src.kernel.logger import get_logger

from .. import bridge, guard, scope

logger = get_logger("snowluma_full")


class SlCallAction(BaseAction):
    """调用 SnowLuma 的任意已开放接口。"""

    name: str = "sl_call"
    description: str = (
        "调用 SnowLuma（QQ）平台的接口，覆盖发送消息以外的全量能力："
        "好友申请审批/删除好友、QQ 空间说说（发表/点赞/评论/删除）、群文件、群相册、"
        "精华消息、群公告、群管理、消息历史、系统表情、在线状态等。"
        "参数：action 为接口名（不确定就先调 sl_help 查），params 为参数对象。"
        "注意：回复/发消息请用正常的发送能力（适配器），不要用本工具调 send_group_msg / "
        "send_private_msg / send_msg——直发不会写聊天历史。"
        "好友/加群的同意或拒绝、以及删除好友交给 bot 自己判断（看 QQ 等级与来源）；"
        "拿不准的操作先在对话里问 OW 用户，不要硬来。"
        "高危接口（踢人/退群/删群文件等）默认不可用，需在插件配置开启。"
    )
    primary_action: bool = False
    associated_types = ["text"]

    async def execute(
        self,
        action: Annotated[str, "要调用的接口名，例如 send_group_msg、set_friend_add_request、send_qzone_msg"],
        params: Annotated[
            dict | None,
            "接口参数对象，键名按接口定义（如 {group_id: 123, message: [{type: 'text', data: {text: '你好'}}]}）。不确定参数时先调 sl_help 查",
        ] = None,
    ) -> tuple[bool, str]:
        """执行一次平台接口调用。"""

        plugin = self.plugin
        config = getattr(plugin, "config", None)
        catalog = getattr(plugin, "catalog", None)
        if catalog is None:
            return False, "接口目录尚未加载（插件可能未完成初始化）。"

        access = getattr(config, "access", None)
        limits = getattr(config, "limits", None)
        allow_danger = bool(getattr(access, "allow_danger", False))
        allow_stream = bool(getattr(access, "allow_stream", False))
        blocked = {
            str(name).strip()
            for name in (getattr(access, "blocked_actions", None) or [])
            if str(name).strip()
        }

        name = (action or "").strip()
        if not name:
            return False, "action 不能为空。可先调 sl_help 查接口名。"

        info = catalog.get(name)
        if info is None:
            logger.info(f"sl_call 未知接口：{name}")
            return False, (
                f"没有名为 {name} 的接口。可用 sl_help 检索关键词，"
                "或先调 sl_help 看分类总览。"
            )

        if info.name in blocked:
            return False, f"{info.name} 已被配置屏蔽（access.blocked_actions）。"
        if info.risk == "danger" and not allow_danger:
            return False, (
                f"{info.name} 是高危接口（{info.summary or '不可逆/敏感操作'}），"
                "当前配置未开启 access.allow_danger，已拒绝执行。"
            )
        if info.stream and not allow_stream:
            return False, (
                f"{info.name} 是流式接口，当前通道是单请求-单响应，"
                "开启 access.allow_stream 也可能超时。"
            )
        if info.name in _DIRECT_SEND_ACTIONS and not bool(
            getattr(access, "allow_direct_send", False)
        ):
            return False, (
                f"{info.name} 是发消息接口：回复/发消息请用框架正常的发送能力（适配器 / send_api），"
                "不要用 sl_call 直发——直发不会写聊天历史、不触发发送事件，会让上下文里看不到自己说过的话。"
                "确实要绕过时在配置里打开 access.allow_direct_send。"
            )

        args = dict(params or {})
        missing = [key for key in info.required_params() if key not in args]
        if missing:
            return False, (
                f"{info.name} 缺少必填参数：{', '.join(missing)}。"
                f"参数说明可调 sl_help 查 {info.name}。"
            )

        # 生效范围：群白/黑名单与私聊开关
        ok, reason = await scope.allowed(self.plugin, self, is_action=True)
        if not ok:
            return False, reason

        # 文件参数：路径白名单 + owner 身份（不涉及文件参数的接口直接放行）
        ok, reason = await guard.guard_file_call(self.plugin, self, info.name, args)
        if not ok:
            return False, reason

        timeout = _timeout_for(info.name, limits)
        max_chars = int(getattr(limits, "max_result_chars", 1500))
        debug_log = bool(getattr(getattr(config, "plugin", None), "debug_log", False))

        result = await bridge.call_action(
            info.name,
            args,
            timeout=timeout,
            debug_log=debug_log,
        )
        return bridge.format_result(result, action=info.name, max_chars=max_chars)


#: 这些接口在平台/适配器侧本来就慢，沿用默认 20 秒会被框架先掐死。
_LONG_ACTIONS = frozenset(
    {
        "get_cookies",  # 适配器侧特判 40 秒
        "create_flash_task",
        "upload_group_file",
        "upload_private_file",
        "upload_image_to_qun_album",
        "upload_video_to_qun_album",
        "send_qzone_msg",
        "comment_qzone",
    }
)

#: 聊天发消息类接口：默认禁止走 sl_call 直发，回复请用框架的适配器发送能力。
_DIRECT_SEND_ACTIONS = frozenset({"send_group_msg", "send_private_msg", "send_msg"})


def _timeout_for(action: str, limits: object) -> float:
    """按接口选择超时：慢接口用长超时，其余用默认值。"""

    base = float(getattr(limits, "timeout_seconds", 20.0) or 20.0)
    long_timeout = float(getattr(limits, "long_timeout_seconds", 45.0) or 45.0)
    if action in _LONG_ACTIONS:
        return max(base, long_timeout)
    return base


__all__ = ["SlCallAction"]
