# modules/tools_jetstream_sub.py

import asyncio
import json
import time

from modules.tools_jetstream_init import get_jetstream
from shared.config            import config
from shared.logger            import logger
from modules.tools_executor   import execute_tool
from modules.tools_registry   import get_global_registry


async def run_responder():
    """
    Durable PUSH‐consumer: for each JS‐request message,
    execute the tool, publish to that message’s reply_to inbox,
    then ACK the request so it’s removed from JetStream.
    """
    js        = await get_jetstream()
    req_sub   = config["NATS_SUBJECT_EXEC_REQ"]    # e.g. "tools.execute.request"
    resp_pref = config["NATS_SUBJECT_EXEC_RESP"]   # e.g. "tools.execute.response"

    async def _message_handler(msg):
        # grab sequence if present
        seq = None
        try:
            seq = msg.metadata.stream_seq
        except Exception:
            pass

        logger.debug("⇨ [responder] got request #%s: %r", seq, msg.data)

        try:
            payload   = json.loads(msg.data.decode())
            tool_name = payload["tool_name"]
            # remove it so execute_tool() doesn’t choke
            reply_to  = payload.pop("reply_to", resp_pref)

            # build exactly the args execute_tool expects
            exec_args = {
                "tool_name":  tool_name,
                "input_args": payload.get("input_args", {}),
                "repo_name":  payload.get("repo_name"),
                "repo_owner": payload.get("repo_owner"),
                "metadata":   payload.get("metadata"),
                "turn_id":    payload.get("turn_id"),
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
                    envelope = execute_tool(**exec_args)
                except Exception as ex:
                    logger.exception("Error executing tool %s", tool_name)
                    envelope = {
                        "status": "failure",
                        "error": {
                            "code":    "EXECUTION_ERROR",
                            "message": str(ex)
                        }
                    }
            envelope["meta"] = {"exec_time": time.perf_counter() - start}

            # publish the one‐to‐one reply
            await js.publish(reply_to, json.dumps(envelope).encode())
            logger.debug("⇨ [responder] published response on %s", reply_to)

        except Exception:
            logger.exception("❌ unexpected error in message handler")
        finally:
            # ack _every_ message so it doesn’t stay “in‐flight”
            try:
                await msg.ack()
                logger.debug("⇨ [responder] acked request #%s", seq)
            except Exception:
                logger.exception("❌ failed to ack request #%s", seq)


    # subscribe once; JS will invoke _message_handler() for each message
    await js.subscribe(
        req_sub,
        durable="TOOLS_EXEC_REQ",
        cb=_message_handler
    )
    logger.info("Responder listening on %s", req_sub)

    # keep the task alive
    await asyncio.Event().wait()
