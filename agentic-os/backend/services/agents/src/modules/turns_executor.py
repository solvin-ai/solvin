# modules/turns_executor.py

import json
import asyncio
from uuid import uuid4
from typing import Any, Dict, Optional

from nats.aio.client import Client as NATS
from shared.client_tools import execute_tool as http_execute_tool
from shared.config import config
from shared.logger import logger
from modules.turns_list import get_turns_metadata


def _run_sync(coro: asyncio.Future) -> Any:
    """
    Run an async coroutine in a fresh event loop, then tear it down.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _wait_for_response(reply_to: str, timeout: float) -> Dict[str, Any]:
    """
    Connect to JetStream, subscribe to our per-request reply subject,
    await exactly one message, ack it, and return its parsed JSON body.
    """
    nats_url = config.get("NATS_URL", "nats://localhost:4222")
    if nats_url.startswith("http://"):
        nats_url = "nats://" + nats_url[len("http://"):]
    nc = NATS()
    await nc.connect(servers=[nats_url])
    js = nc.jetstream()

    # ephemeral push-consumer on our unique reply subject
    sub = await js.subscribe(reply_to)
    try:
        msg = await sub.next_msg(timeout=timeout)
        body = json.loads(msg.data.decode())
        await msg.ack()
        return body
    finally:
        # clean up the connection (unsubscribes and closes)
        await nc.drain()


def execute_and_wait(
    *,
    tool_name: str,
    input_args: Dict[str, Any],
    repo_url: str,
    repo_name: str,
    repo_owner: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    turn_id: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """
    1) HTTP-enqueue a request with a unique reply_to inbox, including repo_url.
    2) Block until we get a pushed message on that inbox.
    3) Return the response dict in the expected shape, including turn_id.
    """
    # ─── Add issue_title from TurnHistory.metadata into metadata ────────────
    conv_meta = get_turns_metadata(repo_url=repo_url)
    issue_title = conv_meta.get("issue_title")
    if issue_title:
        metadata = metadata or {}
        metadata["issue_title"] = issue_title

    # 1) Create a per-request inbox subject
    base_resp = config.get("NATS_SUBJECT_EXEC_RESP", "tools.execute.response")
    reply_to = f"{base_resp}.{uuid4().hex}"

    # 2) Enqueue via HTTP, injecting reply_to and repo_url
    payload: Dict[str, Any] = {
        "tool_name":  tool_name,
        "input_args": input_args,
        "repo_url":   repo_url,
        "repo_name":  repo_name,
        "repo_owner": repo_owner,
        "metadata":   metadata or {},
        "turn_id":    turn_id,
        "reply_to":   reply_to,
    }
    try:
        ack = http_execute_tool(**payload)
        logger.debug(
            "Enqueued '%s' → stream=%s seq=%s reply_to=%s",
            tool_name, ack.get("stream"), ack.get("seq"), reply_to
        )
    except Exception as e:
        logger.error(
            "Failed to enqueue execution request for %s: %s",
            tool_name, e, exc_info=True
        )
        raise

    # 3) Wait for the single response from our private inbox
    to = timeout or config.get("TURN_EXEC_TIMEOUT", 10.0)
    resp = _run_sync(_wait_for_response(reply_to, to))

    # 4) Return the response, carrying through the original turn_id
    return {
        "status":         resp.get("status"),
        "execution_time": resp.get("meta", {}).get("exec_time", 0.0),
        "response":       resp.get("response"),
        "error":          resp.get("error"),
        "turn_id":        turn_id,
    }
