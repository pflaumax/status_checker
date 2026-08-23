import signal
import time
from collections.abc import Callable
from typing import Any

import requests

from common import (
    BOT_TOKEN,
    answer_callback,
    apply_pihole_blocking,
    edit_message,
    get_docker_message,
    get_pihole_keyboard,
    get_pihole_message,
    get_services_message,
    get_speedhistory_message,
    get_speedtest_message,
    get_status_message,
    get_system_message,
    is_owner,
    send_message,
    set_bot_commands,
)

running = True


def shutdown(_sig, _frame):
    global running
    print("Shutting down...")
    running = False


_ = signal.signal(signal.SIGINT, shutdown)
_ = signal.signal(signal.SIGTERM, shutdown)


def get_updates(offset=None):
    params = {"timeout": 30, "offset": offset}
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params=params, timeout=35)
    return r.json().get("result", [])


def send_pihole_panel() -> None:
    text, status = get_pihole_message()
    send_message(text, get_pihole_keyboard(status))


# Handlers take the argument string — everything after the command word — so
# /speedtest can read its numbers. Handlers that need nothing ignore it.
COMMANDS: list[tuple[str, str, Callable[[str], None]]] = [
    ("status", "Service health", lambda _: send_message(get_status_message())),
    ("system", "Hardware stats", lambda _: send_message(get_system_message())),
    ("docker", "Container health", lambda _: send_message(get_docker_message())),
    ("services", "Remote access links", lambda _: send_message(get_services_message())),
    ("pihole", "DNS filtering and pause", lambda _: send_pihole_panel()),
    ("speedtest", "Log a speedtest reading", lambda a: send_message(get_speedtest_message(a))),
    ("speedhistory", "Speeds by network", lambda a: send_message(get_speedhistory_message(a))),
]


def handle_command(text: str) -> None:
    if not text.startswith("/"):
        return
    head, _, args = text[1:].partition(" ")
    # Tolerate the /command@botname form used in groups.
    name = head.split("@")[0].lower()
    for command, _description, handler in COMMANDS:
        if command == name:
            handler(args.strip())
            return


def _parse_action(data: str) -> tuple[bool, int | None] | None:
    """Map callback data to (blocking, timer). None means we do not know it."""
    if data == "ph:resume":
        return True, None
    if data.startswith("ph:pause:"):
        try:
            return False, int(data.split(":")[2])
        except (IndexError, ValueError):
            return None
    return None


def handle_callback(query: dict[str, Any]) -> None:
    query_id = query.get("id", "")
    if not is_owner((query.get("from") or {}).get("id")):
        answer_callback(query_id, "Not allowed")
        return

    try:
        action = _parse_action(query.get("data", ""))
        if action is None:
            answer_callback(query_id, "Unknown button")
            return

        enabled, seconds = action
        ok, text, status = apply_pihole_blocking(enabled, seconds)
        if not ok:
            answer_callback(query_id, "Pi-hole did not accept that")
        elif enabled:
            answer_callback(query_id, "Blocking enabled")
        else:
            answer_callback(query_id, f"Paused for {(seconds or 0) // 60}m")

        message_id = (query.get("message") or {}).get("message_id")
        if message_id is not None:
            edit_message(message_id, text, get_pihole_keyboard(status))
    except Exception as e:
        print(f"Callback failed: {e}")
        answer_callback(query_id, "Something went wrong")


def main() -> None:
    print("Status bot started...")
    set_bot_commands([(c, d) for c, d, _ in COMMANDS])
    offset = None
    while running:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                    continue
                msg = update.get("message", {})
                if not is_owner(msg.get("chat", {}).get("id")):
                    continue
                handle_command(msg.get("text", ""))
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
