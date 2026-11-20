"""decide_role 的归属判定矩阵（批次 2）。"""

import pytest

from src.llm_models.payload_content.message import RoleType
from src.maisaka.context.attribution import decide_role


@pytest.mark.parametrize(
    ("sender_type", "sender_id", "viewer", "expected_role", "self_authored", "reason"),
    [
        ("agent", "a", "a", RoleType.Assistant, True, ""),
        ("agent", "b", "a", RoleType.User, False, ""),
        ("user", "", "a", RoleType.User, False, ""),
        ("system", "", "a", RoleType.User, False, "system_sender"),
        ("agent", "", "a", RoleType.User, False, "agent_without_id"),
        ("", "", "a", RoleType.User, False, "legacy_unknown"),
        ("agent", "a", "", RoleType.User, False, "no_viewer"),
    ],
)
def test_decide_role_matrix(
    sender_type: str,
    sender_id: str,
    viewer: str,
    expected_role: RoleType,
    self_authored: bool,
    reason: str,
):
    decision = decide_role(
        sender_type=sender_type,
        sender_agent_id=sender_id,
        viewer_agent_id=viewer,
        enabled=True,
    )

    assert decision.role is expected_role
    assert decision.self_authored is self_authored
    assert decision.degrade_reason == reason
    assert decision.self_authored == (decision.role is RoleType.Assistant)


def test_disabled_always_user():
    decision = decide_role(
        sender_type="agent",
        sender_agent_id="a",
        viewer_agent_id="a",
        enabled=False,
    )

    assert decision.role is RoleType.User
    assert decision.self_authored is False
    assert decision.degrade_reason == "disabled"


def test_user_sender_never_self_even_if_id_matches():
    decision = decide_role(
        sender_type="user",
        sender_agent_id="a",
        viewer_agent_id="a",
        enabled=True,
    )

    assert decision.role is RoleType.User
    assert decision.self_authored is False
    assert decision.degrade_reason == ""


def test_decide_role_is_idempotent():
    kwargs = {
        "sender_type": "agent",
        "sender_agent_id": "a",
        "viewer_agent_id": "a",
        "enabled": True,
    }

    assert decide_role(**kwargs) == decide_role(**kwargs)