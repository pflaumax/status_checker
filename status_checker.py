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
    result = subprocess.run(
        ["systemctl", "is-active", name],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "active"

def check_website():
    try:
        r = requests.get(WEBSITE_URL, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

for service in SERVICES:
    if not check_service(service):
        send_message(f"⚠️ <b>{service}</b> is DOWN!\n🕐 {datetime.now().strftime('%H:%M')}")

if not check_website():
    send_message(f"⚠️ <b>pflaumax.dev</b> is not responding!\n🕐 {datetime.now().strftime('%H:%M')}")
