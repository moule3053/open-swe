import pytest

from openswe_platform.common.enums import TaskStatus
from openswe_platform.common.errors import ConflictError
from openswe_platform.common.state_machine import assert_task_transition, is_terminal


def test_queued_to_running():
    assert_task_transition(TaskStatus.QUEUED, TaskStatus.RUNNING)


def test_running_to_parked():
    assert_task_transition(TaskStatus.RUNNING, TaskStatus.PARKED)


def test_parked_to_queued():
    assert_task_transition(TaskStatus.PARKED, TaskStatus.QUEUED)


def test_illegal_transition():
    with pytest.raises(ConflictError):
        assert_task_transition(TaskStatus.SUCCEEDED, TaskStatus.RUNNING)


def test_terminal():
    assert is_terminal("succeeded")
    assert is_terminal(TaskStatus.CANCELLED)
    assert not is_terminal(TaskStatus.RUNNING)
