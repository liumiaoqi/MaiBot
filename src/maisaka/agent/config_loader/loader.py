from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from ..config import AgentConfig

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class AgentConfigLoader:
    """从 Markdown Frontmatter 文件加载智能体配置"""

    def __init__(self, config_dir: str | Path = "agents/") -> None:
        self._config_dir = Path(config_dir)
        self._cache: dict[str, tuple[float, AgentConfig]] = {}
        self._mtime_cache: dict[str, float] = {}

    def load(self, agent_id: str) -> Optional[AgentConfig]:
        """加载指定智能体的配置，支持缓存和热重载"""
        file_path = self._find_config_file(agent_id)
        if file_path is None:
            logger.warning("智能体配置文件未找到: %s", agent_id)
            return None

        mtime = file_path.stat().st_mtime
        cached = self._cache.get(agent_id)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        config = self._load_file(file_path)
        if config is not None:
            self._cache[agent_id] = (mtime, config)
        return config

    def load_all(self) -> dict[str, AgentConfig]:
        """加载配置目录下所有智能体配置"""
        if not self._config_dir.exists():
            logger.warning("智能体配置目录不存在: %s", self._config_dir)
            return {}

        result: dict[str, AgentConfig] = {}
        for file_path in sorted(self._config_dir.glob("*.md")):
            agent_id = file_path.stem
            config = self._load_file(file_path)
            if config is not None:
                if config.agent_id != agent_id:
                    logger.warning(
                        "配置文件名与agent_id不匹配: 文件=%s, agent_id=%s",
                        agent_id,
                        config.agent_id,
                    )
                result[config.agent_id] = config
        return result

    def reload(self, agent_id: str) -> Optional[AgentConfig]:
        """强制重新加载指定智能体配置"""
        self._cache.pop(agent_id, None)
        return self.load(agent_id)

    def reload_all(self) -> dict[str, AgentConfig]:
        """强制重新加载所有智能体配置"""
        self._cache.clear()
        return self.load_all()

    def _find_config_file(self, agent_id: str) -> Optional[Path]:
        """查找智能体配置文件"""
        file_path = self._config_dir / f"{agent_id}.md"
        if file_path.exists():
            return file_path
        return None

    def _load_file(self, file_path: Path) -> Optional[AgentConfig]:
        """从Markdown文件加载配置"""
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.error("读取智能体配置文件失败: %s, 错误: %s", file_path, e)
            return None

        frontmatter_data, body = self._parse_frontmatter(content)
        if frontmatter_data is None:
            logger.error("解析Frontmatter失败: %s", file_path)
            return None

        if body.strip():
            frontmatter_data["personality"] = body.strip()

        try:
            config = AgentConfig.model_validate(frontmatter_data)
        except Exception as e:
            logger.error("验证智能体配置失败: %s, 错误: %s", file_path, e)
            return None

        logger.debug("加载智能体配置: %s -> %s", file_path.name, config.agent_id)
        return config

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[Optional[dict], str]:
        """解析Markdown Frontmatter，返回(frontmatter_data, body)"""
        match = _FRONTMATTER_PATTERN.match(content)
        if match is None:
            return None, content

        yaml_str = match.group(1)
        body = content[match.end() :]

        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            logger.error("YAML解析失败: %s", e)
            return None, body

        if not isinstance(data, dict):
            logger.error("Frontmatter不是有效的YAML字典")
            return None, body

        return data, body