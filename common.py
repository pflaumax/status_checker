import subprocess
from datetime import datetime
from pathlib import Path

import requests
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
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
        )
        r.raise_for_status()
    except Exception as e:
        print(f"Failed to send message: {e}")


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


def _footer() -> str:
    return f"⏱ Uptime: {_get_uptime()}\n🕐 {datetime.now().strftime('%H:%M')}"


def get_status_message() -> str:
    lines = ["<b>🫐  Raspberry Pi Status</b>", "───────────────────"]
    site_icon = "✅" if check_website() else "❌"
    lines.append(f"🌐 pflaumax.dev  {site_icon}")
    for s in SERVICES:
        icon = "✅" if check_service(s) else "❌"
        lines.append(f"🤖 {s}  {icon}")
    lines.append("───────────────────")
    lines.append(_footer())
    return "\n".join(lines)


def _get_cpu_load() -> str:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()[:3]
            return f"{parts[0]} {parts[1]} {parts[2]}"
    except Exception:
        return "N/A"


def _parse_meminfo() -> dict[str, int]:
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                try:
                    parts = line.split()
                    info[parts[0].rstrip(":")] = int(parts[1])
                except (IndexError, ValueError):
                    continue
    except Exception:
        pass
    return info


def _fmt_gb(kb: int) -> str:
    return f"{kb / 1024 / 1024:.2f}G"


def _get_cpu_temp() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def _get_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            secs = int(float(f.read().split()[0]))
        days, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        return (
            f"{days} days, {h:02d}:{m:02d}:{s:02d}"
            if days
            else f"{h:02d}:{m:02d}:{s:02d}"
        )
    except Exception:
        return "N/A"


def get_system_message() -> str:
    mem = _parse_meminfo()
    temp = _get_cpu_temp()
    temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
    temp_icon = "🔥" if temp is not None and temp > 75 else "🌡"

    lines = [
        "<b>🫐  Raspberry Pi System</b>",
        "───────────────────",
        f"🖥 <b>CPU (1/5/15m):</b> {_get_cpu_load()}",
    ]

    if mem:
        total = mem.get("MemTotal", 0)
        used = total - mem.get("MemAvailable", 0)
        lines.append(f"💾 <b>RAM:</b> {_fmt_gb(used)}/{_fmt_gb(total)}")

    lines.append(f"{temp_icon} <b>Temp:</b> {temp_str}")
    lines.append("───────────────────")
    lines.append(_footer())

    return "\n".join(lines)


TEMP_THRESHOLD = float(config.get("TEMP_THRESHOLD", "85.0"))
LOAD_THRESHOLD = float(config.get("LOAD_THRESHOLD", "4.0"))


def get_system_alerts() -> list[str]:
    alerts = []
    temp = _get_cpu_temp()
    if temp is not None and temp >= TEMP_THRESHOLD:
        alerts.append(f"🔥 <b>Critical temperature:</b> {temp:.1f}°C")
    load_str = _get_cpu_load()
    if load_str != "N/A":
        load_15m = float(load_str.split()[2])
        if load_15m >= LOAD_THRESHOLD:
            alerts.append(f"⚠️ <b>CPU overloaded for 15m+!</b> (Load: {load_15m})")
    return alerts
