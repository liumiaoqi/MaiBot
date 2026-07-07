"""提醒管理器 — 定时提醒的创建、持久化与触发检查。

提醒分两种：
- 直接提醒：用户明确要求"3点提醒我开会"
- 间接提醒：用户提到"下午有个考试"，到时间关心一下

持久化使用 JSONL 文件，按 session 分文件存储。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("agent_autonomy.reminder")

_TZ_CN = timezone(timedelta(hours=8))
_DEFAULT_STORE_DIR = Path("data/reminders")


def _now() -> datetime:
    return datetime.now(_TZ_CN)


@dataclass
class Reminder:
    """一条提醒记录。"""

    reminder_id: str
    trigger_time: str
    context: str
    is_direct: bool
    session_id: str
    agent_id: str
    fired: bool = False
    created_at: str = field(default_factory=lambda: _now().isoformat())

    @property
    def trigger_datetime(self) -> datetime:
        return datetime.fromisoformat(self.trigger_time)

    def to_dict(self) -> dict:
        return {
            "reminder_id": self.reminder_id,
            "trigger_time": self.trigger_time,
            "context": self.context,
            "is_direct": self.is_direct,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "fired": self.fired,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Reminder:
        return cls(
            reminder_id=data["reminder_id"],
            trigger_time=data["trigger_time"],
            context=data["context"],
            is_direct=data["is_direct"],
            session_id=data["session_id"],
            agent_id=data["agent_id"],
            fired=data.get("fired", False),
            created_at=data.get("created_at", _now().isoformat()),
        )


def parse_time_from_text(text: str) -> tuple[datetime | None, str, bool]:
    """从文本中解析时间。返回 (触发时间, 上下文, 是否直接提醒)。"""
    now = _now()
    is_direct = bool(re.search(r"提醒|记得|别忘了|叫我|通知", text))

    m = re.match(r"(\d{1,2})[点时:：](\d{0,2})?", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target, text, is_direct

    if re.search(r"下午|晚上|今晚", text):
        m2 = re.search(r"(\d{1,2})[点时]?", text)
        if m2:
            hour = int(m2.group(1))
            hour = hour + 12 if hour < 12 else hour
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target, text, is_direct
        target = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target, text, is_direct

    if re.search(r"待会儿|一会儿|等下|稍后|马上|等一下", text):
        return now + timedelta(minutes=1), text, is_direct

    if re.search(r"(\d+)(分钟|分)后", text):
        m3 = re.search(r"(\d+)(分钟|分)后", text)
        if m3:
            mins = int(m3.group(1))
            return now + timedelta(minutes=mins), text, is_direct

    if re.search(r"明天", text):
        m4 = re.search(r"(\d{1,2})[点时]?", text)
        if m4:
            hour = int(m4.group(1))
            target = (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
        else:
            target = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return target, text, is_direct

    return None, text, is_direct


async def extract_reminder_with_llm(text: str, client) -> Reminder | None:
    """用 LLM 从文本中提取提醒信息。当规则解析不到时间时使用。"""
    from src.llm_models.payload_content.message import MessageBuilder, RoleType
    from src.common.data_models.llm_service_data_models import LLMGenerationOptions

    now = _now()
    prompt = (
        "你是一个时间提取器。用户说了一句话，请判断是否包含未来的时间/事件安排。\n"
        f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}\n"
        f"用户说的话：{text}\n\n"
        "如果包含时间安排，请用以下格式回复（不要回复其他内容）：\n"
        "TIME: YYYY-MM-DD HH:MM\n"
        "CONTEXT: 一句话描述事件\n"
        "TYPE: direct 或 indirect\n\n"
        "direct = 用户明确要求提醒\n"
        "indirect = 用户提到有事，但没明确要求提醒\n\n"
        "如果不包含时间安排，回复：NONE"
    )

    def message_factory(_client):
        return [
            MessageBuilder().set_role(RoleType.System).add_text_part(prompt).build(),
            MessageBuilder().set_role(RoleType.User).add_text_part(text).build(),
        ]

    try:
        result = await client.generate_response_with_messages(
            message_factory=message_factory,
            options=LLMGenerationOptions(temperature=0.0),
        )
        response = (result.response or "").strip()
        if response == "NONE" or not response:
            return None

        time_line = ""
        context_line = ""
        type_line = "indirect"
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("TIME:"):
                time_line = line[5:].strip()
            elif line.startswith("CONTEXT:"):
                context_line = line[8:].strip()
            elif line.startswith("TYPE:"):
                type_line = line[5:].strip()

        if not time_line:
            return None

        try:
            trigger_time = datetime.strptime(time_line, "%Y-%m-%d %H:%M").replace(tzinfo=_TZ_CN)
        except ValueError:
            return None

        if trigger_time <= now:
            return None

        return Reminder(
            reminder_id=f"llm_{int(now.timestamp())}",
            trigger_time=trigger_time.isoformat(),
            context=context_line or text,
            is_direct=(type_line == "direct"),
            session_id="",
            agent_id="",
        )
    except Exception as e:
        logger.warning(f"[reminder] LLM提取失败: {e}")
        return None


class ReminderStore:
    """提醒持久化存储，使用 JSONL 文件。按 session 分文件。"""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or _DEFAULT_STORE_DIR
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file(self, session_id: str) -> Path:
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return self._store_dir / f"{safe_id}.jsonl"

    def load_pending(self, session_id: str) -> list[Reminder]:
        """加载指定 session 的未触发提醒。"""
        file_path = self._get_session_file(session_id)
        if not file_path.exists():
            return []

        reminders: list[Reminder] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        reminders.append(Reminder.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception as e:
            logger.warning(f"[reminder] 加载提醒失败: session={session_id} error={e}")

        return [r for r in reminders if not r.fired]

    def save(self, reminder: Reminder) -> None:
        """追加一条提醒。"""
        file_path = self._get_session_file(reminder.session_id)
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(reminder.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[reminder] 保存提醒失败: {e}")

    def mark_fired(self, reminder: Reminder) -> None:
        """标记提醒已触发。Load-Modify-Save 全量覆写。"""
        session_id = reminder.session_id
        file_path = self._get_session_file(session_id)
        if not file_path.exists():
            return

        all_reminders: list[Reminder] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        all_reminders.append(Reminder.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception as e:
            logger.warning(f"[reminder] 读取提醒失败: session={session_id} error={e}")
            return

        for r in all_reminders:
            if r.reminder_id == reminder.reminder_id:
                r.fired = True

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for r in all_reminders:
                    f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[reminder] 更新提醒失败: {e}")


class ReminderManager:
    """提醒管理器 — 创建、检查、持久化。"""

    def __init__(self, store: Optional[ReminderStore] = None) -> None:
        self._store = store or ReminderStore()
        self._in_memory: dict[str, list[Reminder]] = {}

    def load_session(self, session_id: str) -> None:
        """启动时加载 session 的未触发提醒到内存。"""
        pending = self._store.load_pending(session_id)
        self._in_memory[session_id] = pending
        if pending:
            logger.info(f"[reminder] 加载 {len(pending)} 条待触发提醒: session={session_id}")

    def add(self, reminder: Reminder) -> None:
        """添加一条提醒。"""
        sid = reminder.session_id
        if sid not in self._in_memory:
            self._in_memory[sid] = []
        self._in_memory[sid].append(reminder)
        self._store.save(reminder)
        logger.info(
            f"[reminder] 已记录: agent={reminder.agent_id} "
            f"time={reminder.trigger_time} context={reminder.context} "
            f"direct={reminder.is_direct}"
        )

    def check_due(self, session_id: str) -> list[Reminder]:
        """检查到期的提醒，返回已触发的列表。"""
        now = _now()
        pending = self._in_memory.get(session_id, [])
        due = []
        for r in pending:
            if not r.fired and now >= r.trigger_datetime:
                r.fired = True
                self._store.mark_fired(r)
                due.append(r)
                logger.info(
                    f"[reminder] 触发: agent={r.agent_id} context={r.context}"
                )
        self._in_memory[session_id] = [r for r in pending if not r.fired]
        return due

    def get_pending(self, session_id: str) -> list[Reminder]:
        """获取未触发的提醒列表。"""
        return [r for r in self._in_memory.get(session_id, []) if not r.fired]

    async def try_create(
        self,
        text: str,
        session_id: str,
        agent_id: str,
        client=None,
    ) -> Reminder | None:
        """尝试从用户消息中创建提醒。规则优先，匹配不到再用 LLM。"""
        trigger_time, context, is_direct = parse_time_from_text(text)
        if trigger_time is None:
            if client is None:
                return None
            reminder = await extract_reminder_with_llm(text, client)
            if reminder is None:
                return None
            reminder.session_id = session_id
            reminder.agent_id = agent_id
        else:
            reminder = Reminder(
                reminder_id=f"rule_{int(_now().timestamp())}_{agent_id}",
                trigger_time=trigger_time.isoformat(),
                context=context,
                is_direct=is_direct,
                session_id=session_id,
                agent_id=agent_id,
            )

        self.add(reminder)
        return reminder