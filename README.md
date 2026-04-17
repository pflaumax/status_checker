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
💿 HDD: 1638.4G / 1.9T (88%)
🌡 Temp: 48.3°C
───────────────────
⏱ Uptime: 7 days, 07:42:25
🕐 18:03
```

- Load average over 1min, 5min, 15min — under 4.0 = healthy (Pi 5 has 4 cores)
- RAM: actual usage / total (reads `/proc/meminfo`, excludes cache)
- HDD: used / total on `/mnt/hdd` (shows total in TB when ≥ 1024G)
- Temp icon switches to 🔥 above 75°C

## Auto Alerts (cron)

`status_checker.py` runs on a schedule and sends alerts when:

- A service (`hp-bot`, `funko-bot`) is down
- `pflaumax.dev` is not responding
- CPU temperature ≥ 85°C (Pi 5 throttle point)
- CPU load average (15m) ≥ 4.0 (all 4 cores saturated)
- HDD usage ≥ 90% on `/mnt/hdd`

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
# fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBSITE_URL
uv sync
```

## Files

- `common.py` — shared config, checks, system stats, and message helpers
- `telegram_bot.py` — long-running bot, responds to `/status` and `/system`
- `status_checker.py` — cron script, alerts on service/system issues

## Raspberry Pi Service Commands

```bash
sudo systemctl restart status-bot
sudo systemctl status status-bot
journalctl -u status-bot -f
```

## External Monitoring (UptimeRobot)

If the Raspberry Pi itself goes down, all local services go down with it.

Use [UptimeRobot](https://dashboard.uptimerobot.com/monitors) to monitor `pflaumax.dev` from outside — you'll get an email alert if the server becomes unreachable.
