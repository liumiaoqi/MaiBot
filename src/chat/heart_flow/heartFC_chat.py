from rich.traceback import install
from typing import List, Optional, TYPE_CHECKING

import asyncio
import random
import time
import traceback

from src.chat.message_receive.chat_manager import chat_manager
from src.common.logger import get_logger
from src.common.utils.utils_config import ChatConfigUtils, ExpressionConfigUtils
from src.config.config import global_config
from src.config.file_watcher import FileChange
from src.learners.expression_learner import ExpressionLearner
from src.learners.jargon_miner import JargonMiner

from .heartFC_utils import CycleDetail

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage

install(extra_lines=5)

logger = get_logger("heartFC_chat")


class HeartFChatting:
    """
    管理一个连续的Focus Chat聊天会话
    用于在特定的聊天会话里面生成回复
    """

    def __init__(self, session_id: str):
        """
        初始化 HeartFChatting 实例

        Args:
            session_id: 聊天会话ID
        """
        # 基础属性
        self.session_id = session_id
        session_name = chat_manager.get_session_name(session_id) or session_id
        self.log_prefix = f"[{session_name}]"
        self.session_name = session_name

        # 系统运行状态
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._cycle_counter: int = 0
        self._hfc_lock: asyncio.Lock = asyncio.Lock()  # 用于保护 _hfc_func 的并发访问
        # 聊天频率相关
        self._consecutive_no_reply_count = 0  # 跟踪连续 no_reply 次数，用于动态调整阈值
        self._talk_frequency_adjust: float = 1.0  # 发言频率修正值，默认为1.0，可以根据需要调整

        # HFC内消息缓存
        self.message_cache: List[SessionMessage] = []

        # Asyncio Event 用于控制循环的开始和结束
        self._cycle_event = asyncio.Event()

        # 表达方式相关内容
        self._min_messages_for_extraction = 30  # 最少提取消息数
        self._min_extraction_interval = 60  # 最小提取时间间隔，单位为秒
        self._last_extraction_time: float = 0.0  # 上次提取的时间戳
        expr_use, jargon_learn, expr_learn = ExpressionConfigUtils.get_expression_config_for_chat(session_id)
        self._enable_expression_use = expr_use  # 允许使用表达方式，但不一定启用学习
        self._enable_expression_learning = expr_learn  # 允许学习表达方式
        self._enable_jargon_learning = jargon_learn  # 允许学习黑话
        # 表达学习器
        self._expression_learner: ExpressionLearner = ExpressionLearner(session_id)
        # 黑话挖掘器
        self._jargon_miner: JargonMiner = JargonMiner(session_id, session_name=session_name)

        # TODO: ChatSummarizer 聊天总结器重构

    # ====== 公开方法 ======

    async def start(self):
        """启动 HeartFChatting 的主循环"""
        # 先检查是否已经启动运行
        if self._running:
            logger.debug(f"{self.log_prefix} 已经在运行中，无需重复启动")
            return

        try:
            self._running = True
            self._cycle_event.clear()  # 确保事件初始状态为未设置

            self._loop_task = asyncio.create_task(self.main_loop())
            self._loop_task.add_done_callback(self._handle_loop_completion)

            logger.info(f"{self.log_prefix} HeartFChatting 启动完成")
        except Exception as e:
            logger.error(f"{self.log_prefix} 启动 HeartFChatting 失败: {e}", exc_info=True)
            self._running = False  # 确保状态正确
            self._cycle_event.set()  # 确保事件被设置，避免死锁
            self._loop_task = None  # 确保任务引用被清理
            raise

    async def stop(self):
        """停止 HeartFChatting 的主循环"""
        if not self._running:
            logger.debug(f"{self.log_prefix} HeartFChatting 已经停止，无需重复停止")
            return

        self._running = False
        self._cycle_event.set()  # 触发事件，通知循环结束

        if self._loop_task:
            self._loop_task.cancel()  # 取消主循环任务
            try:
                await self._loop_task  # 等待任务完成
            except asyncio.CancelledError:
                logger.info(f"{self.log_prefix} HeartFChatting 主循环已成功取消")
            except Exception as e:
                logger.error(f"{self.log_prefix} 停止 HeartFChatting 时发生错误: {e}", exc_info=True)
            finally:
                self._loop_task = None  # 确保任务引用被清理

        logger.info(f"{self.log_prefix} HeartFChatting 已停止")

    def adjust_talk_frequency(self, new_value: float):
        """调整发言频率的调整值

        Args:
            new_value: 新的修正值，必须为非负数。值越大，修正发言频率越高；值越小，修正发言频率越低。
        """
        self._talk_frequency_adjust = max(0.0, new_value)

    async def register_message(self, message: "SessionMessage"):
        """注册一条消息到 HeartFChatting 的缓存中，并检测其是否产生提及，决定是否唤醒聊天

        Args:
            message: 待注册的消息对象
        """
        self.message_cache.append(message)
        # 先检查at必回复
        if global_config.chat.inevitable_at_reply and message.is_at:
            async with self._hfc_lock:  # 确保与主循环逻辑的互斥访问
                await self._judge_and_response(message)
            return  # 直接返回，避免同一条消息被主循环再次处理
        # 再检查提及必回复
        if global_config.chat.mentioned_bot_reply and message.is_mentioned:
            # 直接获取锁，确保一定一定触发回复逻辑，不受当前是否正在执行主循环的影响
            async with self._hfc_lock:  # 确保与主循环逻辑的互斥访问
                await self._judge_and_response(message)
            return

    async def main_loop(self):
        try:
            while self._running and not self._cycle_event.is_set():
                if not self._hfc_lock.locked():
                    async with self._hfc_lock:  # 确保主循环逻辑的互斥访问
                        await self._hfc_func()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} HeartFChatting: 主循环被取消，正在关闭")
        except Exception as e:
            logger.error(f"{self.log_prefix} 麦麦聊天意外错误: {e}，将于3s后尝试重新启动")
            await self.stop()  # 确保状态正确
            await asyncio.sleep(3)
            await self.start()  # 尝试重新启动

    async def _config_callback(self, file_change: Optional[FileChange] = None):
        """配置文件变更回调函数"""
        # TODO: 根据配置文件变动重新计算相关参数：
        """
        需要计算的参数：
        self._enable_expression_use = expr_use # 允许使用表达方式，但不一定启用学习
        self._enable_expression_learning = expr_learn # 允许学习表达方式
        self._enable_jargon_learning = jargon_learn # 允许学习黑话
        """

    # ====== 心流聊天核心逻辑 ======
    async def _hfc_func(self, mentioned_message: Optional["SessionMessage"] = None):
        """心流聊天的主循环逻辑"""
        if self._consecutive_no_reply_count >= 5:
            threshold = 2
        elif self._consecutive_no_reply_count >= 3:
            threshold = 2 if random.random() < 0.5 else 1
        else:
            threshold = 1

        if len(self.message_cache) < threshold:
            await asyncio.sleep(0.2)
            return True

        talk_value_threshold = (
            random.random() * ChatConfigUtils.get_talk_value(self.session_id) * self._talk_frequency_adjust
        )
        if mentioned_message and global_config.chat.mentioned_bot_reply:
            await self._judge_and_response(mentioned_message)
        elif random.random() < talk_value_threshold:
            await self._judge_and_response()
        return True

    async def _judge_and_response(self, mentioned_message: Optional["SessionMessage"] = None):
        """判定和生成回复"""
        asyncio.create_task(self._trigger_expression_learning(self.message_cache))
        # TODO: 完成反思器之后的逻辑
        current_cycle_detail = self._start_cycle()
        logger.info(f"{self.log_prefix} 开始第{self._cycle_counter}次思考")

        # TODO: 动作检查逻辑
        # TODO: Planner逻辑
        # TODO: 动作执行逻辑

        self._end_cycle(current_cycle_detail)
        await asyncio.sleep(0.1)  # 最小等待时间，避免过快循环
        return True

    def _handle_loop_completion(self, task: asyncio.Task):
        """当 _hfc_func 任务完成时执行的回调。"""
        try:
            if exception := task.exception():
                logger.error(f"{self.log_prefix} HeartFChatting: 脱离了聊天(异常): {exception}")
                logger.error(traceback.format_exc())  # Log full traceback for exceptions
            else:
                logger.info(f"{self.log_prefix} HeartFChatting: 脱离了聊天 (外部停止)")
        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} HeartFChatting: 结束了聊天")

    # ====== 学习器触发逻辑 ======
    async def _trigger_expression_learning(self, messages: List["SessionMessage"]):
        self._expression_learner.add_messages(messages)
        if time.time() - self._last_extraction_time < self._min_extraction_interval:
            return
        if self._expression_learner.get_cache_size() < self._min_messages_for_extraction:
            return
        if not self._enable_expression_learning:
            return
        extraction_end_time = time.time()
        logger.info(
            f"聊天流 {self.session_name} 提取到 {len(messages)} 条消息，"
            f"时间窗口: {self._last_extraction_time:.2f} - {extraction_end_time:.2f}"
        )
        self._last_extraction_time = extraction_end_time
        try:
            jargon_miner = self._jargon_miner if self._enable_jargon_learning else None
            learnt_style = await self._expression_learner.learn(jargon_miner)
            if learnt_style:
                logger.info(f"{self.log_prefix} 表达学习完成")
            else:
                logger.debug(f"{self.log_prefix} 表达学习未获得有效结果")
        except Exception as e:
            logger.error(f"{self.log_prefix} 表达学习失败: {e}", exc_info=True)

    # ====== 记录循环执行信息相关逻辑 ======
    def _start_cycle(self) -> CycleDetail:
        self._cycle_counter += 1
        current_cycle_detail = CycleDetail(cycle_id=self._cycle_counter)
        current_cycle_detail.thinking_id = f"tid{str(round(time.time(), 2))}"
        return current_cycle_detail

    def _end_cycle(self, cycle_detail: CycleDetail, only_long_execution: bool = True):
        cycle_detail.end_time = time.time()
        timer_strings: List[str] = [
            f"{name}: {duration:.2f}s"
            for name, duration in cycle_detail.time_records.items()
            if not only_long_execution or duration >= 0.1
        ]
        logger.info(
            f"{self.log_prefix} 第 {cycle_detail.cycle_id} 个心流循环完成"
            f"耗时: {cycle_detail.end_time - cycle_detail.start_time:.2f}秒\n"
            f"详细计时: {', '.join(timer_strings) if timer_strings else '无'}"
        )

        return cycle_detail

    # ====== Action相关逻辑 ======
    async def _execute_action(self, *args, **kwargs):
        """原ExecuteAction"""
        raise NotImplementedError("执行动作的逻辑尚未实现")  # TODO: 实现动作执行的逻辑，替换掉*args, **kwargs*占位符

    async def _execute_other_actions(self, *args, **kwargs):
        """原HandleAction"""
        raise NotImplementedError(
            "执行其他动作的逻辑尚未实现"
        )  # TODO: 实现其他动作执行的逻辑, 替换掉*args, **kwargs*占位符

    # ====== 响应发送相关方法 ======
    async def _send_response(self, *args, **kwargs):
        raise NotImplementedError("发送回复的逻辑尚未实现")  # TODO: 实现发送回复的逻辑，替换掉*args, **kwargs*占位符
        # 传入的消息至少应该是个MessageSequence实例，最好是SessionMessage实例，随后可直接转化为MessageSending实例
