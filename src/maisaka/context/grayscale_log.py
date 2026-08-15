"""灰度阶段 1 观察日志——ZG16-2 design 模块 D。

纯格式化函数，无副作用。固定字段 + 可 grep 提取（dsh 补充意见 2）。
"""


from typing import Optional


def format_grayscale_log(
    *,
    count_result: int,
    token_est: int,
    usage_prompt: Optional[int],
    overflow_ratio: float,
) -> str:
    """格式化灰度阶段 1 观察日志。

    Args:
        count_result: 条数选择结果（消息条数）。
        token_est: token 估算值。
        usage_prompt: provider 上一次 prompt_tokens（首次请求为 None）。
        overflow_ratio: 超窗比例（token_est / context_window）。

    Returns:
        固定格式日志字符串：[条数=N|token_est=M|usage_prompt=K|overflow_ratio=R]
    """
    usage_str = str(usage_prompt) if usage_prompt is not None else "null"
    return (
        f"[条数={count_result}|token_est={token_est}"
        f"|usage_prompt={usage_str}|overflow_ratio={overflow_ratio:.3f}]"
    )