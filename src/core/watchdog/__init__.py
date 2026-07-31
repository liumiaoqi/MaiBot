"""事件循环阻塞检测与 Runner 健康结果桥接上报的领域模型与引擎。

核心层不依赖组件具体类，借鉴 Linux watchdog/hung_task 双层检测 + touch 机制：
- EventLoopMonitor：主循环协程刷新 touch 时间戳，独立线程周期检测阻塞
- RunnerHealthBridge：V2 回调桥接 + V1 旁路轮询，桥接非重检
- WatchdogAdapter：实现 WatchdogPort，组装引擎，经 ServiceManagerPort 上报
"""