# qBittorrent Telegram Bot

A lightweight, secure Python-based Telegram bot to monitor and control your qBittorrent WebUI container.

## Key Features

- 💾 **Storage Status**: Check remaining disk space on your downloads directory and view global bandwidth speeds.
- ⚡ **Download Progress**: List active downloads with dynamic visual progress bars, speeds, and ETAs.
- ⏸/▶/🗑 **Interactive Control**: Pause, resume, or delete torrents (with deletion safety confirmations) via inline buttons.
- 🔍 **Torrent Search**: Search indexers using qBittorrent's search plugins and trigger downloads instantly.
- ⭐ **Automatic Alert Matches**: Bookmark search terms to favorites and receive instant notifications when new hits are found.
- 🔒 **Access Security**: Enforces an authorization filter matching against a list of allowed Telegram user IDs.

## Getting Started

### 1. Configure Settings
Copy the env template and fill in your details (credentials, bot token, and user IDs):
```bash
cp .env.example .env
```

### 2. Deploy

#### Using Docker Compose (Recommended)
```bash
docker-compose up -d --build
```

#### Running Locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```
