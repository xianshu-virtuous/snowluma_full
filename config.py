"""snowluma_full 插件配置。

配置文件默认路径：``config/plugins/snowluma_full/config.toml``

配置分六节：
- ``plugin``：启用开关与调试日志；
- ``access``：高危 / 流式接口门控、接口名屏蔽、文件类 owner 判定；
- ``limits``：超时、结果截断、目录检索条数；
- ``fold``：按范围折叠本插件自己的能力；
- ``files``：本机文件来源的白名单目录；
- ``scope``：生效的群范围（白/黑名单）与私聊开关。

高危接口（踢人 / 退群 / 删好友 / 取凭证 / 文件外泄链等不可逆或敏感操作）
默认关闭，开启前请确认实例用途。
"""

from __future__ import annotations

from typing import ClassVar

from src.core.components.base.config import BaseConfig, Field, SectionBase, config_section


class SnowLumaFullConfig(BaseConfig):
    """SnowLuma 全量接口扩展配置。"""

    config_name: ClassVar[str] = "config"
    config_description: ClassVar[str] = "SnowLuma 全量接口扩展配置"

    @config_section("plugin", title="插件设置", tag="plugin")
    class PluginSection(SectionBase):
        """插件基础配置。"""

        enabled: bool = Field(default=True, description="是否启用插件")
        debug_log: bool = Field(
            default=False,
            description="是否在日志中输出每次接口调用的接口名、参数键与耗时（不打印敏感值）",
        )

    @config_section("access", title="接口访问门控", tag="access")
    class AccessSection(SectionBase):
        """接口访问门控。"""

        allow_danger: bool = Field(
            default=False,
            description=(
                "是否向 LLM 开放高危接口（默认关闭）。\n"
                "高危含：踢人/退群/删好友/删群文件/删说说/改资料头像/发原始 SSO 包/"
                "清缓存/取凭证等不可逆或敏感操作。\n"
                "关闭时这些接口不会出现在目录检索里，调用也会被拒绝。"
            ),
        )
        allow_stream: bool = Field(
            default=False,
            description=(
                "是否开放流式接口（默认关闭）。\n"
                "流式接口走多帧传输，不适配当前「单请求-单响应」的适配器命令通道，"
                "开启后调用大概率超时；需要时请改用 WebUI 或直连 WebSocket。"
            ),
        )
        blocked_actions: list[str] = Field(
            default_factory=list,
            description="额外屏蔽的接口名列表（即使不是高危也不允许调用），支持精确名称",
        )
        allow_direct_send: bool = Field(
            default=False,
            description=(
                "是否允许 sl_call 直接调用 send_group_msg / send_private_msg / send_msg 发消息（默认关闭）。\n"
                "正常回复/发消息请走框架的适配器发送能力（send_api），直发不会写聊天历史、"
                "不触发发送事件，容易让 bot 重复说话、也让 time_sense 等插件的发言统计失真。\n"
                "只有在明确需要绕过框架发送通道时才打开。"
            ),
        )
        owner_uids: list[str] = Field(
            default_factory=list,
            description=(
                "owner 的平台 QQ 号列表（字符串）。文件类等敏感接口默认只允许 owner 触发；\n"
                "这里列出的号即使框架权限系统里不是 owner 也放行。留空则只认框架权限等级。"
            ),
        )
        files_require_owner: bool = Field(
            default=True,
            description=(
                "文件类接口（上传群文件/私聊文件/空间配图/闪传等）是否只允许 owner 触发。\n"
                "这类接口能把本机文件传出去，非 owner 触发时必须先过路径白名单再过身份判定。"
            ),
        )

    @config_section("limits", title="调用限制", tag="limits")
    class LimitsSection(SectionBase):
        """调用限制。"""

        timeout_seconds: float = Field(
            default=20.0,
            description="单次接口调用超时（秒）；框架适配器命令通道默认 20 秒",
        )
        long_timeout_seconds: float = Field(
            default=45.0,
            description=(
                "长耗时接口的超时（秒）。\n"
                "get_cookies 在适配器侧特判 40 秒，若沿用 20 秒会先被框架掐死；"
                "create_flash_task / 上传类也建议放宽。"
            ),
        )
        max_result_chars: int = Field(
            default=1500,
            description=(
                "返回给 LLM 的结果最大字符数（超出截断并提示）。\n"
                "群成员列表、好友列表这类结果可能非常大，截断可避免撑爆上下文。"
            ),
        )
        help_max_items: int = Field(
            default=12,
            description="sl_help 单次最多返回多少条接口说明",
        )
        help_max_chars: int = Field(
            default=6000,
            description="sl_help 单次返回文本的最大字符数",
        )

    @config_section("fold", title="能力折叠", tag="fold")
    class FoldSection(SectionBase):
        """按范围折叠本插件自己的能力，避免工具 schema 全程占着上下文。"""

        enabled: bool = Field(
            default=True,
            description=(
                "是否启用能力折叠（默认开）。\n"
                "开启后只有常驻工具与已展开的工具会出现在工具列表里，"
                "其余按「QQ空间 / 群管理 / 消息操作 / 私信·群聊 / 通用入口」五个范围收进目录，"
                "模型用 sl_use 展开后，同一会话内下一次请求即可调用。"
            ),
        )
        mode: str = Field(
            default="enforce",
            description=(
                "enforce —— 真折叠（默认）；\n"
                "observe —— 只报告：照常发全量工具，日志里打印「本来会收起哪些」。"
            ),
        )
        inline_catalog: bool = Field(
            default=True,
            description=(
                "是否把能力目录写进 user prompt 末尾。\n"
                "关掉后模型不知道有哪些能力可展开（不建议关）。"
            ),
        )
        keep_always: list[str] = Field(
            default_factory=lambda: ["sl_help", "sl_use"],
            description="永远在手的工具短名（折叠不动的底线）",
        )

    @config_section("files", title="文件参数沙箱", tag="file")
    class FilesSection(SectionBase):
        """本机文件来源的白名单目录。

        SnowLuma 的文件类接口会直接读本机路径再上传，等于把「能读到什么文件」
        的决定权交给了调用方。这里限定只能使用白名单目录里的文件。
        """

        allowed_roots: list[str] = Field(
            default_factory=lambda: ["data"],
            description=(
                "允许作为文件来源的目录（相对实例根或绝对路径）。\n"
                "默认只允许实例的 data 目录；需要传别处的文件请先复制进来。\n"
                "**不要**把磁盘根目录、用户目录或配置目录加进来——那等于取消了沙箱。"
            ),
        )

    @config_section("scope", title="生效范围", tag="scope")
    class ScopeSection(SectionBase):
        """生效范围。"""

        group_whitelist: list[str] = Field(
            default_factory=list,
            description="群白名单（群号字符串）；留空表示不限群",
        )
        group_blacklist: list[str] = Field(
            default_factory=list,
            description="群黑名单（群号字符串）；命中即不提供本插件能力",
        )
        private_enabled: bool = Field(
            default=True,
            description="是否在私聊中提供本插件能力",
        )

    plugin: PluginSection = Field(default_factory=PluginSection)
    access: AccessSection = Field(default_factory=AccessSection)
    limits: LimitsSection = Field(default_factory=LimitsSection)
    fold: FoldSection = Field(default_factory=FoldSection)
    files: FilesSection = Field(default_factory=FilesSection)
    scope: ScopeSection = Field(default_factory=ScopeSection)
