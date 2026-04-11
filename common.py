import subprocess
import requests
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values

ENV_PATH = Path(__file__).parent / ".env"
config: dict[str, str | None] = dotenv_values(ENV_PATH)


def _require(key: str) -> str:
    val = config.get(key)
    if not val:
        raise ValueError(f"Missing env var: {key}")
    return val


BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
CHAT_ID = _require("TELEGRAM_CHAT_ID")
WEBSITE_URL = _require("WEBSITE_URL")
SERVICES: list[str] = ["hp-bot", "funko-bot"]


def send_message(text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
    )


def check_service(name: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", name], capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def check_website() -> bool:
    try:
        r = requests.get(WEBSITE_URL, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def get_status_message() -> str:
    lines = ["<b>🫐  Raspberry Pi Status</b>", "───────────────────"]
    site_icon = "✅" if check_website() else "❌"
    lines.append(f"🌐 pflaumax.dev  {site_icon}")
    for s in SERVICES:
        icon = "✅" if check_service(s) else "❌"
        lines.append(f"🤖 {s}  {icon}")
    lines.append("───────────────────")
    lines.append(f"🕐 {datetime.now().strftime('%H:%M')}")
    return "\n".join(lines)
