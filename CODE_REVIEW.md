# Code Review: Duty System Implementation

## Critical Issues 🔴

### 1. **Hydration Calculation Bug** (loop.py:394)

**Severity: HIGH** ✅ **FIXED**

```python
# BEFORE:
if today in line or True:  # ❌ BUG

# AFTER:
if today in line and line.strip():  # ✅ FIXED
```

### 2. **Hydration Detection False Positive** (loop.py:353-356)

**Severity: HIGH** ✅ **FIXED**

```python
# BEFORE:
if ("water" in low or "drank" in low or
    re.search(r"\b[0-9]+(?:\.[0-9]+)?\s*(ml|l|litre|liters|oz)?\b", low)):

# AFTER:
has_hydration_keyword = "water" in low or "drank" in low
has_unit_with_number = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s+(ml|litre?s?|ltrs|oz|l)\b", low)
if has_hydration_keyword or has_unit_with_number:
```

### 3. **Diary File Inefficiency** (loop.py:304-310)

**Severity: MEDIUM**

```python
content = diary_file.read_text(encoding="utf-8") if diary_file.exists() else ""
if f"## {today}" not in content:
    diary_file.write_text(content + f"\n\n## {today}\n\n")  # Rewrites entire file
```

**Problem:** For large diary files (years of data), this reads and rewrites the entire file on every new day. Performance degrades over time.

**Fix:**

```python
def _ensure_diary_date_heading(diary_file: Path, today: str):
    """Append date heading if not present (append-only, no full rewrite)."""
    if not diary_file.exists():
        diary_file.write_text(f"## {today}\n\n")
        return

    # Check last occurrence without full read
    try:
        # Only check last 500 bytes (date headings won't be deep in file)
        with diary_file.open("rb") as f:
            f.seek(-min(500, diary_file.stat().st_size), 2)
            tail = f.read().decode("utf-8", errors="ignore")
    except:
        return

    if f"## {today}" not in tail:
        with diary_file.open("a", encoding="utf-8") as f:
            f.write(f"\n\n## {today}\n\n")
```

### 4. **Duplicate Duty Installation Check Flawed** (commands.py:462-467)

**Severity: MEDIUM**

```python
if "duty-morning" not in existing:
    cron.add_job(name="duty-morning", ...)
if "duty-morning" not in existing:
    cron.add_job(name="duty-morning", ...)
```

With multiple cron expressions, all jobs have the same name:

```
name: mood
cron: 0 11 * * *, 0 23 * * *
```

If one "mood" job exists, we skip BOTH times instead of checking per-cron-expression.

**Fix:**

```python
for expr in [e.strip() for e in cron_expr.split(",") if e.strip()]:
    job_id = f"{name}:{expr}"  # Unique ID per cron expression
    if job_id not in [f"{j.name}:{j.schedule.expr}" for j in existing_jobs]:
        cron.add_job(name=name, schedule=CronSchedule(kind="cron", expr=expr), ...)
```

---

## Moderate Issues 🟡

### 5. **Silent Exception Handling** (commands.py:463, loop.py:412)

**Severity: MEDIUM** ✅ **FIXED**

```python
# BEFORE:
except Exception:
    pass  # ❌ Silent failure

# AFTER:
except FileNotFoundError:
    pass  # duty.md doesn't exist
except Exception as e:
    logger.error(f"Failed to parse duty.md: {e}")  # ✅ LOGGED
```

### 6. **Config Reloaded on Every Duty Job** (commands.py:481)

**Severity: MEDIUM** ✅ **FIXED**

```python
# BEFORE:
cfg = load_config()  # ❌ Loaded from disk every job

# AFTER:
duty_dir = config.workspace_path / "memory"  # ✅ Uses cached config
```

### 7. **No Timezone Support** (loop.py: all timestamps)

**Severity: MEDIUM**

All timestamps use UTC:

```python
ts = datetime.utcnow().isoformat() + "Z"
```

User might be in EST/PST, making times confusing.

**Fix:**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

# Read user's timezone from config or system
tz = ZoneInfo(config.user.timezone or "UTC")
ts = datetime.now(tz).isoformat()  # Local time with TZ info
```

### 8. **Mood Detection Too Loose** (loop.py:326-330)

**Severity: LOW** ✅ **FIXED**

```python
# BEFORE:
m = re.search(r"\b([0-9]|10)(?:/10)?\b", text)
if "mood" in low or "/10" in text or m:

# AFTER:
has_mood_keyword = bool(re.search(r"\bmood\b", low))  # Word boundary
if (has_mood_keyword and m) or ("/10" in text):  # ✅ Requires both or explicit /10
```

### 9. **Broken Regex Pattern for Hydration Units** (loop.py:362)

**Severity: LOW**

```python
amounts = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ml|l|litre|liters|ltrs|oz)?", low)
```

The `?` makes unit optional, allowing `"I have 5"` to match as `5 liters` (assumed).

**Fix:**

```python
# Only match if unit is present or keyword indicators exist
amounts = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(ml|litre?s?|ltrs|oz|l)(?:\s|$)", low)
```

### 10. **File Handle Not Explicitly Closed** (multiple locations)

**Severity: LOW**

While `with` statements are used in most places, some are dangling:

```python
with report_file.open("a", encoding="utf-8") as f:
    f.write(entry)  # ✓ Properly closed by context manager
```

Good, but ensure consistent pattern everywhere.

---

## Optimization Opportunities 🟢

### 11. **Pre-compile Regex Patterns** (loop.py)

**Performance Issue: LOW**

Regexes are compiled fresh on every message:

```python
m = re.search(r"\b([0-9]|10)(?:/10)?\b", text)  # Recompiled each message
```

**Solution:**

```python
# At module level
MOOD_RATING_PATTERN = re.compile(r"\b([0-9]|10)(?:/10)?\b")
WATER_AMOUNT_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(ml|litre?s?|l|oz)")

# In loop
m = MOOD_RATING_PATTERN.search(text)  # Uses cached compiled pattern
```

### 12. **No Cron Expression Validation** (commands.py:469)

**Data Quality Issue: MEDIUM**

Invalid cron expressions are silently ignored:

```python
for expr in [e.strip() for e in cron_expr.split(",") if e.strip()]:
    job = cron.add_job(
        name=name,
        schedule=CronSchedule(kind="cron", expr=expr),  # No validation here
        ...
    )
```

If `expr` is invalid (e.g., `"0 25 * * *"`), it fails later during execution.

**Fix:**

```python
from croniter import croniter

for expr in [e.strip() for e in cron_expr.split(",") if e.strip()]:
    try:
        croniter(expr)  # Validate early
    except ValueError as e:
        logger.error(f"Invalid cron expression '{expr}': {e}")
        continue

    cron.add_job(name=name, schedule=CronSchedule(kind="cron", expr=expr), ...)
```

### 13. **Hydration File Always Reread** (loop.py:388-399)

**Performance Issue: MEDIUM**

For every hydration entry, the entire file is read again to compute totals:

```python
total_today = 0.0
for line in hydration_file.read_text(encoding="utf-8").splitlines():  # Full reread
```

With 10+ daily hydration entries, this reads the file 10+ times.

**Solution:**

```python
# Keep today's total in memory or use a summary file
# Or: compute incrementally within the loop
total_l = 0.0
with hydration_file.open("a", encoding="utf-8") as f:
    f.write(entry)

# Reuse variables from parsing instead of rereading
return OutboundMessage(..., content=f"Logged hydration ({total_l:.3f} L). Today's total ~2.5 L")
```

Actually, the current implementation already has total_l from parsing. Just don't reread the entire file for today's total:

```python
# Instead of rereading entire file:
# Write to file, then only read back today's entries if needed
total_today = 0.0
if hydration_file.exists():
    for line in hydration_file.read_text(encoding="utf-8").splitlines():
        if today in line:  # Only check today's lines
            m2 = re.search(r"liters: ([0-9]+\.[0-9]+)", line)
            if m2:
                total_today += float(m2.group(1))
```

Wait, this doesn't help since we iterate all lines. Better: maintain a cache or summary file.

### 14. **Memory Accumulation in Large Files**

**Potential Issue: MEDIUM**

As mood.md, gut.md grow (years of data), parsing becomes slower. No archival strategy.

**Suggestion:** Add optional archival after N entries:

```python
# In config
max_entries_per_file: 10000
archive_when_full: true

# If file has >10k entries, move old ones to `mood.archived.md`
```

### 15. **No Batch Writing Option**

**Efficiency Issue: LOW**

Each entry writes individually. With high-frequency duties, could batch:

```python
# Instead of multiple .open("a") calls, buffer and flush once
hydration_buffer = [entry1, entry2, entry3]
with hydration_file.open("a") as f:
    f.writelines(hydration_buffer)
```

Less relevant for duties, but good for future extensibility.

---

## Code Quality Issues 🟠

### 16. **Inconsistent Error Messages**

Files are sometimes referenced with variable expansion, sometimes hardcoded:

```python
report_file = duty_dir / "dutyreport.md"  # Good
# vs
diary_file = memory_dir / "diary.md"  # Same, but should be consistent in naming
```

### 17. **Magic Strings Hardcoded**

**Maintainability Issue**

```python
if f"## {today}" not in content:  # Magic format
diary_file.write_text(content + f"\n\n## {today}\n\n")  # Magic spacing
```

**Fix:**

```python
DATE_SECTION_FORMAT = "## {date}"
SECTION_SPACING = "\n\n"

date_heading = DATE_SECTION_FORMAT.format(date=today)
if date_heading not in content:
    diary_file.write_text(content + f"{SECTION_SPACING}{date_heading}{SECTION_SPACING}")
```

### 18. **No Type Hints on Key Functions**

Functions lack return type hints:

```python
async def on_cron_job(job: CronJob) -> str | None:  # ✓ Good
# But:
if low.startswith("dear diary:"):  # ← Could be in a helper function with better types
```

---

## Security Considerations 🔒

### 19. **Path Traversal Risk (LOW)**

While unlikely, ensure duty.md paths are safe:

```python
duty_file = config.workspace_path / "duty.md"
```

User could theoretically do `name: ../../../etc/passwd` (no risk to file creation, but log carefully).

### 20. **No Rate Limiting on Duty Logging**

If a user sends 1000 messages with "water" keyword, all logged. No limits.

**Suggestion:** Add optional rate limiting:

```python
MAX_ENTRIES_PER_HOUR = 50  # Config param
# Check file timestamps before appending
```

---

## Summary Table

| Issue                             | Severity | Type         | Fix Difficulty | Status   |
| --------------------------------- | -------- | ------------ | -------------- | -------- |
| Hydration calc bug (`or True`)    | CRITICAL | Logic        | ⭐ Easy        | ✅ FIXED |
| Hydration false positives (regex) | HIGH     | Logic        | ⭐ Easy        | ✅ FIXED |
| Diary file rewriting              | MEDIUM   | Performance  | ⭐⭐ Medium    | 🔄 TODO  |
| Duplicate duty check              | MEDIUM   | Logic        | ⭐⭐ Medium    | 🔄 TODO  |
| Silent exceptions                 | MEDIUM   | Logging      | ⭐ Easy        | ✅ FIXED |
| Config reloaded per job           | MEDIUM   | Performance  | ⭐ Easy        | ✅ FIXED |
| Timezone support                  | MEDIUM   | Feature      | ⭐⭐ Medium    | 🔄 TODO  |
| Mood detection loose              | LOW      | Logic        | ⭐ Easy        | ✅ FIXED |
| Hydration units regex             | LOW      | Logic        | ⭐ Easy        | ✅ FIXED |
| Regex precompilation              | LOW      | Performance  | ⭐ Easy        | 🔄 TODO  |
| No cron validation                | MEDIUM   | Data Quality | ⭐ Easy        | ✅ FIXED |
| Hydration file reread             | MEDIUM   | Performance  | ⭐⭐ Medium    | 🔄 TODO  |
| Large file performance            | MEDIUM   | Scalability  | ⭐⭐⭐ Hard    | 🔄 TODO  |
| Magic strings                     | LOW      | Quality      | ⭐ Easy        | 🔄 TODO  |
| No type hints                     | LOW      | Quality      | ⭐ Easy        | 🔄 TODO  |
| Path traversal risk               | LOW      | Security     | ⭐ Easy        | 🔄 TODO  |
| Rate limiting                     | LOW      | Security     | ⭐⭐ Medium    | 🔄 TODO  |

---

## Recommended Actions (Priority Order)

### Phase 1: Critical Fixes (Do First)

1. **Fix hydration `or True` bug** (line 394 in loop.py) ✅ DONE
2. **Fix hydration regex** to require units or keywords ✅ DONE
3. **Fix mood detection** to use word boundaries ✅ DONE
4. **Add error logging** to duty.md parsing ✅ DONE

### Phase 2: Optimization (Next Release)

5. Cache workspace path in gateway ✅ DONE
6. Precompile regex patterns 🔄 TODO
7. Add cron expression validation ✅ DONE
8. Fix diary file rewrite inefficiency 🔄 TODO

### Phase 3: Robustness (Future)

9. Add timezone support 🔄 TODO
10. Implement archival for large files 🔄 TODO
11. Add rate limiting 🔄 TODO
12. Improve exception messages 🔄 TODO

---

## Enhancement Opportunities 🚀

### A. CLI Commands & User Interface

- [ ] **Duty Management**: `nanobot duty list/enable/disable/delete <name>`
- [ ] **Duty Viewer**: `nanobot duty show <name>` — Display duty schedule, next run time, last run status
- [ ] **Duty Editor**: `nanobot duty edit <name>` — Interactive editor for duty.md
- [ ] **Duty Validator**: `nanobot duty validate` — Check syntax, cron expressions, and conflicts
- [ ] **Duty Dry-Run**: `nanobot duty run --dry-run <name>` — Test duty without logging

### B. Data Analytics & Reporting

- [ ] **Mood Summary**: `nanobot summary mood --period week` — Show mood trends, avg rating
- [ ] **Hydration Report**: `nanobot summary hydration --period day` — Daily/weekly/monthly totals
- [ ] **Gut Analysis**: `nanobot summary gut --period month` — Food patterns, meal frequency
- [ ] **Diary Digest**: `nanobot summary diary --recent 7` — Last 7 entries
- [ ] **Export Data**: `nanobot export --type mood --format csv/json` — Export to CSV/JSON
- [ ] **Data Dashboard**: Web UI to visualize mood, hydration, trends over time

### C. Data Quality & Persistence

- [ ] **Automatic Archival**: Move old entries to `{file}.archive.md` after N entries
- [ ] **Data Backup**: Auto-backup `workspace/memory/` daily to `~/.nanobot/backups/`
- [ ] **Data Import**: `nanobot import --from csv/json` — Bulk import duty data
- [ ] **Data Validation**: Verify file integrity on startup; fix corrupted entries
- [ ] **Data Encryption**: Optional encryption for sensitive diary/mood entries (AES-256)
- [ ] **Duty History/Audit**: Track when duties were created/modified/deleted

### D. Configuration & Flexibility

- [ ] **YAML Support**: Parse `duty.yaml` in addition to `duty.md` for complex configs
- [ ] **Duty Templates**: Built-in templates (health, fitness, journaling, productivity)
- [ ] **Per-Duty Config**: Add `output_file`, `timezone`, `language` per duty
- [ ] **Duty Groups**: Group related duties and control them together
- [ ] **Duty Aliases**: Create shortcuts (`mood` → `mood-check-full`)
- [ ] **Duty Inheritance**: Allow `extends: base-duty` in block definitions

### E. Notifications & Alerts

- [ ] **Push Notifications**: Send reminders via system notifications (desktop/mobile)
- [ ] **Email Alerts**: Optional email summaries (daily/weekly mood, hydration goals)
- [ ] **SMS Reminders**: Send duty prompts via SMS (if SMS gateway configured)
- [ ] **Missed Duty Alert**: Notify if duty wasn't completed by end of day
- [ ] **Customizable Reminders**: "5 mins before duty" notification

### F. Advanced Features

- [ ] **Multi-User Support**: Different duty tracking per user (shared workspace)
- [ ] **Duty Workflow**: Create multi-step duties (e.g., mood check → follow-up questions)
- [ ] **Conditional Logic**: `if mood < 5 then send_alert()`
- [ ] **Machine Learning**: Mood prediction, hydration optimization suggestions
- [ ] **Integration with Health APIs**: Sync with Apple Health, Google Fit, Fitbit
- [ ] **Duty Scheduling Optimizer**: Auto-suggest best duty times based on patterns

### G. Testing & Quality Assurance

- [ ] **Unit Tests**: Test duty detection (mood, gut, hydration, diary matchers)
- [ ] **Integration Tests**: Full flow from cron trigger → logging → reporting
- [ ] **Performance Tests**: Load test with 1000+ daily entries in memory files
- [ ] **Edge Case Tests**: Test with special characters, emojis, long entries, Unicode
- [ ] **Regression Tests**: Ensure fixes don't break duty functionality
- [ ] **Test Coverage**: Achieve >90% code coverage for duty modules

### H. Performance Optimizations

- [ ] **Regex Pre-compilation**: Move all regexes to module-level constants
- [ ] **File I/O Optimization**: Use memory-mapped files for large duty logs
- [ ] **Caching Layer**: Cache recent entries (e.g., today's mood) in memory
- [ ] **Batch Writing**: Collect multiple duty entries and write in batches
- [ ] **Index Files**: Create `.index.json` for O(1) lookup instead of O(n) file scans
- [ ] **Lazy Loading**: Load memory files on-demand, not at startup

### I. Documentation & Help

- [ ] **In-App Help**: `nanobot duty help <topic>` — Contextual help for duty features
- [ ] **Video Tutorials**: Setup guide, best practices, tips
- [ ] **FAQ Expansion**: Common questions about duty tracking
- [ ] **API Documentation**: Public API for accessing duty data programmatically
- [ ] **Example Configs**: Pre-built `duty.md` examples for different use cases
- [ ] **Troubleshooting Guide**: Common issues and solutions

### J. Security & Privacy

- [ ] **Input Sanitization**: Sanitize diary content before logging (remove PII)
- [ ] **Rate Limiting**: Max N duty entries per hour/day per user
- [ ] **Access Control**: Restrict who can read/modify duty data
- [ ] **Audit Logging**: Track all duty operations (create, update, delete)
- [ ] **Path Validation**: Prevent path traversal attacks in custom duty names
- [ ] **Secure Backup**: Encrypt backups with GPG or similar

### K. Maintenance & DevOps

- [ ] **Docker Support**: Add duty system to Docker image
- [ ] **Monitoring**: Metrics for duty execution success rate, latency
- [ ] **Logging Levels**: `--debug` flag for detailed duty processing logs
- [ ] **Version Migration**: Handle duty.md format changes across nanobot versions
- [ ] **Cleanup Scripts**: Remove old/duplicate entries, optimize file sizes
- [ ] **Health Check**: Verify all duty files are healthy (not corrupted)

### L. Community & Extensibility

- [ ] **Plugin System**: Allow custom duty types via plugins
- [ ] **Custom Detectors**: Let users define regex patterns for duty detection
- [ ] **Webhook Support**: POST duty events to external services
- [ ] **IFTTT Integration**: `if duty(mood) then send_slack_message()`
- [ ] **Community Duty Packs**: Share pre-built duty configs (GitHub/registry)

### M. Bot Personality & Tone

- [ ] **Tone Configuration**: Add `tone:` setting to bot config (friendly, professional, humorous, casual)
- [ ] **Dynamic Tone Switching**: Change bot tone in real-time without restart
- [ ] **Duty Message Customization**: Customize greeting/farewell messages per duty type
- [ ] **Response Templates**: Create tone-specific response templates for duty confirmations
- [ ] **Emoji Support**: Add emoji customization based on tone (professional: none, friendly: 😊)
- [ ] **Personality Traits**: Define bot personality (patience level, verbosity, humor style)
- [ ] **Tone Per-Channel**: Different tones for different channels (Slack vs WhatsApp)
- [ ] **Language Support**: Add multi-language support with tone-aware translations

---

## Testing Checklist

### Unit Tests Needed

```
tests/test_duty_detection.py
  ✓ test_mood_detection_with_rating()
  ✓ test_mood_detection_without_rating()
  ✓ test_gut_detection_with_keywords()
  ✓ test_hydration_parsing_ml_to_liters()
  ✓ test_hydration_parsing_oz_to_liters()
  ✓ test_diary_date_grouping()
  ✓ test_false_positive_prevention()
  ✓ test_edge_cases_unicode_emojis()

tests/test_duty_parsing.py
  ✓ test_parse_valid_duty_md()
  ✓ test_parse_invalid_cron_expression()
  ✓ test_parse_missing_required_fields()
  ✓ test_parse_multiple_cron_expressions()
  ✓ test_parse_duplicate_duty_detection()

tests/test_duty_integration.py
  ✓ test_duty_cron_job_execution()
  ✓ test_duty_logging_to_file()
  ✓ test_duty_delivery_to_channel()
  ✓ test_end_to_end_flow()
```

### Manual Testing

- [ ] Test with real Telegram/WhatsApp delivery
- [ ] Test with years of data in memory files
- [ ] Test concurrent duty executions
- [ ] Test with corrupted duty files (recovery)
- [ ] Test on different timezones
- [ ] Test on Windows/Mac/Linux

---

## Technical Debt

1. **Missing Logging**: Add `logger.debug()` calls for troubleshooting duty issues
2. **Type Hints**: Add full type annotations to `loop.py` and `commands.py` duty functions
3. **Documentation**: Add docstrings to all duty-related functions
4. **Code Organization**: Consider extracting duty logic into separate `nanobot/duty/` module
5. **Constants**: Define duty-related constants in `nanobot/duty/constants.py`
6. **Error Messages**: Improve error messages for users (currently too technical)

---

## Post-MVP Roadmap (v2.0+)

**Q2 2026**: Land Phase 2 & 3 optimizations + CLI improvements
**Q3 2026**: Analytics, reporting, Dashboard UI
**Q4 2026**: Advanced ML features, multi-user support, integrations
**2027+**: Plugin system, community features, enterprise support
