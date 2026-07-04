"""知识存储 — 持久化行为资产。

使用 JSONL 文件存储提取出的行为资产，支持按智能体查询和去重。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .distill import DistillAsset, DistillAssetType

logger = logging.getLogger(__name__)

_DEFAULT_STORE_DIR = Path("data/knowledge_assets")


@dataclass
class KnowledgeAsset:
    """持久化的知识资产记录。"""

    asset_id: str
    asset_type: str
    agent_id: str
    pattern_key: str
    pattern_description: str
    evidence_count: int = 0
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "agent_id": self.agent_id,
            "pattern_key": self.pattern_key,
            "pattern_description": self.pattern_description,
            "evidence_count": self.evidence_count,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeAsset":
        return cls(
            asset_id=data.get("asset_id", ""),
            asset_type=data.get("asset_type", ""),
            agent_id=data.get("agent_id", ""),
            pattern_key=data.get("pattern_key", ""),
            pattern_description=data.get("pattern_description", ""),
            evidence_count=data.get("evidence_count", 0),
            confidence=data.get("confidence", 0.0),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )

    @classmethod
    def from_distill_asset(cls, asset: DistillAsset) -> "KnowledgeAsset":
        return cls(
            asset_id=f"{asset.asset_type.value}_{asset.agent_id}_{asset.pattern_key}",
            asset_type=asset.asset_type.value,
            agent_id=asset.agent_id,
            pattern_key=asset.pattern_key,
            pattern_description=asset.pattern_description,
            evidence_count=asset.evidence_count,
            confidence=asset.confidence,
            metadata=asset.metadata,
        )


class KnowledgeStore:
    """持久知识存储，使用 JSONL 文件。

    每个智能体一个文件，支持去重（基于 asset_id）。
    """

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or _DEFAULT_STORE_DIR
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def store_asset(self, asset: DistillAsset) -> bool:
        """存储行为资产。幂等：已存在则更新。"""
        knowledge = KnowledgeAsset.from_distill_asset(asset)
        file_path = self._get_agent_file(knowledge.agent_id)

        existing = self._load_all(knowledge.agent_id)
        existing_map = {a.asset_id: a for a in existing}

        if knowledge.asset_id in existing_map:
            old = existing_map[knowledge.asset_id]
            old.evidence_count = knowledge.evidence_count
            old.confidence = knowledge.confidence
            old.pattern_description = knowledge.pattern_description
            old.metadata = knowledge.metadata
            old.updated_at = time.time()
            logger.debug("更新知识资产: %s", knowledge.asset_id)
        else:
            existing.append(knowledge)
            logger.debug("新增知识资产: %s", knowledge.asset_id)

        self._save_all(knowledge.agent_id, existing)
        return True

    def get_assets(
        self,
        agent_id: str,
        asset_type: Optional[DistillAssetType] = None,
    ) -> list[KnowledgeAsset]:
        """获取指定智能体的知识资产。"""
        all_assets = self._load_all(agent_id)
        if asset_type is not None:
            return [a for a in all_assets if a.asset_type == asset_type.value]
        return all_assets

    def delete_asset(self, agent_id: str, asset_id: str) -> bool:
        """删除指定知识资产。"""
        existing = self._load_all(agent_id)
        filtered = [a for a in existing if a.asset_id != asset_id]
        if len(filtered) == len(existing):
            return False
        self._save_all(agent_id, filtered)
        return True

    def _get_agent_file(self, agent_id: str) -> Path:
        return self._store_dir / f"{agent_id}.jsonl"

    def _load_all(self, agent_id: str) -> list[KnowledgeAsset]:
        file_path = self._get_agent_file(agent_id)
        if not file_path.exists():
            return []

        assets: list[KnowledgeAsset] = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        assets.append(KnowledgeAsset.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception as e:
            logger.warning("加载知识资产失败: %s", e)

        return assets

    def _save_all(self, agent_id: str, assets: list[KnowledgeAsset]) -> None:
        file_path = self._get_agent_file(agent_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for asset in assets:
                    f.write(json.dumps(asset.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("保存知识资产失败: %s", e)