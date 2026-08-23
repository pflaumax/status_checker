import json
import time
from datetime import datetime
from pathlib import Path

from common import (
    DOCKER_CONTAINERS,
    DOCKER_ENABLED,
    PIHOLE_ENABLED,
    SERVICES,
    _get_tailscale_ip,
    check_service,
    check_website,
    get_docker_states,
    get_pihole_status,
    get_smart_alerts,
    get_system_alerts,
    send_message,
)

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

# --- Docker containers ---
if DOCKER_ENABLED:
    states = get_docker_states()
    if states is None:
        if _should_alert(state, "docker"):
            send_message(f"⚠️ <b>Docker</b> is not responding!\n🕐 {now}")
            _mark_alerted(state, "docker")
    else:
        _clear_alert(state, "docker", "<b>Docker</b> is responding again!")
        for container in DOCKER_CONTAINERS:
            key = f"container:{container}"
            container_state = states.get(container)
            if container_state == "running":
                _clear_alert(state, key, f"<b>{container}</b> is back up!")
            elif _should_alert(state, key):
                send_message(
                    f"⚠️ <b>{container}</b> is {container_state or 'missing'}!\n🕐 {now}"
                )
                _mark_alerted(state, key)

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

# --- Pi-hole check ---
if PIHOLE_ENABLED:
    pihole = get_pihole_status()
    if not pihole.reachable:
        cause = (
            "password was rejected"
            if pihole.state == "auth"
            else "is not responding"
        )
        if _should_alert(state, "pihole"):
            send_message(f"⚠️ <b>Pi-hole</b> {cause}!\n🕐 {now}")
            _mark_alerted(state, "pihole")
    else:
        _clear_alert(state, "pihole", "<b>Pi-hole</b> is back online!")
        if pihole.state == "disabled" and pihole.timer is None:
            trouble = "blocking is disabled indefinitely"
        elif pihole.state in ("failed", "unknown"):
            trouble = f"reports blocking state: {pihole.state}"
        else:
            trouble = None

        if trouble:
            if _should_alert(state, "pihole:blocking"):
                send_message(f"⚠️ <b>Pi-hole</b> {trouble}!\n🕐 {now}")
                _mark_alerted(state, "pihole:blocking")
        elif pihole.blocking:
            # Recovery only once filtering is genuinely back on -- a timed
            # pause must not clear the alert.
            _clear_alert(state, "pihole:blocking", "<b>Pi-hole</b> blocking is back on!")

# --- Drive health ---
smart_alerts = get_smart_alerts()
if smart_alerts:
    if _should_alert(state, "smart"):
        send_message(
            "🚨 <b>Drive health</b>\n\n" + "\n".join(smart_alerts) + f"\n\n🕐 {now}"
        )
        _mark_alerted(state, "smart")
else:
    _clear_alert(state, "smart", "Drive health back to normal.")

# --- Tailscale check ---
if not _get_tailscale_ip():
    if _should_alert(state, "tailscale"):
        send_message(f"⚠️ <b>Tailscale</b> is offline!\n🕐 {now}")
        _mark_alerted(state, "tailscale")
else:
    _clear_alert(state, "tailscale", "<b>Tailscale</b> is back online!")

_save_state(state)
