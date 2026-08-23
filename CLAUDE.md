# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repo: https://github.com/pflaumax/status_checker

## The code runs on a Raspberry Pi, not on this machine

The bot lives at `~/personal/status_checker` on a Pi reachable through the SSH
alias `pi` (`reiberry@192.168.50.173`, key-based, no password). Run anything
that needs real data there:

```bash
ssh pi "command"
ssh pi "cd ~/personal/status_checker && uv run status_checker.py"
```

Locally almost nothing works: every system probe reads Pi-specific paths and
Pi-hole is only reachable from the Pi. See "Runtime target" below.

## Commands

```bash
uv sync                      # install deps into .venv
uv run telegram_bot.py       # run the long-polling bot (foreground)
uv run status_checker.py     # run one cron-style alert pass
uvx ruff check .             # lint (ruff/mypy are not project deps; run via uvx)
uvx mypy .
```

There is no test suite. Verification is done by running the two entrypoints.

Production (via `ssh pi`):

```bash
ssh pi "sudo systemctl restart status-bot"   # the telegram_bot.py service
ssh pi "journalctl -u status-bot -f"
ssh pi "crontab -l"                          # status_checker.py runs every 5 min
```

Inspecting Pi-hole directly, which needs no password thanks to `cli_pw`:

```bash
ssh pi "sudo -n pihole api stats/summary"
ssh pi "sudo -n pihole api dns/blocking"
```

## Architecture

Three modules, two entrypoints, one shared library:

- `common.py` — config, all probes (service/website/system/Tailscale), and the HTML message builders. Both entrypoints import from here; put shared logic here.
- `telegram_bot.py` — a hand-rolled `getUpdates` long-poll loop (no bot framework). Dispatches `/status`, `/system`, `/services` to `get_*_message()`. Drops any update whose `chat.id` != `CHAT_ID`, so the bot only serves its owner.
- `status_checker.py` — a *script*, not a module: all logic runs at import time. Designed for cron, one pass per invocation.

### Runtime target is Linux/Raspberry Pi

Every system probe reads Pi-specific paths — `/proc/loadavg`, `/proc/meminfo`, `/sys/class/thermal/thermal_zone0/temp`, `/proc/uptime`, `shutil.disk_usage("/mnt/hdd")` — or shells out to `systemctl` / `tailscale`. Each is wrapped in a broad `try/except` that degrades to `"N/A"` / `None` / `False`. On a macOS dev machine nearly every value is empty, so local runs cannot validate stat output; only message formatting and the Telegram round-trip are testable locally, by stubbing `requests`.

### Pi-hole (v6 REST API)

Pi-hole v6 replaced the v5 `api.php?…&auth=<token>` scheme entirely. There is **no API token**: `POST /api/auth` with `{"password": …}` returns `session.sid`, which every later call passes as an `X-FTL-SID` header.

**`PIHOLE_PASSWORD` is optional and its absence means "integration off", not
"integration broken".** `PIHOLE_ENABLED` gates the `/status` row, the `/pihole`
panel, and the whole cron block. Without this an existing deployment that pulls
the code before editing `.env` would authenticate as `""` and alert a permanent
false outage. Keep any new Pi-hole code behind that flag.

Three more things this constrains:

- **Sessions are a limited resource.** `webserver.api.max_sessions` is 16 and sessions live 30 minutes. `_pihole_session()` is a context manager that always `DELETE`s the session in a `finally`; a missed logout would lock the admin panel out after a few cron runs. Never call `/api/auth` outside that context manager.
- **The web port is not 80.** This install serves on `8080` (`webserver.port` in `/etc/pihole/pihole.toml`), so `PIHOLE_URL` must carry the port. The default is `http://localhost:8080` since the bot runs on the Pi.
- **Pi-hole owns the pause timer.** `POST /api/dns/blocking {"blocking": false, "timer": 600}` re-enables itself after 600s, so nothing about a pause is stored in `.alert_state.json` or in the bot. Do not add timer bookkeeping.

#### The status model

`PiholeStatus` carries one `state` string plus an optional `timer`; `reachable`
and `blocking` are derived properties, so there is a single source of truth.
The state is either something Pi-hole reported — `enabled`, `disabled`,
`failed`, `unknown` (the exact enum from `/api/docs/specs/dns.yaml`) — or one of
ours for "no answer": `auth` (password rejected), `unreachable` (no connection),
`unconfigured` (no password set). Never collapse these back into a bool:
`auth` vs `unreachable` is what makes an alert name the real cause, and treating
anything-not-`enabled` as `disabled` is what once produced false "blocking is
disabled indefinitely" alerts for a `failed` state.

`get_pihole_message()` returns `(text, PiholeStatus)`, and `apply_pihole_blocking()`
returns `(ok, text, status)` after doing the write and the redraw in **one**
session — so a button press costs one login, and the toast can tell the truth
when the write failed.

#### Alerting rules

- A pause with a `timer` is deliberate: no alert, and **no recovery message
  either**. Recovery is gated on `state == "enabled"`, because "disabled with a
  timer" once cleared the alert while filtering was still off.
- `disabled` with `timer: null`, and `failed` / `unknown`, each alert with their
  own wording under key `pihole:blocking`.

#### Authorization

Buttons are checked against `callback_query.from.id` (the presser), not
`message.chat.id`, via `is_owner()`. `TELEGRAM_CHAT_ID` is therefore assumed to
be a **private** chat id; pointing it at a group would disable the buttons for
everyone, which is the intended fail-closed direction given they switch off DNS
filtering network-wide.

### Inline keyboards / callback queries

`/pihole` is the only command with buttons, so the bot loop handles `callback_query` updates as well as `message` ones. Two rules when touching this:

- Callback updates carry the chat id at `callback_query.message.chat.id`, **not** `message.chat.id` — the owner check has to be repeated in `handle_callback`, and it matters more there because the buttons switch off DNS filtering for the whole network.
- Always `answerCallbackQuery`, otherwise Telegram leaves a spinner on the button.

`telegram_bot.py` keeps its loop behind `main()` / `if __name__ == "__main__"` so the handlers can be imported and exercised without starting a poll loop.

### Config

`common.py` loads `.env` with `dotenv_values` (not `os.environ`) at import time, and `_require()` raises `ValueError` for a missing `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, or `WEBSITE_URL`. **Importing `common.py` without a populated `.env` fails immediately** — copy `.env.example` first. `CHAT_ID` stays a string and is compared as one.

Thresholds (`TEMP_THRESHOLD`, `LOAD_THRESHOLD`, `DISK_THRESHOLD`) and `LAN_IP` are optional env vars with defaults in `common.py`.

### Messages are HTML

`send_message` posts with `parse_mode: "HTML"`; the builders embed `<b>`/`<i>` tags. Any user- or system-derived text interpolated into a message must be HTML-safe. The README's fenced blocks show the *rendered* Telegram output, not the source strings — update both when changing a message.

### Alert state machine

`status_checker.py` keeps `.alert_state.json` (gitignored): `key -> epoch of last alert`. Keys are `service:<name>`, `website`, `system`, `tailscale`. Presence of a key means "currently in alert". A problem re-notifies only after `COOLDOWN` (24h); clearing a key sends the ✅ recovery message. Every new check needs both the alert branch and the `_clear_alert` branch, or it will never recover.

### Extending

- New monitored systemd unit: add to `SERVICES` in `common.py` (picked up by both `/status` and the cron alerts automatically).
- New remote-access link: add an `(icon, name, port)` tuple to `TAILSCALE_SERVICES`; `/services` renders LAN and Tailscale sections from the same list.
- New system threshold alert: add the probe in `common.py`, emit a line from `get_system_alerts()` (all system alerts share the single `system` state key).
- New bot command: add the `get_*_message()` builder in `common.py` and one `elif` in `handle_command()`.

## Verification status

The 16 issues found in review of the Pi-hole change are all fixed. Coverage as
it stands:

- 39 assertions across three scratch harnesses (stubbed Pi-hole + Telegram):
  bot handlers, the real `status_checker.py` run in an isolated temp dir against
  a fake `common.py`, and the unconfigured path.
- Read paths, `auth` vs `unreachable`, and logout-invalidates-the-session all
  verified against the live Pi-hole v6.4.3 over `ssh pi`.

Not yet exercised: **an actual pause against the live Pi-hole.** Every write
test so far has been a no-op (`{"blocking": true}` while already enabled) or
stubbed, because a real pause switches off DNS filtering for the whole house.
Press a button once after deploying and confirm the panel redraws.

There is no test runner in the repo — the harnesses live in the session
scratchpad. Anything worth keeping should be moved into the repo first.
