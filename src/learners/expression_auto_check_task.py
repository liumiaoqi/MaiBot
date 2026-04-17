"""
表达方式自动检查定时任务。

功能：
1. 定期随机选取指定数量的表达方式
2. 使用 LLM 进行评估
3. 通过评估的：rejected=0, checked=1
4. 未通过评估的：rejected=1, checked=1
"""

import asyncio
import random
from typing import List

from sqlmodel import select

from src.common.data_models.llm_service_data_models import LLMGenerationOptions
from src.common.database.database import get_db_session
from src.common.database.database_model import Expression
from src.common.logger import get_logger
from src.config.config import global_config
from src.learners.expression_review_store import get_review_state, set_review_state
from src.learners.expression_utils import parse_evaluation_response
from src.manager.async_task_manager import AsyncTask
from src.services.llm_service import LLMServiceClient

logger = get_logger("expressor")


def create_evaluation_prompt(situation: str, style: str) -> str:
    """
    创建评估提示词。

    Args:
        situation: 情景
        style: 风格

    Returns:
        评估提示词
    """
    base_criteria = [
        "表达方式或言语风格是否与使用条件或使用情景匹配",
        "允许部分语法错误或口语化或缺省出现",
        "表达方式不能太过特指，需要具有泛用性",
        "一般不涉及具体的人名或名称",
    ]

    custom_criteria = global_config.expression.expression_auto_check_custom_criteria

    all_criteria = base_criteria.copy()
    if custom_criteria:
        all_criteria.extend(custom_criteria)

    criteria_list = "\n".join([f"{i + 1}. {criterion}" for i, criterion in enumerate(all_criteria)])

    prompt = f"""请评估以下表达方式或语言风格以及使用条件或使用情景是否合适：
使用条件或使用情景：{situation}
表达方式或言语风格：{style}

请从以下方面进行评估：
{criteria_list}

请以 JSON 格式输出评估结果：
{{
    "suitable": true/false,
    "reason": "评估理由（如果不合适，请说明原因）"
}}
如果合适，suitable 设为 true；如果不合适，suitable 设为 false，并在 reason 中说明原因。
请严格按照 JSON 格式输出，不要包含其他内容。"""

    return prompt


judge_llm = LLMServiceClient(task_name="utils", request_type="expression_check")


async def single_expression_check(situation: str, style: str) -> tuple[bool, str, str | None]:
    """
    执行单次 LLM 评估。

    Args:
        situation: 情景
        style: 风格

    Returns:
        (suitable, reason, error) 元组，如果出错则 suitable 为 False，error 包含错误信息
    """
    try:
        prompt = create_evaluation_prompt(situation, style)
        logger.debug(f"正在评估表达方式: situation={situation}, style={style}")

        generation_result = await judge_llm.generate_response(
            prompt=prompt,
            options=LLMGenerationOptions(temperature=0.6, max_tokens=1024),
        )
        response = generation_result.response
        logger.debug(f"LLM响应: {response}")

        evaluation = parse_evaluation_response(response)

        suitable = bool(evaluation.get("suitable", False))
        reason = str(evaluation.get("reason", "未提供理由"))

        logger.debug(f"评估结果: {'通过' if suitable else '不通过'}")
        return suitable, reason, None

    except Exception as e:
        logger.error(f"评估表达方式 (situation={situation}, style={style}) 时出错: {e}")
        return False, f"评估过程出错: {str(e)}", str(e)


class ExpressionAutoCheckTask(AsyncTask):
    """表达方式自动检查定时任务。"""

    def __init__(self):
        check_interval = global_config.expression.expression_auto_check_interval
        super().__init__(
            task_name="Expression Auto Check Task",
            wait_before_start=60,
            run_interval=check_interval,
        )

    async def _select_expressions(self, count: int) -> List[Expression]:
        """
        随机选择指定数量的未检查表达方式。

        Args:
            count: 需要选择的数量

        Returns:
            选中的表达方式列表
        """
        try:
            # 这里只做查询，避免退出上下文时自动提交导致 ORM 实例过期。
            with get_db_session(auto_commit=False) as session:
                statement = select(Expression)
                all_expressions = session.exec(statement).all()

            unevaluated_expressions = [expr for expr in all_expressions if not get_review_state(expr.id)["checked"]]

            if not unevaluated_expressions:
                logger.info("没有未检查的表达方式")
                return []

            selected_count = min(count, len(unevaluated_expressions))
            selected = random.sample(unevaluated_expressions, selected_count)

            logger.info(
                f"从 {len(unevaluated_expressions)} 条未检查表达方式中随机选择了 {selected_count} 条"
            )
            return selected

        except Exception as e:
            logger.error(f"选择表达方式时出错: {e}")
            return []

    async def _evaluate_expression(self, expression: Expression) -> bool:
        """
        评估单个表达方式。

        Args:
            expression: 要评估的表达方式

        Returns:
            True 表示通过，False 表示不通过
        """
        suitable, reason, error = await single_expression_check(
            expression.situation,
            expression.style,
        )

        try:
            set_review_state(expression.id, True, not suitable, "ai")

            status = "通过" if suitable else "不通过"
            # 保留这段注释，方便后续需要时恢复更详细的审核日志。
            # logger.info(
            #     f"表达方式评估完成 [ID: {expression.id}] - {status} | "
            #     f"Situation: {expression.situation}... | "
            #     f"Style: {expression.style}... | "
            #     f"Reason: {reason[:50]}..."
            # )

            if error:
                logger.warning(f"表达方式评估时出现错误 [ID: {expression.id}]: {error}")

            logger.debug(f"表达方式 [ID: {expression.id}] 评估完成: {status}, reason={reason}")
            return suitable

        except Exception as e:
            logger.error(f"更新表达方式状态失败 [ID: {expression.id}]: {e}")
            return False

    async def run(self):
        """执行检查任务。"""
        try:
            if not global_config.expression.expression_self_reflect:
                logger.debug("表达方式自动检查未启用，跳过本次执行")
                return

            check_count = global_config.expression.expression_auto_check_count
            if check_count <= 0:
                logger.warning(f"检查数量配置无效: {check_count}，跳过本次执行")
                return

            logger.info(f"开始执行表达方式自动检查，本次将检查 {check_count} 条")

            expressions = await self._select_expressions(check_count)
            if not expressions:
                logger.info("没有需要检查的表达方式")
                return

            passed_count = 0
            failed_count = 0

            for index, expression in enumerate(expressions, 1):
                logger.debug(f"正在评估 [{index}/{len(expressions)}]: ID={expression.id}")

                if await self._evaluate_expression(expression):
                    passed_count += 1
                else:
                    failed_count += 1

                await asyncio.sleep(0.3)

            logger.info(
                f"表达方式自动检查完成: 总计 {len(expressions)} 条，通过 {passed_count} 条，不通过 {failed_count} 条"
            )

        except Exception as e:
            logger.error(f"执行表达方式自动检查任务时出错: {e}", exc_info=True)
