"""`/proc/health` 与 `/proc/health/detail` 的接线判据。

为什么要这两条（2026-10-16 实测代价）：这两个端点**自建立起必 500** —— 两处都调了
`ApiResponse.success(...)`，而 `ApiResponse` 只有 `code`/`data`/`message`（没有 `success`），
真机探针拿到的是 `AttributeError: success`；全仓当时**零测试**覆盖这两个端点，所以没人发现。
⇒ 判据要点：**必须打到响应体形状**（`code`/`data`），只断言路由存在（或只断言 200）抓不到"500"以外的形状错误。
"""

import pytest


def test_proc_health_returns_response_envelope(auth_client) -> None:
    """聚合健康端点：必须是 ApiResponse 信封（code/data），且 data.status 是状态名。"""
    resp = auth_client.get("/api/webui/proc/health")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "code" in body and "data" in body, body
    assert body["data"]["status"] in {"up", "down", "degraded", "unknown"}, body
    assert "timestamp" in body["data"], body


def test_proc_health_detail_returns_per_checker_results(auth_client) -> None:
    """详细端点：必须给出逐检查器结果（这是排查"哪个检查器在 DOWN"的唯一入口）。

    它在 2026-10-16 真机探针里返 500，导致"哪个检查器 DOWN"查不到 —— 本条即那次教训的钉子。
    """
    resp = auth_client.get("/api/webui/proc/health/detail")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "code" in body and "data" in body, body
    assert isinstance(body["data"], dict), body


@pytest.mark.parametrize("path", ["/api/webui/proc/health", "/api/webui/proc/health/detail"])
def test_proc_health_requires_auth(client, path: str) -> None:
    """未认证必须 401（不是 500、不是 200）——两条端点都挂在 require_auth 之后。"""
    resp = client.get(path)

    assert resp.status_code == 401, resp.text
