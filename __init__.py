"""snowluma_full 插件包：SnowLuma 全量接口扩展。

只提供一套「少入口 + 宽覆盖」的 LLM 组件，把 SnowLuma 暴露的 OneBot v11 接口
（当前版本 198 个）纳入可调用范围，而不是每个接口注册一个工具。

包结构与职责：
- ``config.py``：插件配置（启用开关、危险接口门控、结果截断、文件沙箱、群范围）；
- ``src/catalog.py``：内置接口目录（``assets/sl_catalog.json``，兼容旧 ``data/``）的加载与检索；
- ``src/bridge.py``：通过框架 ``adapter_api`` 调平台的薄封装，不依赖具体适配器实现；
- ``src/sandbox.py`` / ``src/guard.py`` / ``src/auth.py``：文件参数白名单与 owner 闸门；
- ``src/tools/sl_help.py``：``sl_help`` 工具——按关键词/分类检索接口目录；
- ``src/actions/sl_call.py``：``sl_call`` 动作——按接口名 + 参数对象调用平台接口；
- ``plugin.py``：插件入口（``@register_plugin``）。

设计边界（与现有插件分工）：
- 消息收发、事件转消息由 ``snowluma_adapter`` 负责，本插件不重造；
- 常用群管理动作 ``snowluma_extension`` 已有，本插件**参考其思路、不复制其代码**，
  并以「全量可调 + 高频强化」为目标补齐缺口；
- 若后续复用第三方代码，将在对应文件标注原作者与许可证。

插件入口在 :mod:`plugin` 中注册。本 ``__init__`` 不导入入口模块，避免加载器
以 ``snowluma_full.plugin`` 执行时的循环导入。
"""

__all__: list[str] = []
