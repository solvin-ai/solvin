# modules/slack_integration.py

import threading
import signal
import atexit
import re
import os
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import backoff
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from shared.config import config
from shared.logger import logger


# ─── Configuration ────────────────────────────────────────────────────────────

SLACK_APP_TOKEN    = config.get('SLACK_APP_TOKEN')
SLACK_BOT_TOKEN    = config.get('SLACK_BOT_TOKEN')
SLACK_TARGET       = config.get('SLACK_TARGET', '').strip().upper()   # "USERNAME"|"CHANNEL_ID"|"CHANNEL_NAME"
SLACK_CHANNEL_ID   = config.get('SLACK_CHANNEL_ID')
SLACK_CHANNEL_NAME = config.get('SLACK_CHANNEL_NAME')
SLACK_USERNAME     = config.get('SLACK_USERNAME')

try:
    SLACK_REPLY_TIMEOUT = int(config.get('SLACK_REPLY_TIMEOUT', 1200))
except (TypeError, ValueError):
    logger.warning("Invalid SLACK_REPLY_TIMEOUT; defaulting to 1200s")
    SLACK_REPLY_TIMEOUT = 1200

if not SLACK_APP_TOKEN or not SLACK_BOT_TOKEN:
    logger.warning("Slack disabled: missing APP or BOT token")
    slack_enabled = False
elif not any([SLACK_USERNAME, SLACK_CHANNEL_ID, SLACK_CHANNEL_NAME]):
    logger.warning("Slack disabled: need SLACK_USERNAME or SLACK_CHANNEL_ID or SLACK_CHANNEL_NAME")
    slack_enabled = False
else:
    slack_enabled = True


# ─── HTTP Client ──────────────────────────────────────────────────────────────

sync_client: Optional[WebClient] = None
if slack_enabled:
    rate_limiter = RateLimitErrorRetryHandler(max_retry_count=3)
    sync_client = WebClient(token=SLACK_BOT_TOKEN, retry_handlers=[rate_limiter])


# ─── In-memory pending replies state ──────────────────────────────────────────

# thread_ts → {
#    'fpath': str,
#    'event': threading.Event,
#    'reply': Optional[str],
#    'user': Optional[str]
# }
pending_replies: Dict[str, Dict[str, Any]] = {}
_listener_started        = False
_listener_lock           = threading.Lock()
_connection_established  = threading.Event()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _giveup_on_non_429(exc: Exception) -> bool:
    if not isinstance(exc, SlackApiError):
        return True
    return exc.response.status_code != 429


def _resolve_user_id(name_or_id: str) -> str:
    v = name_or_id.strip()
    if v.startswith('@'):
        v = v[1:]
    if re.match(r"^U[A-Z0-9]{8,}$", v):
        return v

    cursor: Optional[str] = None
    while True:
        resp = sync_client.users_list(limit=200, cursor=cursor)
        for m in resp.get("members", []):
            prof = m.get("profile", {}) or {}
            if m.get("name") == v or prof.get("display_name") == v or prof.get("real_name") == v:
                return m["id"]
        meta = resp.get("response_metadata", {}) or {}
        cursor = meta.get("next_cursor")
        if not cursor:
            break

    raise ValueError(f"Slack user not found: {name_or_id}")


def _resolve_channel_name(name_or_id: str) -> str:
    v = name_or_id.strip()
    if re.match(r"^[CG][A-Z0-9]{8,}$", v):
        return v
    if v.startswith('#'):
        v = v[1:]
    resp = sync_client.conversations_list(types="public_channel,private_channel")
    for ch in resp.get("channels", []):
        if ch.get("name") == v:
            return ch["id"]
    raise ValueError(f"Slack channel not found: {name_or_id}")


def _get_post_channel() -> str:
    t = (SLACK_TARGET or '').upper()
    if t == "USERNAME" and SLACK_USERNAME:
        uid = _resolve_user_id(SLACK_USERNAME)
        return sync_client.conversations_open(users=uid)["channel"]["id"]
    if t == "CHANNEL_ID" and SLACK_CHANNEL_ID:
        return SLACK_CHANNEL_ID
    if t == "CHANNEL_NAME" and SLACK_CHANNEL_NAME:
        return _resolve_channel_name(SLACK_CHANNEL_NAME)
    if SLACK_USERNAME:
        uid = _resolve_user_id(SLACK_USERNAME)
        return sync_client.conversations_open(users=uid)["channel"]["id"]
    if SLACK_CHANNEL_ID:
        return SLACK_CHANNEL_ID
    if SLACK_CHANNEL_NAME:
        return _resolve_channel_name(SLACK_CHANNEL_NAME)
    raise RuntimeError("No valid Slack target configured")


@backoff.on_exception(
    backoff.expo,
    SlackApiError,
    max_tries=5,
    giveup=_giveup_on_non_429,
    on_backoff=lambda d: logger.warning(
        "Slack rate limit, retrying in %.1fs (try #%d)", d["wait"], d["tries"]
    )
)
def post_message(text: str, blocks: list = None) -> dict:
    channel = _get_post_channel()
    return sync_client.chat_postMessage(channel=channel, text=text, blocks=blocks)


def start_listener() -> None:
    """
    Launch the Slack Bolt SocketMode listener once, in a non-daemon thread.
    """
    global _listener_started
    if not slack_enabled:
        return

    with _listener_lock:
        if _listener_started:
            return
        _listener_started = True

    app = App(token=SLACK_BOT_TOKEN, client=sync_client)
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)

    @app.event("hello")
    def _on_hello(**_):
        logger.info("Slack SocketMode connected")
        _connection_established.set()

    @app.event("message")
    def _on_thread_reply(event, client, logger):
        thread_ts = event.get("thread_ts")
        user_id   = event.get("user")
        text      = event.get("text")
        channel   = event.get("channel")
        if not (thread_ts and user_id and text):
            return

        container = pending_replies.pop(thread_ts, None)
        if not container:
            return

        fpath = container["fpath"]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            with open(fpath, "a", encoding="utf-8") as f:
                f.write(f"[{stamp}] Reply by {user_id}: {text}\n")
        except Exception as e:
            logger.error("Failed writing Slack reply to %s: %s", fpath, e)

        container["reply"] = text
        container["user"]  = user_id
        container["event"].set()

        try:
            client.reactions_add(channel=channel, timestamp=thread_ts, name="white_check_mark")
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=":white_check_mark: Thanks for your reply! This thread is now closed."
            )
        except SlackApiError as e:
            logger.error("Failed closing thread %s: %s", thread_ts, e)

    thread = threading.Thread(target=handler.start, name="SlackSocketMode")
    thread.start()
    logger.info("Slack Socket Mode listener started")

    def _shutdown(signum=None, frame=None):
        logger.info("Shutting down Slack listener (signal=%s)", signum)
        handler.stop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _shutdown)
    atexit.register(_shutdown)

    if not _connection_established.wait(timeout=10):
        logger.warning("Slack SocketMode did not connect within 10s")


def post_and_wait(
    text: str,
    blocks: list = None,
    fpath: Optional[str] = None,
    timeout: Optional[int] = None
) -> Tuple[dict, Optional[str]]:
    """
    Posts a message and blocks until the first thread-reply arrives or timeout.
    Returns (post_response, reply_text or None).
    """
    if not slack_enabled or sync_client is None:
        return {}, None

    start_listener()
    resp = post_message(text=text, blocks=blocks)
    channel = resp.get("channel")
    ts      = resp.get("ts")
    if not (channel and ts):
        return resp, None

    ev = threading.Event()
    pending_replies[ts] = {"fpath": fpath or "", "event": ev, "reply": None, "user": None}

    waited = ev.wait(timeout if timeout is not None else SLACK_REPLY_TIMEOUT)
    container = pending_replies.pop(ts, None)

    if waited and container:
        return resp, container["reply"]
    else:
        return resp, None


@backoff.on_exception(
    backoff.expo,
    SlackApiError,
    max_tries=3,
    giveup=_giveup_on_non_429,
    on_backoff=lambda d: logger.warning(
        "Slack rate limited on file upload, retrying in %.1fs (try #%d)",
        d["wait"], d["tries"]
    )
)
def upload_file(
    file_path: str,
    title: Optional[str] = None,
    initial_comment: Optional[str] = None,
    channels: Optional[str] = None
) -> dict:
    """
    Uploads a local file to Slack:
      - file_path: local filesystem path
      - title: Slack file title
      - initial_comment: accompanying message
      - channels: comma-separated channel IDs (defaults to configured target)
    """
    if not slack_enabled or sync_client is None:
        raise RuntimeError("Slack integration is disabled")

    dest = channels or _get_post_channel()
    with open(file_path, "rb") as fp:
        return sync_client.files_upload(
            channels=dest,
            file=fp,
            filename=os.path.basename(file_path),
            title=title or os.path.basename(file_path),
            initial_comment=initial_comment or ""
        )
