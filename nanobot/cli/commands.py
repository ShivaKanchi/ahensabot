"""CLI commands for nanobot."""

import asyncio
from contextlib import contextmanager, nullcontext

import os
import select
import signal
import sys
from pathlib import Path
from typing import Any

# Force UTF-8 encoding for Windows console
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        # Re-open stdout/stderr with UTF-8 encoding
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import typer
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.formatted_text import ANSI, HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from nanobot import __logo__, __version__
from nanobot.cli.stream import StreamRenderer, ThinkingSpinner
from nanobot.config.paths import get_workspace_path, is_default_workspace
from nanobot.config.schema import Config
from nanobot.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="nanobot",
    context_settings={"help_option_names": ["-h", "--help"]},
    help=f"{__logo__} nanobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios

        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from nanobot.config.paths import get_cli_history_path

    history_file = get_cli_history_path()
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,  # Enter submits (single line mode)
    )


def _make_console() -> Console:
    return Console(file=sys.stdout)


def _render_interactive_ansi(render_fn) -> str:
    """Render Rich output to ANSI so prompt_toolkit can print it safely."""
    ansi_console = Console(
        force_terminal=True,
        color_system=console.color_system or "standard",
        width=console.width,
    )
    with ansi_console.capture() as capture:
        render_fn(ansi_console)
    return capture.get()


def _print_agent_response(
    response: str,
    render_markdown: bool,
    metadata: dict | None = None,
) -> None:
    """Render assistant response with consistent terminal styling."""
    console = _make_console()
    content = response or ""
    body = _response_renderable(content, render_markdown, metadata)
    console.print()
    console.print(f"[cyan]{__logo__} nanobot[/cyan]")
    console.print(body)
    console.print()


def _response_renderable(
    content: str, render_markdown: bool, metadata: dict | None = None
):
    """Render plain-text command output without markdown collapsing newlines."""
    if not render_markdown:
        return Text(content)
    if (metadata or {}).get("render_as") == "text":
        return Text(content)
    return Markdown(content)


async def _print_interactive_line(text: str) -> None:
    """Print async interactive updates with prompt_toolkit-safe Rich styling."""

    def _write() -> None:
        ansi = _render_interactive_ansi(lambda c: c.print(f"  [dim]↳ {text}[/dim]"))
        print_formatted_text(ANSI(ansi), end="")

    await run_in_terminal(_write)


async def _print_interactive_response(
    response: str,
    render_markdown: bool,
    metadata: dict | None = None,
) -> None:
    """Print async interactive replies with prompt_toolkit-safe Rich styling."""

    def _write() -> None:
        content = response or ""
        ansi = _render_interactive_ansi(
            lambda c: (
                c.print(),
                c.print(f"[cyan]{__logo__} nanobot[/cyan]"),
                c.print(_response_renderable(content, render_markdown, metadata)),
                c.print(),
            )
        )
        print_formatted_text(ANSI(ansi), end="")

    await run_in_terminal(_write)


def _print_cli_progress_line(text: str, thinking: ThinkingSpinner | None) -> None:
    """Print a CLI progress line, pausing the spinner if needed."""
    with thinking.pause() if thinking else nullcontext():
        console.print(f"  [dim]↳ {text}[/dim]")


async def _print_interactive_progress_line(
    text: str, thinking: ThinkingSpinner | None
) -> None:
    """Print an interactive progress line, pausing the spinner if needed."""
    with thinking.pause() if thinking else nullcontext():
        await _print_interactive_line(text)


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} nanobot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """nanobot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard(
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Workspace directory"
    ),
    config: str | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
    wizard: bool = typer.Option(False, "--wizard", help="Use interactive wizard"),
):
    """Initialize nanobot configuration and workspace."""
    from nanobot.config.loader import (
        get_config_path,
        load_config,
        save_config,
        set_config_path,
    )
    from nanobot.config.schema import Config

    if config:
        config_path = Path(config).expanduser().resolve()
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")
    else:
        config_path = get_config_path()

    def _apply_workspace_override(loaded: Config) -> Config:
        if workspace:
            loaded.agents.defaults.workspace = workspace
        return loaded

    # Create or update config
    if config_path.exists():
        if wizard:
            config = _apply_workspace_override(load_config(config_path))
        else:
            console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
            console.print(
                "  [bold]y[/bold] = overwrite with defaults (existing values will be lost)"
            )
            console.print(
                "  [bold]N[/bold] = refresh config, keeping existing values and adding new fields"
            )
            if typer.confirm("Overwrite?"):
                config = _apply_workspace_override(Config())
                save_config(config, config_path)
                console.print(
                    f"[green]✓[/green] Config reset to defaults at {config_path}"
                )
            else:
                config = _apply_workspace_override(load_config(config_path))
                save_config(config, config_path)
                console.print(
                    f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)"
                )
    else:
        config = _apply_workspace_override(Config())
        # In wizard mode, don't save yet - the wizard will handle saving if should_save=True
        if not wizard:
            save_config(config, config_path)
            console.print(f"[green]✓[/green] Created config at {config_path}")

    # Run interactive wizard if enabled
    if wizard:
        from nanobot.cli.onboard import run_onboard

        try:
            result = run_onboard(initial_config=config)
            if not result.should_save:
                console.print(
                    "[yellow]Configuration discarded. No changes were saved.[/yellow]"
                )
                return

            config = result.config
            save_config(config, config_path)
            console.print(f"[green]✓[/green] Config saved at {config_path}")
        except Exception as e:
            console.print(f"[red]✗[/red] Error during configuration: {e}")
            console.print(
                "[yellow]Please run 'nanobot onboard' again to complete setup.[/yellow]"
            )
            raise typer.Exit(1)
    _onboard_plugins(config_path)

    # Create workspace, preferring the configured workspace path.
    workspace_path = get_workspace_path(config.workspace_path)
    if not workspace_path.exists():
        workspace_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created workspace at {workspace_path}")

    sync_workspace_templates(workspace_path)

    agent_cmd = 'nanobot agent -m "Hello!"'
    gateway_cmd = "nanobot gateway"
    if config:
        agent_cmd += f" --config {config_path}"
        gateway_cmd += f" --config {config_path}"

    console.print(f"\n{__logo__} nanobot is ready!")
    console.print("\nNext steps:")
    if wizard:
        console.print(f"  1. Chat: [cyan]{agent_cmd}[/cyan]")
        console.print(f"  2. Start gateway: [cyan]{gateway_cmd}[/cyan]")
    else:
        console.print(f"  1. Add your API key to [cyan]{config_path}[/cyan]")
        console.print("     Get one at: https://openrouter.ai/keys")
        console.print(f"  2. Chat: [cyan]{agent_cmd}[/cyan]")
    console.print(
        "\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]"
    )


def _merge_missing_defaults(existing: Any, defaults: Any) -> Any:
    """Recursively fill in missing values from defaults without overwriting user config."""
    if not isinstance(existing, dict) or not isinstance(defaults, dict):
        return existing

    merged = dict(existing)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
        else:
            merged[key] = _merge_missing_defaults(merged[key], value)
    return merged


def _onboard_plugins(config_path: Path) -> None:
    """Inject default config for all discovered channels (built-in + plugins)."""
    import json

    from nanobot.channels.registry import discover_all

    all_channels = discover_all()
    if not all_channels:
        return

    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)

    channels = data.setdefault("channels", {})
    for name, cls in all_channels.items():
        if name not in channels:
            channels[name] = cls.default_config()
        else:
            channels[name] = _merge_missing_defaults(
                channels[name], cls.default_config()
            )

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from nanobot.providers.azure_openai_provider import AzureOpenAIProvider
    from nanobot.providers.base import GenerationSettings
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        provider = OpenAICodexProvider(default_model=model)
    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    elif provider_name == "custom":
        from nanobot.providers.custom_provider import CustomProvider

        provider = CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
            extra_headers=p.extra_headers if p else None,
        )
    # Azure OpenAI: direct Azure OpenAI endpoint with deployment name
    elif provider_name == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            console.print(
                "[red]Error: Azure OpenAI requires api_key and api_base.[/red]"
            )
            console.print(
                "Set them in ~/.nanobot/config.json under providers.azure_openai section"
            )
            console.print("Use the model field to specify the deployment name.")
            raise typer.Exit(1)
        provider = AzureOpenAIProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
        )
    # OpenVINO Model Server: direct OpenAI-compatible endpoint at /v3
    elif provider_name == "ovms":
        from nanobot.providers.custom_provider import CustomProvider

        provider = CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v3",
            default_model=model,
        )
    else:
        from nanobot.providers.litellm_provider import LiteLLMProvider
        from nanobot.providers.registry import find_by_name

        spec = find_by_name(provider_name)
        if (
            not model.startswith("bedrock/")
            and not (p and p.api_key)
            and not (spec and (spec.is_oauth or spec.is_local))
        ):
            console.print("[red]Error: No API key configured.[/red]")
            console.print("Set one in ~/.nanobot/config.json under providers section")
            raise typer.Exit(1)
        provider = LiteLLMProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            provider_name=provider_name,
        )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


def _load_runtime_config(
    config: str | None = None, workspace: str | None = None
) -> Config:
    """Load config and optionally override the active workspace."""
    from nanobot.config.loader import load_config, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    loaded = load_config(config_path)
    _warn_deprecated_config_keys(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def _warn_deprecated_config_keys(config_path: Path | None) -> None:
    """Hint users to remove obsolete keys from their config file."""
    import json
    from nanobot.config.loader import get_config_path

    path = config_path or get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "memoryWindow" in raw.get("agents", {}).get("defaults", {}):
        console.print(
            "[dim]Hint: `memoryWindow` in your config is no longer used "
            "and can be safely removed.[/dim]"
        )


def _migrate_cron_store(config: "Config") -> None:
    """One-time migration: move legacy global cron store into the workspace."""
    from nanobot.config.paths import get_cron_dir

    legacy_path = get_cron_dir() / "jobs.json"
    new_path = config.workspace_path / "cron" / "jobs.json"
    if legacy_path.is_file() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.move(str(legacy_path), str(new_path))


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int | None = typer.Option(None, "--port", "-p", help="Gateway port"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Workspace directory"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config: str | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Start the nanobot gateway."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.heartbeat.service import HeartbeatService
    from nanobot.session.manager import SessionManager

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    config = _load_runtime_config(config, workspace)
    port = port if port is not None else config.gateway.port

    console.print(
        f"{__logo__} Starting nanobot gateway version {__version__} on port {port}..."
    )
    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    # Preserve existing single-workspace installs, but keep custom workspaces clean.
    if is_default_workspace(config.workspace_path):
        _migrate_cron_store(config)

    # Create cron service with workspace-scoped store
    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    # If user provided a `duty.md` in the workspace, parse and auto-install duties
    try:
        duty_file = config.workspace_path / "duty.md"
        if duty_file.exists():
            from nanobot.cron.types import CronSchedule
            from croniter import croniter

            raw = duty_file.read_text(encoding="utf-8")
            # Parse simple blocks separated by blank lines. Each block: key: value lines
            blocks = []
            cur = {}
            for line in raw.splitlines():
                s = line.strip()
                if not s:
                    if cur:
                        blocks.append(cur)
                        cur = {}
                    continue
                if ":" in s:
                    k, v = s.split(":", 1)
                    cur[k.strip().lower()] = v.strip()
            if cur:
                blocks.append(cur)

            existing_jobs = cron._load_store().jobs
            existing_exprs = {(j.name, j.schedule.expr) for j in existing_jobs}

            for idx, b in enumerate(blocks):
                name = b.get("name") or b.get("id") or b.get("kind")
                if not name:
                    logger.warning(f"Duty block #{idx} missing 'name' field, skipping")
                    continue

                # allow multiple cron expressions separated by ','
                cron_expr = b.get("cron") or b.get("schedule")
                prompt_text = b.get("prompt") or b.get("message") or "How are you?"
                duty_kind = b.get("type") or b.get("kind") or name

                if cron_expr:
                    # If user provided multiple cron expressions, create multiple jobs
                    for expr in [e.strip() for e in cron_expr.split(",") if e.strip()]:
                        # Check per-expression to allow same duty at different times
                        if (name, expr) in existing_exprs:
                            logger.debug(
                                f"Duty '{name}' with expr '{expr}' already installed, skipping"
                            )
                            continue

                        # Validate cron expression early
                        try:
                            croniter(expr)  # Validate syntax
                        except (ValueError, KeyError) as e:
                            logger.error(
                                f"Invalid cron expression '{expr}' in duty '{name}': {e}"
                            )
                            continue

                        job = cron.add_job(
                            name=name,
                            schedule=CronSchedule(kind="cron", expr=expr),
                            message=prompt_text,
                            deliver=False,
                        )
                        # mark payload with duty kind so handler knows how to log replies
                        try:
                            job.payload.kind = f"duty:{duty_kind}"
                        except Exception:
                            pass
                else:
                    # no schedule -> skip automated job but log it
                    logger.debug(f"Duty '{name}' has no cron schedule, skipping")
    except FileNotFoundError:
        pass  # duty.md doesn't exist, no duties to install
    except Exception as e:
        logger.error(f"Failed to parse duty.md: {e}")

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent.

        Duty jobs (payload.kind startswith 'duty:') publish the prompt out so the
        user/master can reply. Replies are captured by incoming message processing
        and logged to the appropriate files. Other jobs run through the agent.
        """
        try:
            payload_kind = job.payload.kind if job.payload else None
        except Exception:
            payload_kind = None

        # If this is a duty job, publish the prompt (or log scheduled prompt)
        if isinstance(payload_kind, str) and payload_kind.startswith("duty:"):
            # Publish prompt to configured channel/to when available
            if job.payload.deliver and job.payload.to:
                from nanobot.bus.events import OutboundMessage

                await bus.publish_outbound(
                    OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=job.payload.message or "",
                    )
                )
            else:
                # No external delivery configured — record that a prompt was scheduled
                # Use cached workspace path instead of reloading config
                try:
                    duty_dir = config.workspace_path / "memory"
                    duty_dir.mkdir(parents=True, exist_ok=True)
                    report_file = duty_dir / "dutyreport.md"
                    ts = datetime.utcnow().isoformat() + "Z"
                    entry = f"- {ts} | job:{job.name} | prompt: {job.payload.message or ''}\n"
                    with report_file.open("a", encoding="utf-8") as f:
                        f.write(entry)
                except Exception as e:
                    logger.error(f"Failed to log duty prompt for job '{job.name}': {e}")
            return None

        # Non-duty: run through the agent as before
        from nanobot.agent.tools.message import MessageTool
        from nanobot.utils.evaluator import evaluate_response

        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )

        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            resp = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        response = resp.content if resp else ""

        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            should_notify = await evaluate_response(
                response,
                job.payload.message,
                provider,
                agent.model,
            )
            if should_notify:
                from nanobot.bus.events import OutboundMessage

                await bus.publish_outbound(
                    OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=response,
                    )
                )
        return response

    cron.on_job = on_cron_job

    # Create channel manager
    channels = ChannelManager(config, bus)

    def _pick_heartbeat_target() -> tuple[str, str]:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        enabled = set(channels.enabled_channels)
        # Prefer the most recently updated non-internal session on an enabled channel.
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        # Fallback keeps prior behavior but remains explicit.
        return "cli", "direct"

    # Create heartbeat service
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        channel, chat_id = _pick_heartbeat_target()

        async def _silent(*_args, **_kwargs):
            pass

        resp = await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

        # Keep a small tail of heartbeat history so the loop stays bounded
        # without losing all short-term context between runs.
        session = agent.sessions.get_or_create("heartbeat")
        session.retain_recent_legal_suffix(hb_cfg.keep_recent_messages)
        agent.sessions.save(session)

        return resp.content if resp else ""

    async def on_heartbeat_notify(response: str) -> None:
        """Deliver a heartbeat response to the user's channel."""
        from nanobot.bus.events import OutboundMessage

        channel, chat_id = _pick_heartbeat_target()
        if channel == "cli":
            return  # No external channel available to deliver to
        await bus.publish_outbound(
            OutboundMessage(channel=channel, chat_id=chat_id, content=response)
        )

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    if channels.enabled_channels:
        console.print(
            f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}"
        )
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    # Create web server
    server = WebServer(cron_service=cron, channel_manager=channels, port=port)

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await server.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        except Exception:
            import traceback

            console.print("\n[red]Error: Gateway crashed unexpectedly[/red]")
            console.print(traceback.format_exc())
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(
        None, "--message", "-m", help="Message to send to the agent"
    ),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(
        None, "--workspace", "-w", help="Workspace directory"
    ),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(
        False, "--logs/--no-logs", help="Show nanobot runtime logs during chat"
    ),
):
    """Interact with the agent directly."""
    from loguru import logger

    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.cron.service import CronService

    config = _load_runtime_config(config, workspace)
    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)

    # Preserve existing single-workspace installs, but keep custom workspaces clean.
    if is_default_workspace(config.workspace_path):
        _migrate_cron_store(config)

    # Create cron service with workspace-scoped store
    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("nanobot")
    else:
        logger.disable("nanobot")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        context_window_tokens=config.agents.defaults.context_window_tokens,
        web_search_config=config.tools.web.search,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    # Shared reference for progress callbacks
    _thinking: ThinkingSpinner | None = None

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        ch = agent_loop.channels_config
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        _print_cli_progress_line(content, _thinking)

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            renderer = StreamRenderer(render_markdown=markdown)
            response = await agent_loop.process_direct(
                message,
                session_id,
                on_progress=_cli_progress,
                on_stream=renderer.on_delta,
                on_stream_end=renderer.on_end,
            )
            if not renderer.streamed:
                await renderer.close()
                _print_agent_response(
                    response.content if response else "",
                    render_markdown=markdown,
                    metadata=response.metadata if response else None,
                )
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from nanobot.bus.events import InboundMessage

        _init_prompt_session()
        console.print(
            f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
        )

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            _restore_terminal()
            console.print(f"\nReceived {sig_name}, goodbye!")
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        # SIGHUP is not available on Windows
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, _handle_signal)
        # Ignore SIGPIPE to prevent silent process termination when writing to closed pipes
        # SIGPIPE is not available on Windows
        if hasattr(signal, "SIGPIPE"):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[tuple[str, dict]] = []
            renderer: StreamRenderer | None = None

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(
                            bus.consume_outbound(), timeout=1.0
                        )

                        if msg.metadata.get("_stream_delta"):
                            if renderer:
                                await renderer.on_delta(msg.content)
                            continue
                        if msg.metadata.get("_stream_end"):
                            if renderer:
                                await renderer.on_end(
                                    resuming=msg.metadata.get("_resuming", False),
                                )
                            continue
                        if msg.metadata.get("_streamed"):
                            turn_done.set()
                            continue

                        if msg.metadata.get("_progress"):
                            is_tool_hint = msg.metadata.get("_tool_hint", False)
                            ch = agent_loop.channels_config
                            if ch and is_tool_hint and not ch.send_tool_hints:
                                pass
                            elif ch and not is_tool_hint and not ch.send_progress:
                                pass
                            else:
                                await _print_interactive_progress_line(
                                    msg.content, _thinking
                                )
                            continue

                        if not turn_done.is_set():
                            if msg.content:
                                turn_response.append(
                                    (msg.content, dict(msg.metadata or {}))
                                )
                            turn_done.set()
                        elif msg.content:
                            await _print_interactive_response(
                                msg.content,
                                render_markdown=markdown,
                                metadata=msg.metadata,
                            )

                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()
                        renderer = StreamRenderer(render_markdown=markdown)

                        await bus.publish_inbound(
                            InboundMessage(
                                channel=cli_channel,
                                sender_id="user",
                                chat_id=cli_chat_id,
                                content=user_input,
                                metadata={"_wants_stream": True},
                            )
                        )

                        await turn_done.wait()

                        if turn_response:
                            content, meta = turn_response[0]
                            if content and not meta.get("_streamed"):
                                if renderer:
                                    await renderer.close()
                                _print_agent_response(
                                    content,
                                    render_markdown=markdown,
                                    metadata=meta,
                                )
                        elif renderer and not renderer.streamed:
                            await renderer.close()
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanobot.channels.registry import discover_all
    from nanobot.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")

    for name, cls in sorted(discover_all().items()):
        section = getattr(config.channels, name, None)
        if section is None:
            enabled = False
        elif isinstance(section, dict):
            enabled = section.get("enabled", False)
        else:
            enabled = getattr(section, "enabled", False)
        table.add_row(
            cls.display_name,
            "[green]\u2713[/green]" if enabled else "[dim]\u2717[/dim]",
        )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    from nanobot.config.paths import get_bridge_install_dir

    user_bridge = get_bridge_install_dir()

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    npm_path = shutil.which("npm")
    if not npm_path:
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanobot/bridge (installed)
    src_bridge = (
        Path(__file__).parent.parent.parent / "bridge"
    )  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall nanobot")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(
        source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist")
    )

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(
            [npm_path, "install"], cwd=user_bridge, check=True, capture_output=True
        )

        console.print("  Building...")
        subprocess.run(
            [npm_path, "run", "build"], cwd=user_bridge, check=True, capture_output=True
        )

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login(
    channel_name: str = typer.Argument(
        ..., help="Channel name (e.g. weixin, whatsapp)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-authentication even if already logged in"
    ),
):
    """Authenticate with a channel via QR code or other interactive login."""
    from nanobot.channels.registry import discover_all
    from nanobot.config.loader import load_config

    config = load_config()
    channel_cfg = getattr(config.channels, channel_name, None) or {}

    # Validate channel exists
    all_channels = discover_all()
    if channel_name not in all_channels:
        available = ", ".join(all_channels.keys())
        console.print(
            f"[red]Unknown channel: {channel_name}[/red]  Available: {available}"
        )
        raise typer.Exit(1)

    console.print(f"{__logo__} {all_channels[channel_name].display_name} Login\n")

    channel_cls = all_channels[channel_name]
    channel = channel_cls(channel_cfg, bus=None)

    success = asyncio.run(channel.login(force=force))

    if not success:
        raise typer.Exit(1)


# ============================================================================
# Plugin Commands
# ============================================================================

plugins_app = typer.Typer(help="Manage channel plugins")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list():
    """List all discovered channels (built-in and plugins)."""
    from nanobot.channels.registry import discover_all, discover_channel_names
    from nanobot.config.loader import load_config

    config = load_config()
    builtin_names = set(discover_channel_names())
    all_channels = discover_all()

    table = Table(title="Channel Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="magenta")
    table.add_column("Enabled", style="green")

    for name in sorted(all_channels):
        cls = all_channels[name]
        source = "builtin" if name in builtin_names else "plugin"
        section = getattr(config.channels, name, None)
        if section is None:
            enabled = False
        elif isinstance(section, dict):
            enabled = section.get("enabled", False)
        else:
            enabled = getattr(section, "enabled", False)
        table.add_row(
            cls.display_name,
            source,
            "[green]yes[/green]" if enabled else "[dim]no[/dim]",
        )

    console.print(table)


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanobot status."""
    from nanobot.config.loader import load_config, get_config_path

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanobot Status\n")

    console.print(
        f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}"
    )
    console.print(
        f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}"
    )

    if config_path.exists():
        from nanobot.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(
                    f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}"
                )


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn

    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(
        ..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"
    ),
):
    """Authenticate with an OAuth provider."""
    from nanobot.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(
            f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}"
        )
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive

        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(
            f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]"
        )
    except ImportError:
        console.print(
            "[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]"
        )
        raise typer.Exit(1)


@_register_login("github_copilot")
def _login_github_copilot() -> None:
    import asyncio

    console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

    async def _trigger():
        from litellm import acompletion

        await acompletion(
            model="github_copilot/gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )

    try:
        asyncio.run(_trigger())
        console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()


#

# """CLI commands for nanobot."""

# import asyncio
# import os
# import signal
# from pathlib import Path
# import select
# import sys
# from datetime import datetime

# import typer
# from rich.console import Console
# from rich.markdown import Markdown
# from rich.table import Table
# from rich.text import Text
# from loguru import logger

# from prompt_toolkit import PromptSession
# from prompt_toolkit.formatted_text import HTML
# from prompt_toolkit.history import FileHistory
# from prompt_toolkit.patch_stdout import patch_stdout

# from nanobot import __version__, __logo__
# from nanobot.config.schema import Config

# app = typer.Typer(
#     name="nanobot",
#     help=f"{__logo__} nanobot - Personal AI Assistant",
#     no_args_is_help=True,
# )

# console = Console()
# EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# # ---------------------------------------------------------------------------
# # CLI input: prompt_toolkit for editing, paste, history, and display
# # ---------------------------------------------------------------------------

# _PROMPT_SESSION: PromptSession | None = None
# _SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


# def _flush_pending_tty_input() -> None:
#     """Drop unread keypresses typed while the model was generating output."""
#     try:
#         fd = sys.stdin.fileno()
#         if not os.isatty(fd):
#             return
#     except Exception:
#         return

#     try:
#         import termios

#         termios.tcflush(fd, termios.TCIFLUSH)
#         return
#     except Exception:
#         pass

#     try:
#         while True:
#             ready, _, _ = select.select([fd], [], [], 0)
#             if not ready:
#                 break
#             if not os.read(fd, 4096):
#                 break
#     except Exception:
#         return


# def _restore_terminal() -> None:
#     """Restore terminal to its original state (echo, line buffering, etc.)."""
#     if _SAVED_TERM_ATTRS is None:
#         return
#     try:
#         import termios

#         termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
#     except Exception:
#         pass


# def _init_prompt_session() -> None:
#     """Create the prompt_toolkit session with persistent file history."""
#     global _PROMPT_SESSION, _SAVED_TERM_ATTRS

#     # Save terminal state so we can restore it on exit
#     try:
#         import termios

#         _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
#     except Exception:
#         pass

#     history_file = Path.home() / ".nanobot" / "history" / "cli_history"
#     history_file.parent.mkdir(parents=True, exist_ok=True)

#     _PROMPT_SESSION = PromptSession(
#         history=FileHistory(str(history_file)),
#         enable_open_in_editor=False,
#         multiline=False,  # Enter submits (single line mode)
#     )


# def _print_agent_response(response: str, render_markdown: bool) -> None:
#     """Render assistant response with consistent terminal styling."""
#     content = response or ""
#     body = Markdown(content) if render_markdown else Text(content)
#     console.print()
#     console.print(f"[cyan]{__logo__} nanobot[/cyan]")
#     console.print(body)
#     console.print()


# def _is_exit_command(command: str) -> bool:
#     """Return True when input should end interactive chat."""
#     return command.lower() in EXIT_COMMANDS


# async def _read_interactive_input_async() -> str:
#     """Read user input using prompt_toolkit (handles paste, history, display).

#     prompt_toolkit natively handles:
#     - Multiline paste (bracketed paste mode)
#     - History navigation (up/down arrows)
#     - Clean display (no ghost characters or artifacts)
#     """
#     if _PROMPT_SESSION is None:
#         raise RuntimeError("Call _init_prompt_session() first")
#     try:
#         with patch_stdout():
#             return await _PROMPT_SESSION.prompt_async(
#                 HTML("<b fg='ansiblue'>You:</b> "),
#             )
#     except EOFError as exc:
#         raise KeyboardInterrupt from exc


# def version_callback(value: bool):
#     if value:
#         console.print(f"{__logo__} nanobot v{__version__}")
#         raise typer.Exit()


# @app.callback()
# def main(
#     version: bool = typer.Option(
#         None, "--version", "-v", callback=version_callback, is_eager=True
#     ),
# ):
#     """nanobot - Personal AI Assistant."""
#     pass


# # ============================================================================
# # Onboard / Setup
# # ============================================================================


# @app.command()
# def onboard():
#     """Initialize nanobot configuration and workspace."""
#     from nanobot.config.loader import get_config_path, load_config, save_config
#     from nanobot.config.schema import Config
#     from nanobot.utils.helpers import get_workspace_path

#     config_path = get_config_path()

#     if config_path.exists():
#         console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
#         console.print(
#             "  [bold]y[/bold] = overwrite with defaults (existing values will be lost)"
#         )
#         console.print(
#             "  [bold]N[/bold] = refresh config, keeping existing values and adding new fields"
#         )
#         if typer.confirm("Overwrite?"):
#             config = Config()
#             save_config(config)
#             console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
#         else:
#             config = load_config()
#             save_config(config)
#             console.print(
#                 f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)"
#             )
#     else:
#         save_config(Config())
#         console.print(f"[green]✓[/green] Created config at {config_path}")

#     # Create workspace
#     workspace = get_workspace_path()

#     if not workspace.exists():
#         workspace.mkdir(parents=True, exist_ok=True)
#         console.print(f"[green]✓[/green] Created workspace at {workspace}")

#     # Create default bootstrap files
#     _create_workspace_templates(workspace)

#     console.print(f"\n{__logo__} nanobot is ready!")
#     console.print("\nNext steps:")
#     console.print("  1. Add your API key to [cyan]~/.nanobot/config.json[/cyan]")
#     console.print("     Get one at: https://openrouter.ai/keys")
#     console.print('  2. Chat: [cyan]nanobot agent -m "Hello!"[/cyan]')
#     console.print(
#         "\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]"
#     )


# def _create_workspace_templates(workspace: Path):
#     """Create default workspace template files from bundled templates."""
#     from importlib.resources import files as pkg_files

#     templates_dir = pkg_files("nanobot") / "templates"

#     for item in templates_dir.iterdir():
#         if not item.name.endswith(".md"):
#             continue
#         dest = workspace / item.name
#         if not dest.exists():
#             dest.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
#             console.print(f"  [dim]Created {item.name}[/dim]")

#     memory_dir = workspace / "memory"
#     memory_dir.mkdir(exist_ok=True)

#     memory_template = templates_dir / "memory" / "MEMORY.md"
#     memory_file = memory_dir / "MEMORY.md"
#     if not memory_file.exists():
#         memory_file.write_text(
#             memory_template.read_text(encoding="utf-8"), encoding="utf-8"
#         )
#         console.print("  [dim]Created memory/MEMORY.md[/dim]")

#     history_file = memory_dir / "HISTORY.md"
#     if not history_file.exists():
#         history_file.write_text("", encoding="utf-8")
#         console.print("  [dim]Created memory/HISTORY.md[/dim]")

#     (workspace / "skills").mkdir(exist_ok=True)


# def _make_provider(config: Config):
#     """Create the appropriate LLM provider from config."""
#     from nanobot.providers.litellm_provider import LiteLLMProvider
#     from nanobot.providers.openai_codex_provider import OpenAICodexProvider
#     from nanobot.providers.custom_provider import CustomProvider

#     model = config.agents.defaults.model
#     provider_name = config.get_provider_name(model)
#     p = config.get_provider(model)

#     # OpenAI Codex (OAuth)
#     if provider_name == "openai_codex" or model.startswith("openai-codex/"):
#         return OpenAICodexProvider(default_model=model)

#     # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
#     if provider_name == "custom":
#         return CustomProvider(
#             api_key=p.api_key if p else "no-key",
#             api_base=config.get_api_base(model) or "http://localhost:8000/v1",
#             default_model=model,
#         )

#     from nanobot.providers.registry import find_by_name

#     spec = find_by_name(provider_name)
#     if (
#         (not p or not p.api_key)
#         and (not spec or not spec.is_oauth)
#         and not any(
#             model.startswith(prefix)
#             for prefix in ("bedrock/", "ollama/", "hosted_vllm/")
#         )
#     ):
#         console.print("[red]Error: No API key configured.[/red]")
#         console.print("Set one in ~/.nanobot/config.json under providers section")
#         raise typer.Exit(1)

#     return LiteLLMProvider(
#         api_key=p.api_key if p else None,
#         api_base=config.get_api_base(model),
#         default_model=model,
#         extra_headers=p.extra_headers if p else None,
#         provider_name=provider_name,
#     )


# # ============================================================================
# # Gateway / Server
# # ============================================================================


# @app.command()
# def gateway(
#     port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
#     verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
# ):
#     """Start the nanobot gateway."""
#     from nanobot.config.loader import load_config, get_data_dir
#     from nanobot.bus.queue import MessageBus
#     from nanobot.agent.loop import AgentLoop
#     from nanobot.channels.manager import ChannelManager
#     from nanobot.session.manager import SessionManager
#     from nanobot.cron.service import CronService
#     from nanobot.cron.types import CronJob
#     from nanobot.heartbeat.service import HeartbeatService
#     from nanobot.server import WebServer

#     if verbose:
#         import logging

#         logging.basicConfig(level=logging.DEBUG)

#     from nanobot.config.loader import get_config_path as _get_config_path

#     config_path = _get_config_path()
#     console.print(f"{__logo__} Starting nanobot gateway on port {port}...")
#     console.print(f"[dim]Config: {config_path.resolve()}[/dim]")

#     config = load_config()
#     bus = MessageBus()
#     provider = _make_provider(config)
#     session_manager = SessionManager(config.workspace_path)

#     # Create cron service first (callback set after agent creation)
#     cron_store_path = get_data_dir() / "cron" / "jobs.json"
#     cron = CronService(cron_store_path)
#     # If user provided a `duty.md` in the workspace, parse and auto-install duties
#     try:
#         duty_file = config.workspace_path / "duty.md"
#         if duty_file.exists():
#             from nanobot.cron.types import CronSchedule
#             from croniter import croniter

#             raw = duty_file.read_text(encoding="utf-8")
#             # Parse simple blocks separated by blank lines. Each block: key: value lines
#             blocks = []
#             cur = {}
#             for line in raw.splitlines():
#                 s = line.strip()
#                 if not s:
#                     if cur:
#                         blocks.append(cur)
#                         cur = {}
#                     continue
#                 if ":" in s:
#                     k, v = s.split(":", 1)
#                     cur[k.strip().lower()] = v.strip()
#             if cur:
#                 blocks.append(cur)

#             existing_jobs = cron._load_store().jobs
#             existing_exprs = {(j.name, j.schedule.expr) for j in existing_jobs}

#             for idx, b in enumerate(blocks):
#                 name = b.get("name") or b.get("id") or b.get("kind")
#                 if not name:
#                     logger.warning(f"Duty block #{idx} missing 'name' field, skipping")
#                     continue

#                 # allow multiple cron expressions separated by ','
#                 cron_expr = b.get("cron") or b.get("schedule")
#                 prompt_text = b.get("prompt") or b.get("message") or "How are you?"
#                 duty_kind = b.get("type") or b.get("kind") or name

#                 if cron_expr:
#                     # If user provided multiple cron expressions, create multiple jobs
#                     for expr in [e.strip() for e in cron_expr.split(",") if e.strip()]:
#                         # Check per-expression to allow same duty at different times
#                         if (name, expr) in existing_exprs:
#                             logger.debug(
#                                 f"Duty '{name}' with expr '{expr}' already installed, skipping"
#                             )
#                             continue

#                         # Validate cron expression early
#                         try:
#                             croniter(expr)  # Validate syntax
#                         except (ValueError, KeyError) as e:
#                             logger.error(
#                                 f"Invalid cron expression '{expr}' in duty '{name}': {e}"
#                             )
#                             continue

#                         job = cron.add_job(
#                             name=name,
#                             schedule=CronSchedule(kind="cron", expr=expr),
#                             message=prompt_text,
#                             deliver=False,
#                         )
#                         # mark payload with duty kind so handler knows how to log replies
#                         try:
#                             job.payload.kind = f"duty:{duty_kind}"
#                         except Exception:
#                             pass
#                 else:
#                     # no schedule -> skip automated job but log it
#                     logger.debug(f"Duty '{name}' has no cron schedule, skipping")
#     except FileNotFoundError:
#         pass  # duty.md doesn't exist, no duties to install
#     except Exception as e:
#         logger.error(f"Failed to parse duty.md: {e}")

#     # Create agent with cron service
#     agent = AgentLoop(
#         bus=bus,
#         provider=provider,
#         workspace=config.workspace_path,
#         model=config.agents.defaults.model,
#         temperature=config.agents.defaults.temperature,
#         max_tokens=config.agents.defaults.max_tokens,
#         max_iterations=config.agents.defaults.max_tool_iterations,
#         memory_window=config.agents.defaults.memory_window,
#         brave_api_key=config.tools.web.search.api_key or None,
#         web_proxy=config.tools.web.proxy or None,
#         exec_config=config.tools.exec,
#         cron_service=cron,
#         restrict_to_workspace=config.tools.restrict_to_workspace,
#         session_manager=session_manager,
#         mcp_servers=config.tools.mcp_servers,
#         channels_config=config.channels,
#     )

#     # Set cron callback (needs agent)
#     async def on_cron_job(job: CronJob) -> str | None:
#         """Execute a cron job through the agent.

#         Duty jobs (payload.kind startswith 'duty:') publish the prompt out so the
#         user/master can reply. Replies are captured by incoming message processing
#         and logged to the appropriate files. Other jobs run through the agent.
#         """
#         try:
#             payload_kind = job.payload.kind if job.payload else None
#         except Exception:
#             payload_kind = None

#         # If this is a duty job, publish the prompt (or log scheduled prompt)
#         if isinstance(payload_kind, str) and payload_kind.startswith("duty:"):
#             # Publish prompt to configured channel/to when available
#             if job.payload.deliver and job.payload.to:
#                 from nanobot.bus.events import OutboundMessage

#                 await bus.publish_outbound(
#                     OutboundMessage(
#                         channel=job.payload.channel or "cli",
#                         chat_id=job.payload.to,
#                         content=job.payload.message or "",
#                     )
#                 )
#             else:
#                 # No external delivery configured — record that a prompt was scheduled
#                 # Use cached workspace path instead of reloading config
#                 try:
#                     duty_dir = config.workspace_path / "memory"
#                     duty_dir.mkdir(parents=True, exist_ok=True)
#                     report_file = duty_dir / "dutyreport.md"
#                     ts = datetime.utcnow().isoformat() + "Z"
#                     entry = f"- {ts} | job:{job.name} | prompt: {job.payload.message or ''}\n"
#                     with report_file.open("a", encoding="utf-8") as f:
#                         f.write(entry)
#                 except Exception as e:
#                     logger.error(f"Failed to log duty prompt for job '{job.name}': {e}")
#             return None

#         # Non-duty: run through the agent as before
#         from nanobot.agent.tools.message import MessageTool

#         reminder_note = (
#             "[Scheduled Task] Timer finished.\n\n"
#             f"Task '{job.name}' has been triggered.\n"
#             f"Scheduled instruction: {job.payload.message}"
#         )

#         response = await agent.process_direct(
#             reminder_note,
#             session_key=f"cron:{job.id}",
#             channel=job.payload.channel or "cli",
#             chat_id=job.payload.to or "direct",
#         )

#         message_tool = agent.tools.get("message")
#         if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
#             return response

#         if job.payload.deliver and job.payload.to and response:
#             from nanobot.bus.events import OutboundMessage

#             await bus.publish_outbound(
#                 OutboundMessage(
#                     channel=job.payload.channel or "cli",
#                     chat_id=job.payload.to,
#                     content=response or "",
#                 )
#             )
#         return response

#     cron.on_job = on_cron_job

#     # Create channel manager
#     channels = ChannelManager(config, bus)

#     def _pick_heartbeat_target() -> tuple[str, str]:
#         """Pick a routable channel/chat target for heartbeat-triggered messages."""
#         enabled = set(channels.enabled_channels)
#         # Prefer the most recently updated non-internal session on an enabled channel.
#         for item in session_manager.list_sessions():
#             key = item.get("key") or ""
#             if ":" not in key:
#                 continue
#             channel, chat_id = key.split(":", 1)
#             if channel in {"cli", "system"}:
#                 continue
#             if channel in enabled and chat_id:
#                 return channel, chat_id
#         # Fallback keeps prior behavior but remains explicit.
#         return "cli", "direct"

#     # Create heartbeat service
#     async def on_heartbeat_execute(tasks: str) -> str:
#         """Phase 2: execute heartbeat tasks through the full agent loop."""
#         channel, chat_id = _pick_heartbeat_target()

#         async def _silent(*_args, **_kwargs):
#             pass

#         return await agent.process_direct(
#             tasks,
#             session_key="heartbeat",
#             channel=channel,
#             chat_id=chat_id,
#             on_progress=_silent,
#         )

#     async def on_heartbeat_notify(response: str) -> None:
#         """Deliver a heartbeat response to the user's channel."""
#         from nanobot.bus.events import OutboundMessage

#         channel, chat_id = _pick_heartbeat_target()
#         if channel == "cli":
#             return  # No external channel available to deliver to
#         await bus.publish_outbound(
#             OutboundMessage(channel=channel, chat_id=chat_id, content=response)
#         )

#     hb_cfg = config.gateway.heartbeat
#     heartbeat = HeartbeatService(
#         workspace=config.workspace_path,
#         provider=provider,
#         model=agent.model,
#         on_execute=on_heartbeat_execute,
#         on_notify=on_heartbeat_notify,
#         interval_s=hb_cfg.interval_s,
#         enabled=hb_cfg.enabled,
#     )

#     if channels.enabled_channels:
#         console.print(
#             f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}"
#         )
#     else:
#         console.print("[yellow]Warning: No channels enabled[/yellow]")

#     # Create web server
#     server = WebServer(cron_service=cron, channel_manager=channels, port=port)

#     cron_status = cron.status()
#     if cron_status["jobs"] > 0:
#         console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

#     console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")

#     async def run():
#         try:
#             await cron.start()
#             await heartbeat.start()
#             await server.start()
#             await asyncio.gather(
#                 agent.run(),
#                 channels.start_all(),
#             )
#         except KeyboardInterrupt:
#             console.print("\nShutting down...")
#         finally:
#             await agent.close_mcp()
#             heartbeat.stop()
#             cron.stop()
#             agent.stop()
#             await channels.stop_all()

#     asyncio.run(run())


# # ============================================================================
# # Agent Commands
# # ============================================================================


# @app.command()
# def agent(
#     message: str = typer.Option(
#         None, "--message", "-m", help="Message to send to the agent"
#     ),
#     session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
#     markdown: bool = typer.Option(
#         True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
#     ),
#     logs: bool = typer.Option(
#         False, "--logs/--no-logs", help="Show nanobot runtime logs during chat"
#     ),
# ):
#     """Interact with the agent directly."""
#     from nanobot.config.loader import load_config, get_data_dir
#     from nanobot.bus.queue import MessageBus
#     from nanobot.agent.loop import AgentLoop
#     from nanobot.cron.service import CronService
#     from loguru import logger

#     config = load_config()

#     bus = MessageBus()
#     provider = _make_provider(config)

#     # Create cron service for tool usage (no callback needed for CLI unless running)
#     cron_store_path = get_data_dir() / "cron" / "jobs.json"
#     cron = CronService(cron_store_path)

#     if logs:
#         logger.enable("nanobot")
#     else:
#         logger.disable("nanobot")

#     agent_loop = AgentLoop(
#         bus=bus,
#         provider=provider,
#         workspace=config.workspace_path,
#         model=config.agents.defaults.model,
#         temperature=config.agents.defaults.temperature,
#         max_tokens=config.agents.defaults.max_tokens,
#         max_iterations=config.agents.defaults.max_tool_iterations,
#         memory_window=config.agents.defaults.memory_window,
#         brave_api_key=config.tools.web.search.api_key or None,
#         web_proxy=config.tools.web.proxy or None,
#         exec_config=config.tools.exec,
#         cron_service=cron,
#         restrict_to_workspace=config.tools.restrict_to_workspace,
#         mcp_servers=config.tools.mcp_servers,
#         channels_config=config.channels,
#     )

#     # Show spinner when logs are off (no output to miss); skip when logs are on
#     def _thinking_ctx():
#         if logs:
#             from contextlib import nullcontext

#             return nullcontext()
#         # Animated spinner is safe to use with prompt_toolkit input handling
#         return console.status("[dim]nanobot is thinking...[/dim]", spinner="dots")

#     async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
#         ch = agent_loop.channels_config
#         if ch and tool_hint and not ch.send_tool_hints:
#             return
#         if ch and not tool_hint and not ch.send_progress:
#             return
#         console.print(f"  [dim]↳ {content}[/dim]")

#     if message:
#         # Single message mode — direct call, no bus needed
#         async def run_once():
#             with _thinking_ctx():
#                 response = await agent_loop.process_direct(
#                     message, session_id, on_progress=_cli_progress
#                 )
#             _print_agent_response(response, render_markdown=markdown)
#             await agent_loop.close_mcp()

#         asyncio.run(run_once())
#     else:
#         # Interactive mode — route through bus like other channels
#         from nanobot.bus.events import InboundMessage

#         _init_prompt_session()
#         console.print(
#             f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
#         )

#         if ":" in session_id:
#             cli_channel, cli_chat_id = session_id.split(":", 1)
#         else:
#             cli_channel, cli_chat_id = "cli", session_id

#         def _exit_on_sigint(signum, frame):
#             _restore_terminal()
#             console.print("\nGoodbye!")
#             os._exit(0)

#         signal.signal(signal.SIGINT, _exit_on_sigint)

#         async def run_interactive():
#             bus_task = asyncio.create_task(agent_loop.run())
#             turn_done = asyncio.Event()
#             turn_done.set()
#             turn_response: list[str] = []

#             async def _consume_outbound():
#                 while True:
#                     try:
#                         msg = await asyncio.wait_for(
#                             bus.consume_outbound(), timeout=1.0
#                         )
#                         if msg.metadata.get("_progress"):
#                             is_tool_hint = msg.metadata.get("_tool_hint", False)
#                             ch = agent_loop.channels_config
#                             if ch and is_tool_hint and not ch.send_tool_hints:
#                                 pass
#                             elif ch and not is_tool_hint and not ch.send_progress:
#                                 pass
#                             else:
#                                 console.print(f"  [dim]↳ {msg.content}[/dim]")
#                         elif not turn_done.is_set():
#                             if msg.content:
#                                 turn_response.append(msg.content)
#                             turn_done.set()
#                         elif msg.content:
#                             console.print()
#                             _print_agent_response(msg.content, render_markdown=markdown)
#                     except asyncio.TimeoutError:
#                         continue
#                     except asyncio.CancelledError:
#                         break

#             outbound_task = asyncio.create_task(_consume_outbound())

#             try:
#                 while True:
#                     try:
#                         _flush_pending_tty_input()
#                         user_input = await _read_interactive_input_async()
#                         command = user_input.strip()
#                         if not command:
#                             continue

#                         if _is_exit_command(command):
#                             _restore_terminal()
#                             console.print("\nGoodbye!")
#                             break

#                         turn_done.clear()
#                         turn_response.clear()

#                         await bus.publish_inbound(
#                             InboundMessage(
#                                 channel=cli_channel,
#                                 sender_id="user",
#                                 chat_id=cli_chat_id,
#                                 content=user_input,
#                             )
#                         )

#                         with _thinking_ctx():
#                             await turn_done.wait()

#                         if turn_response:
#                             _print_agent_response(
#                                 turn_response[0], render_markdown=markdown
#                             )
#                     except KeyboardInterrupt:
#                         _restore_terminal()
#                         console.print("\nGoodbye!")
#                         break
#                     except EOFError:
#                         _restore_terminal()
#                         console.print("\nGoodbye!")
#                         break
#             finally:
#                 agent_loop.stop()
#                 outbound_task.cancel()
#                 await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
#                 await agent_loop.close_mcp()

#         asyncio.run(run_interactive())


# # ============================================================================
# # Channel Commands
# # ============================================================================


# channels_app = typer.Typer(help="Manage channels")
# app.add_typer(channels_app, name="channels")


# @channels_app.command("status")
# def channels_status():
#     """Show channel status."""
#     from nanobot.config.loader import load_config

#     config = load_config()

#     table = Table(title="Channel Status")
#     table.add_column("Channel", style="cyan")
#     table.add_column("Enabled", style="green")
#     table.add_column("Configuration", style="yellow")

#     # WhatsApp
#     wa = config.channels.whatsapp
#     table.add_row("WhatsApp", "✓" if wa.enabled else "✗", wa.bridge_url)

#     dc = config.channels.discord
#     table.add_row("Discord", "✓" if dc.enabled else "✗", dc.gateway_url)

#     # Feishu
#     fs = config.channels.feishu
#     fs_config = (
#         f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
#     )
#     table.add_row("Feishu", "✓" if fs.enabled else "✗", fs_config)

#     # Mochat
#     mc = config.channels.mochat
#     mc_base = mc.base_url or "[dim]not configured[/dim]"
#     table.add_row("Mochat", "✓" if mc.enabled else "✗", mc_base)

#     # Telegram
#     tg = config.channels.telegram
#     tg_config = (
#         f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
#     )
#     table.add_row("Telegram", "✓" if tg.enabled else "✗", tg_config)

#     # Slack
#     slack = config.channels.slack
#     slack_config = (
#         "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
#     )
#     table.add_row("Slack", "✓" if slack.enabled else "✗", slack_config)

#     # DingTalk
#     dt = config.channels.dingtalk
#     dt_config = (
#         f"client_id: {dt.client_id[:10]}..."
#         if dt.client_id
#         else "[dim]not configured[/dim]"
#     )
#     table.add_row("DingTalk", "✓" if dt.enabled else "✗", dt_config)

#     # QQ
#     qq = config.channels.qq
#     qq_config = (
#         f"app_id: {qq.app_id[:10]}..." if qq.app_id else "[dim]not configured[/dim]"
#     )
#     table.add_row("QQ", "✓" if qq.enabled else "✗", qq_config)

#     # Email
#     em = config.channels.email
#     em_config = em.imap_host if em.imap_host else "[dim]not configured[/dim]"
#     table.add_row("Email", "✓" if em.enabled else "✗", em_config)

#     console.print(table)


# def _get_bridge_dir() -> Path:
#     """Get the bridge directory, setting it up if needed."""
#     import shutil
#     import subprocess

#     # User's bridge location
#     user_bridge = Path.home() / ".nanobot" / "bridge"

#     # Check if already built
#     if (user_bridge / "dist" / "index.js").exists():
#         return user_bridge

#     # Check for npm
#     if not shutil.which("npm"):
#         console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
#         raise typer.Exit(1)

#     # Find source bridge: first check package data, then source dir
#     pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanobot/bridge (installed)
#     src_bridge = (
#         Path(__file__).parent.parent.parent / "bridge"
#     )  # repo root/bridge (dev)

#     source = None
#     if (pkg_bridge / "package.json").exists():
#         source = pkg_bridge
#     elif (src_bridge / "package.json").exists():
#         source = src_bridge

#     if not source:
#         console.print("[red]Bridge source not found.[/red]")
#         console.print("Try reinstalling: pip install --force-reinstall nanobot")
#         raise typer.Exit(1)

#     console.print(f"{__logo__} Setting up bridge...")

#     # Copy to user directory
#     user_bridge.parent.mkdir(parents=True, exist_ok=True)
#     if user_bridge.exists():
#         shutil.rmtree(user_bridge)
#     shutil.copytree(
#         source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist")
#     )

#     # Install and build
#     try:
#         console.print("  Installing dependencies...")
#         subprocess.run(
#             ["npm", "install"], cwd=user_bridge, check=True, capture_output=True
#         )

#         console.print("  Building...")
#         subprocess.run(
#             ["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True
#         )

#         console.print("[green]✓[/green] Bridge ready\n")
#     except subprocess.CalledProcessError as e:
#         console.print(f"[red]Build failed: {e}[/red]")
#         if e.stderr:
#             console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
#         raise typer.Exit(1)

#     return user_bridge


# @channels_app.command("login")
# def channels_login():
#     """Link device via QR code."""
#     import subprocess
#     from nanobot.config.loader import load_config

#     config = load_config()
#     bridge_dir = _get_bridge_dir()

#     console.print(f"{__logo__} Starting bridge...")
#     console.print("Scan the QR code to connect.\n")

#     env = {**os.environ}
#     if config.channels.whatsapp.bridge_token:
#         env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token

#     try:
#         subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
#     except subprocess.CalledProcessError as e:
#         console.print(f"[red]Bridge failed: {e}[/red]")
#     except FileNotFoundError:
#         console.print("[red]npm not found. Please install Node.js.[/red]")


# # ============================================================================
# # Cron Commands
# # ============================================================================

# cron_app = typer.Typer(help="Manage scheduled tasks")
# app.add_typer(cron_app, name="cron")


# @cron_app.command("list")
# def cron_list(
#     all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
# ):
#     """List scheduled jobs."""
#     from nanobot.config.loader import get_data_dir
#     from nanobot.cron.service import CronService

#     store_path = get_data_dir() / "cron" / "jobs.json"
#     service = CronService(store_path)

#     jobs = service.list_jobs(include_disabled=all)

#     if not jobs:
#         console.print("No scheduled jobs.")
#         return

#     table = Table(title="Scheduled Jobs")
#     table.add_column("ID", style="cyan")
#     table.add_column("Name")
#     table.add_column("Schedule")
#     table.add_column("Status")
#     table.add_column("Next Run")

#     import time
#     from datetime import datetime as _dt
#     from zoneinfo import ZoneInfo

#     for job in jobs:
#         # Format schedule
#         if job.schedule.kind == "every":
#             sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
#         elif job.schedule.kind == "cron":
#             sched = (
#                 f"{job.schedule.expr or ''} ({job.schedule.tz})"
#                 if job.schedule.tz
#                 else (job.schedule.expr or "")
#             )
#         else:
#             sched = "one-time"

#         # Format next run
#         next_run = ""
#         if job.state.next_run_at_ms:
#             ts = job.state.next_run_at_ms / 1000
#             try:
#                 tz = ZoneInfo(job.schedule.tz) if job.schedule.tz else None
#                 next_run = _dt.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
#             except Exception:
#                 next_run = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

#         status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"

#         table.add_row(job.id, job.name, sched, status, next_run)

#     console.print(table)


# @cron_app.command("add")
# def cron_add(
#     name: str = typer.Option(..., "--name", "-n", help="Job name"),
#     message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
#     every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
#     cron_expr: str = typer.Option(
#         None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"
#     ),
#     tz: str | None = typer.Option(
#         None, "--tz", help="IANA timezone for cron (e.g. 'America/Vancouver')"
#     ),
#     at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
#     deliver: bool = typer.Option(
#         False, "--deliver", "-d", help="Deliver response to channel"
#     ),
#     to: str = typer.Option(None, "--to", help="Recipient for delivery"),
#     channel: str = typer.Option(
#         None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"
#     ),
# ):
#     """Add a scheduled job."""
#     from nanobot.config.loader import get_data_dir
#     from nanobot.cron.service import CronService
#     from nanobot.cron.types import CronSchedule

#     if tz and not cron_expr:
#         console.print("[red]Error: --tz can only be used with --cron[/red]")
#         raise typer.Exit(1)

#     # Determine schedule type
#     if every:
#         schedule = CronSchedule(kind="every", every_ms=every * 1000)
#     elif cron_expr:
#         schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
#     elif at:
#         import datetime

#         dt = datetime.datetime.fromisoformat(at)
#         schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
#     else:
#         console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
#         raise typer.Exit(1)

#     store_path = get_data_dir() / "cron" / "jobs.json"
#     service = CronService(store_path)

#     try:
#         job = service.add_job(
#             name=name,
#             schedule=schedule,
#             message=message,
#             deliver=deliver,
#             to=to,
#             channel=channel,
#         )
#     except ValueError as e:
#         console.print(f"[red]Error: {e}[/red]")
#         raise typer.Exit(1) from e

#     console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


# @cron_app.command("remove")
# def cron_remove(
#     job_id: str = typer.Argument(..., help="Job ID to remove"),
# ):
#     """Remove a scheduled job."""
#     from nanobot.config.loader import get_data_dir
#     from nanobot.cron.service import CronService

#     store_path = get_data_dir() / "cron" / "jobs.json"
#     service = CronService(store_path)

#     if service.remove_job(job_id):
#         console.print(f"[green]✓[/green] Removed job {job_id}")
#     else:
#         console.print(f"[red]Job {job_id} not found[/red]")


# @cron_app.command("enable")
# def cron_enable(
#     job_id: str = typer.Argument(..., help="Job ID"),
#     disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
# ):
#     """Enable or disable a job."""
#     from nanobot.config.loader import get_data_dir
#     from nanobot.cron.service import CronService

#     store_path = get_data_dir() / "cron" / "jobs.json"
#     service = CronService(store_path)

#     job = service.enable_job(job_id, enabled=not disable)
#     if job:
#         status = "disabled" if disable else "enabled"
#         console.print(f"[green]✓[/green] Job '{job.name}' {status}")
#     else:
#         console.print(f"[red]Job {job_id} not found[/red]")


# @cron_app.command("run")
# def cron_run(
#     job_id: str = typer.Argument(..., help="Job ID to run"),
#     force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
# ):
#     """Manually run a job."""
#     from loguru import logger
#     from nanobot.config.loader import load_config, get_data_dir
#     from nanobot.cron.service import CronService
#     from nanobot.cron.types import CronJob
#     from nanobot.bus.queue import MessageBus
#     from nanobot.agent.loop import AgentLoop

#     logger.disable("nanobot")

#     config = load_config()
#     provider = _make_provider(config)
#     bus = MessageBus()
#     agent_loop = AgentLoop(
#         bus=bus,
#         provider=provider,
#         workspace=config.workspace_path,
#         model=config.agents.defaults.model,
#         temperature=config.agents.defaults.temperature,
#         max_tokens=config.agents.defaults.max_tokens,
#         max_iterations=config.agents.defaults.max_tool_iterations,
#         memory_window=config.agents.defaults.memory_window,
#         brave_api_key=config.tools.web.search.api_key or None,
#         web_proxy=config.tools.web.proxy or None,
#         exec_config=config.tools.exec,
#         restrict_to_workspace=config.tools.restrict_to_workspace,
#         mcp_servers=config.tools.mcp_servers,
#         channels_config=config.channels,
#     )

#     store_path = get_data_dir() / "cron" / "jobs.json"
#     service = CronService(store_path)

#     result_holder = []

#     async def on_job(job: CronJob) -> str | None:
#         response = await agent_loop.process_direct(
#             job.payload.message,
#             session_key=f"cron:{job.id}",
#             channel=job.payload.channel or "cli",
#             chat_id=job.payload.to or "direct",
#         )
#         result_holder.append(response)
#         return response

#     service.on_job = on_job

#     async def run():
#         return await service.run_job(job_id, force=force)

#     if asyncio.run(run()):
#         console.print("[green]✓[/green] Job executed")
#         if result_holder:
#             _print_agent_response(result_holder[0], render_markdown=True)
#     else:
#         console.print(f"[red]Failed to run job {job_id}[/red]")


# # ============================================================================
# # Status Commands
# # ============================================================================


# @app.command()
# def status():
#     """Show nanobot status."""
#     from nanobot.config.loader import load_config, get_config_path

#     config_path = get_config_path()
#     config = load_config()
#     workspace = config.workspace_path

#     console.print(f"{__logo__} nanobot Status\n")

#     console.print(
#         f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}"
#     )
#     console.print(
#         f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}"
#     )

#     if config_path.exists():
#         from nanobot.providers.registry import PROVIDERS

#         console.print(f"Model: {config.agents.defaults.model}")

#         # Check API keys from registry
#         for spec in PROVIDERS:
#             p = getattr(config.providers, spec.name, None)
#             if p is None:
#                 continue
#             if spec.is_oauth:
#                 console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
#             elif spec.is_local:
#                 # Local deployments show api_base instead of api_key
#                 if p.api_base:
#                     console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
#                 else:
#                     console.print(f"{spec.label}: [dim]not set[/dim]")
#             else:
#                 has_key = bool(p.api_key)
#                 console.print(
#                     f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}"
#                 )


# # ============================================================================
# # OAuth Login
# # ============================================================================

# provider_app = typer.Typer(help="Manage providers")
# app.add_typer(provider_app, name="provider")


# _LOGIN_HANDLERS: dict[str, callable] = {}


# def _register_login(name: str):
#     def decorator(fn):
#         _LOGIN_HANDLERS[name] = fn
#         return fn

#     return decorator


# @provider_app.command("login")
# def provider_login(
#     provider: str = typer.Argument(
#         ..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"
#     ),
# ):
#     """Authenticate with an OAuth provider."""
#     from nanobot.providers.registry import PROVIDERS

#     key = provider.replace("-", "_")
#     spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
#     if not spec:
#         names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
#         console.print(
#             f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}"
#         )
#         raise typer.Exit(1)

#     handler = _LOGIN_HANDLERS.get(spec.name)
#     if not handler:
#         console.print(f"[red]Login not implemented for {spec.label}[/red]")
#         raise typer.Exit(1)

#     console.print(f"{__logo__} OAuth Login - {spec.label}\n")
#     handler()


# @_register_login("openai_codex")
# def _login_openai_codex() -> None:
#     try:
#         from oauth_cli_kit import get_token, login_oauth_interactive

#         token = None
#         try:
#             token = get_token()
#         except Exception:
#             pass
#         if not (token and token.access):
#             console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
#             token = login_oauth_interactive(
#                 print_fn=lambda s: console.print(s),
#                 prompt_fn=lambda s: typer.prompt(s),
#             )
#         if not (token and token.access):
#             console.print("[red]✗ Authentication failed[/red]")
#             raise typer.Exit(1)
#         console.print(
#             f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]"
#         )
#     except ImportError:
#         console.print(
#             "[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]"
#         )
#         raise typer.Exit(1)


# @_register_login("github_copilot")
# def _login_github_copilot() -> None:
#     import asyncio

#     console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

#     async def _trigger():
#         from litellm import acompletion

#         await acompletion(
#             model="github_copilot/gpt-4o",
#             messages=[{"role": "user", "content": "hi"}],
#             max_tokens=1,
#         )

#     try:
#         asyncio.run(_trigger())
#         console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
#     except Exception as e:
#         console.print(f"[red]Authentication error: {e}[/red]")
#         raise typer.Exit(1)


# if __name__ == "__main__":
#     app()
