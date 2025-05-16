# modules/tools_jetstream_sub.py

import asyncio
import json
import time

from modules.tools_jetstream_init import get_jetstream
from shared.config import config
from shared.logger import logger
from modules.tools_executor import execute_tool
from modules.tools_registry import get_global_registry


async def run_responder():
    """
    Durable PUSH‐consumer: for each JS‐request message,
    offload the blocking execute_tool(...) into a thread,
    publish to that message’s reply_to inbox,
    then ACK the request so it’s removed from JetStream.
    """
    js        = await get_jetstream()
    req_sub   = config["NATS_SUBJECT_EXEC_REQ"]    # e.g. "tools.execute.request"
    resp_pref = config["NATS_SUBJECT_EXEC_RESP"]   # e.g. "tools.execute.response"
    durable   = config.get("NATS_CONSUMER_NAME", "TOOLS_EXEC_REQ")

    async def _message_handler(msg):
        # grab the stream sequence for logging
        seq = None
        try:
            seq = msg.metadata.stream_seq
        except Exception:
            pass

        logger.debug("⇨ [responder] got request #%s: %r", seq, msg.data)

        try:
            # 1) parse and extract fields
            payload   = json.loads(msg.data.decode())
            tool_name = payload.get("tool_name")
            reply_to  = payload.pop("reply_to", resp_pref)

            exec_args = {
                "tool_name":  tool_name,
                "input_args": payload.get("input_args", {}),
                "repo_url":   payload.get("repo_url"),
                "repo_name":  payload.get("repo_name"),
                "repo_owner": payload.get("repo_owner"),
                "metadata":   payload.get("metadata", {}),
                "turn_id":    payload.get("turn_id"),
            }

            # 2) time the execution
            start = time.perf_counter()

            # 3) invoke the tool off the event loop
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

            # 4) attach execution time metadata
            envelope.setdefault("meta", {})
            envelope["meta"]["exec_time"] = time.perf_counter() - start

            # 5) publish the response
            await js.publish(reply_to, json.dumps(envelope).encode())
            logger.debug("⇨ [responder] published response on %s", reply_to)

        except Exception:
            logger.exception("❌ unexpected error in message handler")

        finally:
            # 6) ACK the original request so it's removed from the stream
            try:
                await msg.ack()
                logger.debug("⇨ [responder] acked request #%s", seq)
            except Exception:
                logger.exception("❌ failed to ack request #%s", seq)


    # subscribe with an async callback
    await js.subscribe(
        req_sub,
        durable=durable,
        cb=_message_handler,
        ack_wait=config.get("NATS_ACK_WAIT", 30_000_000_000)  # 30s in nanoseconds
    )
    logger.info("Responder listening on %s (durable=%s)", req_sub, durable)

    # keep the coroutine alive forever
    await asyncio.Event().wait()
