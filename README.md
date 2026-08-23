# 🫐 Raspberry Pi 5 Status Bot

Telegram bot that monitors services, website, and system health on a Raspberry Pi 5.

## Bot Commands

### `/status` — service health

```
🫐  Raspberry Pi Status
───────────────────
🌐 pflaumax.dev  ✅
🤖 hp-bot  ✅
🤖 funko-bot  ✅
🐳 Containers  ✅ 6/6
🛡 Pi-hole  ✅
───────────────────
⏱ Uptime: 23:24:44
🕐 09:46
```

The container and Pi-hole rows only appear when those features are configured.

### `/system` — hardware stats

```
🫐  Raspberry Pi System
───────────────────
🖥 CPU (1/5/15m): 0.00 0.00 0.00
💾 RAM: 2.56G/7.87G
💿 HDD: 253.6G free / 1.82T (86% used)
🩺 Disk health: ✅ OK · 32°C · 6,257h
🌡 Temp: 59.5°C
───────────────────
⏱ Uptime: 23:24:44
🕐 09:46
```

- Load average over 1min, 5min, 15min — under 4.0 = healthy (Pi 5 has 4 cores)
- RAM: actual usage / total (reads `/proc/meminfo`, excludes cache)
- HDD: free / total on `/mnt/hdd` (shows total in TB when ≥ 1000G)
- Temp icon switches to 🔥 above 75°C
- Disk health comes from the drive's own SMART log. A failing drive normally
  reports bad sectors for weeks before it stops working, so the line turns to
  ⚠️ with a count long before anything is lost. Needs `smartmontools`; the
  drive is set with `SMART_DEVICE` (empty disables the check)

### `/pihole` — DNS filtering

```
🛡  Pi-hole
───────────────────
State: ✅ Blocking
📊 Queries today: 29,929
🚫 Blocked: 2,649 (8.9%)
📜 Blocklist: 93,516 domains
💻 Active clients: 9

Top blocked:
  • mask.icloud.com (687)
  • firebaselogging-pa.googleapis.com (531)
  • _dns.resolver.arpa (144)
  • mask-h2.icloud.com (110)
  • www.googletagmanager.com (84)
───────────────────
🕐 09:46
```

Inline buttons pause blocking for **5 / 10 / 30 minutes**. Pi-hole owns the
timer and re-enables itself — the bot stores no timer state. While paused the
panel shows `▶️ Enable now` instead, and `/status` shows `⏸ 9m 12s` rather
than ❌, so a deliberate pause never looks like an outage.

Only the account in `TELEGRAM_CHAT_ID` can press the buttons; they control DNS
filtering for the whole network. If a press does not go through, the toast says
so rather than claiming success.

Leaving `PIHOLE_PASSWORD` empty switches the whole integration off: no Pi-hole
row in `/status`, no alerts, and `/pihole` just says it is not configured.

### `/docker` — container health

```
🐳  Containers
───────────────────
✅ jellyfin  running
✅ qbittorrent  running
✅ sonarr  running
✅ radarr  running
✅ prowlarr  running
✅ flaresolverr  running
───────────────────
⏱ Uptime: 23:24:44
🕐 09:46
```

- A container that is present but stopped shows ❌ with its state (`exited`,
  `restarting`, …); one that no longer exists at all shows ❓ `not found`
- Containers running outside the watch list are listed separately, so a new
  service is visible rather than silently unmonitored
- The watch list defaults to the six above and is overridden with
  `DOCKER_CONTAINERS` in `.env` (comma-separated; empty disables the feature)

The bot reaches Docker through `docker ps`, which needs its user in the
`docker` group — already the case for `reiberry`.

### `/speedtest` — speeds by network

Bare, it shows the history grouped by network, fastest first — comparing places
is the point:

```
📈  Speedtest history
───────────────────
Home (1 test)
  669.9 / 552.4 Mbps  6ms
Office (2 tests)
  204.2 / 94.0 Mbps  12ms
Nero Brasov (1 test)
  84.3 / 21.7 Mbps  24ms
```

Run a test in whichever speedtest app you trust, then record it by starting
with the numbers:

```
/speedtest 84.3 21.7 24 Nero Brasov
```

```
📡  Logged
───────────────────
⬇️ 84.3  ⬆️ 21.7 Mbps  ⏱ 24 ms
🛜 Nero Brasov
───────────────────
1st test here · median 84.3 / 21.7
vs Home (670): -87% ▼
🕐 10:03
```

Anything that does not start with a number is read as a network name, so
`/speedtest office` lists that network's readings individually.

Arguments are `<download> <upload> <ping> <network name>`; the name may contain
spaces and `84,3` is accepted alongside `84.3`.

The network name has to be typed. Telegram relays your message, so the bot
never sees the device's address and cannot work out which network you are on.
Names match case-insensitively, so `office` and `Office` stay one network.

History lives in `.speedtest_history.jsonl`, one JSON object per line,
append-only and gitignored. A line damaged by a crash is skipped rather than
taking the file down with it.

### `/services` — remote access links

```
🌐  Remote Services
───────────────────
🔗 Tailscale: ✅ Online (100.102.29.66)

📡 LAN (192.168.50.173):
🎬 Jellyfin:     http://192.168.50.173:8096
⬇️ qBittorrent:  http://192.168.50.173:8090
📺 Sonarr:       http://192.168.50.173:8989
🎥 Radarr:       http://192.168.50.173:7878
🔍 Prowlarr:     http://192.168.50.173:9696

🌍 Tailscale (100.102.29.66):
🎬 Jellyfin:     http://100.102.29.66:8096
⬇️ qBittorrent:  http://100.102.29.66:8090
📺 Sonarr:       http://100.102.29.66:8989
🎥 Radarr:       http://100.102.29.66:7878
🔍 Prowlarr:     http://100.102.29.66:9696
───────────────────
💡 Tailscale VPN must be on your device
🕐 18:03
```

- LAN links always shown (work on home network)
- Tailscale section only shown when Tailscale is online
- All links are clickable in Telegram

## Auto Alerts (cron)

`status_checker.py` runs on a schedule and sends alerts when:

- A service (`hp-bot`, `funko-bot`) is down
- `pflaumax.dev` is not responding
- CPU temperature ≥ 85°C (Pi 5 throttle point)
- CPU load average (15m) ≥ 4.0 (all 4 cores saturated)
- HDD usage ≥ 90% on `/mnt/hdd`
- Tailscale is offline
- A watched Docker container is not running, or the Docker daemon itself is unreachable
- The drive reports bad sectors, cable errors, a failed self-assessment, or runs hot
- Pi-hole is not responding, or rejects the password (reported as separate causes)
- Pi-hole blocking is disabled **indefinitely**, or reports a `failed` / `unknown` state

A timed pause is deliberate, so it is neither alerted nor reported as a recovery —
the "blocking is back on" message waits until filtering is genuinely on again.

Alerts use a **24-hour cooldown** — you get one notification when an issue starts, a reminder every 24h if it persists, and a ✅ recovery message when it clears. State is stored in `.alert_state.json`.

Example alert:

```
🚨 Critical Raspberry Pi state!

🔥 Critical temperature: 86.2°C
⚠️ CPU overloaded for 15m+! (Load: 4.7)

🕐 18:03
```

### Cron setup

On the Raspberry Pi:

```bash
crontab -e
```

What is actually installed — every 10 minutes, calling the venv interpreter
directly rather than going through `uv`:

```
*/10 * * * * /home/reiberry/personal/status_checker/.venv/bin/python3 /home/reiberry/personal/status_checker/status_checker.py
```

Since cron bypasses `uv`, new dependencies only reach it after a `uv sync`.

## Setup

```bash
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBSITE_URL, PIHOLE_PASSWORD
uv sync
```

### Pi-hole credentials

Pi-hole v6 dropped the v5 API token — the REST API authenticates with a
password and hands back a session id. Rather than putting the admin password in
`.env`, create a dedicated one in the admin panel:

**Settings → Web interface / API → Configure app password** → generate → paste
into `PIHOLE_PASSWORD`.

An app password can be revoked on its own without changing the password you log
in with. `PIHOLE_URL` must include the web port — this install serves the
interface on `8080`, not `80`. Leave `PIHOLE_PASSWORD` empty to disable the
Pi-hole features entirely.

## Files

- `common.py` — shared config, checks, system stats, and message helpers
- `.speedtest_history.jsonl` — append-only speedtest ledger (gitignored)
- `telegram_bot.py` — long-running bot; its `COMMANDS` table is the single
  source of truth for both the command dispatcher and the `/` menu registered
  with Telegram at startup, so a new command cannot ship without appearing in
  the menu
- `status_checker.py` — cron script, alerts on service/system/Tailscale issues

## Raspberry Pi Service Commands

```bash
sudo systemctl restart status-bot
sudo systemctl status status-bot
journalctl -u status-bot -f
```

The unit sets `Environment=PYTHONUNBUFFERED=1`. Without it Python block-buffers
stdout into journald, and since every diagnostic here is a `print()`
(`Pi-hole auth failed`, `Callback failed`, …), `journalctl -f` would show
nothing until the process exited. Keep that line if the unit is ever rewritten.

## External Monitoring (UptimeRobot)

If the Raspberry Pi itself goes down, all local services go down with it.

Use [UptimeRobot](https://dashboard.uptimerobot.com/monitors) to monitor `pflaumax.dev` from outside — you'll get an email alert if the server becomes unreachable.
