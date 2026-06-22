# Diary Bot

A Telegram bot that acts as a micro-journaling assistant. Send quick text updates and voice notes throughout the day, then generate a polished AI-written diary entry on command.

## Features

- **Text & Voice Input** — Send messages or voice notes anytime; they're collected for your daily entry
- **AI Diary Generation** — Run `/diary` to get a beautifully written diary entry from the day's inputs
- **Customizable Tone** — Choose between poetic, casual, or reflective writing styles
- **Mood Tracking** — Bot checks in 2-3 times a day to capture how you're feeling
- **Gentle Reminders** — Nudges you if you haven't journaled in a while
- **Weekly Summary** — `/week` gives you a summary highlighting patterns and themes
- **Memory Callbacks** — "This time last week you were..." nostalgia prompts
- **Export & Delete** — Full control over your data

## Tech Stack

- **Python** with `python-telegram-bot`
- **Groq Cloud** — Free LLM (Llama) + Whisper transcription
- **APScheduler** — Scheduled check-ins and reminders
- **SQLite** — Local database, zero config
- **AWS EC2** (t2.micro free tier) — Hosting

## Commands

| Command | Description |
|---------|-------------|
| `/diary` | Generate today's diary entry |
| `/week` | Weekly summary with patterns |
| `/tone` | Set writing style (poetic/casual/reflective) |
| `/export` | Export all entries as JSON |
| `/delete` | Delete entries by date or all data |
| `/settings` | View/update bot settings |

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Get a free [Groq Cloud](https://console.groq.com/) API key
3. Set environment variables:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   GROQ_API_KEY=your_groq_key
   AUTHORIZED_USER_ID=your_telegram_user_id
   ```
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python main.py`

## License

MIT
