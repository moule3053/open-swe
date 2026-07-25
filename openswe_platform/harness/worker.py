"""Harness worker main loop: consume NATS TASKS, claim, run agent, checkpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import uuid
from typing import Any

from sqlalchemy import select

from openswe_platform.common.config import get_settings
from openswe_platform.common.db import dispose_engine, get_session_factory
from openswe_platform.common.enums import ParkReason
from openswe_platform.common.messaging import SUBJECT_ENQUEUE_PREFIX, NatsBus
from openswe_platform.common.models import Message, ProcessedMessage, SandboxRow, Task
from openswe_platform.common.tasks import (
    append_event,
    claim_task,
    complete_task,
    heartbeat_lease,
    load_latest_checkpoint,
    park_task,
    requeue_expired_leases,
    save_checkpoint,
    upsert_sandbox,
)
from openswe_platform.harness.agents import RunContext, get_agent
from openswe_platform.harness.llm_client import make_llm_client
from openswe_platform.harness.mcp_runtime import connect_mcp_servers
from openswe_platform.harness.sandboxes import get_sandbox_provider

logger = logging.getLogger(__name__)


class HarnessWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = self.settings.worker_id
        self.bus = NatsBus(self.settings.nats_url)
        self.llm = make_llm_client()
        self._stop = asyncio.Event()
        self._busy = False

    async def start(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [harness] %(message)s",
        )
        await self.bus.connect()
        assert self.bus.js is not None

        # Durable pull consumer on work queue
        try:
            await self.bus.js.add_consumer(
                "TASKS",
                durable_name="harness-workers",
                filter_subject=f"{SUBJECT_ENQUEUE_PREFIX}.>",
            )
        except Exception:
            # may already exist
            pass

        reaper = asyncio.create_task(self._reaper_loop())
        logger.info("Harness worker %s started", self.worker_id)
        try:
            await self._consume_loop()
        finally:
            self._stop.set()
            reaper.cancel()
            await self.bus.close()
            await dispose_engine()

    async def _reaper_loop(self) -> None:
        while not self._stop.is_set():
            try:
                factory = get_session_factory()
                async with factory() as session:
                    n = await requeue_expired_leases(
                        session, max_retries=self.settings.max_run_retries
                    )
                    await session.commit()
                    if n:
                        logger.warning("Reaped %s expired leases", n)
            except Exception:
                logger.exception("Reaper failed")
            await asyncio.sleep(self.settings.lease_ttl_seconds)

    async def _consume_loop(self) -> None:
        assert self.bus.js is not None
        psub = await self.bus.js.pull_subscribe(
            f"{SUBJECT_ENQUEUE_PREFIX}.>",
            durable="harness-workers",
            stream="TASKS",
        )
        while not self._stop.is_set():
            if self._busy:
                await asyncio.sleep(0.5)
                continue
            try:
                msgs = await psub.fetch(1, timeout=2)
            except Exception:
                continue
            for msg in msgs:
                try:
                    body = json.loads(msg.data.decode())
                    claimed = await self._claim_enqueue(body)
                    await msg.ack()
                    if claimed is not None:
                        task_id, run_id = claimed
                        self._busy = True
                        try:
                            await self._execute_run(task_id, run_id)
                        finally:
                            self._busy = False
                except Exception:
                    logger.exception("Failed handling message")
                    try:
                        await msg.nak()
                    except Exception:
                        pass

    async def _claim_enqueue(self, body: dict[str, Any]) -> tuple[uuid.UUID, uuid.UUID] | None:
        payload = body.get("payload") or body
        task_id_raw = payload.get("task_id") or body.get("task_id")
        if not task_id_raw:
            return None
        task_id = uuid.UUID(str(task_id_raw))
        msg_id = str(body.get("msg_id") or "")

        factory = get_session_factory()
        async with factory() as session:
            if msg_id and await session.get(ProcessedMessage, msg_id):
                return None
            claimed = await claim_task(
                session,
                task_id=task_id,
                worker_id=self.worker_id,
                lease_ttl_seconds=self.settings.lease_ttl_seconds,
            )
            if msg_id:
                session.add(ProcessedMessage(msg_id=msg_id))
            await session.commit()
            if claimed is None:
                logger.info("Task %s not claimable; acking", task_id)
                return None
            _, run = claimed
            return task_id, run.run_id

    async def _execute_run(self, task_id: uuid.UUID, run_id: uuid.UUID) -> None:
        factory = get_session_factory()
        async with factory() as session:
            task = await session.get(Task, task_id)
            if task is None:
                return
            cp = await load_latest_checkpoint(session, task_id=task_id)
            checkpoint_last_seq = int((cp.blob if cp else {}).get("last_message_seq", 0))
            msg_result = await session.execute(
                select(Message)
                .where(Message.task_id == task_id, Message.seq > checkpoint_last_seq)
                .order_by(Message.seq)
            )
            message_rows = list(msg_result.scalars().all())
            messages = [{"role": m.role, "content": m.content} for m in message_rows]
            last_message_seq = max(
                [checkpoint_last_seq, *(int(m.seq) for m in message_rows)],
            )
            # existing sandbox?
            sb_result = await session.execute(
                select(SandboxRow)
                .where(
                    SandboxRow.task_id == task_id,
                    SandboxRow.provider == task.sandbox_provider,
                    SandboxRow.status == "active",
                )
                .order_by(SandboxRow.created_at.desc())
                .limit(1)
            )
            existing_sb = sb_result.scalar_one_or_none()
            task_snapshot = {
                "org_id": str(task.org_id),
                "task_id": str(task.task_id),
                "run_id": str(run_id),
                "thread_id": task.thread_id,
                "agent_type": task.agent_type,
                "repo": task.repo,
                "base_ref": task.base_ref,
                "model": task.model,
                "prompt": task.prompt,
                "messages": messages,
                "sandbox_provider": task.sandbox_provider,
                "sandbox_id": existing_sb.sandbox_id if existing_sb else None,
                "mcp_snapshot": list(task.mcp_snapshot or []),
                "checkpoint": cp.blob if cp else None,
                "last_message_seq": last_message_seq,
                "cancel_requested": bool(task.cancel_requested_at),
            }
            await session.commit()

        provider = get_sandbox_provider(task_snapshot["sandbox_provider"])
        try:
            if task_snapshot["sandbox_id"]:
                try:
                    sandbox_ref = await provider.connect(task_snapshot["sandbox_id"])
                    event_type = "sandbox_reused"
                except Exception:
                    logger.warning(
                        "Sandbox reconnect failed; creating a replacement", exc_info=True
                    )
                    sandbox_ref = await provider.create(task_id=str(task_id))
                    event_type = "sandbox_created"
            else:
                sandbox_ref = await provider.create(task_id=str(task_id))
                event_type = "sandbox_created"
        except Exception as exc:
            async with factory() as session:
                await append_event(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    event_type="sandbox_error",
                    payload={"provider": task_snapshot["sandbox_provider"], "error": str(exc)},
                )
                await complete_task(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    success=False,
                    error_code="sandbox_unavailable",
                    error_message=str(exc),
                )
                await session.commit()
            return

        async with factory() as session:
            await upsert_sandbox(
                session,
                task_id=task_id,
                provider=sandbox_ref.provider,
                sandbox_id=sandbox_ref.sandbox_id,
                metadata=sandbox_ref.metadata,
            )
            await append_event(
                session,
                task_id=task_id,
                run_id=run_id,
                event_type=event_type,
                payload={"sandbox_id": sandbox_ref.sandbox_id, "provider": sandbox_ref.provider},
            )
            await session.commit()

        # MCP
        mcp_sessions = []
        try:
            mcp_sessions = await connect_mcp_servers(task_snapshot["mcp_snapshot"])
            async with factory() as session:
                for s in mcp_sessions:
                    if s.ok:
                        await append_event(
                            session,
                            task_id=task_id,
                            run_id=run_id,
                            event_type="mcp_connected",
                            payload={
                                "mcp_server_id": s.server_id,
                                "name": s.name,
                                "tools": [t.tool_name for t in s.tools],
                            },
                        )
                        await append_event(
                            session,
                            task_id=task_id,
                            run_id=run_id,
                            event_type="mcp_tools_loaded",
                            payload={
                                "mcp_server_id": s.server_id,
                                "tools": [t.namespaced for t in s.tools],
                            },
                        )
                    else:
                        await append_event(
                            session,
                            task_id=task_id,
                            run_id=run_id,
                            event_type="mcp_error",
                            payload={"mcp_server_id": s.server_id, "error": s.error},
                        )
                await session.commit()
        except Exception as exc:
            async with factory() as session:
                await append_event(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    event_type="mcp_error",
                    payload={"error": str(exc), "required": True},
                )
                await complete_task(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    success=False,
                    error_code="mcp_required_failed",
                    error_message=str(exc),
                )
                await session.commit()
            return

        ctx = RunContext(
            org_id=task_snapshot["org_id"],
            task_id=task_snapshot["task_id"],
            run_id=task_snapshot["run_id"],
            thread_id=task_snapshot["thread_id"],
            agent_type=task_snapshot["agent_type"],
            repo=task_snapshot["repo"],
            base_ref=task_snapshot["base_ref"],
            model=task_snapshot["model"],
            prompt=task_snapshot["prompt"],
            messages=task_snapshot["messages"],
            sandbox_provider=task_snapshot["sandbox_provider"],
            sandbox_id=sandbox_ref.sandbox_id,
            mcp_snapshot=task_snapshot["mcp_snapshot"],
            checkpoint=task_snapshot["checkpoint"],
            last_message_seq=task_snapshot["last_message_seq"],
            cancel_requested=task_snapshot["cancel_requested"],
        )

        try:
            agent = get_agent(ctx.agent_type)
        except KeyError:
            async with factory() as session:
                await complete_task(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    success=False,
                    error_code="unknown_agent_type",
                    error_message=ctx.agent_type,
                )
                await session.commit()
            return

        async def on_step(event_type: str, payload: dict[str, Any]) -> None:
            async with factory() as session:
                if event_type == "checkpoint":
                    await save_checkpoint(
                        session,
                        task_id=task_id,
                        run_id=run_id,
                        blob={**payload, "last_message_seq": ctx.last_message_seq},
                    )
                else:
                    await append_event(
                        session,
                        task_id=task_id,
                        run_id=run_id,
                        event_type=event_type,
                        payload=payload,
                    )
                await session.commit()

        async def on_boundary() -> list[dict[str, str]]:
            async with factory() as session:
                task_row = await session.get(Task, task_id)
                if task_row and task_row.cancel_requested_at:
                    ctx.cancel_requested = True
                lease_ok = await heartbeat_lease(
                    session,
                    run_id=run_id,
                    worker_id=self.worker_id,
                    lease_ttl_seconds=self.settings.lease_ttl_seconds,
                )
                if not lease_ok:
                    raise RuntimeError("Worker lease was lost")
                pending = await session.execute(
                    select(Message)
                    .where(Message.task_id == task_id, Message.seq > ctx.last_message_seq)
                    .order_by(Message.seq)
                )
                rows = list(pending.scalars().all())
                if rows:
                    ctx.last_message_seq = max(int(row.seq) for row in rows)
                await session.commit()
                return [{"role": row.role, "content": row.content} for row in rows]

        heartbeat_stop = asyncio.Event()

        async def heartbeat_loop() -> None:
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.wait_for(
                        heartbeat_stop.wait(),
                        timeout=self.settings.heartbeat_interval_seconds,
                    )
                    return
                except TimeoutError:
                    pass
                async with factory() as session:
                    task_row = await session.get(Task, task_id)
                    if task_row and task_row.cancel_requested_at:
                        ctx.cancel_requested = True
                    ok = await heartbeat_lease(
                        session,
                        run_id=run_id,
                        worker_id=self.worker_id,
                        lease_ttl_seconds=self.settings.lease_ttl_seconds,
                    )
                    await session.commit()
                    if not ok:
                        ctx.cancel_requested = True
                        return

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        try:
            async with asyncio.timeout(self.settings.max_run_duration_seconds):
                result = await agent.run(
                    ctx,
                    llm=self.llm,
                    sandbox=provider,
                    sandbox_ref=sandbox_ref,
                    mcp_sessions=mcp_sessions,
                    on_step=on_step,
                    on_boundary=on_boundary,
                )
        except Exception as exc:
            logger.exception("Agent run failed")
            async with factory() as session:
                await save_checkpoint(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    blob={"error": str(exc), "last_message_seq": ctx.last_message_seq},
                    metadata={"fatal": True},
                )
                await complete_task(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    success=False,
                    error_code="agent_exception",
                    error_message=str(exc),
                )
                await session.commit()
            return
        finally:
            heartbeat_stop.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        async with factory() as session:
            if result.checkpoint_blob:
                await save_checkpoint(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    blob={**result.checkpoint_blob, "last_message_seq": ctx.last_message_seq},
                )
            if result.park:
                await park_task(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    reason=result.park_reason or ParkReason.PLAN_APPROVAL.value,
                    approval_payload=result.approval_payload,
                )
            else:
                await complete_task(
                    session,
                    task_id=task_id,
                    run_id=run_id,
                    success=result.success,
                    error_code=result.error_code,
                    error_message=None if result.success else result.final_message,
                )
            await session.commit()


def main() -> None:
    worker = HarnessWorker()

    loop = asyncio.new_event_loop()

    def _stop(*_args: Any) -> None:
        worker._stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    loop.run_until_complete(worker.start())


if __name__ == "__main__":
    main()
