# SPDX-License-Identifier: GPL-3.0-or-later
"""One-shot Discord connectivity test via REST (no gateway needed)."""

import logging

logger = logging.getLogger(__name__)

_API = "https://discord.com/api/v10"
_DEFAULT_MSG = "WorkerBee bot test: this channel is reachable. You can run from here."


def test_post(token: str, channel_id: str, content: str = _DEFAULT_MSG):
    """Post `content` to `channel_id`; return (ok, message)."""
    token = (token or "").strip()
    channel_id = str(channel_id or "").strip()
    if not token:
        return False, "Enter a bot token first."
    if not channel_id.isdigit():
        return False, "Enter a valid numeric channel ID first."

    try:
        import requests
    except Exception:
        return False, "The 'requests' library is not available."

    try:
        resp = requests.post(
            f"{_API}/channels/{channel_id}/messages",
            headers={
                "Authorization": f"Bot {token}",
                "Content-Type": "application/json",
            },
            json={"content": content},
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"

    if 200 <= resp.status_code < 300:
        return True, "Test message posted. Check your channel."
    if resp.status_code == 401:
        return False, "Invalid bot token (401)."
    if resp.status_code == 403:
        return False, ("Bot has no access (403). Invite the bot to the server "
                       "and let it post in this channel.")
    if resp.status_code == 404:
        return False, "Channel not found (404). Check the channel ID."
    if resp.status_code == 429:
        return False, "Rate limited by Discord (429). Try again shortly."

    detail = ""
    try:
        detail = str(resp.json().get("message", "")).strip()
    except Exception:
        detail = ""
    return False, f"Failed ({resp.status_code})" + (f": {detail}" if detail else ".")
