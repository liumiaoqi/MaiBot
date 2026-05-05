from src.config.model_configs import ModelInfo


def test_model_identifier_strips_surrounding_whitespace() -> None:
    model_info = ModelInfo(
        api_provider="test-provider",
        model_identifier=" glm-5.1 ",
        name="test-model",
    )

    assert model_info.model_identifier == "glm-5.1"
