import pytest

from src.webui.routers import reasoning_process
from src.webui.routers.reasoning_process import ReasoningPromptSessionInfo


@pytest.mark.asyncio
async def test_list_files_resolves_all_sessions_for_dropdown(tmp_path, monkeypatch):
    stage = "planner"
    session_names = ["qq_group_10000", "qq_group_20000", "qq_group_30000"]
    for session_name in session_names:
        session_dir = tmp_path / stage / session_name
        session_dir.mkdir(parents=True)
        (session_dir / "1700000000000.txt").write_text("[Prompt]\n测试", encoding="utf-8")

    captured_session_names = []

    def fake_list_session_infos(
        stage_name: str,
        session_names_arg: list[str] | None = None,
    ) -> list[ReasoningPromptSessionInfo]:
        assert stage_name == stage
        captured_session_names.extend(session_names_arg or [])
        return [
            ReasoningPromptSessionInfo(name=name, display_name=f"真实名称 {name}")
            for name in session_names_arg or []
        ]

    monkeypatch.setattr(reasoning_process, "PROMPT_LOG_ROOT", tmp_path)
    monkeypatch.setattr(reasoning_process, "_list_session_infos", fake_list_session_infos)

    response = await reasoning_process.list_reasoning_prompt_files(
        stage=stage,
        session=session_names[0],
        search="",
        page=1,
        page_size=50,
    )

    assert set(captured_session_names) == set(session_names)
    assert {item.name for item in response.session_infos} == set(session_names)
    assert all(item.display_name.startswith("真实名称 ") for item in response.session_infos)


def test_replyer_search_matches_full_output_beyond_preview(tmp_path, monkeypatch):
    session_name = "qq_group_10000"
    session_dir = tmp_path / "replyer" / session_name
    session_dir.mkdir(parents=True)

    needle = "只在完整回复中出现的关键词"
    leading_text = "开头内容" * 80
    (session_dir / "1700000000000.txt").write_text(
        f"[输出结果]\n\n{leading_text}\n{needle}\n\n{'=' * 80}\n\n[Prompt]\n系统提示",
        encoding="utf-8",
    )

    monkeypatch.setattr(reasoning_process, "PROMPT_LOG_ROOT", tmp_path)

    items = reasoning_process._collect_prompt_files(
        "replyer",
        session_name,
        {session_name: ReasoningPromptSessionInfo(name=session_name, display_name="测试群")},
    )

    assert len(items) == 1
    assert items[0].output_preview
    assert needle not in items[0].output_preview
    assert reasoning_process._matches_prompt_file_search(items[0], needle.casefold())


def test_collect_prompt_files_extracts_model_and_duration_metadata(tmp_path, monkeypatch):
    session_name = "qq_group_10000"
    session_dir = tmp_path / "planner" / session_name
    session_dir.mkdir(parents=True)

    (session_dir / "1700000000001.txt").write_text(
        f"""[请求信息]

请求模型：test-planner-model
推理耗时：88.5 ms

{'=' * 80}

[输出结果]

需要先查询资料，然后回复用户。

工具调用:
[
  {{
    "id": "call_1",
    "name": "query_memory",
    "arguments": {{}}
  }}
]

{'=' * 80}

[Prompt]
系统提示
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(reasoning_process, "PROMPT_LOG_ROOT", tmp_path)

    items = reasoning_process._collect_prompt_files(
        "planner",
        session_name,
        {session_name: ReasoningPromptSessionInfo(name=session_name, display_name="测试群")},
    )

    assert len(items) == 1
    assert items[0].model_name == "test-planner-model"
    assert items[0].duration_ms == 88.5
    assert items[0].action_preview == "动作：query_memory"
    assert reasoning_process._matches_prompt_file_search(items[0], "test-planner-model")


def test_collect_prompt_files_extracts_metadata_from_html(tmp_path, monkeypatch):
    session_name = "qq_group_10000"
    session_dir = tmp_path / "planner" / session_name
    session_dir.mkdir(parents=True)

    (session_dir / "1700000000003.html").write_text(
        """<!DOCTYPE html>
<html lang="zh-CN">
<body>
<script type="application/json" id="prompt-preview-metadata">
{"model_name":"html-model","duration_ms":7.25}
</script>
</body>
</html>
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(reasoning_process, "PROMPT_LOG_ROOT", tmp_path)

    items = reasoning_process._collect_prompt_files(
        "planner",
        session_name,
        {session_name: ReasoningPromptSessionInfo(name=session_name, display_name="测试群")},
    )

    assert len(items) == 1
    assert items[0].model_name == "html-model"
    assert items[0].duration_ms == 7.25


def test_planner_collects_action_preview(tmp_path, monkeypatch):
    session_name = "qq_group_10000"
    session_dir = tmp_path / "planner" / session_name
    session_dir.mkdir(parents=True)

    (session_dir / "1700000000001.txt").write_text(
        """[输出结果]

需要先查询资料，然后回复用户。

工具调用:
[
  {
    "id": "call_1",
    "name": "query_memory",
    "arguments": {}
  },
  {
    "id": "call_2",
    "name": "reply",
    "arguments": {"target_message_id": 123}
  }
]

================================================================================

[Prompt]
系统提示
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(reasoning_process, "PROMPT_LOG_ROOT", tmp_path)

    items = reasoning_process._collect_prompt_files(
        "planner",
        session_name,
        {session_name: ReasoningPromptSessionInfo(name=session_name, display_name="测试群")},
    )

    assert len(items) == 1
    assert items[0].action_preview == "动作：query_memory、reply"
    assert reasoning_process._matches_prompt_file_search(items[0], "reply")


def test_timing_gate_collects_action_preview(tmp_path, monkeypatch):
    session_name = "qq_group_10000"
    session_dir = tmp_path / "timing_gate" / session_name
    session_dir.mkdir(parents=True)

    (session_dir / "1700000000002.txt").write_text(
        """[输出结果]

这轮用户可能还在继续发言，先等待一下。

工具调用:
[
  {
    "id": "call_1",
    "name": "wait",
    "arguments": {"seconds": 10}
  }
]

================================================================================

[Prompt]
系统提示
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(reasoning_process, "PROMPT_LOG_ROOT", tmp_path)

    items = reasoning_process._collect_prompt_files(
        "timing_gate",
        session_name,
        {session_name: ReasoningPromptSessionInfo(name=session_name, display_name="测试群")},
    )

    assert len(items) == 1
    assert items[0].action_preview == "动作：wait"
    assert reasoning_process._matches_prompt_file_search(items[0], "wait")
