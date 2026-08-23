import html
import json
import math
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

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
LAN_IP = config.get("LAN_IP", "192.168.50.173")
SERVICES: list[str] = ["hp-bot", "funko-bot"]

PIHOLE_URL = (config.get("PIHOLE_URL") or "http://localhost:8080").rstrip("/")
PIHOLE_PASSWORD = config.get("PIHOLE_PASSWORD") or ""

PIHOLE_ENABLED = bool(PIHOLE_PASSWORD)
PAUSE_MINUTES: list[int] = [5, 10, 30]

# Containers that are expected to be running. Override with a comma-separated
# DOCKER_CONTAINERS; set it empty to drop container monitoring entirely.
_DEFAULT_CONTAINERS = "jellyfin,qbittorrent,sonarr,radarr,prowlarr,flaresolverr"
_containers_cfg = config.get("DOCKER_CONTAINERS")
if _containers_cfg is None:
    _containers_cfg = _DEFAULT_CONTAINERS
DOCKER_CONTAINERS: list[str] = [c.strip() for c in _containers_cfg.split(",") if c.strip()]
DOCKER_ENABLED = bool(DOCKER_CONTAINERS)

# The drive holding /mnt/hdd. Empty disables SMART monitoring. smartctl needs
# raw device access, hence sudo, and an absolute path because the bot's PATH
# has no /usr/sbin.
SMART_DEVICE = config.get("SMART_DEVICE", "/dev/sdb") or ""
SMART_BIN = config.get("SMART_BIN") or "/usr/sbin/smartctl"
SMART_TEMP_THRESHOLD = float(config.get("SMART_TEMP_THRESHOLD", "55") or 55)
SMART_ENABLED = bool(SMART_DEVICE)

# Counters that should stay at zero for the life of a healthy drive. A drive
# on its way out fills these in weeks before it stops working, which is the
# whole reason for watching them.
SMART_FAILURE_COUNTERS = {
    "Reallocated_Sector_Ct": "reallocated sectors",
    "Current_Pending_Sector": "sectors pending reallocation",
    "Offline_Uncorrectable": "uncorrectable sectors",
    "UDMA_CRC_Error_Count": "cable/CRC errors",
}

TAILSCALE_SERVICES: list[tuple[str, str, int]] = [
    ("🎬", "Jellyfin", 8096),
    ("⬇️", "qBittorrent", 8090),
    ("📺", "Sonarr", 8989),
    ("🎥", "Radarr", 7878),
    ("🔍", "Prowlarr", 9696),
]


def set_bot_commands(commands: list[tuple[str, str]]) -> None:
    """Register the /-menu shown in Telegram clients."""
    _telegram(
        "setMyCommands",
        {"commands": [{"command": c, "description": d} for c, d in commands]},
    )


def is_owner(telegram_id: Any) -> bool:
    """The bot serves exactly one chat; buttons toggle network-wide DNS."""
    return str(telegram_id) == CHAT_ID


def _telegram(method: str, payload: dict[str, Any]) -> None:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
            json=payload,
            timeout=15,
        )
        if r.status_code == 400 and "message is not modified" in r.text:
            return  # redrew a panel that had not changed; nothing to report
        r.raise_for_status()
    except Exception as e:
        print(f"Telegram {method} failed: {e}")


def send_message(text: str, reply_markup: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _telegram("sendMessage", payload)


def edit_message(
    message_id: int, text: str, reply_markup: dict[str, Any] | None = None
) -> None:
    payload: dict[str, Any] = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    payload["reply_markup"] = reply_markup or {"inline_keyboard": []}
    _telegram("editMessageText", payload)


def answer_callback(callback_id: str, text: str = "") -> None:
    _telegram("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def check_service(name: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as e:
        print(f"Service check for {name} failed: {e}")
        return False
    return result.stdout.strip() == "active"


def check_website() -> bool:
    try:
        r = requests.get(WEBSITE_URL, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def _footer() -> str:
    return f"⏱ Uptime: {_get_uptime()}\n🕐 {datetime.now().strftime('%H:%M')}"


def _get_tailscale_ip() -> str | None:
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True
        )
        ip = result.stdout.strip()
        return ip if ip.startswith("100.") else None
    except Exception:
        return None


def _service_links(ip: str) -> str:
    return "\n".join(
        f"{icon} <b>{name}:</b> http://{ip}:{port}"
        for icon, name, port in TAILSCALE_SERVICES
    )


def get_services_message() -> str:
    ip = _get_tailscale_ip()
    lines = ["<b>🌐  Remote Services</b>", "───────────────────"]
    if ip:
        lines.append(f"🔗 Tailscale: ✅ Online ({ip})\n")
    else:
        lines.append("🔗 Tailscale: ❌ Offline\n")
    lines.append(f"<b>📡 LAN ({LAN_IP}):</b>")
    lines.append(_service_links(LAN_IP))
    if ip:
        lines.append(f"\n<b>🌍 Tailscale ({ip}):</b>")
        lines.append(_service_links(ip))
    lines.append("───────────────────")
    if ip:
        lines.append("<i>💡 Tailscale VPN must be on your device</i>")
    lines.append(f"🕐 {datetime.now().strftime('%H:%M')}")
    return "\n".join(lines)


PIHOLE_TIMEOUT = 5  # loopback: keeps a hung FTL from stalling the bot loop

PIHOLE_STATES = ("enabled", "disabled", "failed", "unknown")
_UNREACHABLE_STATES = ("auth", "unreachable", "unconfigured")


def get_docker_states() -> dict[str, str] | None:
    """Map container name -> state ("running", "exited", ...)."""
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception as e:
        print(f"docker ps failed: {e}")
        return None
    if r.returncode != 0:
        print(f"docker ps failed: {r.stderr.strip()}")
        return None
    states: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            states[parts[0]] = parts[1]
    return states


def _docker_short() -> str:
    states = get_docker_states()
    if states is None:
        return "❌ no daemon"
    running = sum(1 for n in DOCKER_CONTAINERS if states.get(n) == "running")
    total = len(DOCKER_CONTAINERS)
    return f"{'✅' if running == total else '❌'} {running}/{total}"


def get_docker_message() -> str:
    lines = ["<b>🐳  Containers</b>", "───────────────────"]
    states = get_docker_states()
    if states is None:
        lines.append("❌ <b>Docker is not responding</b>")
    else:
        for name in DOCKER_CONTAINERS:
            state = states.get(name)
            icon = "✅" if state == "running" else ("❓" if state is None else "❌")
            lines.append(
                f"{icon} {html.escape(name)}  <i>{html.escape(state or 'not found')}</i>"
            )
        extra = sorted(n for n in states if n not in DOCKER_CONTAINERS)
        if extra:
            lines.append(f"\n<i>Not watched: {html.escape(', '.join(extra))}</i>")
    lines.append("───────────────────")
    lines.append(_footer())
    return "\n".join(lines)


class PiholeStatus(NamedTuple):
    state: str  # a PIHOLE_STATES value, or one of _UNREACHABLE_STATES
    timer: int | None = None  # seconds left of a temporary pause

    @property
    def reachable(self) -> bool:
        return self.state not in _UNREACHABLE_STATES

    @property
    def blocking(self) -> bool:
        return self.state == "enabled"


class _Session(NamedTuple):
    sid: str | None
    problem: str | None  # "auth" or "unreachable" whenever sid is None


@contextmanager
def _pihole_session() -> Iterator[_Session]:
    """Open a Pi-hole v6 API session and always release it."""
    sid: str | None = None
    problem: str | None = None
    try:
        r = requests.post(
            f"{PIHOLE_URL}/api/auth",
            json={"password": PIHOLE_PASSWORD},
            timeout=PIHOLE_TIMEOUT,
        )
        if r.status_code in (400, 401):
            problem = "auth"
        else:
            r.raise_for_status()
            sid = r.json().get("session", {}).get("sid")
            problem = None if sid else "auth"
    except Exception as e:
        print(f"Pi-hole auth failed: {e}")
        problem = "unreachable"
    try:
        yield _Session(sid, problem)
    finally:
        if sid:
            try:
                requests.delete(
                    f"{PIHOLE_URL}/api/auth",
                    headers={"X-FTL-SID": sid},
                    timeout=PIHOLE_TIMEOUT,
                )
            except Exception:
                pass


def _pihole_get(
    sid: str, path: str, params: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    try:
        r = requests.get(
            f"{PIHOLE_URL}/api/{path}",
            headers={"X-FTL-SID": sid},
            params=params,
            timeout=PIHOLE_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Pi-hole GET {path} failed: {e}")
        return None


def _as_status(data: dict[str, Any] | None) -> PiholeStatus:
    """Map a /dns/blocking payload to a status. A missing payload means the
    session was fine but this one call was not, which is unknown, not down."""
    if data is None:
        return PiholeStatus("unknown")
    state = data.get("blocking")
    timer = data.get("timer")
    return PiholeStatus(
        state if state in PIHOLE_STATES else "unknown",
        int(timer) if isinstance(timer, (int, float)) and timer is not True else None,
    )


def get_pihole_status() -> PiholeStatus:
    if not PIHOLE_ENABLED:
        return PiholeStatus("unconfigured")
    with _pihole_session() as session:
        if session.sid is None:
            return PiholeStatus(session.problem or "unreachable")
        return _as_status(_pihole_get(session.sid, "dns/blocking"))


def _fmt_remaining(secs: int) -> str:
    h, rem = divmod(max(secs, 0), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s" if m else f"{s}s"


_STATE_TEXT = {
    "enabled": "✅ Blocking",
    "failed": "⚠️ Pi-hole reports: failed",
    "unknown": "⚠️ Unknown state",
    "auth": "🔑 Password rejected",
    "unreachable": "❌ Unreachable",
    "unconfigured": "➖ Not configured",
}
_STATE_SHORT = {
    "enabled": "✅",
    "failed": "⚠️ failed",
    "unknown": "⚠️",
    "auth": "🔑 auth",
    "unreachable": "❌",
    "unconfigured": "➖",
}


def _pihole_state_text(st: PiholeStatus) -> str:
    if st.state == "disabled":
        if st.timer is not None:
            return f"⏸ Paused ({_fmt_remaining(st.timer)} left)"
        return "⏸ Disabled"
    return _STATE_TEXT.get(st.state, "⚠️ Unknown state")


def _pihole_short(st: PiholeStatus) -> str:
    if st.state == "disabled":
        return f"⏸ {_fmt_remaining(st.timer)}" if st.timer is not None else "⏸ off"
    return _STATE_SHORT.get(st.state, "⚠️")


def get_pihole_keyboard(st: PiholeStatus) -> dict[str, Any] | None:
    if not st.reachable:
        return None
    if not st.blocking:
        return {
            "inline_keyboard": [[{"text": "▶️ Enable now", "callback_data": "ph:resume"}]]
        }
    return {
        "inline_keyboard": [
            [
                {"text": f"⏸ {m}m", "callback_data": f"ph:pause:{m * 60}"}
                for m in PAUSE_MINUTES
            ]
        ]
    }


def _num(value: Any) -> str | None:
    """Thousands-separated, or None if Pi-hole sent something unexpected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"{value:,}"


def _pihole_panel(session: _Session) -> tuple[str, PiholeStatus]:
    """Render the /pihole panel using an already-open session."""
    lines = ["<b>🛡  Pi-hole</b>", "───────────────────"]
    if session.sid is None:
        st = PiholeStatus(session.problem or "unreachable")
        summary = top = None
    else:
        st = _as_status(_pihole_get(session.sid, "dns/blocking"))
        summary = _pihole_get(session.sid, "stats/summary")
        top = _pihole_get(
            session.sid, "stats/top_domains", {"blocked": "true", "count": 5}
        )

    lines.append(f"<b>State:</b> {_pihole_state_text(st)}")

    # Every section is optional: Pi-hole may answer with a key present but null.
    if summary:
        q = summary.get("queries") or {}
        total = _num(q.get("total"))
        if total:
            lines.append(f"📊 <b>Queries today:</b> {total}")
        blocked = _num(q.get("blocked"))
        if blocked:
            pct = q.get("percent_blocked")
            pct_str = f" ({pct:.1f}%)" if isinstance(pct, (int, float)) else ""
            lines.append(f"🚫 <b>Blocked:</b> {blocked}{pct_str}")
        gravity = _num((summary.get("gravity") or {}).get("domains_being_blocked"))
        if gravity:
            lines.append(f"📜 <b>Blocklist:</b> {gravity} domains")
        active = _num((summary.get("clients") or {}).get("active"))
        if active:
            lines.append(f"💻 <b>Active clients:</b> {active}")

    domains = (top or {}).get("domains") or []
    if domains:
        lines.append("\n<b>Top blocked:</b>")
        for d in domains:
            name = html.escape(str((d or {}).get("domain", "?")))
            lines.append(f"  • {name} ({_num((d or {}).get('count')) or '?'})")

    lines.append("───────────────────")
    lines.append(f"🕐 {datetime.now().strftime('%H:%M')}")
    return "\n".join(lines), st


def _unconfigured_panel() -> str:
    return (
        "<b>🛡  Pi-hole</b>\n───────────────────\n"
        "➖ Not configured — set <b>PIHOLE_PASSWORD</b> in <code>.env</code>\n"
        "───────────────────\n"
        f"🕐 {datetime.now().strftime('%H:%M')}"
    )


def get_pihole_message() -> tuple[str, PiholeStatus]:
    """Build the /pihole panel. Returns the status too, so the caller can pick
    the right keyboard without paying for a second login."""
    if not PIHOLE_ENABLED:
        return _unconfigured_panel(), PiholeStatus("unconfigured")
    with _pihole_session() as session:
        return _pihole_panel(session)


def apply_pihole_blocking(
    enabled: bool, seconds: int | None = None
) -> tuple[bool, str, PiholeStatus]:
    """Toggle blocking and redraw the panel inside the same session."""
    if not PIHOLE_ENABLED:
        return False, _unconfigured_panel(), PiholeStatus("unconfigured")
    with _pihole_session() as session:
        ok = False
        if session.sid:
            try:
                r = requests.post(
                    f"{PIHOLE_URL}/api/dns/blocking",
                    json={"blocking": enabled, "timer": seconds},
                    headers={"X-FTL-SID": session.sid},
                    timeout=PIHOLE_TIMEOUT,
                )
                r.raise_for_status()
                ok = True
            except Exception as e:
                print(f"Pi-hole blocking change failed: {e}")
        text, st = _pihole_panel(session)
        return ok, text, st


def get_status_message() -> str:
    lines = ["<b>🫐  Raspberry Pi Status</b>", "───────────────────"]
    site_icon = "✅" if check_website() else "❌"
    lines.append(f"🌐 pflaumax.dev  {site_icon}")
    for s in SERVICES:
        icon = "✅" if check_service(s) else "❌"
        lines.append(f"🤖 {s}  {icon}")
    if DOCKER_ENABLED:
        lines.append(f"🐳 Containers  {_docker_short()}")
    if PIHOLE_ENABLED:
        lines.append(f"🛡 Pi-hole  {_pihole_short(get_pihole_status())}")
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


def _get_disk_usage(path: str = "/mnt/hdd") -> str:
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        pct = used / total * 100

        def fmt(b: int) -> str:
            gb = b / 1024**3
            return f"{gb / 1024:.2f}T" if gb >= 1000 else f"{gb:.1f}G"

        return f"{fmt(free)} free / {fmt(total)} ({pct:.0f}% used)"
    except Exception:
        return "N/A"


def _get_disk_pct(path: str = "/mnt/hdd") -> float | None:
    try:
        import shutil
        total, used, _ = shutil.disk_usage(path)
        return used / total * 100
    except Exception:
        return None


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

    lines.append(f"💿 <b>HDD:</b> {_get_disk_usage()}")
    if SMART_ENABLED:
        lines.append(_smart_line(get_smart_status()))
    lines.append(f"{temp_icon} <b>Temp:</b> {temp_str}")
    lines.append("───────────────────")
    lines.append(_footer())

    return "\n".join(lines)


TEMP_THRESHOLD = float(config.get("TEMP_THRESHOLD", "85.0"))
LOAD_THRESHOLD = float(config.get("LOAD_THRESHOLD", "4.0"))
DISK_THRESHOLD = float(config.get("DISK_THRESHOLD", "90.0"))


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
    disk_pct = _get_disk_pct()
    if disk_pct is not None and disk_pct >= DISK_THRESHOLD:
        alerts.append(f"💿 <b>Disk almost full!</b> {disk_pct:.0f}% used on /mnt/hdd")
    return alerts


# --- Speedtest ledger ---------------------------------------------------
# Readings are taken on whatever device is on the network being measured and
# typed in here; Telegram relays the message, so the bot never sees the
# client's address and cannot identify the network on its own.

SPEEDTEST_FILE = Path(__file__).parent / ".speedtest_history.jsonl"
SPEEDTEST_MAX_MBPS = 100_000.0


class Reading(NamedTuple):
    ts: str
    download: float
    upload: float
    ping: float
    network: str
    source: str


def _load_readings() -> list[Reading]:
    """Read the ledger, skipping any line a crash left half-written."""
    readings: list[Reading] = []
    damaged = 0
    try:
        text = SPEEDTEST_FILE.read_text()
    except FileNotFoundError:
        return readings
    except Exception as e:
        print(f"Speedtest history unreadable: {e}")
        return readings
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            readings.append(
                Reading(
                    str(d["ts"]),
                    float(d["download_mbps"]),
                    float(d["upload_mbps"]),
                    float(d["ping_ms"]),
                    str(d["network"]),
                    str(d.get("source", "manual")),
                )
            )
        except Exception:
            damaged += 1
    if damaged:
        print(f"Speedtest history: skipped {damaged} unreadable line(s)")
    return readings


def _append_reading(r: Reading) -> bool:
    try:
        with SPEEDTEST_FILE.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": r.ts,
                        "download_mbps": r.download,
                        "upload_mbps": r.upload,
                        "ping_ms": r.ping,
                        "network": r.network,
                        "source": r.source,
                    }
                )
                + "\n"
            )
        return True
    except Exception as e:
        print(f"Could not append speedtest reading: {e}")
        return False


def _looks_numeric(token: str) -> bool:
    """Whether the user meant a measurement here, valid or not.

    Kept separate from _parse_speed so that -5 routes to "that is not a valid
    speed" rather than being mistaken for the name of a network.
    """
    try:
        float(token.replace(",", "."))
    except ValueError:
        return False
    return True


def _parse_speed(token: str) -> float | None:
    """Accept 84.3 and 84,3 alike; reject anything not a sane speed."""
    if not _looks_numeric(token):
        return None
    value = float(token.replace(",", "."))
    if math.isnan(value) or value < 0 or value > SPEEDTEST_MAX_MBPS:
        return None
    return value


def _canonical_network(name: str, known: list[str]) -> str:
    """Reuse an existing spelling so 'office' and 'Office' stay one network."""
    for existing in known:
        if existing.casefold() == name.casefold():
            return existing
    return name


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _by_network(readings: list[Reading]) -> dict[str, list[Reading]]:
    grouped: dict[str, list[Reading]] = {}
    for r in readings:
        grouped.setdefault(r.network, []).append(r)
    return grouped


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


_SPEEDTEST_USAGE = (
    "<i>Log a reading:</i>  "
    "<code>/speedtest &lt;down&gt; &lt;up&gt; &lt;ping&gt; &lt;network&gt;</code>\n"
    "<i>One network:</i>  <code>/speedtest office</code>"
)


def get_speedtest_message(args: str) -> str:
    """One command, three shapes.

    Bare  -> the history, grouped by network.
    Text  -> that network in detail.
    Number-first -> a new reading to log.
    """
    tokens = args.split()
    if not tokens:
        return _speedhistory("")
    if not _looks_numeric(tokens[0]):
        return _speedhistory(args)

    if len(tokens) < 4:
        return (
            "⚠️ Need download, upload, ping and a network name.\n\n"
            + _SPEEDTEST_USAGE
        )

    down, up, ping = (_parse_speed(t) for t in tokens[:3])
    if down is None or up is None or ping is None:
        return (
            f"⚠️ Download, upload and ping must be numbers between 0 and "
            f"{SPEEDTEST_MAX_MBPS:,.0f}.\n\n" + _SPEEDTEST_USAGE
        )

    readings = _load_readings()
    grouped = _by_network(readings)
    network = _canonical_network(" ".join(tokens[3:]), sorted(grouped))

    reading = Reading(
        datetime.now().isoformat(timespec="seconds"), down, up, ping, network, "manual"
    )
    if not _append_reading(reading):
        return "⚠️ Could not write to the history file — nothing was saved."

    same = [*grouped.get(network, []), reading]
    lines = [
        "<b>📡  Logged</b>",
        "───────────────────",
        f"⬇️ <b>{down:.1f}</b>  ⬆️ <b>{up:.1f}</b> Mbps  ⏱ <b>{ping:.0f}</b> ms",
        f"🛜 <b>{html.escape(network)}</b>",
        "───────────────────",
    ]
    lines.append(
        f"{_ordinal(len(same))} test here · median "
        f"{_median([r.download for r in same]):.1f} / "
        f"{_median([r.upload for r in same]):.1f}"
    )

    # Context only means something once there is another network to compare to.
    others = {n: rs for n, rs in grouped.items() if n != network}
    if others:
        best = max(others, key=lambda n: _median([r.download for r in others[n]]))
        best_median = _median([r.download for r in others[best]])
        if best_median > 0:
            delta = (down - best_median) / best_median * 100
            arrow = "▲" if delta >= 0 else "▼"
            lines.append(
                f"vs {html.escape(best)} ({best_median:.0f}): {delta:+.0f}% {arrow}"
            )

    lines.append(f"🕐 {datetime.now().strftime('%H:%M')}")
    return "\n".join(lines)


def _speedhistory(args: str) -> str:
    readings = _load_readings()
    if not readings:
        return (
            "<b>📡  Speedtest</b>\n"
            "───────────────────\n"
            "Nothing logged yet.\n\n" + _SPEEDTEST_USAGE
        )

    grouped = _by_network(readings)
    wanted = args.strip()

    if wanted:
        network = _canonical_network(wanted, sorted(grouped))
        rows = grouped.get(network)
        if not rows:
            return (
                f"⚠️ No readings for <b>{html.escape(wanted)}</b>.\n\n"
                "<b>Networks so far:</b>\n"
                + "\n".join(f"  • {html.escape(n)}" for n in sorted(grouped))
                + "\n\n"
                + _SPEEDTEST_USAGE
            )
        lines = [
            f"<b>📈  {html.escape(network)}</b>",
            "───────────────────",
        ]
        for r in sorted(rows, key=lambda r: r.ts, reverse=True)[:10]:
            stamp = r.ts[5:16].replace("T", " ")
            lines.append(
                f"<code>{stamp}</code>  {r.download:.1f} / {r.upload:.1f}"
                f"  <i>{r.ping:.0f}ms</i>"
            )
        lines.append("───────────────────")
        lines.append(
            f"{len(rows)} tests · median "
            f"{_median([r.download for r in rows]):.1f} / "
            f"{_median([r.upload for r in rows]):.1f}"
        )
        return "\n".join(lines)

    # Grouped overview, fastest network first — comparing places is the point.
    lines = ["<b>📈  Speedtest history</b>", "───────────────────"]
    order = sorted(
        grouped, key=lambda n: _median([r.download for r in grouped[n]]), reverse=True
    )
    for network in order:
        rows = grouped[network]
        lines.append(
            f"<b>{html.escape(network)}</b> <i>({len(rows)} "
            f"{'test' if len(rows) == 1 else 'tests'})</i>"
        )
        lines.append(
            f"  {_median([r.download for r in rows]):.1f} / "
            f"{_median([r.upload for r in rows]):.1f} Mbps"
            f"  <i>{_median([r.ping for r in rows]):.0f}ms</i>"
        )
    lines.append("───────────────────")
    lines.append(_SPEEDTEST_USAGE)
    return "\n".join(lines)


# --- Drive health (SMART) ----------------------------------------------


class SmartStatus(NamedTuple):
    available: bool
    passed: bool | None  # the drive's own overall self-assessment
    temp_c: float | None
    hours: int | None
    counters: dict[str, int]  # attribute name -> raw value


def get_smart_status() -> SmartStatus:
    """Read the drive's own health log. Unavailable is not the same as unwell."""
    if not SMART_ENABLED:
        return SmartStatus(False, None, None, None, {})
    try:
        r = subprocess.run(
            ["sudo", "-n", SMART_BIN, "--json", "-H", "-A", SMART_DEVICE],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        # smartctl uses its exit code as a bitfield; bits 0-1 mean it could not
        # talk to the device at all, anything above that still yields output.
        if r.returncode & 0b11:
            print(f"smartctl could not read {SMART_DEVICE}: {r.stderr.strip()}")
            return SmartStatus(False, None, None, None, {})
        data = json.loads(r.stdout)
    except Exception as e:
        print(f"smartctl failed: {e}")
        return SmartStatus(False, None, None, None, {})

    # No self-assessment means we learned nothing, which must not read as "OK".
    passed = (data.get("smart_status") or {}).get("passed")
    if not isinstance(passed, bool):
        print(f"smartctl returned no health verdict for {SMART_DEVICE}")
        return SmartStatus(False, None, None, None, {})

    counters: dict[str, int] = {}
    for attr in (data.get("ata_smart_attributes") or {}).get("table") or []:
        name = attr.get("name")
        raw = (attr.get("raw") or {}).get("value")
        if name in SMART_FAILURE_COUNTERS and isinstance(raw, int):
            counters[name] = raw

    return SmartStatus(
        True,
        passed,
        (data.get("temperature") or {}).get("current"),
        (data.get("power_on_time") or {}).get("hours"),
        counters,
    )


def get_smart_alerts() -> list[str]:
    """Problems worth waking someone for. Empty when the drive is fine."""
    status = get_smart_status()
    if not status.available:
        return []  # unreadable SMART is not evidence of a failing drive
    alerts = []
    if status.passed is False:
        alerts.append("🚨 <b>Drive self-assessment FAILED</b> — replace it")
    for name, label in SMART_FAILURE_COUNTERS.items():
        count = status.counters.get(name, 0)
        if count > 0:
            alerts.append(f"💿 <b>{count} {label}</b> on {html.escape(SMART_DEVICE)}")
    if status.temp_c is not None and status.temp_c >= SMART_TEMP_THRESHOLD:
        alerts.append(f"🌡 <b>Drive at {status.temp_c:.0f}°C</b>")
    return alerts


def _smart_line(status: SmartStatus) -> str:
    if not status.available:
        return "🩺 <b>Disk health:</b> unavailable"
    problems = []
    if status.passed is False:
        problems.append("FAILED")
    problems += [
        f"{status.counters[n]} {label}"
        for n, label in SMART_FAILURE_COUNTERS.items()
        if status.counters.get(n, 0) > 0
    ]
    if problems:
        return f"🩺 <b>Disk health:</b> ⚠️ {', '.join(problems)}"
    extra = []
    if status.temp_c is not None:
        extra.append(f"{status.temp_c:.0f}°C")
    if status.hours is not None:
        extra.append(f"{status.hours:,}h")
    suffix = f" · {' · '.join(extra)}" if extra else ""
    return f"🩺 <b>Disk health:</b> ✅ OK{suffix}"
