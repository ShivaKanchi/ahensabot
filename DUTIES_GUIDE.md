# Duty System Setup Guide

## Quick Start

### 1. Create `workspace/duty.md`

In your ahensabot workspace, create a file named `duty.md` with duty blocks (one per duty, separated by blank lines):

```
name: mood-check
cron: 0 11 * * *, 0 23 * * *
prompt: How are you feeling today? Rate 0-10 and tell me why.
type: mood

name: gut-check
cron: 0 13 * * *, 0 19 * * *
prompt: What did you eat? List meals and snacks.
type: gut

name: hydration-check
cron: 0 20 * * *
prompt: How much water did you drink today?
type: hydration
```

### 2. Start the Gateway

```bash
nanobot gateway
```

The gateway will automatically detect `duty.md` and install the duties as cron jobs.

### 3. Respond to Duty Prompts

When a duty prompt arrives, respond naturally:

- **Mood**: `7/10 feeling great today`
- **Gut**: `ate eggs, toast, and coffee`
- **Hydration**: `drank 1.5 liters`
- **Diary**: (any time) `Dear diary: Had an amazing day!`

The system detects keywords and logs entries to `workspace/memory/{duty_type}.md`.

---

## Duty Types & Examples

### Mood Check 🎭

**Config:**

```
name: mood-check
cron: 0 11 * * *, 0 23 * * *
prompt: How are you feeling? Rate 0-10.
type: mood
```

**User responses:**

- `7/10 feeling good`
- `mood: 5 - tired but okay`
- `8` (just the number)

**Stored in:** `workspace/memory/mood.md`

**Example entry:**

```
- 2026-02-22T11:00:00Z | rating: 7 | note: feeling good today
```

---

### Gut Check 🍽️

**Config:**

```
name: gut-check
cron: 0 13 * * *, 0 19 * * *
prompt: What did you eat?
type: gut
```

**User responses:**

- `Gut: eggs, toast, coffee`
- `I ate salad and rice`
- `food: chicken, broccoli, brown rice`

**Stored in:** `workspace/memory/gut.md`

**Example entry:**

```
- 2026-02-22T13:00:00Z | Gut: eggs, toast, coffee
```

---

### Hydration Check 💧

**Config:**

```
name: hydration-check
cron: 0 20 * * *
prompt: How much water did you drink?
type: hydration
```

**User responses:**

- `drank 500ml`
- `1 liter`
- `water: 750 ml`
- `2 L`

**Stored in:** `workspace/memory/hydration.md`

**System automatically:**

- Parses amounts (ml, L, oz)
- Sums daily totals
- Returns today's total

**Example entry:**

```
- 2026-02-22T20:00:00Z | raw: drank 500ml | liters: 0.500
Logged hydration (0.5 L). Today's total ~2.5 L
```

---

### Diary (Journal) 📔

**No cron needed** — manual anytime!

**User messages:**

- `Dear diary: Today I went to the gym!`
- `Diary: Had a productive meeting.`

**Stored in:** `workspace/memory/diary.md`

**Entries grouped by date:**

```
## 2026-02-22

- 10:15:23 | Today I went to the gym!
- 14:45:00 | Had a productive meeting.
```

Multiple entries on the same day append under one heading with timestamps.

---

## Configuration Reference

### Block Format

Each duty is a block of `key: value` pairs, separated by blank lines:

```
name: my-duty
cron: 0 11 * * *
prompt: Your prompt here?
type: mood
deliver: true
channel: telegram
to: 123456789
```

### Keys (all optional unless noted)

| Key                   | Example           | Purpose                                                          |
| --------------------- | ----------------- | ---------------------------------------------------------------- |
| `name` or `id`        | `mood-check`      | **Required** — Duty name (must be unique)                        |
| `cron` or `schedule`  | `0 11 * * *`      | Cron expression(s). Multiple times: `0 11 * * *, 0 23 * * *`     |
| `prompt` or `message` | `How are you?`    | **Required** — Question to ask                                   |
| `type` or `kind`      | `mood`            | **Recommended** — `mood`, `gut`, `hydration`, `diary`, or custom |
| `deliver`             | `true` or `false` | Send prompt to external channel? (default: internal)             |
| `channel`             | `telegram`        | Channel to deliver to (if `deliver: true`)                       |
| `to`                  | `123456789`       | Chat ID / recipient ID (if `deliver: true`)                      |

### Cron Syntax

Standard cron format: `minute hour day month weekday`

**Examples:**

- `0 11 * * *` — Daily at 11:00 AM
- `0 9,17 * * *` — Daily at 9 AM and 5 PM
- `0 11 * * 1-5` — Weekdays at 11 AM
- `*/30 * * * *` — Every 30 minutes
- `0 0 * * 0` — Sundays at midnight

### Multiple Times

Separate multiple cron expressions with commas:

```
name: mood-check
cron: 0 11 * * *, 0 23 * * *
```

This creates a single duty that runs at 11 AM and 11 PM.

---

## Data Files

### Generated Files in `workspace/memory/`

| File            | Created by                 | Format                                     |
| --------------- | -------------------------- | ------------------------------------------ |
| `mood.md`       | Mood duty / detection      | `- TIMESTAMP \| rating: N \| note: ...`    |
| `gut.md`        | Gut duty / detection       | `- TIMESTAMP \| meal description`          |
| `hydration.md`  | Hydration duty / detection | `- TIMESTAMP \| raw: ... \| liters: X.XXX` |
| `diary.md`      | Diary detection            | `## YYYY-MM-DD\n- HH:MM:SS \| entry`       |
| `dutyreport.md` | Duty prompts (backup)      | `- TIMESTAMP \| job: NAME \| prompt: ...`  |

---

## Viewing Data

### Command Line

```bash
# Watch real-time mood entries
tail -f ~/.nanobot/workspace/memory/mood.md

# View today's hydration
grep "$(date +%Y-%m-%d)" ~/.nanobot/workspace/memory/hydration.md

# Count meals eaten
wc -l ~/.nanobot/workspace/memory/gut.md

# View diary entries
cat ~/.nanobot/workspace/memory/diary.md
```

### In Chat

(Coming soon: CLI summary commands)

```bash
nanobot summary --type mood --period week
nanobot summary --type hydration --period day
nanobot summary --type gut --period month
```

---

## Advanced Setup

### Deliver to Telegram

1. Get your Telegram chat ID (use bot or `@userinfobot`)
2. Edit `duty.md`:

```
name: mood-check
cron: 0 11 * * *
prompt: How are you feeling?
type: mood
deliver: true
channel: telegram
to: 123456789
```

3. Bot will send the prompt to your Telegram chat; replies are logged automatically.

### Deliver to WhatsApp

Similar setup with `channel: whatsapp` and WhatsApp chat number as `to`.

### Custom Duty Type

Create any custom duty with a unique `type`:

```
name: exercise-log
cron: 0 19 * * *
prompt: How much did you exercise today?
type: exercise

name: sleep-log
cron: 0 8 * * *
prompt: How many hours did you sleep?
type: sleep
```

Data logged to `workspace/memory/exercise.md` and `workspace/memory/sleep.md` respectively.

---

## Troubleshooting

### Duty prompts not appearing

1. **Check if gateway is running:**

   ```bash
   ps aux | grep "nanobot gateway"
   ```

2. **Check duty.md is valid:**

   ```bash
   cat ~/.nanobot/workspace/duty.md
   ```

3. **Check cron jobs installed:**

   ```bash
   cat ~/.nanobot/data/cron/jobs.json
   ```

4. **Check gateway logs:**
   ```bash
   # Look for "Cron: executing job" in logs
   ```

### Entries not logging

1. **Check detection keywords** — "mood" or "0-10" for mood, "water" or "ml" for hydration, etc.
2. **Check file permissions** — Can the bot write to `workspace/memory/`?
3. **Check message format** — Use natural language (e.g., "7/10 feeling great").

### Fix cron syntax errors

Use an online cron validator: https://crontab.guru/

---

## Examples

### Health Tracking

```
name: morning-mood
cron: 0 7 * * *
prompt: Good morning! How are you feeling today? (0-10)
type: mood

name: lunch-log
cron: 0 13 * * *
prompt: What did you have for lunch?
type: gut

name: evening-hydration
cron: 0 21 * * *
prompt: How much water did you drink today?
type: hydration
```

### Journaling + Mood

```
name: mood-check
cron: 0 11 * * *, 0 23 * * *
prompt: How are you feeling? (0-10 scale)
type: mood
```

Then anytime, journal manually:

```
Dear diary: Today was amazing! Finished the project.
```

### Weekly Meal Planning

```
name: meal-check
cron: 0 13 * * *
prompt: What did you eat? Include ingredients if you remember.
type: gut
```

---

## Tips & Best Practices

1. **Start simple** — Begin with mood checks only; add others later.
2. **Use consistent language** — "drank 500ml" works better than "had some water".
3. **Review weekly** — Check `mood.md` to spot trends.
4. **Backup memory files** — Optional: version control `workspace/memory/` with git.
5. **Adjust schedules** — Edit `duty.md` and restart gateway to change times.
6. **Use diary for context** — Journal entries help the bot understand your life better.

---

## FAQ

**Q: Can I add custom duties?**  
A: Yes! Any `type:` value creates a custom duty logged to `workspace/memory/{type}.md`.

**Q: How is hydration calculated?**  
A: The system parses ml, L, oz and sums daily totals. 1 oz ≈ 0.03 L.

**Q: What if I miss a check-in?**  
A: You can reply anytime with natural language. It gets logged to the same file.

**Q: Can I delete old entries?**  
A: Yes, edit the file directly. But keeping full history is recommended for trend analysis.

**Q: Will mood checks notification?**  
A: Only if `deliver: true` and channel configured. Otherwise check your chat history or `mood.md`.

**Q: Can I change a duty schedule?**  
A: Edit `duty.md` and restart the gateway. Old jobs are kept unless manually removed.

---

## See Also

- [FEATURES.md](FEATURES.md) — Full feature documentation
- [STRUCTURE.md](STRUCTURE.md) — Project folder layout
- [README.md](README.md) — Getting started
