import subprocess
import requests
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values

config = dotenv_values(Path.home() / "personal/status_checker/.env")
BOT_TOKEN = config["TELEGRAM_BOT_TOKEN"]
CHAT_ID = config["TELEGRAM_CHAT_ID"]
WEBSITE_URL = config["WEBSITE_URL"]
SERVICES = ["hp-bot", "funko-bot"]

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    )

def check_service(name):
    result = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True)
    return result.stdout.strip() == "active"

def check_website():
    try:
        r = requests.get(WEBSITE_URL, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def get_status_message():
    lines = ["<b>🫐  Raspberry Pi Status</b>", "───────────────────"]
    site_icon = "✅" if check_website() else "❌"
    lines.append(f"🌐 pflaumax.dev  {site_icon}")
    for s in SERVICES:
        icon = "✅" if check_service(s) else "❌"
        lines.append(f"🤖 {s}  {icon}")
    lines.append("───────────────────")
    lines.append(f"🕐 {datetime.now().strftime('%H:%M')}")
    return "\n".join(lines)

def get_updates(offset=None):
    params = {"timeout": 30, "offset": offset}
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params=params, timeout=35)
    return r.json().get("result", [])

print("Status bot started...")
offset = None
while True:
    try:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            text = msg.get("text", "")
            if text == "/status":
                send_message(get_status_message())
    except Exception as e:
        print(f"Error: {e}")
