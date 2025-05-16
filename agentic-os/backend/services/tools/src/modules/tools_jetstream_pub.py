# modules/tools_jetstream_pub.py

import json
import time
from typing import Any

from modules.tools_jetstream_init import get_jetstream
from shared.config import config
from shared.logger import logger

async def publish_exec_request(payload: dict) -> Any:
    """
    Publish the given payload dict to the exec‐request subject,
    returning the raw JetStream publish‐ack (has .stream and .seq).
    Instrumented with debug/timing logs to see where any delay occurs.
    """
    # 1) Ensure we have an initialized JetStream context
    t0_js = time.perf_counter()
    js = await get_jetstream()
    t_js = (time.perf_counter() - t0_js) * 1000
    logger.debug("publish_exec_request: get_jetstream() took %.1fms", t_js)

    # 2) Prepare subject & payload
    subject = config["NATS_SUBJECT_EXEC_REQ"]
    data = json.dumps(payload).encode()
    timeout = config.get("NATS_PUBLISH_ACK_TIMEOUT", 5.0)

    logger.debug(
        "publish_exec_request: publishing to %s (timeout=%.1fs), payload keys=%s",
        subject,
        timeout,
        list(payload.keys()),
    )

    # 3) Publish and measure
    t0_pub = time.perf_counter()
    try:
        ack = await js.publish(subject, data, timeout=timeout)
    except Exception as e:
        t_pub_err = (time.perf_counter() - t0_pub) * 1000
        logger.error(
            "publish_exec_request: js.publish FAILED after %.1fms: %s",
            t_pub_err,
            e,
            exc_info=True,
        )
        raise
    t_pub = (time.perf_counter() - t0_pub) * 1000
    logger.debug(
        "publish_exec_request: js.publish SUCCEEDED in %.1fms → stream=%s seq=%s",
        t_pub,
        getattr(ack, "stream", None),
        getattr(ack, "seq", None),
    )

    return ack
