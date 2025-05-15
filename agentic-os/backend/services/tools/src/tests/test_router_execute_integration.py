# tests/test_router_execute_integration.py

import os
import json
import asyncio
import pytest

from shared.client_tools import (
    execute_tool_blocking as execute_blocking,
    execute_tool          as execute,
)
from nats.aio.client import Client as NATS

# ─── helper to pull one message from the response subject ────────────────

def pull_response(timeout: float = 5.0):
    """
    Connect to NATS, pull exactly 1 message from the response subject,
    ack it, and return its parsed JSON body.
    """
    NATS_URL         = os.getenv("NATS_URL", "nats://localhost:4222")
    RESP_SUBJECT     = os.getenv("NATS_SUBJECT_EXEC_RESP", "tools.execute.response")
    STREAM_RESP      = os.getenv("NATS_STREAM_EXEC_RESP", "STREAM_TOOLS")
    DURABLE_CONSUMER = "TEST_INTEG_RESP"

    async def _pull():
        nc = NATS()
        await nc.connect(servers=[NATS_URL])
        js = nc.jetstream()
        try:
            await js.add_stream(name=STREAM_RESP, subjects=[RESP_SUBJECT])
        except:
            pass

        sub = await js.pull_subscribe(RESP_SUBJECT, durable=DURABLE_CONSUMER)
        msgs = await sub.fetch(1, timeout=timeout)

        out = []
        for m in msgs:
            await m.ack()
            out.append(json.loads(m.data.decode()))

        await nc.drain()
        return out

    return asyncio.get_event_loop().run_until_complete(_pull())

# ─── tests ───────────────────────────────────────────────────────────────────

def test_execute_blocking_echo():
    """
    Call the blocking helper for the built-in 'echo' tool,
    and assert that it reflects back our input_text.
    """
    res = execute_blocking(
        tool_name="echo",
        input_args={"input_text": "ping-blocking"},
        repo_url="dummy-repo",
        repo_name="dummy-repo",
    )
    # the blocking helper returns the full tool‐response envelope as data
    # which should include its own status and response fields
    assert res["status"] == "ok"
    out = res["response"]
    assert isinstance(out, dict) and len(out) == 1
    echoed = list(out.values())[0]
    assert echoed == "ping-blocking"

def test_execute_nonblocking_echo():
    """
    Call the non‐blocking helper for 'echo',
    then pull the real response off NATS and compare it to
    the identical blocking result.
    """
    # first, obtain the expected output by calling the blocking helper
    expected_env = execute_blocking(
        tool_name="echo",
        input_args={"input_text": "ping-async"},
        repo_url="dummy-repo",
        repo_name="dummy-repo",
    )
    assert expected_env["status"] == "ok"
    expected = expected_env["response"]
    assert isinstance(expected, dict) and len(expected) == 1

    # now enqueue via non‐blocking helper
    nb_env = execute(
        tool_name="echo",
        input_args={"input_text": "ping-async"},
        repo_url="dummy-repo",
        repo_name="dummy-repo",
    )
    # the non‐blocking helper returns {"stream": "...", "seq": ...}
    assert "stream" in nb_env and "seq" in nb_env

    # finally, pull the one message from JetStream
    msgs = pull_response(timeout=10.0)
    assert len(msgs) == 1
    msg = msgs[0]

    # verify the envelope from NATS
    assert msg["status"] == "ok"
    assert msg.get("error") is None

    # and the actual echo matches our blocking helper result
    assert msg["response"] == expected
