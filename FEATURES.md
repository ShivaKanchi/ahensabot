# Features

## Overview

Ahensabot is a personal AI assistant with multi-channel support, scheduled tasks (cron), memory management, and now — **Duty system** for health tracking and journaling.

---

## Core Features

### 1. **Multi-Channel Support**

Connect with your AI assistant across multiple platforms:

- **CLI** — Direct terminal chat
- **Telegram** — Send/receive messages via Telegram Bot
- **WhatsApp** — Send/receive via WhatsApp
- **Discord** — Discord bot integration
- **Slack** — Slack workspace integration
- **Email** — Email-based interactions
- **Feishu** (Lark) — Enterprise chat
- **DingTalk** — Corporate messaging
- **MoChat** — WeChat integration
- **QQ** — QQ messaging

### 2. **Scheduled Tasks (Cron)**

Set up recurring or one-time tasks using familiar cron syntax.

**Example:**

```bash
nanobot cron add --name "morning" --message "Good morning!" --cron "0 9 * * *"
nanobot cron add --name "check" --message "Status check" --every 3600
nanobot cron add --name "meeting" --message "Meeting starts!" --at "2025-02-22T15:00:00"
```

### 3. **Memory System**

Automatically consolidate and store important information for context across sessions.

**Storage:**

- `workspace/memory/MEMORY.md` — Long-term facts, preferences, user info
- `workspace/memory/HISTORY.md` — Session-by-session conversation summaries

### 4. **Agent Skills**

Built-in tools and abilities:

- **Filesystem** — Read, write, edit, list files
- **Shell** — Execute terminal commands (with restrictions)
- **Web Search** — Brave Search integration
- **Web Fetch** — Browse and extract info from URLs
- **Messaging** — Send messages to users
- **Spawn** — Run subagents for parallel work
- **MCP (Model Context Protocol)** — Extensible tool integration

---

## 🎯 Duty System (Master Health & Wellness Tracker)

The **Duty system** is a smart, configurable health and wellness tracker built into ahensabot. It automatically asks the master about mood, food intake, water consumption, and journal entries at scheduled times, then organizes and archives the responses for health insights.

### What are Duties?

Duties are **scheduled check-ins** (like cron jobs) that ask health/wellness questions. Unlike traditional reminders, duties:

- Are **configurable** in a simple `duty.md` file (key:value blocks)
- Track **timestamped responses** to memory files for analysis
- Support **multiple schedules** (e.g., 11am and 11pm mood checks)
- Can be **delivered to external channels** (Telegram, WhatsApp, etc.) or stay internal
- Allow **flexible user input** (diary, mood, hydration, food entries)

### Available Duty Types

#### 1. **mood-check** 🎭

Asks how the master is feeling and records mood on a 0–10 scale.

**Files:**

- `workspace/memory/mood.md` — Timestamped mood entries
- `workspace/memory/dutyreport.md` — Scheduled prompts (backup log)

**User input examples:**

- `7/10 feeling good today`
- `mood: 5 - tired but okay`
- `6` (just a number)

**Output format:**

```
- 2026-02-22T11:00:00Z | rating: 7 | note: feeling good today
```

---

#### 2. **gut-check** 🍽️

Tracks what the master ate and when, for dietary and health monitoring.

**Files:**

- `workspace/memory/gut.md` — Food/meal entries with timestamps
- Daily summaries available via CLI commands

**User input examples:**

- `Gut: eggs, toast, coffee for breakfast`
- `I ate salad and rice for lunch`
- `food: chicken, broccoli, brown rice`

**Output format:**

```
- 2026-02-22T12:30:00Z | I ate salad and rice for lunch
```

---

#### 3. **hydration-check** 💧

Records water intake and computes daily totals for health awareness.

**Files:**

- `workspace/memory/hydration.md` — Timestamped hydration entries with parsed liters
- Daily/weekly totals computed on-the-fly

**User input examples:**

- `Drank 500ml water`
- `water: 1 liter`
- `750 ml`
- `2 L`

**Output format:**

```
- 2026-02-22T14:00:00Z | raw: drank 500ml water | liters: 0.500
```

The system **sums** all entries for the day and provides a total:

```
Logged hydration (0.5 L). Today's total ~2.5 L
```

---

#### 4. **diary-add** 📔

Free-form journaling. Master can write diary entries anytime; they're auto-organized by date.

**Files:**

- `workspace/memory/diary.md` — Entries grouped by date (ISO format)

**User input examples:**

- `Dear diary: Today I went to the gym and felt amazing!`
- `Diary: Had a tough meeting but learned something new.`

**Output format:**

```
## 2026-02-22

- 10:15:23 | Today I went to the gym and felt amazing!
- 14:45:00 | Had a tough meeting but learned something new.
```

Multiple entries on the same day are appended (with timestamps) under one heading.

---

### How to Set Up Duties

#### Step 1: Create `workspace/duty.md`

Edit or create `workspace/duty.md` with one block per duty (blocks separated by blank lines):

```
name: mood-check
cron: 0 11 * * *, 0 23 * * *
prompt: How are you feeling? Rate 0-10 and describe your mood.
type: mood

name: gut-check
cron: 0 13 * * *, 0 19 * * *
prompt: What did you eat today? List meals and snacks.
type: gut

name: hydration-check
cron: 0 20 * * *
prompt: How much water did you drink today?
type: hydration

name: diary-add
prompt: (optional; usually triggered manually)
type: diary
```

**Parsing rules:**

- `name` or `id` — Duty name (required)
- `cron` or `schedule` — Cron expression(s); comma-seperated for multiple times (required unless manual)
- `prompt` or `message` — Question/prompt to ask (required)
- `type` or `kind` — Duty category (`mood`, `gut`, `hydration`, `diary`; optional but helpful for logging)

#### Step 2: Start the Gateway

```bash
nanobot gateway
```

When the gateway starts, it reads `workspace/duty.md` and **auto-installs** all duties as cron jobs.

#### Step 3: Respond to Prompts

When a duty prompt is scheduled, it appears in your chat (CLI, Telegram, etc.). Reply naturally:

- **Mood**: `7/10 feeling great`
- **Gut**: `ate eggs, toast, coffee`
- **Hydration**: `drank 500ml`
- **Diary**: `Dear diary: Had a productive day!`

The system detects keywords, extracts info, and logs to the appropriate file.

---

### Data Storage & Access

All duty data is stored in `workspace/memory/`:

| File            | Purpose                         | Format                                     |
| --------------- | ------------------------------- | ------------------------------------------ |
| `mood.md`       | Mood ratings over time          | `- TIMESTAMP \| rating: 0-10 \| note: ...` |
| `gut.md`        | Food intake log                 | `- TIMESTAMP \| meal description`          |
| `hydration.md`  | Water intake with parsed liters | `- TIMESTAMP \| raw: ... \| liters: X.XXX` |
| `diary.md`      | Journaling grouped by date      | `## YYYY-MM-DD\n- HH:MM:SS \| entry`       |
| `dutyreport.md` | Backup log of scheduled prompts | `- TIMESTAMP \| job: NAME \| prompt: ...`  |

---

### View & Analyze Data

#### Quick View (CLI)

```bash
# View recent mood entries
cat ~/.nanobot/workspace/memory/mood.md

# View today's hydration total
grep "$(date +%Y-%m-%d)" ~/.nanobot/workspace/memory/hydration.md

# View diary entries
cat ~/.nanobot/workspace/memory/diary.md
```

#### Summaries (CLI commands — coming soon)

```bash
nanobot summary --type mood --period week
nanobot summary --type hydration --period day
nanobot summary --type gut --period month
```

---

### Integration with External Channels

To deliver duty prompts to Telegram, WhatsApp, etc., configure `duty.md`:

```
name: mood-check
cron: 0 11 * * *
prompt: How are you feeling?
type: mood
deliver: true
channel: telegram
to: YOUR_TELEGRAM_CHAT_ID
```

The prompt is then sent to the channel; replies are logged automatically.

---

## Workspace Structure

See [STRUCTURE.md](STRUCTURE.md) for detailed folder layout.

---

## Changelog

### v1.0.0 (Feb 2026)

- ✅ Core duty system (mood, gut, hydration, diary)
- ✅ Configurable `duty.md` (simple blocks)
- ✅ Auto-install cron jobs from config
- ✅ Timestamped memory storage
- ✅ Keyword detection for user inputs
- ✅ Daily aggregation (hydration totals)
- 🔜 CLI summary commands
- 🔜 Channel delivery (Telegram, WhatsApp)
- 🔜 Mood trend analysis & cheering suggestions

---

## Examples

### Example 1: Set up morning mood + hydration checks

**workspace/duty.md:**

```
name: morning-routine
cron: 0 7 * * *
prompt: Good morning! How are you feeling today? (0-10 scale)
type: mood

name: evening-hydration
cron: 0 21 * * *
prompt: How much water did you drink today?
type: hydration
```

**In chat when prompts arrive:**

```
Bot: Good morning! How are you feeling today? (0-10 scale)
You: 7/10 slept well, ready for the day

Bot: How much water did you drink today?
You: drank 2 liters today
```

**Resulting files:**

- `mood.md`: `- 2026-02-22T07:00:00Z | rating: 7 | note: 7/10 slept well, ready for the day`
- `hydration.md`: `- 2026-02-22T21:00:00Z | raw: drank 2 liters today | liters: 2.000`

---

### Example 2: Food tracking with automated reports

**workspace/duty.md:**

```
name: gut-check
cron: 0 14 * * *
prompt: What did you eat for lunch?
type: gut
```

**In chat:**

```
Bot: What did you eat for lunch?
You: I ate chicken, brown rice, and broccoli
```

**Resulting file:**

- `gut.md`: `- 2026-02-22T14:00:00Z | I ate chicken, brown rice, and broccoli`

---

### Example 3: Free-form journaling (manual)

**In chat, anytime:**

```
You: Dear diary: Today was amazing! Finished the project and got praise from the team.
Bot: Diary entry saved.

You: Diary: Feeling grateful and excited for what's next.
Bot: Diary entry saved.
```

**Resulting file (workspace/memory/diary.md):**

```
## 2026-02-22

- 14:30:15 | Today was amazing! Finished the project and got praise from the team.
- 15:45:00 | Feeling grateful and excited for what's next.
```

---

## Customization

### Change duty schedules

Edit `workspace/duty.md` and restart the gateway.

### Add new duty types

Create a new entry in `duty.md` with a custom `name` and `type`. The system logs to `workspace/memory/{type}.md`.

### Use external channels

Set `deliver: true`, `channel: telegram`, and `to: CHAT_ID` in a duty block.

---

## FAQ

**Q: Can I manually add diary entries anytime?**  
A: Yes! Just message `Dear diary: ...` or `Diary: ...` anytime. No cron schedule needed.

**Q: How is hydration in ounces handled?**  
A: Automatically converted to liters (1 oz ≈ 0.0296 L) for totaling.

**Q: Can I view summaries for a specific date range?**  
A: Not yet, but you can grep the files:

```bash
grep "2026-02-" ~/.nanobot/workspace/memory/mood.md
```

**Q: What if I miss a duty check-in?**  
A: All prompts are logged to `dutyreport.md`. You can manually reply anytime by sending the corresponding message type (mood, gut, diary, hydration).

**Q: Can duties send notifications to my phone?**  
A: Yes, if you configure `deliver: true`, `channel: telegram` (or whatsapp), and the corresponding bot token + chat ID.

---

## See Also

- [STRUCTURE.md](STRUCTURE.md) — Folder layout & architecture
- [AGENTS.md](../workspace/AGENTS.md) — Agent instructions
- [SOUL.md](../workspace/SOUL.md) — Bot personality
- [TOOLS.md](../workspace/TOOLS.md) — Available tools
- [MEMORY.md](../workspace/memory/MEMORY.md) — Long-term memory
