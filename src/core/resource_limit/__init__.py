"""ZG-5 资源限制组件 — 插件资源计量、四档限制、压力分级、OOM 处理、事件传播。

对标 Linux cgroup memory controller v2 + vmpressure + OOM killer。
核心通过 ResourceLimitPort Protocol 接口交互，不直接导入本模块具体类。
适配器层（src/core/adapters/resource_limit_adapter.py）是唯一允许导入本模块的地方。
"""