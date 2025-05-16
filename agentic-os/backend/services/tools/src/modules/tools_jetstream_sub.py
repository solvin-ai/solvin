# modules/tools_jetstream_sub.py

import asyncio
import json
import time

from modules.tools_jetstream_init import get_jetstream
from shared.config import config
from shared.logger import logger
from modules.tools_executor import execute_tool
from modules.tools_registry import get_global_registry


async def _process_and_ack(msg):
    """
    1) Run the (potentially long) execute_tool(...) in a thread.
    2) Publish the result to the reply_to subject.
    3) ACK the original request.
    """
    # extract the sequence for logging
    seq = getattr(msg.metadata, "stream_seq", None)
    logger.debug("⇨ [responder] processing request #%s", seq)

    try:
        data = json.loads(msg.data.decode())
        tool_name = data.get("tool_name")
        reply_to  = data.get("reply_to") or config["NATS_SUBJECT_EXEC_RESP"]

        # build args for execute_tool
        exec_args = {
            "tool_name":  tool_name,
            "input_args": data.get("input_args", {}),
            "repo_url":   data.get("repo_url"),
            "repo_name":  data.get("repo_name"),
            "repo_owner": data.get("repo_owner"),
            "metadata":   data.get("metadata", {}),
            "turn_id":    data.get("turn_id"),
        }

        start = time.perf_counter()
        if tool_name not in get_global_registry():
            envelope = {
                "status": "error",
                "error": {
                    "code":    "TOOL_NOT_FOUND",
                    "message": f"Tool '{tool_name}' not registered"
                }
            }
        else:
            try:
                # run the blocking work off the event loop
                result = await asyncio.to_thread(execute_tool, **exec_args)
                envelope = result
            except Exception as ex:
                logger.exception("Error executing tool %s", tool_name)
                envelope = {
                    "status": "failure",
                    "error": {
                        "code":    "EXECUTION_ERROR",
                        "message": str(ex)
                    }
                }

        # attach timing metadata
        envelope.setdefault("meta", {})
        envelope["meta"]["exec_time"] = time.perf_counter() - start

        # publish the response
        js = await get_jetstream()
        await js.publish(reply_to, json.dumps(envelope).encode())
        logger.debug("⇨ [responder] published response on %s for request #%s", reply_to, seq)

    except Exception:
        logger.exception("❌ unexpected error in message handler")

    finally:
        # ACK the original request so it's removed from the stream
        try:
            await msg.ack()
            logger.debug("⇨ [responder] acked request #%s", seq)
        except Exception:
            logger.exception("❌ failed to ack request #%s", seq)


async def run_responder():
    """
    1) Warm‐up JetStream (connect & ensure stream exists)
    2) Pull‐subscribe to tools.execute.request with manual ack
    3) For each incoming message, immediately create a task to handle it
    4) Leave the coroutine alive so the consumer stays registered
    """
    logger.info("🤖 [responder] run_responder() starting")
    js = await get_jetstream()
    logger.info("🤖 [responder] obtained JetStream context")

    subject = config["NATS_SUBJECT_EXEC_REQ"]    # typically "tools.execute.request"
    durable = config.get("NATS_CONSUMER_NAME", "TOOLS_EXEC_REQ")

    sub = await js.subscribe(
        subject,
        durable=durable,
        manual_ack=True    # we will ack ourselves after processing
    )
    logger.info(
        "✅ [responder] subscribed on %s (durable=%s), entering message loop",
        subject, durable
    )

    # this loop will fire immediately for *every* message in the stream,
    # regardless of how long other tasks take
    async for msg in sub.messages:
        # schedule each message independently
        asyncio.create_task(_process_and_ack(msg))

    # never returns
    await asyncio.Event().wait()
