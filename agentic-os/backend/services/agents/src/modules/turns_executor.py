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
    # normalize URL
    nats_url = config.get("NATS_URL", "nats://localhost:4222")
    if nats_url.startswith("http://"):
        nats_url = "nats://" + nats_url[len("http://"):]

    logger.debug("[NATS] about to connect to %s", nats_url)
    nc = NATS()
    try:
        await nc.connect(servers=[nats_url])
        logger.debug("[NATS] connected")

        js = nc.jetstream()
        logger.debug("[NATS] obtained jetstream context")

        logger.debug("[NATS] subscribing to %s", reply_to)
        sub = await js.subscribe(reply_to)
        logger.debug("[NATS] subscription established, waiting for next message (timeout=%.1f)", timeout)

        try:
            msg = await sub.next_msg(timeout=timeout)
            logger.debug("[NATS] message received on %s: %r", reply_to, msg.data)
            await msg.ack()
            logger.debug("[NATS] message acked")
            body = json.loads(msg.data.decode())
            return body

        except asyncio.TimeoutError:
            logger.error("[NATS] timed out waiting for a message on %s", reply_to)
            raise

        except Exception as e:
            logger.error("[NATS] error while waiting for message: %s", e, exc_info=True)
            raise

    finally:
        logger.debug("[NATS] draining/closing connection")
        try:
            await nc.drain()
            logger.debug("[NATS] drain complete")
        except Exception as e:
            logger.error("[NATS] error during drain(): %s", e, exc_info=True)


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
    logger.debug(
        "execute_and_wait ENTER tool=%s turn_id=%s repo=%s",
        tool_name, turn_id, repo_url
    )

    # ─── Add issue_title from TurnHistory.metadata into metadata ────────────
    conv_meta = get_turns_metadata(repo_url=repo_url)
    issue_title = conv_meta.get("issue_title")
    if issue_title:
        metadata = metadata or {}
        metadata["issue_title"] = issue_title

    # 1) Create a per-request inbox subject
    base_resp = config.get("NATS_SUBJECT_EXEC_RESP", "tools.execute.response")
    reply_to = f"{base_resp}.{uuid4().hex}"
    logger.debug("  → will enqueue with reply_to=%s", reply_to)

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
        logger.debug("  → http_enqueue ack=%s", ack)
    except Exception as e:
        logger.error(
            "Failed to enqueue execution request for %s: %s",
            tool_name, e, exc_info=True
        )
        raise

    # 3) Wait for the single response from our private inbox
    to = timeout or config.get("TURN_EXEC_TIMEOUT", 10.0)
    logger.debug("  → about to block on NATS for %.1fs", to)
    try:
        resp = _run_sync(_wait_for_response(reply_to, to))
        logger.debug("  → got back NATS response: %s", resp)
    except Exception:
        logger.error("execute_and_wait FAILED waiting for NATS response", exc_info=True)
        raise

    # 4) Return the response, carrying through the original turn_id
    return {
        "status":         resp.get("status"),
        "execution_time": resp.get("meta", {}).get("exec_time", 0.0),
        "response":       resp.get("response"),
        "error":          resp.get("error"),
        "turn_id":        turn_id,
    }
