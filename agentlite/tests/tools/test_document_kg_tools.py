"""工具专项测试 - 文档提取和知识图谱工具

本模块测试基于数据基底的工具功能，包括：
1. 文档读取和解析工具
2. 实体提取工具
3. 知识图谱查询工具
4. 推理工具
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentlite import Agent, Message, TextPart, tool


def tool_output(result: Any) -> Any:
    """兼容旧式返回值和 ToolResult 返回值."""
    return getattr(result, "output", result)


# =============================================================================
# 数据加载 fixtures
# =============================================================================


@pytest.fixture
def data_dir() -> Path:
    """返回测试数据目录路径."""
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def sample_article(data_dir: Path) -> str:
    """加载样例文章."""
    return (data_dir / "documents" / "sample_article.md").read_text(encoding="utf-8")


@pytest.fixture
def technical_spec(data_dir: Path) -> str:
    """加载技术规范文档."""
    return (data_dir / "documents" / "technical_spec.md").read_text(encoding="utf-8")


@pytest.fixture
def meeting_notes(data_dir: Path) -> str:
    """加载会议记录."""
    return (data_dir / "documents" / "meeting_notes.txt").read_text(encoding="utf-8")


@pytest.fixture
def knowledge_graph_entities(data_dir: Path) -> dict[str, Any]:
    """加载知识图谱实体数据."""
    with open(data_dir / "knowledge_base" / "entities.json") as f:
        return json.load(f)


@pytest.fixture
def knowledge_graph_relations(data_dir: Path) -> dict[str, Any]:
    """加载知识图谱关系数据."""
    with open(data_dir / "knowledge_base" / "relations.json") as f:
        return json.load(f)


@pytest.fixture
def graph_queries(data_dir: Path) -> list[dict[str, Any]]:
    """加载图谱查询测试用例."""
    with open(data_dir / "knowledge_base" / "graph_queries.yaml") as f:
        data = yaml.safe_load(f)
        return data.get("queries", [])


# =============================================================================
# 知识图谱工具实现
# =============================================================================


class KnowledgeGraph:
    """知识图谱内存存储."""

    def __init__(self, entities: list[dict], relations: list[dict]):
        self._entities = {e["id"]: e for e in entities}
        self._relations = relations
        self._index_by_type: dict[str, list[str]] = {}
        self._index_by_name: dict[str, str] = {}

        # 构建索引
        for entity_id, entity in self._entities.items():
            entity_type = entity.get("type", "Unknown")
            if entity_type not in self._index_by_type:
                self._index_by_type[entity_type] = []
            self._index_by_type[entity_type].append(entity_id)

            name = entity.get("name", "")
            if name:
                self._index_by_name[name] = entity_id

    def get_entity(self, entity_id: str) -> dict | None:
        """获取实体."""
        return self._entities.get(entity_id)

    def get_entity_by_name(self, name: str) -> dict | None:
        """通过名称获取实体."""
        entity_id = self._index_by_name.get(name)
        if entity_id:
            return self._entities.get(entity_id)
        return None

    def get_entities_by_type(self, entity_type: str) -> list[dict]:
        """获取特定类型的所有实体."""
        entity_ids = self._index_by_type.get(entity_type, [])
        return [self._entities[eid] for eid in entity_ids if eid in self._entities]

    def get_relations(
        self, from_id: str | None = None, to_id: str | None = None, relation_type: str | None = None
    ) -> list[dict]:
        """获取关系."""
        results = []
        for rel in self._relations:
            if from_id and rel.get("from") != from_id:
                continue
            if to_id and rel.get("to") != to_id:
                continue
            if relation_type and rel.get("type") != relation_type:
                continue
            results.append(rel)
        return results

    def get_neighbors(self, entity_id: str, relation_type: str | None = None) -> list[dict]:
        """获取邻居实体."""
        relations = self.get_relations(from_id=entity_id, relation_type=relation_type)
        neighbors = []
        for rel in relations:
            target_id = rel.get("to")
            if target_id and target_id in self._entities:
                neighbors.append({"entity": self._entities[target_id], "relation": rel})
        return neighbors

    def find_path(self, start_id: str, end_id: str, max_depth: int = 3) -> list[list[str]] | None:
        """查找两个实体之间的路径."""
        if start_id == end_id:
            return [[start_id]]

        if max_depth <= 0:
            return None

        # BFS
        from collections import deque

        queue = deque([(start_id, [start_id])])
        visited = {start_id}
        all_paths = []

        while queue:
            current_id, path = queue.popleft()

            if len(path) > max_depth + 1:
                continue

            relations = self.get_relations(from_id=current_id)
            for rel in relations:
                next_id = rel.get("to")
                if not next_id:
                    continue

                new_path = path + [next_id]

                if next_id == end_id:
                    all_paths.append(new_path)
                elif next_id not in visited and len(new_path) <= max_depth:
                    visited.add(next_id)
                    queue.append((next_id, new_path))

        return all_paths if all_paths else None


@pytest.fixture
def knowledge_graph(knowledge_graph_entities, knowledge_graph_relations) -> KnowledgeGraph:
    """创建知识图谱实例."""
    return KnowledgeGraph(
        entities=knowledge_graph_entities.get("entities", []),
        relations=knowledge_graph_relations.get("relations", []),
    )


# =============================================================================
# 工具定义
# =============================================================================


@tool()
async def read_document(file_path: str) -> str:
    """读取文档内容.

    Args:
        file_path: 文档路径

    Returns:
        文档内容
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


@tool()
async def extract_entities(text: str) -> str:
    """从文本中提取实体.

    Args:
        text: 输入文本

    Returns:
        JSON 格式的实体列表
    """
    # 简化的实体提取 - 实际应使用 NLP 模型
    import re

    entities = []

    # 提取人名（简单的中文姓名匹配）
    person_pattern = r"[\u4e00-\u9fa5]{2,4}"
    potential_names = re.findall(person_pattern, text)
    common_names = ["张三", "李四", "王五", "赵六", "李飞飞", "吴恩达", "Yann LeCun"]

    for name in potential_names:
        if name in common_names or len(name) == 3:
            entities.append({"type": "Person", "name": name})

    # 提取公司/组织名
    org_pattern = r"(TechCorp|OpenAI|GitHub|Google)"
    orgs = re.findall(org_pattern, text)
    for org in set(orgs):
        entities.append({"type": "Organization", "name": org})

    # 提取技术术语
    tech_pattern = r"(Python|TensorFlow|PyTorch|GPT-4|AI|LLM)"
    techs = re.findall(tech_pattern, text)
    for tech in set(techs):
        entities.append({"type": "Technology", "name": tech})

    return json.dumps(entities, ensure_ascii=False)


@tool()
async def query_knowledge_graph(query_type: str, params: str) -> str:
    """查询知识图谱.

    Args:
        query_type: 查询类型 (person_relations, company_employees, technology_users, etc.)
        params: JSON 格式的查询参数

    Returns:
        查询结果
    """
    # 这里使用全局的 kg 实例，实际应在 Agent 初始化时注入
    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON params"})

    # 简化实现 - 实际应基于知识图谱查询
    result = {"query_type": query_type, "params": params_dict, "results": []}

    return json.dumps(result, ensure_ascii=False)


@tool()
async def reason_about_path(start_entity: str, end_entity: str) -> str:
    """推理两个实体之间的关系路径.

    Args:
        start_entity: 起始实体名称
        end_entity: 目标实体名称

    Returns:
        推理结果
    """
    return json.dumps(
        {
            "start": start_entity,
            "end": end_entity,
            "reasoning": f"分析 {start_entity} 到 {end_entity} 的关系链...",
            "path": [],
        },
        ensure_ascii=False,
    )


# =============================================================================
# 测试用例
# =============================================================================


@pytest.mark.tools
class TestDocumentTools:
    """文档工具测试."""

    @pytest.mark.asyncio
    async def test_read_document(self, data_dir: Path, sample_article: str):
        """测试文档读取工具."""
        result = tool_output(await read_document(str(data_dir / "documents" / "sample_article.md")))

        assert "人工智能" in result
        assert "GitHub Copilot" in result
        assert "张三" in result

    @pytest.mark.asyncio
    async def test_read_document_not_found(self):
        """测试读取不存在的文档."""
        result = tool_output(await read_document("/nonexistent/file.md"))

        assert "Error" in result
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_extract_entities_from_article(self, sample_article: str):
        """测试从文章中提取实体."""
        result = tool_output(await extract_entities(sample_article))
        entities = json.loads(result)

        # 验证提取到实体
        assert len(entities) > 0

        # 验证实体类型
        entity_names = [e["name"] for e in entities]
        assert "张三" in entity_names
        assert "TechCorp" in entity_names or "OpenAI" in entity_names


@pytest.mark.tools
class TestKnowledgeGraphTools:
    """知识图谱工具测试."""

    def test_knowledge_graph_initialization(self, knowledge_graph: KnowledgeGraph):
        """测试知识图谱初始化."""
        # 验证实体数量
        entity = knowledge_graph.get_entity_by_name("张三")
        assert entity is not None
        assert entity["type"] == "Person"

        # 验证公司实体
        company = knowledge_graph.get_entity_by_name("TechCorp")
        assert company is not None
        assert company["type"] == "Company"

    def test_get_entities_by_type(self, knowledge_graph: KnowledgeGraph):
        """测试按类型获取实体."""
        persons = knowledge_graph.get_entities_by_type("Person")
        assert len(persons) >= 3  # 张三、李四、李飞飞

        technologies = knowledge_graph.get_entities_by_type("Technology")
        assert len(technologies) >= 2  # Python、OpenAI API

    def test_get_relations(self, knowledge_graph: KnowledgeGraph):
        """测试获取关系."""
        # 获取张三的所有关系
        zhangsan = knowledge_graph.get_entity_by_name("张三")
        assert zhangsan is not None

        relations = knowledge_graph.get_relations(from_id=zhangsan["id"])
        assert len(relations) >= 2  # works_for, uses

        # 验证关系类型
        relation_types = [r["type"] for r in relations]
        assert "works_for" in relation_types
        assert "uses" in relation_types

    def test_get_neighbors(self, knowledge_graph: KnowledgeGraph):
        """测试获取邻居节点."""
        zhangsan = knowledge_graph.get_entity_by_name("张三")
        assert zhangsan is not None

        neighbors = knowledge_graph.get_neighbors(zhangsan["id"])
        assert len(neighbors) >= 2

        # 验证邻居包含 TechCorp
        neighbor_names = [n["entity"]["name"] for n in neighbors]
        assert "TechCorp" in neighbor_names

    def test_find_path(self, knowledge_graph: KnowledgeGraph):
        """测试查找路径."""
        zhangsan = knowledge_graph.get_entity_by_name("张三")
        techcorp = knowledge_graph.get_entity_by_name("TechCorp")

        assert zhangsan is not None
        assert techcorp is not None

        paths = knowledge_graph.find_path(zhangsan["id"], techcorp["id"])
        assert paths is not None
        assert len(paths) > 0

        # 验证路径长度
        first_path = paths[0]
        assert len(first_path) == 2  # 张三 -> TechCorp

    @pytest.mark.asyncio
    async def test_query_knowledge_graph(self):
        """测试知识图谱查询工具."""
        params = json.dumps({"entity_name": "张三"})
        result = tool_output(await query_knowledge_graph("person_relations", params))

        data = json.loads(result)
        assert data["query_type"] == "person_relations"
        assert "params" in data

    @pytest.mark.asyncio
    async def test_reason_about_path(self):
        """测试路径推理工具."""
        result = tool_output(await reason_about_path("张三", "OpenAI"))

        data = json.loads(result)
        assert data["start"] == "张三"
        assert data["end"] == "OpenAI"
        assert "reasoning" in data


@pytest.mark.tools
class TestDataIntegrity:
    """数据完整性测试."""

    def test_entities_json_valid(self, knowledge_graph_entities: dict):
        """验证实体 JSON 格式正确."""
        assert "entities" in knowledge_graph_entities
        entities = knowledge_graph_entities["entities"]
        assert len(entities) > 0

        # 验证每个实体都有必需的字段
        for entity in entities:
            assert "id" in entity
            assert "type" in entity
            assert "name" in entity

    def test_relations_json_valid(
        self, knowledge_graph_relations: dict, knowledge_graph_entities: dict
    ):
        """验证关系 JSON 格式正确且引用的实体存在."""
        assert "relations" in knowledge_graph_relations
        relations = knowledge_graph_relations["relations"]

        entity_ids = {e["id"] for e in knowledge_graph_entities["entities"]}

        for relation in relations:
            assert "from" in relation
            assert "to" in relation
            assert "type" in relation

            # 验证引用的实体存在
            assert relation["from"] in entity_ids, f"Entity {relation['from']} not found"
            assert relation["to"] in entity_ids, f"Entity {relation['to']} not found"

    def test_graph_queries_yaml_valid(self, graph_queries: list):
        """验证查询 YAML 格式正确."""
        assert len(graph_queries) > 0

        for query in graph_queries:
            assert "id" in query
            assert "description" in query
            assert "query" in query
            assert "expected_results" in query

    def test_documents_exist(self, data_dir: Path):
        """验证测试文档存在且非空."""
        docs_dir = data_dir / "documents"

        sample_article = docs_dir / "sample_article.md"
        assert sample_article.exists()
        assert sample_article.stat().st_size > 0

        tech_spec = docs_dir / "technical_spec.md"
        assert tech_spec.exists()
        assert tech_spec.stat().st_size > 0

        meeting_notes = docs_dir / "meeting_notes.txt"
        assert meeting_notes.exists()
        assert meeting_notes.stat().st_size > 0


@pytest.mark.tools
class TestAgentWithTools:
    """Agent 集成工具测试."""

    @pytest.mark.asyncio
    async def test_agent_with_document_tools(self, mock_provider, data_dir: Path):
        """测试带有文档工具的 Agent."""
        mock_provider.add_text_response("我已经读取了文档")

        agent = Agent(
            provider=mock_provider,
            tools=[read_document],
            system_prompt="你是一个文档助手，可以读取和分析文档。",
        )

        response = await agent.run(f"请读取文档 {data_dir / 'documents' / 'sample_article.md'}")

        assert "文档" in response or "读取" in response

    @pytest.mark.asyncio
    async def test_agent_with_kg_tools(self, mock_provider):
        """测试带有知识图谱工具的 Agent."""
        mock_provider.add_text_response("张三在 TechCorp 工作")

        agent = Agent(
            provider=mock_provider,
            tools=[query_knowledge_graph, reason_about_path],
            system_prompt="你是一个知识图谱助手，可以查询实体关系。",
        )

        response = await agent.run("张三在哪里工作？")

        assert response is not None
        assert len(response) > 0
