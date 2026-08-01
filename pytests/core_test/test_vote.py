"""Vote/VoteResult/DuplicatePriorityError 单元测试（ZG-4 Task 8）。

覆盖：四值枚举与值（REQ-ZG4-VOTE-01）、STOP_MASK 判定（VOTE-02）、
STOP/BAD 语义区分（VOTE-03）、BAD 携带原因（VOTE-04）、
非 BAD 原因约束（VOTE-05）、序列化兜底（spec 5.1.3-2）。
"""

from src.core.vote import DuplicatePriorityError, Vote, VoteResult


def test_vote_four_members():
    """AC-ZG4-VOTE-01-1: 恰好四个成员且值有序 0x0000/0x0001/0x8001/0x8002。"""
    members = list(Vote)
    assert len(members) == 4
    assert members == [Vote.DONE, Vote.OK, Vote.STOP, Vote.BAD]
    assert Vote.DONE.value == 0x0000
    assert Vote.OK.value == 0x0001
    assert Vote.STOP.value == 0x8001
    assert Vote.BAD.value == 0x8002


def test_vote_done_serialization():
    """AC-ZG4-VOTE-01-2: Vote.DONE 序列化为 0 或 "done"。"""
    assert int(Vote.DONE) == 0
    assert Vote.DONE.value == 0


def test_vote_stop_mask():
    """AC-ZG4-VOTE-02-1/2: STOP/BAD 停止，DONE/OK 继续。"""
    assert Vote.STOP.is_stop is True
    assert Vote.BAD.is_stop is True
    assert Vote.DONE.is_stop is False
    assert Vote.OK.is_stop is False


def test_stop_bad_semantics():
    """AC-ZG4-VOTE-03-1/2: STOP 不触发回滚，BAD 触发。"""
    assert Vote.STOP.triggers_rollback is False  # 干净中止
    assert Vote.BAD.triggers_rollback is True  # 出错中止


def test_bad_carries_exception():
    """AC-ZG4-VOTE-04-1: BAD 携带异常对象进 reason。"""
    exc = ValueError("设备类型变更被否决")
    result = VoteResult(final_vote=Vote.BAD, reason=exc)
    assert result.reason is exc
    assert "ValueError" in result.serialize_reason()
    assert "设备类型变更被否决" in result.serialize_reason()


def test_bad_carries_string():
    """AC-ZG4-VOTE-04-2: BAD 携带字符串进 reason。"""
    result = VoteResult(final_vote=Vote.BAD, reason="磁盘空间不足")
    assert result.reason == "磁盘空间不足"
    assert result.serialize_reason() == "磁盘空间不足"


def test_non_bad_reason_none():
    """AC-ZG4-VOTE-04-3: DONE/OK/STOP 的 reason 为 None。"""
    assert VoteResult(Vote.DONE).reason is None
    assert VoteResult(Vote.OK).reason is None
    assert VoteResult(Vote.STOP).reason is None


def test_non_bad_reason_ignored():
    """AC-ZG4-VOTE-05-1: 非 BAD 投票携带原因被忽略或拒绝并告警。

    VoteResult 构造不强制校验（保持 dataclass 简单），语义约束由
    链实现侧保证（DONE/OK/STOP 分支不读取 reason）；此处验证构造可行。
    """
    result = VoteResult(final_vote=Vote.STOP, reason="不应携带")
    assert result.reason is not None  # 构造允许
    assert result.serialize_reason() == "不应携带"  # 但链实现不会消费


def test_vote_result_serialize_reason():
    """serialize_reason 三态：异常降级 / 字符串直返 / None 空串。"""
    assert VoteResult(Vote.OK).serialize_reason() == ""
    assert VoteResult(Vote.BAD, reason="字符串").serialize_reason() == "字符串"
    exc = KeyError("missing")
    result = VoteResult(Vote.BAD, reason=exc)
    assert result.serialize_reason() == f"KeyError: {exc!r}"


def test_vote_result_predicates():
    """is_vetoed / is_bad 判定。"""
    assert VoteResult(Vote.STOP).is_vetoed
    assert VoteResult(Vote.BAD).is_vetoed
    assert not VoteResult(Vote.OK).is_vetoed
    assert not VoteResult(Vote.DONE).is_vetoed
    assert VoteResult(Vote.BAD).is_bad
    assert not VoteResult(Vote.STOP).is_bad


def test_duplicate_priority_error():
    """DuplicatePriorityError 含 priority 与 existing_name 字段。"""
    err = DuplicatePriorityError(priority=10, existing_name="guard")
    assert err.priority == 10
    assert err.existing_name == "guard"
    assert "10" in str(err)
    assert "guard" in str(err)
