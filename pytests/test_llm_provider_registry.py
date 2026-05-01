from typing import List

from src.llm_models.model_client.base_client import (
    APIResponse,
    AudioTranscriptionRequest,
    BaseClient,
    ClientProviderRegistration,
    ClientRegistry,
    EmbeddingRequest,
    ResponseRequest,
)


class DummyClient(BaseClient):
    """测试用 LLM 客户端。"""

    async def get_response(self, request: ResponseRequest) -> APIResponse:
        """获取测试响应。

        Args:
            request: 统一响应请求。

        Returns:
            APIResponse: 测试响应。
        """
        del request
        return APIResponse(content="ok")

    async def get_embedding(self, request: EmbeddingRequest) -> APIResponse:
        """获取测试嵌入。

        Args:
            request: 统一嵌入请求。

        Returns:
            APIResponse: 测试嵌入响应。
        """
        del request
        return APIResponse(embedding=[1.0])

    async def get_audio_transcriptions(self, request: AudioTranscriptionRequest) -> APIResponse:
        """获取测试音频转写。

        Args:
            request: 统一音频转写请求。

        Returns:
            APIResponse: 测试音频转写响应。
        """
        del request
        return APIResponse(content="audio")

    def get_support_image_formats(self) -> List[str]:
        """获取测试支持的图片格式。

        Returns:
            List[str]: 支持的图片格式列表。
        """
        return ["png"]


def test_client_registry_rejects_provider_conflict():
    """同一 client_type 被不同插件注册时应拒绝。"""
    registry = ClientRegistry()
    registry.replace_plugin_providers(
        "plugin.alpha",
        [
            ClientProviderRegistration(
                client_type="example",
                factory=DummyClient,
                owner_plugin_id="plugin.alpha",
            )
        ],
    )

    try:
        registry.validate_plugin_provider_replacement("plugin.beta", ["example"])
    except ValueError as exc:
        assert "冲突" in str(exc)
    else:
        raise AssertionError("不同插件注册相同 client_type 应失败")


def test_client_registry_unregisters_plugin_providers():
    """插件注销时应移除它拥有的 Provider 注册。"""
    registry = ClientRegistry()
    registry.replace_plugin_providers(
        "plugin.alpha",
        [
            ClientProviderRegistration(
                client_type="example",
                factory=DummyClient,
                owner_plugin_id="plugin.alpha",
            )
        ],
    )

    removed_count = registry.unregister_plugin_providers("plugin.alpha")

    assert removed_count == 1
    assert "example" not in registry.client_registry
