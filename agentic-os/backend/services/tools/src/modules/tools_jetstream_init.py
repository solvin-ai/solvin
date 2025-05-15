# modules/tools_jetstream_init.py

import asyncio
from typing import Optional

from nats.aio.client import Client as NATS
from nats.js.client import JetStreamContext

from shared.config import config
from shared.logger import logger

_nats_cli: NATS = NATS()
_js: Optional[JetStreamContext] = None
_lock = asyncio.Lock()

async def get_jetstream() -> JetStreamContext:
    """
    Lazy-init a single NATS+JetStream connection,
    and ensure STREAM_TOOLS exists covering both the fixed
    request subject and all per-request response subjects.
    """
    global _js
    async with _lock:
        if _js is not None:
            return _js

        # 1) connect to NATS
        url = config["NATS_URL"]
        if url.startswith("http://"):
            url = "nats://" + url[len("http://"):]
        await _nats_cli.connect(servers=[url])
        js = _nats_cli.jetstream()
        logger.info("JetStream connected to %s", url)

        # 2) declare or update our single stream
        stream_name = config["NATS_STREAM_EXEC_REQ"]
        req_sub     = config["NATS_SUBJECT_EXEC_REQ"]
        resp_pref   = config["NATS_SUBJECT_EXEC_RESP"]
        # include both the fixed response subject and any sub-subjects (for per-UUID inboxes)
        subjects = [req_sub, resp_pref, f"{resp_pref}.>"]

        try:
            await js.add_stream(name=stream_name, subjects=subjects)
            logger.debug("Created stream %s → %s", stream_name, subjects)
        except Exception:
            try:
                await js.update_stream(name=stream_name, subjects=subjects)
                logger.debug("Updated stream %s → %s", stream_name, subjects)
            except Exception:
                logger.debug("Stream %s already exists with %s", stream_name, subjects)

        _js = js
        return _js
