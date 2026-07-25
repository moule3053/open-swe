from openswe_platform.common.messaging import (
    control_subject,
    enqueue_subject,
    envelope,
    task_enqueue_payload,
)


def test_subjects():
    assert enqueue_subject("o", "coding", "t").startswith("tasks.enqueue.")
    assert control_subject("t") == "tasks.control.t"


def test_envelope():
    env = envelope(
        "task.enqueue",
        org_id="o",
        task_id="t",
        payload=task_enqueue_payload("t", "coding"),
    )
    assert env["schema_version"] == 1
    assert env["type"] == "task.enqueue"
    assert env["payload"]["agent_type"] == "coding"
