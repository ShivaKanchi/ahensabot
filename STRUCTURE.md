# Project Structure

## Overview

Ahensabot is organized into core bot logic, channels, skills, agents, and workspace data. This document explains the folder layout and purpose of each directory.

---

## Root Level

```
ahensabot/
├── nanobot/              # Core bot engine
├── bridge/               # WhatsApp bridge (Node.js)
├── workspace/            # User's workspace (config, memory, agents)
├── tests/                # Test suite
├── case/                 # Case studies / examples
├── FEATURES.md           # Feature documentation (THIS part 1)
├── STRUCTURE.md          # Folder structure (THIS - part 2)
├── README.md             # Main readme
├── COMMUNICATION.md      # Communication protocols
├── SECURITY.md           # Security best practices
├── pyproject.toml        # Python dependencies
├── Dockerfile            # Docker container definition
├── docker-compose.yml    # Multi-service docker setup
└── LICENSE               # License
```

---

## `nanobot/` — Core Engine

The Python core that powers the assistant.

```
nanobot/
├── __main__.py           # CLI entry point
├── __init__.py           # Version, logo
├── server.py             # Web server (status dashboard)
├── agent/                # Agent processing engine
│   ├── __init__.py
│   ├── context.py        # Context builder (history, memory, skills)
│   ├── loop.py           # Agent loop (message processing, LLM calls)
│   ├── memory.py         # Memory store (long-term + history)
│   ├── skills.py         # Skill registry & loader
│   ├── subagent.py       # Subagent manager (parallel tasks)
│   └── tools/            # Tool implementations
│       ├── __init__.py
│       ├── base.py       # Tool base class
│       ├── registry.py   # Tool registry
│       ├── filesystem.py # Read/write/edit files
│       ├── shell.py      # Execute shell commands
│       ├── web.py        # Web search & fetch
│       ├── message.py    # Send messages to users
│       ├── spawn.py      # Spawn subagents
│       ├── cron.py       # Schedule tasks
│       └── mcp.py        # Model Context Protocol support
├── bus/                  # Message bus
│   ├── __init__.py
│   ├── events.py         # Message types (InboundMessage, OutboundMessage)
│   └── queue.py          # Async message queue
├── channels/             # Channel adapters (multi-platform)
│   ├── __init__.py
│   ├── base.py           # Channel base class
│   ├── manager.py        # Channel manager
│   ├── cli.py            # CLI adapter
│   ├── telegram.py       # Telegram bot
│   ├── whatsapp.py       # WhatsApp adapter
│   ├── discord.py        # Discord bot
│   ├── slack.py          # Slack adapter
│   ├── email.py          # Email adapter
│   ├── feishu.py         # Feishu (Lark) adapter
│   ├── dingtalk.py       # DingTalk adapter
│   ├── mochat.py         # MoChat (WeChat) adapter
│   └── qq.py             # QQ adapter
├── config/               # Configuration handling
│   ├── __init__.py
│   ├── schema.py         # Config data models (Pydantic)
│   └── loader.py         # Load/save config files
├── cron/                 # Scheduled tasks (duty system)
│   ├── __init__.py
│   ├── service.py        # Cron scheduler
│   └── types.py          # CronJob, CronSchedule types
├── heartbeat/            # Heartbeat (periodic check-ins)
│   ├── __init__.py
│   └── service.py        # Heartbeat service
├── session/              # Session management
│   ├── __init__.py
│   └── manager.py        # Session store
├── skills/               # Built-in skills (agents can call these)
│   ├── README.md
│   ├── cron/             # Cron skill (manage scheduled tasks)
│   │   └── SKILL.md
│   ├── github/           # GitHub interaction
│   │   └── SKILL.md
│   ├── memory/           # Memory skill
│   │   └── SKILL.md
│   ├── skill-creator/    # Create custom skills
│   │   └── SKILL.md
│   ├── summarize/        # Summarization skill
│   │   └── SKILL.md
│   ├── weather/          # Weather lookup
│   │   └── SKILL.md
│   ├── tmux/             # Terminal multiplexer
│   │   ├── SKILL.md
│   │   └── scripts/
│   └── clawhub/          # (Custom) Clawhub integration
│       └── SKILL.md
├── providers/            # LLM providers
│   ├── __init__.py
│   ├── base.py           # Provider base class
│   ├── litellm_provider.py # LiteLLM (OpenAI, Claude, etc.)
│   ├── openai_codex_provider.py # OpenAI Codex
│   ├── transcription.py  # Audio transcription
│   └── registry.py       # Provider registry
├── cli/                  # CLI interface (nanobot commands)
│   ├── __init__.py
│   └── commands.py       # Typer CLI app & commands (gateway, agent, cron, etc.)
├── utils/                # Utilities
│   ├── __init__.py
│   └── helpers.py        # Helper functions
└── __pycache__/          # Python cache (auto-generated)
```

---

## `bridge/` — WhatsApp Bridge

Node.js/TypeScript bridge for WhatsApp integration (optional).

```
bridge/
├── src/
│   ├── index.ts          # Entry point
│   ├── server.ts         # WhatsApp API server
│   ├── whatsapp.ts       # WhatsApp client (Baileys)
│   └── types.d.ts        # TypeScript definitions
├── package.json          # Node dependencies
├── tsconfig.json         # TypeScript config
└── dist/                 # Compiled JS (auto-generated)
```

---

## `workspace/` — User Workspace

Configuration, instructions, and data for the user's bot instance.

```
workspace/
├── AGENTS.md             # Agent instructions (system prompt)
├── SOUL.md               # Bot personality / tone
├── USER.md               # User preferences & info
├── TOOLS.md              # Tool documentation
├── HEARTBEAT.md          # Heartbeat configuration
├── duty.md               # DUTY SYSTEM CONFIG (new!)
├── memory/               # Persistent memory & logs
│   ├── MEMORY.md         # Long-term facts & preferences
│   ├── HISTORY.md        # Session conversation summaries
│   ├── mood.md           # Mood tracking (duty system)
│   ├── gut.md            # Food/meal tracking (duty system)
│   ├── hydration.md      # Water intake tracking (duty system)
│   ├── diary.md          # Journal entries (duty system)
│   ├── dutyreport.md     # Duty log (scheduled prompts)
│   └── (other memory files as needed)
└── skills/               # Custom user skills (optional)
```

### What each file does:

| File                   | Purpose                                                            |
| ---------------------- | ------------------------------------------------------------------ |
| `AGENTS.md`            | System instructions for the agent (custom persona, guidelines)     |
| `SOUL.md`              | Bot personality (tone, style, values)                              |
| `USER.md`              | User info (name, preferences, timezone)                            |
| `TOOLS.md`             | Documentation of available tools                                   |
| `HEARTBEAT.md`         | Periodic check-in config (30-min default)                          |
| `duty.md`              | **[NEW]** Configurable duty schedule (mood, gut, hydration, diary) |
| `memory/MEMORY.md`     | Long-term facts (learned over sessions)                            |
| `memory/HISTORY.md`    | Session summaries (auto-consolidation)                             |
| `memory/mood.md`       | **[NEW]** Mood ratings with timestamps                             |
| `memory/gut.md`        | **[NEW]** Food/meal intake log                                     |
| `memory/hydration.md`  | **[NEW]** Water intake with parsed liters                          |
| `memory/diary.md`      | **[NEW]** Journal entries grouped by date                          |
| `memory/dutyreport.md` | **[NEW]** Backup log of duty prompts                               |

---

## `tests/` — Test Suite

Automated tests for the bot.

```
tests/
├── test_cli_input.py         # CLI input handling
├── test_commands.py          # Command parsing
├── test_consolidate_offset.py # Memory consolidation
├── test_docker.sh            # Docker setup test
├── test_email_channel.py      # Email channel
└── test_tool_validation.py    # Tool validation
```

---

## `case/` — Case Studies

Example implementations and use cases (currently empty).

```
case/
```

---

## Configuration Files

### `pyproject.toml`

Python dependencies, scripts, and metadata.

**Key sections:**

- `dependencies` — Python packages (croniter, litellm, pydantic, etc.)
- `scripts` — CLI entry point (`nanobot = nanobot.cli.commands:app`)

### `Dockerfile` & `docker-compose.yml`

Containerization setup. Run with:

```bash
docker-compose up
```

---

## Key Concepts

### Message Flow

1. **User** sends message in channel (CLI, Telegram, etc.)
2. **Channel adapter** wraps it in `InboundMessage` and publishes to message bus
3. **Agent loop** consumes message, detects **duty keywords** (new!)
4. If duty detected → logs to `memory/{duty_type}.md` → returns confirmation
5. Else → passes to LLM, executes tools, returns response
6. **Channel adapter** sends response back to user

### Duty Detection (NEW!)

In `nanobot/agent/loop.py`, quick detectors intercept messages:

- **Diary**: Message starts with `Dear diary:` or `Diary:` → logs to `memory/diary.md`
- **Mood**: Message contains `mood` or a 0-10 rating → logs to `memory/mood.md`
- **Gut**: Message starts with `gut:` or contains `ate`, `food`, `meal` → logs to `memory/gut.md`
- **Hydration**: Message mentions `water`/`drank` or has ml/L amounts → logs to `memory/hydration.md` (with liters total)

### Cron Job Scheduling

`nanobot/cron/service.py` manages scheduled tasks:

1. Loads jobs from `~/.nanobot/data/cron/jobs.json`
2. At startup, (re)reads `workspace/duty.md` and auto-installs duties
3. Computes next run times using `croniter`
4. On schedule, publishes prompts (for duties) or executes agents (for regular jobs)
5. Logs & histories to memory files

---

## Data Directories

### `~/.nanobot/` (User Home)

```
~/.nanobot/
├── config.json           # API keys, model settings
├── history/
│   └── cli_history       # CLI command history
└── data/
    ├── sessions/         # Session state (message history)
    └── cron/
        └── jobs.json     # Installed cron jobs (duties, etc.)
```

### `workspace/` Mutable Files

The `workspace/` folder is where users customize and store data:

- `AGENTS.md` — Custom instructions
- `SOUL.md` — Custom personality
- `duty.md` — Duty schedule (editable!)
- `memory/*` — All logs, memories, journals (auto-written)

---

## Adding New Duties (Quick Guide)

1. **Edit** `workspace/duty.md`:

   ```
   name: my-duty
   cron: 0 12 * * *
   prompt: Your question here?
   type: custom
   ```

2. **Restart** gateway:

   ```bash
   nanobot gateway
   ```

3. **Respond** in chat with natural text. The system auto-logs to `workspace/memory/custom.md`.

---

## Dependencies

### Core Python

- `python 3.11+`
- `typer` — CLI framework
- `pydantic` — Data validation
- `aiohttp` — Async HTTP
- `loguru` — Logging
- `croniter` — Cron expression parsing

### AI/LLM

- `litellm` — LLM provider abstraction (OpenAI, Claude, etc.)
- `json_repair` — Robust JSON parsing

### Channels

- `telethon` or `pyrogram` — Telegram
- `whatsapp-web.js` — WhatsApp (Node.js)
- `discord.py` — Discord
- `slack-bolt` — Slack
- etc.

See `pyproject.toml` for full list with versions.

---

## Environment Variables

Key variables used:

| Variable             | Purpose                                              |
| -------------------- | ---------------------------------------------------- |
| `NANOBOT_WORKSPACE`  | Workspace folder (default: `~/.nanobot/workspace`)   |
| `NANOBOT_CONFIG`     | Config file path (default: `~/.nanobot/config.json`) |
| `OPENROUTER_API_KEY` | OpenRouter LLM API key                               |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (if using Telegram)               |
| `WHATSAPP_API_URL`   | WhatsApp API endpoint                                |

Set in `.env` or in `config.json`.

---

## Common Commands

### Gateway (main server)

```bash
nanobot gateway --port 18790
```

### CLI Chat

```bash
nanobot agent -m "Hello!"
nanobot agent          # Interactive mode
```

### Cron Management

```bash
nanobot cron add --name "duty" --message "How are you?" --cron "0 11 * * *"
nanobot cron list
nanobot cron run <job_id>
```

### Onboard / Setup

```bash
nanobot onboard       # Initialize workspace & config
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        User Channels                         │
│  CLI | Telegram | WhatsApp | Discord | Slack | Email | etc. │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ InboundMessage
                 ▼
          ┌──────────────┐
          │ Message Bus  │
          │   (Queue)    │
          └──────┬───────┘
                 │
                 │ Consume
                 ▼
    ┌─────────────────────────────┐
    │     Agent Loop              │
    │ (nanobot/agent/loop.py)     │
    │                             │
    │  1. Quick duty detectors←──┐│
    │  2. Slash commands / help  ││ (New!)
    │  3. Memory consolidation   ││
    │  4. LLM chat + tools       ││
    │  5. Return response        ││
    └────────────┬────────────────┘
                 │
              Response│
                 ▼
          ┌──────────────┐
          │ Message Bus  │
          │ (Outbound)   │
          └──────┬───────┘
                 │
                 ▼
            ┌────────────┐
  ┌─────────┤  Channels  │─────────┐
  │         └────────────┘         │
  │                                │
  ▼                                ▼
User Response            Memory / Logs
(back to channel)      (workspace/memory/*)
```

---

## File Permissions & Safety

- `config.json` — Contains API keys; readable only by user (mode: 600)
- `workspace/` — User-editable config & logs
- `memory/` — Auto-generated logs; append-only to prevent data loss

---

## See Also

- [FEATURES.md](FEATURES.md) — Duty system & features
- [README.md](README.md) — Getting started
- [COMMUNICATION.md](COMMUNICATION.md) — Channel protocols
- [SECURITY.md](SECURITY.md) — Security best practices
