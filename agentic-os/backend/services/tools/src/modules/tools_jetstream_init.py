# modules/tools_jetstream_init.py

import asyncio
import time
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
    Lazy‐init a single NATS+JetStream connection,
    and ensure the EXEC_REQ stream exists.
    """
    global _js
    async with _lock:
        if _js is not None:
            logger.debug("get_jetstream: returning cached JetStreamContext")
            return _js

        # 1) Connect to NATS
        url = config["NATS_URL"]
        if url.startswith("http://"):
            url = "nats://" + url[len("http://"):]
        logger.debug("get_jetstream: connecting to NATS at %s", url)
        t0 = time.perf_counter()
        await _nats_cli.connect(servers=[url])
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("get_jetstream: connected to NATS at %s (%.1fms)", url, elapsed)

        js = _nats_cli.jetstream()

        # 2) Declare or update our single stream
        stream_name = config["NATS_STREAM_EXEC_REQ"]
        req_sub     = config["NATS_SUBJECT_EXEC_REQ"]
        resp_pref   = config["NATS_SUBJECT_EXEC_RESP"]
        subjects    = [req_sub, resp_pref, f"{resp_pref}.>"]

        # try to create the stream
        try:
            logger.debug("get_jetstream: adding stream %s → %s", stream_name, subjects)
            t0 = time.perf_counter()
            await js.add_stream(name=stream_name, subjects=subjects)
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("get_jetstream: stream %s created in %.1fms", stream_name, elapsed)
        except Exception as e_add:
            logger.debug("get_jetstream: add_stream failed (%s), trying update", e_add)
            try:
                t0 = time.perf_counter()
                await js.update_stream(name=stream_name, subjects=subjects)
                elapsed = (time.perf_counter() - t0) * 1000
                logger.info("get_jetstream: stream %s updated in %.1fms", stream_name, elapsed)
            except Exception as e_upd:
                logger.debug(
                    "get_jetstream: update_stream also failed (%s); assuming existing stream configuration is correct",
                    e_upd
                )

        _js = js
        return _js
