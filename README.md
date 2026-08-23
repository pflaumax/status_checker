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
───────────────────
⏱ Uptime: 7 days, 07:42:25
🕐 18:03
```

### `/system` — hardware stats

```
🫐  Raspberry Pi System
───────────────────
🖥 CPU Load (1/5/15m): 0.42 0.41 0.59
💾 RAM: 1.99G/7.87G
💿 HDD: 229.0G free / 1.86T (88% used)
🌡 Temp: 48.3°C
───────────────────
⏱ Uptime: 7 days, 07:42:25
🕐 18:03
```

- Load average over 1min, 5min, 15min — under 4.0 = healthy (Pi 5 has 4 cores)
- RAM: actual usage / total (reads `/proc/meminfo`, excludes cache)
- HDD: free / total on `/mnt/hdd` (shows total in TB when ≥ 1000G)
- Temp icon switches to 🔥 above 75°C

### `/pihole` — DNS filtering

```
🛡  Pi-hole
───────────────────
State: ✅ Blocking
📊 Queries today: 17,151
🚫 Blocked: 1,643 (9.6%)
📜 Blocklist: 93,516 domains
💻 Active clients: 9

Top blocked:
  • mask.icloud.com (342)
  • firebaselogging-pa.googleapis.com (268)
  • www.googletagmanager.com (73)
───────────────────
🕐 18:03
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

Add (every 5 minutes):

```
*/5 * * * * cd /home/pi/status_checker && /home/pi/.local/bin/uv run status_checker.py
```

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
- `telegram_bot.py` — long-running bot, responds to `/status`, `/system`, `/services`, and `/pihole`
- `status_checker.py` — cron script, alerts on service/system/Tailscale issues

## Raspberry Pi Service Commands

```bash
sudo systemctl restart status-bot
sudo systemctl status status-bot
journalctl -u status-bot -f
```

## External Monitoring (UptimeRobot)

If the Raspberry Pi itself goes down, all local services go down with it.

Use [UptimeRobot](https://dashboard.uptimerobot.com/monitors) to monitor `pflaumax.dev` from outside — you'll get an email alert if the server becomes unreachable.
