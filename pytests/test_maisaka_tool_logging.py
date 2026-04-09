from src.maisaka.chat_loop_service import MaisakaChatLoopService


def test_build_tool_names_log_text_supports_openai_function_schema() -> None:
    tool_definitions = [
        {
            "type": "function",
            "function": {
                "name": "mute_user",
                "description": "禁言指定用户",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "name": "reply",
            "description": "发送回复",
        },
    ]

    assert MaisakaChatLoopService._build_tool_names_log_text(tool_definitions) == "mute_user、reply"
