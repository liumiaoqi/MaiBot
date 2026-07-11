from __future__ import annotations

import json
from typing import Any

from src.common.logger import get_logger


from ..connectionist.enums import Valence
from ..connectionist.models import ExtractedConcept, ExtractedRelation, ExtractionResult

logger = get_logger("LLMConceptExtractor")

_CONCEPT_EXTRACTION_PROMPT = """你是一个概念提取器。从以下文本中提取概念、关系和情感极性。

要求：
1. 提取所有有意义的语义概念（人名、地点、物品、活动、情感、抽象概念）
2. 提取概念间的语义关系（不是简单共现，而是有意义的语义连接）
3. 判断整体情感极性
4. 归一化概念粒度：如"打游戏"和"游戏"统一为"游戏"，"吵架"和"争吵"统一为"吵架"
5. 为每个概念标注类型：person/object/place/activity/emotion/abstract

以JSON格式返回：
{
  "concepts": [{"name": "概念名", "type": "类型", "confidence": 0.9}],
  "relations": [{"source": "概念A", "target": "概念B", "relation": "关系描述"}],
  "valence": "positive/negative/neutral",
  "summary": "一句话摘要"
}

文本：
{text}"""


class LLMConceptExtractor:
    """LLM 语义概念提取器，LLM 失败时降级到 jieba 分词"""

    def __init__(self, llm_client: Any = None, *, task_name: str = "utils", concept_index=None) -> None:
        if llm_client is not None:
            self._llm = llm_client
        else:
            from src.services.llm_service import LLMServiceClient
            self._llm = LLMServiceClient(task_name=task_name)
        self._concept_index = concept_index

    async def extract(self, text: str) -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult()

        prompt = _CONCEPT_EXTRACTION_PROMPT.format(text=text)
        try:
            result = await self._llm.generate_response(prompt)
            content = result.response_text
            if not content:
                logger.error("LLM 概念提取返回空结果，跳过本次 observe")
                return ExtractionResult()
            return self._parse_response(content)
        except Exception as e:
            logger.warning(f"LLM 概念提取失败，降级到 jieba: {e}")
            return await self._fallback_extract(text)

    def _parse_response(self, content: str) -> ExtractionResult:
        try:
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"LLM 返回非标准 JSON，跳过: {e}, content={content[:200]}")
            return ExtractionResult()

        concepts = []
        for c in data.get("concepts", []):
            concepts.append(
                ExtractedConcept(
                    name=c.get("name", ""),
                    concept_type=c.get("type", "unknown"),
                    confidence=c.get("confidence", 1.0),
                )
            )

        relations = []
        for r in data.get("relations", []):
            relations.append(
                ExtractedRelation(
                    source=r.get("source", ""),
                    target=r.get("target", ""),
                    relation=r.get("relation", ""),
                )
            )

        valence_str = data.get("valence", "neutral")
        try:
            valence = Valence(valence_str)
        except ValueError:
            valence = Valence.NEUTRAL

        return ExtractionResult(
            concepts=concepts,
            relations=relations,
            valence=valence,
            summary=data.get("summary", ""),
        )

    async def _fallback_extract(self, text: str) -> ExtractionResult:
        if self._concept_index is None:
            logger.error("无 ConceptIndex，jieba 降级不可用，返回空结果")
            return ExtractionResult()
        from .semantic_concept_extractor import SemanticConceptExtractor
        extractor = SemanticConceptExtractor(self._concept_index)
        try:
            return await extractor.extract(text)
        except Exception as e:
            logger.error(f"jieba 降级提取也失败: {e}")
            return ExtractionResult()