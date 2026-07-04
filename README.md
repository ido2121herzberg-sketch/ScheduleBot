# ScheduleBot

A Telegram bot that builds a personalized daily schedule for each user from their own data — not from hardcoded rules.

## Overview

ScheduleBot turns a person's recurring commitments, energy patterns, and one-off exceptions into a clean daily plan, delivered straight through Telegram. Each user fills in a simple weekly skeleton once; the bot handles the rest — assembling each day, layering on exceptions, and respecting personal constraints like rest days, buffers, and out-of-home time.

It's built in Python, runs in the cloud, and is in active development toward a multi-tenant SaaS product.

## The problem

Most scheduling tools sit at one of two extremes: fully manual (you rebuild your day every morning) or rigidly automated (one-size-fits-all rules that don't match how you actually live). ScheduleBot sits in between — it automates the assembly while keeping every personalization decision in the user's own data, so the same codebase serves very different people without changes.

## Key features

- **Weekly skeleton, filled once** — users define their recurring week in a set of structured tables, and the bot generates each day from it.
- **Weekly exceptions** — one-off changes (a canceled class, an away day) layer on top without touching the skeleton.
- **Per-user personalization** — rest days, day-start and bedtime, buffer times, out-of-home detection, and rotating activities are all driven by user settings rather than code.
- **Energy-aware planning** — a short mood/energy flow at the start of the day shapes what gets scheduled.
- **Dated task inbox** — tasks tied to specific dates flow into the right day automatically.
- **Hebrew-first** — designed and used natively in Hebrew.

## Architecture

The core design principle: **personalization lives in data, not in code.**

Early versions hardcoded individual quirks — specific names for out-of-home detection, a fixed rest day, hardcoded rotation pairs. The current architecture replaces all of that with per-user data properties, so onboarding a new user means filling in their data, not editing `bot.py`. That keeps the logic clean and generic, and turns the path to multi-tenancy (per-user tokens, routing, billing) into a data-and-infrastructure problem rather than a rewrite.

- **Bot layer** — Python (`bot.py`): handles Telegram interactions and the daily build logic.
- **Data layer** — user schedules, settings, and exceptions stored in structured Notion tables, designed to be duplicated per user from a single template.
- **Deployment** — hosted on Railway, version-controlled on GitHub.

## Tech stack

- Python
- Telegram Bot API
- Notion API (structured data backend)
- Railway (deployment)
- Git / GitHub

## Running locally

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/schedulebot.git
cd schedulebot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export TELEGRAM_TOKEN="your-telegram-bot-token"
export NOTION_TOKEN="your-notion-integration-token"

# 4. Run
python bot.py
```

## Status & roadmap

ScheduleBot is a personal product in active development.

- **Done** — core weekly build engine
- **Done** — dated task inbox
- **Done** — energy/mood-based daily flow
- **In progress** — onboarding refactor: moving all remaining hardcoded personalization into per-user data
- **Planned** — self-serve onboarding: a duplicable template so new users can set themselves up
- **Planned** — multi-tenant infrastructure: per-user tokens, bot routing, and billing

---

*Built by Ido Herzberg.*
