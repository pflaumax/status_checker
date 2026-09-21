import html
import json
import time
from datetime import datetime
from pathlib import Path

from common import (
    DOCKER_CONTAINERS,
    DOCKER_ENABLED,
    INTEGRITY_ENABLED,
    JOPLIN_ENABLED,
    PIHOLE_ENABLED,
    ROOTFS_ENABLED,
    SERVICES,
    USB_CLONE_ENABLED,
    USB_CLONE_MAX_DAYS,
    _get_tailscale_ip,
    _rootfs_line,
    _usb_clone_line,
    check_joplin,
    check_service,
    check_website,
    get_docker_states,
    get_integrity_status,
    get_pihole_status,
    get_rootfs_status,
    get_smart_alerts,
    get_system_alerts,
    integrity_problem,
    rootfs_has_errors,
    send_message,
    usb_clone_overdue,
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

# --- Joplin Server check ---
if JOPLIN_ENABLED:
    if not check_joplin():
        if _should_alert(state, "joplin"):
            send_message(f"⚠️ <b>Joplin Server</b> is not responding!\n🕐 {now}")
            _mark_alerted(state, "joplin")
    else:
        _clear_alert(state, "joplin", "<b>Joplin Server</b> is back online!")

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

# --- SD card filesystem (ext4 error flag) ---
# Unavailable is not damage: only a superblock that reports errors alerts.
if ROOTFS_ENABLED:
    rootfs = get_rootfs_status()
    if rootfs_has_errors(rootfs):
        if _should_alert(state, "rootfs"):
            send_message(
                "🚨 <b>SD card filesystem reports errors</b>\n\n"
                f"{_rootfs_line(rootfs)}\n\n"
                "Files on the SD card may be damaged. Do not reboot yet: take fresh\n"
                "database dumps, then run a filesystem check (fsck) on the next boot.\n"
                f"🕐 {now}"
            )
            _mark_alerted(state, "rootfs")
    elif rootfs.available:
        _clear_alert(state, "rootfs", "SD card filesystem is clean again.")

# --- Weekly file integrity scan (dpkg -V) ---
if INTEGRITY_ENABLED:
    integrity = get_integrity_status()
    problem = integrity_problem(integrity)
    if problem:
        if _should_alert(state, "integrity"):
            detail = ""
            if integrity and integrity.mismatches:
                shown = "\n".join(f"• <code>{html.escape(p)}</code>" for p in integrity.mismatches[:8])
                more = len(integrity.mismatches) - 8
                detail = f"\n\n{shown}" + (f"\n… and {more} more" if more > 0 else "")
            send_message(
                f"🧬 <b>File integrity:</b> {html.escape(problem)}{detail}\n\n"
                "Check with <code>sudo dpkg -V</code>, then reinstall the affected\n"
                "packages with <code>sudo apt-get install --reinstall</code>.\n"
                f"🕐 {now}"
            )
            _mark_alerted(state, "integrity")
    else:
        _clear_alert(state, "integrity", "File integrity scan is clean again.")

# --- USB clone reminder ---
# The flash drive is kept out of the Pi, so an old clone is expected to happen;
# this nags once a day (COOLDOWN) until a fresh clone clears it.
if USB_CLONE_ENABLED:
    if usb_clone_overdue():
        if _should_alert(state, "usb_clone"):
            send_message(
                f"💾 <b>Time to refresh the USB clone</b> (older than {USB_CLONE_MAX_DAYS} days)\n\n"
                f"{_usb_clone_line()}\n\n"
                "Plug in the flash drive: it is cloned on Sunday at 05:00, or now with\n"
                "<code>sudo ~/personal/reiberry-rbi-backup/scripts/weekly-clone.sh</code>\n"
                f"🕐 {now}"
            )
            _mark_alerted(state, "usb_clone")
    else:
        _clear_alert(state, "usb_clone", "USB clone is up to date again.")

# --- Tailscale check ---
if not _get_tailscale_ip():
    if _should_alert(state, "tailscale"):
        send_message(f"⚠️ <b>Tailscale</b> is offline!\n🕐 {now}")
        _mark_alerted(state, "tailscale")
else:
    _clear_alert(state, "tailscale", "<b>Tailscale</b> is back online!")

_save_state(state)
