# snowluma_full — SnowLuma 全量接口扩展

把 SnowLuma 暴露的 OneBot v11 接口（当前 **198 个**）收进**一个插件**，用少量入口覆盖全量能力，
避免「一个接口一个工具 / 一堆插件拼拼凑凑」把提示词撑爆。

## 为什么需要它

- SnowLuma（SL）本体把 QQ 能力全暴露出来了：好友、群管理、群文件、群相册、QQ 空间、
  系统表情、闪传、消息历史……共 198 个 action。
- 但现有生态只做了其中一小块：`snowluma_extension` 直接调用 31 个（约 15.7%），
  其余接口只能在代码里手写调用，模型用不上。
- 每个接口都注册成独立 LLM 工具，schema 会随每轮请求全量注入——198 个工具常驻开销
  是「一个通用入口」的 10 倍以上。

本插件用一个目录检索 + 一个通用调用入口 + 一个请求列表工具解决这件事。

## 组件

| 组件 | 类型 | 折叠范围 | 作用 |
| --- | --- | --- | --- |
| `sl_help` | tool | **常驻** | 按关键词/分类检索 198 个接口（带中文同义映射） |
| `sl_use` | tool | **常驻** | 按工具名或范围名展开能力，展开后同一会话内即可调用 |
| `sl_call` | action | 通用入口 | **通用入口**：按接口名 + 参数对象调用任意已开放接口 |
| `sl_qzone_post` | action | QQ空间 | 发表 QQ 空间说说（支持配图、可见范围） |
| `sl_qzone_read` | tool | QQ空间 | 读自己的说说（带 tid / 评论数）与好友动态（仅摘要，没有 tid） |
| `sl_qzone_interact` | action | QQ空间 | 说说点赞 / 取消赞 / 评论 |
| `sl_group_file_list` | tool | 群管理 | 浏览当前群文件（根目录 / 子文件夹） |
| `sl_group_file_upload` | action | 群管理 | 上传文件到当前群文件 |
| `sl_requests` | tool | 群管理 | 列出待处理好友/加群申请，带审批所需 `flag` 与 QQ 等级 |
| `sl_user_info` | tool | 群管理 | 查 QQ 资料（昵称、等级、备注、注册时间），审批前用 |
| `sl_group_ban` | action | 群管理 | 禁言 / 解禁群成员 |
| `sl_group_whole_ban` | action | 群管理 | 全员禁言开关 |
| `sl_group_kick` | action | 群管理 | 踢出群成员 |
| `sl_group_card` | action | 群管理 | 修改群名片 |
| `sl_group_name` | action | 群管理 | 修改群名 |
| `sl_poke` | action | 消息操作 | 戳一戳（群聊/私聊自动路由） |
| `sl_reaction` | action | 消息操作 | 给消息贴表情回应 / 取消 |
| `sl_recall` | action | 消息操作 | 撤回消息 |
| `sl_essence` | action | 消息操作 | 精华消息：设 / 取消 / 查看 |
| `sl_msg_history` | tool | 私信/群聊 | 读群聊 / 私聊历史消息 |
| `sl_events` | tool | 私信/群聊 | 整理通知事件：撤回/戳/禁言/上传/贴表情等 |

调用链：`sl_*` → 框架 `adapter_api.send_adapter_command()` → 适配器
`adapter_command` 信封 → SnowLuma 平台。

## 安全：文件参数沙箱（重要）

SnowLuma 的一批接口接受「本地路径」作为文件来源，平台侧会直接
`fs.readFileSync` 读走再上传。**只靠风险档位挡不住**——例如
`create_flash_task`（任意本机文件上传）+ `get_share_link`（拿分享链接）
串起来就是一条本机文件外泄链。

插件做了两层约束：

1. **路径白名单**：文件类参数只能指向 `files.allowed_roots`（默认实例 `data` 目录）；
   `file://`、裸 Windows 路径、相对路径都会被解析后检查，路径穿越（`data/../config`）
   同样会被拒；`http(s)://`、`base64://` 不读本机文件，放行。
2. **owner 身份**：文件类接口默认只允许 owner 触发（`access.files_require_owner`）。
   身份来源：`access.owner_uids` 显式名单 + 框架权限系统的 `PermissionLevel.OWNER`。

安全边界就四条，绕不过去：

- **文件类参数只允许白名单目录**：`files.allowed_roots`（默认实例 `data`）以外的
  路径一律拒绝，需要发别处的文件请先复制进来；
- **本机文件外发只允许 owner**：`access.files_require_owner = true`（默认）时，
  非 owner 触发直接拒；owner 名单写在 `access.owner_uids`（默认空，只认框架权限等级）；
- **消息段里的本地路径同样受限**：`send_group_msg` / `send_private_msg` 等接口的
  `message` 段里 `{type: "image", data: {file: "F:\\..."}}` 这类本地来源会被解析成
  路径，走同一套白名单 + owner 判定；纯文本、`http(s)://` 图片、`base64://` 不触发；
- **聊天回复不走本插件**：`send_group_msg` / `send_private_msg` / `send_msg` 默认
  禁止 `sl_call` 直发（`access.allow_direct_send = false`），回复请用框架正常的
  适配器发送能力——直发不会写聊天历史、不触发发送事件，会让 bot 看不到自己说过的话。

这些只在**真的会读本机文件**或**真的在发聊天消息**的调用上生效，普通发言、网络图床不会被误拦。

## 审批与群管理：交给 bot 判断

- **好友申请 / 加群申请**：都在 `sl_requests` 里列出（带 `flag` 与 QQ 等级），由 bot
  自己决定：等级高、来源熟悉（同群/有备注/留言可信）就同意；拿不准先 `sl_user_info`
  查资料，仍不确定就在对话里问 OW 用户。插件不硬卡 OW 权限。
- **删除好友**：`delete_friend` 是常规档（默认可用），同样由 bot 判断。
- **群管理动作**（禁言/解禁、全员禁言、踢人、改群名片、改群名）：
  - **暴露条件**：bot 自己在该群是群主或管理员时才把工具发给模型；普通成员群里
    这些工具不出现（查 `get_group_member_info` 的 bot 角色，缓存 5 分钟）。
  - **调用**：不新增配置项，也不看 `access.allow_danger`；由 LLM 按上下文判断，
    拿不准先问 OW 用户。平台权限不足时接口会返回错误。
- `allow_danger` 仍然只约束 `sl_call` 通用入口里的其它高危接口。

默认关闭 / 加强的高危项：

| 接口 | 处理 |
| --- | --- |
| `create_flash_task` / `get_share_link` / `get_fileset_*` / `download_fileset` / `list_filesets` / `send_flash_msg` / `rename_flash_file` / `delete_flash_file` | **danger**，默认关闭（整条闪传链） |
| `upload_private_file` | **danger**，默认关闭 |
| `upload_group_file`、`send_qzone_msg.images`、`comment_qzone.images`、`upload_image_to_qun_album`、`upload_video_to_qun_album` | 保留常规档位，但必须过路径白名单 + owner 判定 |

> 别把磁盘根目录、用户目录、配置目录加进 `allowed_roots`——那等于取消沙箱。
> 需要发 `data` 之外的文件，先复制进来。

## 能力折叠（按范围，不按插件）

默认**折叠**：只有 `sl_help`、`sl_use` 常驻在工具列表里，其余 19 个按范围收起来；
能力目录直接写进 user prompt 末尾（五行），模型看到目录后 `sl_use(["QQ空间"])`
一次展开整组。

折叠发生在 **payload 层**（每次 LLM 请求前重算），可执行注册表始终全量；展开状态
按会话记录，**同一会话内的下一次请求就会把工具回补进工具列表**——不用等新会话、
也不用重启插件。被摘掉的工具由登记表回补，不会出现"展开过一次就再也回不来"。

- **只折叠本插件自己的工具**，别家插件的工具原样保留，不与独立安装的 `tool_hub` 抢活；
- `mode = "observe"` 可先只观测：照常发全量，日志里打印"本来会收起几个"；
- 常驻底线 `keep_always` 可在配置里加减。

常驻成本对比：全部 11 个工具 ≈ 5.5k 字符 schema；折叠后常驻只剩
`sl_help` + `sl_use`（约 1k 字符），其余按需展开。

## 实现的功能

- **全量目录 + 通用入口**：一个 `sl_help` 检索 SnowLuma 的 198 个接口，一个 `sl_call`
  按接口名 + 参数调用（含必填校验、风险档位、流式拦截、黑名单）。
- **消息操作**：戳一戳、贴表情回应/取消、撤回消息、精华消息（设/取消/查看）。
- **群管理**：禁言/解禁、全员禁言、踢人、改群名片、改群名；只有 bot 自己是群主或
  管理员时才把工具发给模型，是否动手由 LLM 判断，拿不准先问 OW。
- **好友/加群审批**：`sl_requests` 列出申请与 `flag`，`sl_user_info` 查 QQ 资料与等级，
  由 bot 按「等级高、来源熟悉」决定同意/拒绝；删除好友同样是常规能力。
- **QQ 空间**：发说说（配图、可见范围）、读说说/好友动态、点赞/取消赞/评论。
- **群文件**：浏览根目录/子文件夹、上传文件。
- **消息与事件回溯**：读群聊/私聊历史消息；整理撤回、戳一戳、禁言、群文件上传、
  贴表情、精华、成员变动等通知事件。
- **文件安全**：本机文件来源只允许白名单目录；消息段里的本地路径同样拦截；
  文件外发只允许 owner。
- **上下文经济**：payload 层按范围折叠，常驻只有 `sl_help` + `sl_use`，展开后同一
  会话内回补；目录文本按群聊/私聊调整顺序。
- **发送与审查**：聊天回复禁止走 `sl_call` 直发（改走适配器），审批/管理由 LLM 决策。

## 参考与差异：言柒的插件

本插件的调用方式与事件结构参考了言柒的两个插件（均为 AGPL-3.0），**未复制其代码**：

- **`snowluma_adapter`**：消息收发、事件转消息仍由它负责，本插件不重造。参考点：
  适配器命令通道（`adapter_command`）的用法，以及 notice/request 注入上下文时的
  `extra` 约定（`is_notice` / `notice_type` / `is_request` / `flag`）。
- **`snowluma_extension`**：参考了它的能力划分（戳一戳、贴表情、撤回、精华、禁言、
  踢人、群名片、群名）与「按身份/开关决定是否暴露」的思路；本插件用「bot 群角色 +
  LLM 决策」重新实现，组件形态与权限模型不同。
- **接口目录**：来自 SnowLuma WebUI 的 `GET /api/debug/actions` 只读导出，不是言柒
  的代码。

差异与共存：官方 extension 是「一个能力一个动作」的插件，本插件是「全量目录 + 通用
入口 + 高频动作」。两者同时启用会出现重复工具、浪费上下文，建议只留一个。


## 风险档位

目录为每个接口标了 `read` / `write` / `danger`：

- `read` 只读查询、`write` 常规副作用（发消息、禁言、撤回、点赞、改名片…）；
- `danger` 不可逆或敏感：踢人、退群、删群文件、删说说、改资料头像、
  发原始 SSO 包、清缓存、取凭证等，**默认不开放**。

开启方式：配置 `access.allow_danger = true`。流式接口（目录里 `stream` 标记的
5 个）走多帧传输，不适配当前单请求通道，默认也不开放（`access.allow_stream`）。

## 配置

`config/plugins/snowluma_full/config.toml`：

```toml
[plugin]
enabled = true
debug_log = false

[access]
allow_danger = false       # 高危接口总开关
allow_stream = false       # 流式接口总开关
blocked_actions = []       # 额外屏蔽的接口名（精确名）
owner_uids = []            # owner 的 QQ 号，默认空（只认框架权限等级）
files_require_owner = true # 文件类接口是否强制 owner，默认 true

[files]
allowed_roots = ["data"]   # 文件来源白名单目录，默认 ["data"]（别放宽到磁盘根/配置目录）

[limits]
timeout_seconds = 20.0     # 单次调用超时
long_timeout_seconds = 45.0  # 慢接口（get_cookies / 上传 / 闪传）的超时，默认 45
max_result_chars = 1500    # 返回给模型的结果截断长度
help_max_items = 12        # sl_help 单次条数
help_max_chars = 6000      # sl_help 单次字符上限

[fold]
enabled = true             # 是否启用按范围折叠
mode = "enforce"           # enforce=真折叠；observe=只观测不折
inline_catalog = true      # 目录写进 user prompt
keep_always = ["sl_help", "sl_use"]   # 永远在手的工具

[scope]
group_whitelist = []       # 留空=不限群
group_blacklist = []
private_enabled = true
```

## 接口目录

`assets/sl_catalog.json` 是随包分发的精简目录（当前对应 SnowLuma v1.14.22，
198 个接口），来源是 SnowLuma WebUI 的 `GET /api/debug/actions`（只读），
插件运行时不联网、也不需要 WebUI 登录。

更新目录用的是**维护者本地脚本**，不在插件仓库里（仓库只收生成好的 JSON）：

```bash
# 1) 从运行中的 SL WebUI 导出原始目录（只读，在本机跑）
python tools/fetch_sl_action_catalog.py --port 5101 --password <webui密码> \
    -o tools/sl_action_catalog-<版本>.json

# 2) 精简 + 标注风险档位，生成插件内置目录
python tools/build_sl_catalog.py
```

这两个脚本放在维护者的开发工作区（`<工作区>/tools/`）下，不属于发版产物；
装好插件的人只会看到 `assets/sl_catalog.json`。重新生成目录后，记得同步核对
`src/catalog.py` 里对风险档位的假设；`src/fold.py` 的接口数文案已经改成从目录
动态读取，不用再手改。

## 兼容性

插件只调 `adapter_api` / `log_api` / `permission_api` 三个模块（都是稳定入口）
和 `stream_api.get_stream()`。`stream_api` 从 1.0.0 到 2.0.0 只是把
`add_sent_message_to_history` 改名为 `add_message_to_history`，`get_stream()`
的名称与签名一直没变——所以 manifest **故意不声明 `stream_api`**：声明 1.0.0 会
挡住 2.x 核心、声明 2.0.0 会挡住还没升级的 1.x 核心（框架对 major 不匹配直接
拒绝注册），不声明则两代都能装。真正需要新核心能力时，用 `min_core_version`
控下限，别用 `api_version` 写死次版本。

## 已知限制

1. 流式接口（`upload_file_stream` / `download_file_stream*` 等）需要多帧通道，
   当前适配器命令是单请求-单响应，暂不适配。
2. `sl_requests` 依赖 `snowluma_adapter` 把 request 事件注入上下文的现有行为；
   更换适配器时需要重新确认 `extra.is_request` / `extra.flag` 字段。
3. 平台侧个别接口标注「未实现 / 占位」（如 `set_restart`、`create_collection`），
   调用会返回平台错误，属预期。
4. 语音 / 通话 / 纯二进制类接口（`get_record`、`send_group_ai_record`、
   `download_file_record_stream` 等）不做专用工具：LLM 消费不了音频本身，
   需要时用 `sl_call` 直接调（流式接口默认关闭）；`fetch_ptt_text`（语音转文字）
   这类能产出文字的仍可直接使用。
5. `sl_events` 的数据来源是「适配器已注入上下文的 notice 消息」：撤回、戳一戳、
   禁言、上传、精华、头衔、贴表情、申请都能看到；适配器侧直接丢弃的少数通知
   （`input_status`、`bot_status`、群名变更、资料点赞等）插件侧拿不到，
   要么接受看不到，要么改适配器 / 自建一个 WebSocket 客户端另收原始事件。
6. **好友动态（`get_qzone_feeds`）没有 tid、也没有结构化正文**，只有
   `{uin, nickname, time, appid, key, html}`；点赞/评论只能用自己空间说说
   （`kind=self`）里的 tid。

## 许可

MIT，作者 Aemeath。

参考与致谢：`snowluma_extension` / `snowluma_adapter`（言柒，AGPL-3.0）。
本插件只参考了调用方式、事件字段与能力划分，**没有复制它们的代码**；若将来
复用其中代码，会在对应文件头标注原作者与 AGPL-3.0 许可。
