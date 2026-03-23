# 🧠 ADHD Hub

**Telegram bot that captures your thoughts via voice, text, or files — transcribes, classifies with AI, and organizes into a structured file system.**

Built for people who think faster than they can organize. Send a voice memo, a quick text, a photo, or a file — the bot transcribes (if voice), passes it through Claude for classification, and files it into `~/hub/`.

## How it works

```
You ──→ Telegram ──→ Bot ──→ [Voice?] ──→ Groq Whisper ──→ Transcript
                      │                                        │
                      │         [Text / File / Photo]          │
                      │                │                       │
                      │                ▼                       ▼
                      │           Claude CLI ◄─────────── Content
                      │               │
                      │               ▼
                      │         Classify & Route
                      │               │
                      │               ▼
                      │          ~/hub/ filesystem
                      │               │
                      ◄───────────────┘
                   Report
```

1. You send the bot a thought — voice, text, file, or photo
2. Voice/audio → transcribed via [Groq Whisper](https://groq.com/) (fast, free tier available)
3. Content → [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/overview) classifies and routes it
4. Result saved to `~/hub/` following rules in [`CLAUDE.md`](CLAUDE.md)
5. Bot sends you a short report of what was done

## Features

- 🎙 **Voice messages** — transcription → AI routing
- 🎵 **Audio files** — transcription → AI routing
- 💬 **Text** — direct AI routing
- 📎 **Documents** — saved to inbox, text content analyzed
- 📷 **Photos** — saved to inbox, caption routed
- 📊 **Queue** — handles bursts (10 voice memos in a row — no problem)
- 🔒 **Single-user** — only your Telegram ID is allowed
- 🤖 **Claude as router** — uses Claude Code CLI with tool access (Read, Write, Edit, Bash)

## File structure

Claude organizes your thoughts into `./hub/` (or custom path via `HUB_DIR`):

```
hub/
├── projects/          # Project folders (created freely by Claude)
│   └── {name}/
│       ├── README.md
│       ├── TODO.md
│       └── bugs/
├── tasks/tasks.md     # Standalone tasks
├── notes/
│   ├── ideas.md       # General ideas
│   ├── log.md         # Thoughts & notes (dated)
│   └── unsorted.md    # Unclear items
└── inbox/             # Temporary storage
    └── index.md
```

Routing rules are in [`prompts/router.md`](prompts/router.md), search prompt in [`prompts/search.md`](prompts/search.md).

## Prerequisites

| Dependency | Purpose | Required |
|---|---|---|
| Python 3.11+ | Runtime | Yes |
| [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/overview) | AI routing | Yes |
| Telegram Bot Token | Bot interface | Yes |
| Groq API Key | Voice transcription | Yes (for voice) |

## Getting tokens

### 1. Telegram Bot Token

1. Open [@BotFather](https://t.me/BotFather) in Telegram
2. Send `/newbot`
3. Choose a name and username for your bot
4. Copy the token (looks like `123456789:ABCdefGHI...`)

### 2. Groq API Key (free)

1. Sign up at [console.groq.com](https://console.groq.com)
2. Go to [API Keys](https://console.groq.com/keys)
3. Click **Create API Key**
4. Copy the key (starts with `gsk_...`)

Groq's free tier includes generous limits for Whisper transcription.

### 3. Claude Code CLI

```bash
# Install
npm install -g @anthropic-ai/claude-code

# Authenticate (requires Claude Max subscription for -p mode)
claude auth login
```

Verify it works:
```bash
echo "Say hi" | claude -p
```

> **Note:** The bot uses `claude -p` (print/pipe mode) which requires a Claude Max subscription.

### 4. Your Telegram User ID

Send any message to [@userinfobot](https://t.me/userinfobot) — it will reply with your numeric user ID.

## Installation

```bash
git clone https://github.com/egorkaBurkenya/adhd-hub.git
cd adhd-hub

# Create virtual environment (pick one)
python3 -m venv .venv
# or with uv:
uv venv

# Install dependencies
.venv/bin/pip install -r requirements.txt
# or with uv:
uv pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your tokens
```

## Configuration

Edit `.env`:

```bash
TELEGRAM_TOKEN=your-telegram-bot-token
GROQ_API_KEY=your-groq-api-key
ALLOWED_USER_ID=your-telegram-user-id

# Optional
HUB_DIR=/custom/path    # Where to store files (default: ./hub in project dir)
CLAUDE_MODEL=opus        # Claude model alias (default: opus)
```

## Running

```bash
./run.sh
```

Or manually:

```bash
source .env
.venv/bin/python bot.py
```

## Auto-start (macOS LaunchAgent)

For running as a daemon on macOS (e.g., Mac Mini server):

1. Edit `com.adhd-hub.plist` — update the path to match your installation:

```bash
sed "s|__ADHD_HUB_DIR__|$(pwd)|g" com.adhd-hub.plist.template > com.adhd-hub.plist
```

2. Copy and load:

```bash
cp com.adhd-hub.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.adhd-hub.plist
```

3. Check status:

```bash
launchctl list | grep adhd-hub
```

4. View logs:

```bash
tail -f /tmp/adhd-hub.stdout.log
tail -f /tmp/adhd-hub.stderr.log
```

5. Stop:

```bash
launchctl unload ~/Library/LaunchAgents/com.adhd-hub.plist
```

## Bot commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/status` | Queue status + current mode + hub file tree |
| `/search` | Switch to search mode — ask questions about your hub files |
| `/capture` | Switch back to capture mode (default) — route thoughts to files |

Everything else you send (text, voice, files, photos) gets processed based on the current mode:
- **Capture** (default) — AI classifies and routes to hub files
- **Search** — AI searches hub files and returns answers

## Customizing prompts

Prompts live in the `prompts/` folder:
- [`prompts/router.md`](prompts/router.md) — how Claude classifies and routes your thoughts
- [`prompts/search.md`](prompts/search.md) — how Claude searches and answers questions

Files are loaded on every request, so changes take effect immediately.

## Tech stack

- [python-telegram-bot](https://python-telegram-bot.org/) — Telegram Bot API
- [Groq](https://groq.com/) — fast Whisper transcription
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/overview) — AI classification and file operations
- asyncio — sequential task queue

## License

[MIT](LICENSE)
