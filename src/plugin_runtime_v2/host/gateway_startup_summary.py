"""网关启动摘要适配器 — 收集 MessageGateway 注册状态并输出结构化日志。"""


from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.gateway_startup_summary")


class GatewayStartupSummaryAdapter:
    """收集每个 MessageGateway 的注册状态，在启动摘要中输出汇总条目。

    实现 V2GatewayRegistrar 所需的鸭子类型接口 report_gateway_status()。
    每次状态上报时立即输出一条结构化日志；最终汇总通过 format_summary() 获取。
    """

    def __init__(self) -> None:
        # key = (plugin_id, gateway_name) → value = {status, detail, platform}
        self._entries: dict[tuple[str, str], dict[str, str]] = {}

    def report_gateway_status(
        self,
        plugin_id: str,
        gateway_name: str,
        status: str,
        detail: str = "",
        platform: str = "",
    ) -> None:
        """上报单个网关的注册状态（由 V2GatewayRegistrar 调用）。"""
        self._entries[(plugin_id, gateway_name)] = {
            "status": status,
            "detail": detail,
            "platform": platform,
        }
        detail_str = f" — {detail}" if detail else ""
        logger.info(
            "[网关启动摘要] %s/%s (platform=%s): %s%s",
            plugin_id,
            gateway_name,
            platform or "?",
            status,
            detail_str,
        )

    def format_summary(self) -> str:
        """返回网关注册状态的多行汇总文本（供启动摘要追加）。"""
        if not self._entries:
            return ""
        lines = ["", "=== MessageGateway 注册状态 ==="]
        for (plugin_id, gateway_name), info in sorted(self._entries.items()):
            status_label = _STATUS_LABELS.get(info["status"], info["status"])
            detail_str = f" ({info['detail']})" if info["detail"] else ""
            lines.append(
                f"  {plugin_id}/{gateway_name} "
                f"[platform={info['platform'] or '?'}] "
                f"→ {status_label}{detail_str}"
            )
        return "\n".join(lines)

    def get_entry_count(self) -> int:
        """返回已收集的网关状态条目数。"""
        return len(self._entries)


_STATUS_LABELS: dict[str, str] = {
    "registered": "✓ 已注册并绑定",
    "failed": "✗ 注册失败",
    "scope_denied": "⚠ scope 未授予",
    "not_ready": "○ 未就绪",
    "disconnected": "○ 已断开",
}