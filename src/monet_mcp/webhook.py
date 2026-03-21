"""Notification and webhook logic."""

import json
import logging
import threading
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger("monet")

# Event display config: (title, tags, priority)
_WEBHOOK_EVENTS = {
    "plot_started":         ("Plot Started",        "art,arrow_forward",    "3"),
    "plot_complete":        ("Plot Complete",        "art,white_check_mark", "3"),
    "plot_error":           ("Plot Error",           "art,x",                "5"),
    "pen_change_requested": ("Pen Change Needed",    "pen,raised_hand",      "5"),
    "notification":         ("Monet",                "speech_balloon",       "3"),
}

# Module-level webhook URL, set by server at startup
_webhook_url: str = ""


def configure_webhook(url: str) -> None:
    """Set the webhook URL. Called once at server startup."""
    global _webhook_url
    _webhook_url = url


def _send_webhook(event: str, data: Dict[str, Any]) -> None:
    """Fire-and-forget POST to the configured webhook URL.
    Supports ntfy.sh natively (detected by URL containing 'ntfy')
    and falls back to plain JSON POST for generic webhooks.
    Runs in a daemon thread to avoid blocking tool responses."""
    if not _webhook_url:
        return

    def _post():
        title, tags, priority = _WEBHOOK_EVENTS.get(event, ("Monet", "robot", "3"))
        message = data.get("message") or data.get("pen") or data.get("filename") or event

        is_ntfy = "ntfy" in _webhook_url.lower()

        if is_ntfy:
            # ntfy expects the message as the raw body, metadata in headers
            body = str(message).encode("utf-8")
            headers = {
                "Title": title,
                "Tags": tags,
                "Priority": priority,
            }
            # Append extra detail lines for richer notifications
            details = []
            for k, v in data.items():
                if k != "message" and v is not None:
                    details.append(f"{k}: {v}")
            if details:
                body = (str(message) + "\n" + "\n".join(details)).encode("utf-8")
        else:
            # Generic JSON webhook
            body = json.dumps({
                "event": event,
                "timestamp": datetime.now().isoformat(),
                **data,
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}

        req = urllib.request.Request(
            _webhook_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Webhook sent ({event}): {resp.status}")
        except Exception as e:
            logger.warning(f"Webhook failed ({event}): {e}")

    threading.Thread(target=_post, daemon=True).start()
