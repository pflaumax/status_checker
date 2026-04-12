import signal
import time
import requests
from common import BOT_TOKEN, CHAT_ID, send_message, get_status_message, get_system_message

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


print("Status bot started...")
offset = None
while running:
    try:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            if str(msg.get("chat", {}).get("id")) != CHAT_ID:
                continue
            if text == "/status":
                send_message(get_status_message())
            elif text == "/system":
                send_message(get_system_message())
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
