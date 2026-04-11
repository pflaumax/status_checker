# 🫐 Raspberry Pi Status Bot

Telegram bot that monitors services and website on a Raspberry Pi.

## Bot Command

`/status` — returns current status:

```
🫐  Raspberry Pi Status
───────────────────
🌐 pflaumax.dev  ✅
🤖 hp-bot  ✅
🤖 funko-bot  ✅
───────────────────
🕐 18:03
```

## Setup

```bash
cp .env.example .env
# fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBSITE_URL
uv sync
```

## Files

- `common.py` — shared config, checks, and message helpers
- `telegram_bot.py` — long-running bot, responds to `/status`
- `status_checker.py` — cron script, alerts when services are down

## Raspberry Pi Service Commands

```bash
sudo systemctl restart status-bot
sudo systemctl status status-bot
journalctl -u status-bot -f
```

## External Monitoring (UptimeRobot)

If the Raspberry Pi itself goes down, all local services (website, bots, this status bot) go down with it.

Use [UptimeRobot](https://dashboard.uptimerobot.com/monitors) to monitor `pflaumax.dev` from outside — you'll get an email alert if the server becomes unreachable.
