# AgentLite Comprehensive Test Suite Plan

## Context

AgentLite is a lightweight, async-first Agent component library for LLM applications. It provides:
- **Agent**: Main agent class with tool calling loop and streaming support
- **OpenAIProvider**: OpenAI-compatible provider implementation
- **Tool System**: @tool decorator, CallableTool, CallableTool2, SimpleToolset
- **MCPClient**: MCP server integration
- **Message Types**: ContentPart, Message, ToolCall, etc.
- **Configuration**: Pydantic-based config models

## Test Location
`/home/tcmofashi/proj/general_agent/agentlite/tests/`

## Task Dependency Graph

| Task | Depends On | Reason |
|------|------------|--------|
| 1. Test Configuration Setup | None | Foundation for all tests |
| 2. Message Types Unit Tests | Task 1 | Core data structures |
| 3. Tool System Unit Tests | Task 1 | Core tool abstractions |
| 4. Configuration Unit Tests | Task 1 | Config validation |
| 5. Provider Protocol Unit Tests | Task 1 | Provider interface |
| 6. Mock Provider Implementation | Task 1 | Required for integration tests |
| 7. Agent Integration Tests | Tasks 2, 3, 6 | Tests agent with mocked provider |
| 8. Tool Calling Loop Tests | Tasks 3, 6 | Tests tool execution flow |
| 9. Streaming Response Tests | Tasks 2, 6 | Tests streaming functionality |
| 10. Conversation History Tests | Task 7 | Tests history management |
| 11. Real-World Scenario: Data Quality Agent | Tasks 7, 8 | Practical use case |
| 12. Real-World Scenario: Fact-Checking Agent | Tasks 7, 8 | Practical use case |
| 13. Real-World Scenario: Multi-Agent Workflow | Tasks 7, 10 | Practical use case |
| 14. MCP Mock Tests | Tasks 3, 6 | Tests MCP integration with mocks |
| 15. Error Handling Tests | Tasks 6, 7 | Tests error scenarios |
| 16. Test Coverage Analysis | All above | Verify coverage targets |

## Parallel Execution Graph

```
Wave 1 (Foundation - Start immediately):
├── Task 1: Test Configuration Setup
├── Task 2: Message Types Unit Tests
├── Task 3: Tool System Unit Tests
├── Task 4: Configuration Unit Tests
├── Task 5: Provider Protocol Unit Tests
└── Task 6: Mock Provider Implementation

Wave 2 (Core Integration - After Wave 1):
├── Task 7: Agent Integration Tests (depends: 1, 2, 3, 6)
├── Task 8: Tool Calling Loop Tests (depends: 3, 6)
└── Task 9: Streaming Response Tests (depends: 2, 6)

Wave 3 (Advanced Features - After Wave 2):
├── Task 10: Conversation History Tests (depends: 7)
├── Task 14: MCP Mock Tests (depends: 3, 6)
└── Task 15: Error Handling Tests (depends: 6, 7)

Wave 4 (Real-World Scenarios - After Wave 3):
├── Task 11: Data Quality Agent Scenario (depends: 7, 8)
├── Task 12: Fact-Checking Agent Scenario (depends: 7, 8)
└── Task 13: Multi-Agent Workflow Scenario (depends: 7, 10)

Wave 5 (Finalization - After Wave 4):
└── Task 16: Test Coverage Analysis (depends: all)

Critical Path: Task 1 → Task 6 → Task 7 → Task 10 → Task 13 → Task 16
Parallel Speedup: ~60% faster than sequential execution
```

## Tasks

### Task 1: Test Configuration Setup

**Description**: Create pytest configuration, conftest.py with shared fixtures, and test utilities.

**Delegation Recommendation**:
- Category: `quick` - Configuration setup is straightforward
- Skills: [`python-programmer`] - Python testing infrastructure knowledge

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for pytest configuration and fixture design
- OMITTED `git-master`: No git operations needed for this task
- OMITTED `frontend-ui-ux`: No UI work involved

**Depends On**: None

**Acceptance Criteria**:
- [ ] `pytest.ini` configured with asyncio mode
- [ ] `conftest.py` with shared fixtures (mock_provider, sample_messages, temp_agent)
- [ ] Test utilities module for common assertions
- [ ] All tests can be run with `pytest tests/`

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/conftest.py`
- `/home/tcmofashi/proj/general_agent/agentlite/tests/utils.py`

**Commit**: YES
- Message: `test: setup pytest configuration and shared fixtures`
- Files: `tests/conftest.py`, `tests/utils.py`

---

### Task 2: Message Types Unit Tests

**Description**: Test all message types: ContentPart, TextPart, ImageURLPart, AudioURLPart, ToolCall, ToolCallPart, Message.

**Delegation Recommendation**:
- Category: `quick` - Unit tests for data structures
- Skills: [`python-programmer`] - Python testing patterns

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for writing unit tests
- OMITTED `frontend-ui-ux`: No UI involved

**Depends On**: Task 1

**Acceptance Criteria**:
- [ ] ContentPart polymorphic validation works correctly
- [ ] TextPart merge_in_place works for streaming
- [ ] ToolCall merge_in_place works with ToolCallPart
- [ ] Message content coercion from string works
- [ ] Message.extract_text() returns correct text
- [ ] Message.has_tool_calls() returns correct boolean
- [ ] All edge cases covered (empty content, None values)

**Test Cases**:
1. `test_content_part_registry` - Verify subclass registration
2. `test_text_part_creation` - Basic TextPart instantiation
3. `test_text_part_merge` - Streaming text merge
4. `test_image_url_part` - ImageURLPart creation and serialization
5. `test_audio_url_part` - AudioURLPart creation and serialization
6. `test_tool_call_creation` - ToolCall instantiation
7. `test_tool_call_merge` - ToolCall merging with ToolCallPart
8. `test_message_string_content` - Message with string content coercion
9. `test_message_list_content` - Message with list of ContentParts
10. `test_message_extract_text` - Text extraction from mixed content
11. `test_message_has_tool_calls` - Tool call detection
12. `test_message_serialization` - Pydantic model_dump works

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/unit/test_message.py`

**Commit**: YES
- Message: `test: add unit tests for message types`
- Files: `tests/unit/test_message.py`

---

### Task 3: Tool System Unit Tests

**Description**: Test tool system: Tool, CallableTool, CallableTool2, SimpleToolset, @tool decorator, ToolResult types.

**Delegation Recommendation**:
- Category: `unspecified-low` - Moderate complexity with async patterns
- Skills: [`python-programmer`] - Python async testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for async tool testing
- OMITTED `frontend-ui-ux`: No UI involved

**Depends On**: Task 1

**Acceptance Criteria**:
- [ ] Tool JSON schema validation works
- [ ] CallableTool validates arguments against schema
- [ ] CallableTool2 uses Pydantic for validation
- [ ] SimpleToolset manages tools correctly
- [ ] @tool decorator creates valid tools
- [ ] Tool execution handles errors gracefully
- [ ] Async tool execution works correctly

**Test Cases**:
1. `test_tool_schema_validation` - Invalid schema raises ValueError
2. `test_tool_ok_result` - ToolOk creation and properties
3. `test_tool_error_result` - ToolError creation and properties
4. `test_callable_tool_validation` - Argument validation against schema
5. `test_callable_tool_execution` - Successful tool execution
6. `test_callable_tool_error_handling` - Exception handling in tools
7. `test_callable_tool2_pydantic_validation` - Pydantic model validation
8. `test_callable_tool2_execution` - Type-safe tool execution
9. `test_simple_toolset_add_remove` - Tool management
10. `test_simple_toolset_handle` - Tool call handling
11. `test_simple_toolset_tool_not_found` - Missing tool error
12. `test_tool_decorator_basic` - @tool creates valid tool
13. `test_tool_decorator_with_params` - @tool with custom name/description
14. `test_tool_decorator_type_hints` - Type hint to schema conversion
15. `test_tool_concurrent_execution` - Multiple tools execute concurrently

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/unit/test_tool.py`

**Commit**: YES
- Message: `test: add unit tests for tool system`
- Files: `tests/unit/test_tool.py`

---

### Task 4: Configuration Unit Tests

**Description**: Test Pydantic configuration models: ProviderConfig, ModelConfig, ToolConfig, AgentConfig.

**Delegation Recommendation**:
- Category: `quick` - Pydantic model validation tests
- Skills: [`python-programmer`] - Pydantic testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for Pydantic validation tests

**Depends On**: Task 1

**Acceptance Criteria**:
- [ ] ProviderConfig validates base_url format
- [ ] ProviderConfig stores api_key as SecretStr
- [ ] ModelConfig validates temperature range
- [ ] ModelConfig validates provider is not empty
- [ ] AgentConfig validates default_model exists in models
- [ ] AgentConfig validates all model providers exist
- [ ] get_provider_config and get_model_config work correctly

**Test Cases**:
1. `test_provider_config_validation` - Valid config creation
2. `test_provider_config_invalid_url` - Invalid base_url raises error
3. `test_provider_config_secret_str` - API key is SecretStr
4. `test_model_config_validation` - Valid model config
5. `test_model_config_temperature_range` - Temperature bounds checking
6. `test_model_config_empty_provider` - Empty provider raises error
7. `test_agent_config_validation` - Valid agent config
8. `test_agent_config_missing_default_model` - Missing default_model raises error
9. `test_agent_config_unknown_provider` - Unknown provider raises error
10. `test_agent_config_get_provider` - get_provider_config works
11. `test_agent_config_get_model` - get_model_config works

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/unit/test_config.py`

**Commit**: YES
- Message: `test: add unit tests for configuration models`
- Files: `tests/unit/test_config.py`

---

### Task 5: Provider Protocol Unit Tests

**Description**: Test provider protocol and exception types: ChatProvider, StreamedMessage, TokenUsage, exception hierarchy.

**Delegation Recommendation**:
- Category: `quick` - Protocol and exception testing
- Skills: [`python-programmer`] - Python protocol testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for protocol testing

**Depends On**: Task 1

**Acceptance Criteria**:
- [ ] TokenUsage calculates total correctly
- [ ] Exception hierarchy is correct
- [ ] APIStatusError stores status_code
- [ ] ChatProvider protocol can be implemented

**Test Cases**:
1. `test_token_usage_total` - Total token calculation
2. `test_token_usage_defaults` - Default cached_tokens = 0
3. `test_chat_provider_error_base` - Base exception class
4. `test_api_connection_error` - APIConnectionError creation
5. `test_api_timeout_error` - APITimeoutError creation
6. `test_api_status_error` - APIStatusError with status_code
7. `test_api_empty_response_error` - APIEmptyResponseError creation
8. `test_chat_provider_protocol` - Protocol implementation check

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/unit/test_provider.py`

**Commit**: YES
- Message: `test: add unit tests for provider protocol`
- Files: `tests/unit/test_provider.py`

---

### Task 6: Mock Provider Implementation

**Description**: Create a comprehensive mock provider for testing that simulates OpenAI API responses without real API calls.

**Delegation Recommendation**:
- Category: `unspecified-low` - Requires understanding of streaming and async patterns
- Skills: [`python-programmer`] - Async generator implementation

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for mock provider implementation

**Depends On**: Task 1

**Acceptance Criteria**:
- [ ] MockProvider implements ChatProvider protocol
- [ ] Can simulate text responses
- [ ] Can simulate tool calls
- [ ] Can simulate streaming responses
- [ ] Can simulate errors
- [ ] Configurable response sequences
- [ ] Tracks calls for verification

**Implementation Details**:
```python
class MockProvider:
    """Mock provider for testing.
    
    Usage:
        provider = MockProvider()
        provider.add_response("Hello!")
        provider.add_tool_call("add", {"a": 1, "b": 2}, "3")
        
        agent = Agent(provider=provider)
        response = await agent.run("Hi")
        
        assert provider.calls == [...]
    """
```

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/mocks/provider.py`

**Commit**: YES
- Message: `test: add mock provider for testing`
- Files: `tests/mocks/provider.py`

---

### Task 7: Agent Integration Tests

**Description**: Test Agent class with mocked provider: initialization, run(), generate(), history management.

**Delegation Recommendation**:
- Category: `unspecified-low` - Integration testing with async
- Skills: [`python-programmer`] - Async integration testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for agent integration testing

**Depends On**: Tasks 1, 2, 3, 6

**Acceptance Criteria**:
- [ ] Agent initializes correctly with provider
- [ ] Agent.run() returns string response
- [ ] Agent.run(stream=True) returns async iterator
- [ ] Agent.generate() returns Message
- [ ] Agent adds messages to history
- [ ] Agent.clear_history() clears history
- [ ] Agent respects max_iterations

**Test Cases**:
1. `test_agent_initialization` - Basic agent creation
2. `test_agent_with_tools` - Agent with toolset
3. `test_agent_run_simple` - Simple non-streaming run
4. `test_agent_run_streaming` - Streaming response
5. `test_agent_generate` - Generate without tool loop
6. `test_agent_history_tracking` - Messages added to history
7. `test_agent_clear_history` - History cleared correctly
8. `test_agent_max_iterations` - Respects iteration limit
9. `test_agent_system_prompt` - System prompt used

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/integration/test_agent.py`

**Commit**: YES
- Message: `test: add agent integration tests`
- Files: `tests/integration/test_agent.py`

---

### Task 8: Tool Calling Loop Tests

**Description**: Test the complete tool calling loop: agent requests tool, tool executes, result returned.

**Delegation Recommendation**:
- Category: `unspecified-low` - Complex async flow testing
- Skills: [`python-programmer`] - Async flow testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for tool loop testing

**Depends On**: Tasks 3, 6

**Acceptance Criteria**:
- [ ] Agent calls tool when requested by LLM
- [ ] Tool result is added to history
- [ ] Agent continues conversation after tool result
- [ ] Multiple tool calls in one response handled
- [ ] Tool errors are handled gracefully
- [ ] Tool calls are concurrent

**Test Cases**:
1. `test_single_tool_call` - One tool call in conversation
2. `test_multiple_tool_calls` - Multiple tools in one response
3. `test_tool_call_chain` - Sequential tool calls
4. `test_tool_error_handling` - Tool returns error
5. `test_tool_not_found` - Unknown tool requested
6. `test_tool_concurrent_execution` - Tools execute concurrently
7. `test_tool_result_in_history` - Tool results in conversation history
8. `test_tool_call_with_arguments` - Arguments passed correctly

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/integration/test_tool_loop.py`

**Commit**: YES
- Message: `test: add tool calling loop tests`
- Files: `tests/integration/test_tool_loop.py`

---

### Task 9: Streaming Response Tests

**Description**: Test streaming responses: text streaming, tool call streaming, mixed content.

**Delegation Recommendation**:
- Category: `unspecified-low` - Async streaming testing
- Skills: [`python-programmer`] - Async generator testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for streaming testing

**Depends On**: Tasks 2, 6

**Acceptance Criteria**:
- [ ] Text streams in chunks
- [ ] Tool calls stream correctly
- [ ] Mixed content (text + tool) streams correctly
- [ ] Complete response can be reconstructed
- [ ] Streaming works with tool calling loop

**Test Cases**:
1. `test_stream_text_only` - Simple text streaming
2. `test_stream_tool_call` - Tool call streaming
3. `test_stream_mixed_content` - Text then tool call
4. `test_stream_reconstruction` - Rebuild full response
5. `test_stream_with_tool_loop` - Streaming in tool loop
6. `test_stream_empty_response` - Empty stream handling

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/integration/test_streaming.py`

**Commit**: YES
- Message: `test: add streaming response tests`
- Files: `tests/integration/test_streaming.py`

---

### Task 10: Conversation History Tests

**Description**: Test conversation history management: message ordering, role tracking, history limits.

**Delegation Recommendation**:
- Category: `quick` - History management testing
- Skills: [`python-programmer`] - State management testing

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for history testing

**Depends On**: Task 7

**Acceptance Criteria**:
- [ ] Messages added in correct order
- [ ] Roles tracked correctly (user, assistant, tool)
- [ ] Tool call IDs preserved
- [ ] History can be inspected
- [ ] History can be cleared
- [ ] History persists across multiple runs

**Test Cases**:
1. `test_history_message_order` - Messages in correct order
2. `test_history_roles` - Correct role tracking
3. `test_history_tool_responses` - Tool call IDs preserved
4. `test_history_persistence` - History across multiple runs
5. `test_history_clear` - Clear history works
6. `test_history_manual_add` - Manually add messages
7. `test_history_copy` - history property returns copy

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/integration/test_history.py`

**Commit**: YES
- Message: `test: add conversation history tests`
- Files: `tests/integration/test_history.py`

---

### Task 11: Real-World Scenario - Data Quality Agent

**Description**: Test a realistic data quality improvement agent that validates and cleans data.

**Delegation Recommendation**:
- Category: `unspecified-high` - Complex scenario testing
- Skills: [`python-programmer`] - Complex test scenario design

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for scenario implementation

**Depends On**: Tasks 7, 8

**Acceptance Criteria**:
- [ ] Agent validates data format
- [ ] Agent identifies data quality issues
- [ ] Agent suggests corrections
- [ ] Uses multiple tools (validate, clean, analyze)
- [ ] Handles edge cases (empty data, invalid format)

**Scenario**:
```python
# Data Quality Agent validates CSV data
# Tools: validate_csv, detect_anomalies, suggest_fixes
# Test with sample data containing errors
```

**Test Cases**:
1. `test_data_quality_valid_data` - Clean data passes validation
2. `test_data_quality_detects_errors` - Errors detected and reported
3. `test_data_quality_suggests_fixes` - Corrections suggested
4. `test_data_quality_empty_data` - Handles empty input
5. `test_data_quality_invalid_format` - Handles format errors

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/scenarios/test_data_quality.py`

**Commit**: YES
- Message: `test: add data quality agent scenario tests`
- Files: `tests/scenarios/test_data_quality.py`

---

### Task 12: Real-World Scenario - Fact-Checking Agent

**Description**: Test a fact-checking agent that verifies claims using tools.

**Delegation Recommendation**:
- Category: `unspecified-high` - Complex scenario testing
- Skills: [`python-programmer`] - Complex test scenario design

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for scenario implementation

**Depends On**: Tasks 7, 8

**Acceptance Criteria**:
- [ ] Agent extracts claims from text
- [ ] Agent uses search tool to verify
- [ ] Agent provides verdict with evidence
- [ ] Handles uncertain claims appropriately
- [ ] Multiple claims in one text handled

**Scenario**:
```python
# Fact-Checking Agent verifies statements
# Tools: search_facts, calculate_statistics, check_date
# Test with verifiable and unverifiable claims
```

**Test Cases**:
1. `test_fact_check_true_claim` - Correctly identifies true claim
2. `test_fact_check_false_claim` - Correctly identifies false claim
3. `test_fact_check_multiple_claims` - Multiple claims in one text
4. `test_fact_check_uncertain` - Handles uncertain claims
5. `test_fact_check_with_evidence` - Provides supporting evidence

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/scenarios/test_fact_checking.py`

**Commit**: YES
- Message: `test: add fact-checking agent scenario tests`
- Files: `tests/scenarios/test_fact_checking.py`

---

### Task 13: Real-World Scenario - Multi-Agent Workflow

**Description**: Test multiple agents collaborating on a complex task.

**Delegation Recommendation**:
- Category: `unspecified-high` - Complex multi-agent testing
- Skills: [`python-programmer`] - Complex scenario design

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for multi-agent testing

**Depends On**: Tasks 7, 10

**Acceptance Criteria**:
- [ ] Multiple agents can share a provider
- [ ] Agents maintain separate histories
- [ ] Workflow stages execute in order
- [ ] Output from one agent feeds into next
- [ ] Each agent has specialized role

**Scenario**:
```python
# Research → Write → Edit workflow
# Researcher gathers facts
# Writer creates content
# Editor reviews and improves
```

**Test Cases**:
1. `test_multi_agent_research_write` - Research to writer flow
2. `test_multi_agent_with_editor` - Three-agent workflow
3. `test_multi_agent_isolated_histories` - Histories don't leak
4. `test_multi_agent_shared_provider` - Provider shared correctly
5. `test_multi_agent_error_handling` - Errors don't break workflow

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/scenarios/test_multi_agent.py`

**Commit**: YES
- Message: `test: add multi-agent workflow scenario tests`
- Files: `tests/scenarios/test_multi_agent.py`

---

### Task 14: MCP Mock Tests

**Description**: Test MCP integration with mocked MCP server.

**Delegation Recommendation**:
- Category: `unspecified-low` - MCP protocol mocking
- Skills: [`python-programmer`] - Protocol mocking

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for MCP mocking

**Depends On**: Tasks 3, 6

**Acceptance Criteria**:
- [ ] MCPClient connects to mock server
- [ ] Tools load from mock server
- [ ] MCP tools execute correctly
- [ ] MCP errors handled gracefully
- [ ] Connection cleanup works

**Test Cases**:
1. `test_mcp_connect_stdio` - STDIO connection mock
2. `test_mcp_connect_sse` - SSE connection mock
3. `test_mcp_load_tools` - Load tools from mock
4. `test_mcp_tool_execution` - Execute MCP tool
5. `test_mcp_error_handling` - MCP errors handled
6. `test_mcp_context_manager` - Async context manager works

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/mocks/mcp_server.py`
- `/home/tcmofashi/proj/general_agent/agentlite/tests/integration/test_mcp.py`

**Commit**: YES
- Message: `test: add MCP integration tests with mocks`
- Files: `tests/mocks/mcp_server.py`, `tests/integration/test_mcp.py`

---

### Task 15: Error Handling Tests

**Description**: Test error scenarios: provider errors, tool errors, timeout, connection issues.

**Delegation Recommendation**:
- Category: `unspecified-low` - Error scenario testing
- Skills: [`python-programmer`] - Error testing patterns

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for error testing

**Depends On**: Tasks 6, 7

**Acceptance Criteria**:
- [ ] APIConnectionError handled correctly
- [ ] APITimeoutError handled correctly
- [ ] APIStatusError handled correctly
- [ ] Tool execution errors don't crash agent
- [ ] Invalid tool arguments handled
- [ ] Max iterations prevents infinite loops

**Test Cases**:
1. `test_provider_connection_error` - Connection failure
2. `test_provider_timeout_error` - Request timeout
3. `test_provider_status_error` - HTTP error status
4. `test_provider_empty_response` - Empty response handling
5. `test_tool_execution_error` - Tool raises exception
6. `test_tool_invalid_arguments` - Invalid args to tool
7. `test_tool_not_found_error` - Unknown tool called
8. `test_max_iterations_reached` - Loop prevention
9. `test_json_decode_error` - Invalid JSON in tool args

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/integration/test_errors.py`

**Commit**: YES
- Message: `test: add error handling tests`
- Files: `tests/integration/test_errors.py`

---

### Task 16: Test Coverage Analysis

**Description**: Analyze test coverage and ensure targets are met.

**Delegation Recommendation**:
- Category: `quick` - Coverage analysis
- Skills: [`python-programmer`] - Coverage tooling

**Skills Evaluation**:
- INCLUDED `python-programmer`: Required for coverage analysis

**Depends On**: All previous tasks

**Acceptance Criteria**:
- [ ] Overall coverage >= 80%
- [ ] Core modules (message, tool, agent) >= 90%
- [ ] Provider module >= 70%
- [ ] MCP module >= 60%
- [ ] Coverage report generated
- [ ] Missing coverage documented

**Coverage Targets**:
| Module | Target | Priority |
|--------|--------|----------|
| agentlite.message | 95% | P0 |
| agentlite.tool | 95% | P0 |
| agentlite.agent | 90% | P0 |
| agentlite.config | 90% | P0 |
| agentlite.provider | 80% | P1 |
| agentlite.providers.openai | 70% | P1 |
| agentlite.mcp | 60% | P2 |

**Files to Create**:
- `/home/tcmofashi/proj/general_agent/agentlite/tests/.coveragerc`

**Commit**: YES
- Message: `test: add coverage configuration and analysis`
- Files: `tests/.coveragerc`

---

## Test File Structure

```
/home/tcmofashi/proj/general_agent/agentlite/tests/
├── conftest.py                    # Shared fixtures and configuration
├── utils.py                       # Test utilities and helpers
├── .coveragerc                    # Coverage configuration
├── unit/                          # Unit tests
│   ├── __init__.py
│   ├── test_message.py           # Message types tests
│   ├── test_tool.py              # Tool system tests
│   ├── test_config.py            # Configuration tests
│   └── test_provider.py          # Provider protocol tests
├── integration/                   # Integration tests
│   ├── __init__.py
│   ├── test_agent.py             # Agent integration tests
│   ├── test_tool_loop.py         # Tool calling loop tests
│   ├── test_streaming.py         # Streaming tests
│   ├── test_history.py           # History management tests
│   ├── test_mcp.py               # MCP integration tests
│   └── test_errors.py            # Error handling tests
├── scenarios/                     # Real-world scenario tests
│   ├── __init__.py
│   ├── test_data_quality.py      # Data quality agent
│   ├── test_fact_checking.py     # Fact-checking agent
│   └── test_multi_agent.py       # Multi-agent workflow
└── mocks/                         # Mock implementations
    ├── __init__.py
    ├── provider.py               # Mock OpenAI provider
    └── mcp_server.py             # Mock MCP server
```

## Test Fixtures (conftest.py)

### Core Fixtures

```python
# Mock provider fixtures
@pytest.fixture
def mock_provider():
    """Create a mock provider with no responses configured."""
    return MockProvider()

@pytest.fixture
def mock_provider_with_response():
    """Create a mock provider that returns a simple text response."""
    provider = MockProvider()
    provider.add_text_response("Hello!")
    return provider

# Sample message fixtures
@pytest.fixture
def sample_text_message():
    """Create a sample text message."""
    return Message(role="user", content="Hello!")

@pytest.fixture
def sample_tool_call():
    """Create a sample tool call."""
    return ToolCall(
        id="call_123",
        function=ToolCall.FunctionBody(
            name="add",
            arguments='{"a": 1, "b": 2}'
        )
    )

# Tool fixtures
@pytest.fixture
def add_tool():
    """Create a simple add tool."""
    @tool()
    async def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b
    return add

@pytest.fixture
def error_tool():
    """Create a tool that raises an error."""
    @tool()
    async def error() -> str:
        """Always raises an error."""
        raise ValueError("Test error")
    return error

# Agent fixtures
@pytest.fixture
async def simple_agent(mock_provider):
    """Create a simple agent with mocked provider."""
    return Agent(provider=mock_provider)

@pytest.fixture
async def agent_with_tools(mock_provider, add_tool):
    """Create an agent with tools."""
    return Agent(provider=mock_provider, tools=[add_tool])
```

## Mock Implementations

### MockProvider

```python
class MockProvider:
    """Mock provider for testing AgentLite without real API calls.
    
    This provider simulates OpenAI API responses and allows:
    - Configuring response sequences
    - Simulating tool calls
    - Simulating errors
    - Tracking all calls for verification
    
    Example:
        provider = MockProvider()
        provider.add_text_response("Hello!")
        provider.add_tool_call("add", {"a": 1, "b": 2}, "3")
        
        agent = Agent(provider=provider)
        response = await agent.run("Hi")
        
        # Verify calls
        assert len(provider.calls) == 1
        assert provider.calls[0].system_prompt == "You are helpful."
    """
    
    def __init__(self):
        self.responses = []
        self.calls = []
        self.model = "mock-model"
    
    def add_text_response(self, text: str):
        """Add a text response to the queue."""
        self.responses.append({"type": "text", "content": text})
    
    def add_tool_call(self, name: str, arguments: dict, result: str):
        """Add a tool call response to the queue."""
        self.responses.append({
            "type": "tool_call",
            "name": name,
            "arguments": arguments,
            "result": result
        })
    
    def add_error(self, error: Exception):
        """Add an error response to the queue."""
        self.responses.append({"type": "error", "error": error})
    
    async def generate(self, system_prompt, tools, history):
        """Generate a mock response."""
        self.calls.append(MockCall(
            system_prompt=system_prompt,
            tools=tools,
            history=list(history)
        ))
        
        if not self.responses:
            return MockStreamedMessage([TextPart(text="Mock response")])
        
        response = self.responses.pop(0)
        
        if response["type"] == "error":
            raise response["error"]
        elif response["type"] == "text":
            return MockStreamedMessage([TextPart(text=response["content"])])
        elif response["type"] == "tool_call":
            return MockStreamedMessage([
                ToolCall(
                    id="call_123",
                    function=ToolCall.FunctionBody(
                        name=response["name"],
                        arguments=json.dumps(response["arguments"])
                    )
                )
            ])
```

## Test Configuration (pytest.ini)

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
pythonpath = src
addopts = -v --tb=short --strict-markers
markers =
    unit: Unit tests
    integration: Integration tests
    scenario: Real-world scenario tests
    slow: Slow tests
```

## Running Tests

```bash
# Run all tests
cd /home/tcmofashi/proj/general_agent/agentlite
pytest tests/

# Run with coverage
pytest tests/ --cov=agentlite --cov-report=html --cov-report=term

# Run specific test categories
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/scenarios/ -v

# Run with markers
pytest -m unit
pytest -m integration
pytest -m "not slow"

# Run specific test file
pytest tests/unit/test_message.py -v

# Run with debugging
pytest tests/ -v --pdb
```

## Commit Strategy

| After Task | Commit Message | Files |
|------------|----------------|-------|
| Task 1 | `test: setup pytest configuration and shared fixtures` | `tests/conftest.py`, `tests/utils.py` |
| Task 2 | `test: add unit tests for message types` | `tests/unit/test_message.py` |
| Task 3 | `test: add unit tests for tool system` | `tests/unit/test_tool.py` |
| Task 4 | `test: add unit tests for configuration models` | `tests/unit/test_config.py` |
| Task 5 | `test: add unit tests for provider protocol` | `tests/unit/test_provider.py` |
| Task 6 | `test: add mock provider for testing` | `tests/mocks/provider.py` |
| Task 7 | `test: add agent integration tests` | `tests/integration/test_agent.py` |
| Task 8 | `test: add tool calling loop tests` | `tests/integration/test_tool_loop.py` |
| Task 9 | `test: add streaming response tests` | `tests/integration/test_streaming.py` |
| Task 10 | `test: add conversation history tests` | `tests/integration/test_history.py` |
| Task 11 | `test: add data quality agent scenario tests` | `tests/scenarios/test_data_quality.py` |
| Task 12 | `test: add fact-checking agent scenario tests` | `tests/scenarios/test_fact_checking.py` |
| Task 13 | `test: add multi-agent workflow scenario tests` | `tests/scenarios/test_multi_agent.py` |
| Task 14 | `test: add MCP integration tests with mocks` | `tests/mocks/mcp_server.py`, `tests/integration/test_mcp.py` |
| Task 15 | `test: add error handling tests` | `tests/integration/test_errors.py` |
| Task 16 | `test: add coverage configuration and analysis` | `tests/.coveragerc` |

## Success Criteria

### Verification Commands

```bash
# All tests pass
pytest tests/ -v

# Coverage meets targets
pytest tests/ --cov=agentlite --cov-report=term-missing

# No import errors
python -c "import agentlite; print('OK')"

# Type checking passes (if mypy configured)
mypy src/agentlite/
```

### Final Checklist

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All scenario tests pass
- [ ] Coverage >= 80% overall
- [ ] Core modules >= 90% coverage
- [ ] All mocks work correctly
- [ ] Tests run without real API keys
- [ ] Tests are deterministic
- [ ] Tests are well-documented
- [ ] Test files follow naming convention

## Notes

1. **No Real API Calls**: All tests must work without real API keys using mocks
2. **Deterministic**: Tests should produce consistent results
3. **Fast**: Unit tests should complete in < 1 second each
4. **Isolated**: Tests should not depend on each other
5. **Documented**: Complex scenarios should have docstrings explaining the use case
