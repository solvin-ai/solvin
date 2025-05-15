# modules/tools_jetstream_pub.py
# modules/tools_jetstream_pub.py

import json
from typing import Any

from modules.tools_jetstream_init import get_jetstream
from shared.config import config
from shared.logger import logger


async def publish_exec_request(payload: dict) -> Any:
    """
    Publish the given payload dict to the exec-request subject.
    Returns the raw ack (has .stream and .seq attributes).
    """
    # 1) Get or initialize our shared NATS+JetStream context
    js = await get_jetstream()

    # 2) Prepare subject & data
    subject = config["NATS_SUBJECT_EXEC_REQ"]
    data = json.dumps(payload).encode()

    # 3) Publish with an optional timeout for the server ack
    timeout = config.get("NATS_PUBLISH_ACK_TIMEOUT", 5.0)
    ack = await js.publish(subject, data, timeout=timeout)

    # 4) Log & return the publish‐ack (contains stream & seq)
    logger.debug("Published exec request to %s, stream=%s seq=%s",
                 subject, getattr(ack, "stream", None), getattr(ack, "seq", None))
    return ack
