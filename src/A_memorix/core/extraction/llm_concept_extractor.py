from __future__ import annotations

import json

from src.common.logger import get_logger
from src.services.llm_service import LLMServiceClient

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
    """LLM 语义概念提取器"""

    def __init__(self, task_name: str = "utils") -> None:
        self._llm = LLMServiceClient(task_name=task_name)

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
            logger.error(f"LLM 概念提取失败，跳过本次 observe: {e}")
            return ExtractionResult()

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