import json
import time
from datetime import datetime
from pathlib import Path
from common import SERVICES, send_message, check_service, check_website, get_system_alerts
from common import _get_tailscale_ip

COOLDOWN = 24 * 3600  # 24 hours
STATE_FILE = Path(__file__).parent / ".alert_state.json"

now = datetime.now().strftime("%H:%M")


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def _should_alert(state: dict, key: str) -> bool:
    last = state.get(key, 0)
    return (time.time() - last) >= COOLDOWN


def _mark_alerted(state: dict, key: str) -> None:
    state[key] = time.time()


def _clear_alert(state: dict, key: str, recovery_msg: str) -> None:
    if key in state:
        del state[key]
        send_message(f"✅ {recovery_msg}\n🕐 {now}")


state = _load_state()

# --- Service checks ---
for service in SERVICES:
    key = f"service:{service}"
    if not check_service(service):
        if _should_alert(state, key):
            send_message(f"⚠️ <b>{service}</b> is DOWN!\n🕐 {now}")
            _mark_alerted(state, key)
    else:
        _clear_alert(state, key, f"<b>{service}</b> is back up!")

# --- Website check ---
if not check_website():
    if _should_alert(state, "website"):
        send_message(f"⚠️ <b>pflaumax.dev</b> is not responding!\n🕐 {now}")
        _mark_alerted(state, "website")
else:
    _clear_alert(state, "website", "<b>pflaumax.dev</b> is back online!")

# --- System alerts (temp, cpu, disk) ---
alerts = get_system_alerts()
if alerts:
    if _should_alert(state, "system"):
        send_message(f"🚨 <b>Critical Raspberry Pi state!</b>\n\n" + "\n".join(alerts) + f"\n\n🕐 {now}")
        _mark_alerted(state, "system")
else:
    _clear_alert(state, "system", "System metrics back to normal.")

# --- Tailscale check ---
if not _get_tailscale_ip():
    if _should_alert(state, "tailscale"):
        send_message(f"⚠️ <b>Tailscale</b> is offline!\n🕐 {now}")
        _mark_alerted(state, "tailscale")
else:
    _clear_alert(state, "tailscale", "<b>Tailscale</b> is back online!")

_save_state(state)
