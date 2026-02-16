"""Data management commands (export/import)."""

import json
import shutil
import zipfile
from pathlib import Path

import typer
from rich.console import Console

from nanobot.config.loader import get_config_path, get_data_dir, load_config
from nanobot.utils.helpers import get_workspace_path

data_app = typer.Typer(help="Manage data export and import")
console = Console()


@data_app.command("export")
def export_data(
    output: Path = typer.Option("nanobot_backup.zip", "--output", "-o", help="Output file path"),
    memory_only: bool = typer.Option(False, "--memory-only", "-m", help="Export only memory"),
):
    """Export nanobot data (workspace, config, memory)."""
    output = Path(output).resolve()
    if output.suffix != ".zip":
        output = output.with_suffix(".zip")

    console.print(f"Exporting to {output}...")

    workspace_path = get_workspace_path()
    config_path = get_config_path()
    data_dir = get_data_dir()

    try:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
            if memory_only:
                # Export only workspace/memory
                memory_dir = workspace_path / "memory"
                if memory_dir.exists():
                    for file in memory_dir.rglob("*"):
                        if file.is_file():
                            arcname = file.relative_to(workspace_path)
                            zipf.write(file, arcname)
                    console.print("[green]✓[/green] Exported memory")
                else:
                    console.print("[yellow]Warning: No memory directory found[/yellow]")
            else:
                # Full export
                # 1. Config
                if config_path.exists():
                    zipf.write(config_path, "config.json")
                    console.print("  [dim]Added config.json[/dim]")

                # 2. Workspace
                if workspace_path.exists():
                    for file in workspace_path.rglob("*"):
                        if file.is_file() and "__pycache__" not in file.parts and not file.name.startswith("."):
                            arcname = Path("workspace") / file.relative_to(workspace_path)
                            zipf.write(file, arcname)
                    console.print("  [dim]Added workspace/[/dim]")

                # 3. Cron jobs
                cron_jobs = data_dir / "cron" / "jobs.json"
                if cron_jobs.exists():
                    zipf.write(cron_jobs, "cron/jobs.json")
                    console.print("  [dim]Added cron/jobs.json[/dim]")

                # 4. History
                history_file = data_dir / "history" / "cli_history"
                if history_file.exists():
                    zipf.write(history_file, "history/cli_history")
                    console.print("  [dim]Added history/cli_history[/dim]")

                # 5. Sessions
                sessions_dir = data_dir / "sessions"
                if sessions_dir.exists():
                    for file in sessions_dir.glob("*.jsonl"):
                        zipf.write(file, Path("sessions") / file.name)
                    console.print("  [dim]Added sessions/[/dim]")

        console.print(f"[green]✓[/green] Export complete: {output}")

    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        raise typer.Exit(1)


@data_app.command("import")
def import_data(
    input_file: Path = typer.Argument(..., help="Input zip file"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing data without confirmation"),
):
    """Import nanobot data from a zip file."""
    if not input_file.exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        raise typer.Exit(1)

    if not zipfile.is_zipfile(input_file):
        console.print(f"[red]Not a zip file: {input_file}[/red]")
        raise typer.Exit(1)

    if not force:
        if not typer.confirm("This will overwrite existing data. Continue?"):
            raise typer.Abort()

    console.print(f"Importing from {input_file}...")

    try:
        with zipfile.ZipFile(input_file, "r") as zipf:
            file_list = zipf.namelist()

            # Detect type
            # Memory export puts files under `memory/` (relative to workspace)
            # Full export puts files under `workspace/` and config at root
            is_memory_only = any(f.startswith("memory/") for f in file_list) and "config.json" not in file_list

            if is_memory_only:
                console.print("Detected memory-only backup.")
                workspace_path = get_workspace_path()
                # Extract files starting with memory/ to workspace_path
                for member in file_list:
                    if member.startswith("memory/"):
                        source = zipf.open(member)
                        target = workspace_path / member
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with open(target, "wb") as f:
                            shutil.copyfileobj(source, f)
                console.print("[green]✓[/green] Imported memory")

            else:
                # Full import
                console.print("Detected full backup.")
                data_dir = get_data_dir()

                # 1. Config
                if "config.json" in file_list:
                    # Read config from zip
                    with zipf.open("config.json") as f:
                        config_data = json.load(f)

                    # Update workspace path to current default if not set in zip or to avoid path issues
                    # Let's load current config to see where workspace is.
                    current_config = load_config()
                    current_workspace = current_config.agents.defaults.workspace

                    # Update the imported config to use the *current* workspace path
                    if "agents" in config_data and "defaults" in config_data["agents"]:
                        config_data["agents"]["defaults"]["workspace"] = current_workspace

                    # Save to ~/.nanobot/config.json
                    config_path = get_config_path()
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(config_path, "w") as f:
                        json.dump(config_data, f, indent=2)
                    console.print("  [dim]Restored config.json[/dim]")

                # Reload config to get the (potentially updated) workspace path
                config = load_config()
                workspace_path = config.workspace_path

                # 2. Workspace
                # Files in zip are under workspace/
                for member in file_list:
                    if member.startswith("workspace/"):
                        # Strip "workspace/" prefix
                        rel_path = member[len("workspace/"):]
                        if not rel_path:
                            continue

                        target = workspace_path / rel_path
                        # Check for directory
                        if member.endswith("/"):
                            target.mkdir(parents=True, exist_ok=True)
                            continue

                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zipf.open(member) as source, open(target, "wb") as f:
                            shutil.copyfileobj(source, f)
                console.print("  [dim]Restored workspace/[/dim]")

                # 3. Cron
                if "cron/jobs.json" in file_list:
                    target = data_dir / "cron" / "jobs.json"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipf.open("cron/jobs.json") as source, open(target, "wb") as f:
                        shutil.copyfileobj(source, f)
                    console.print("  [dim]Restored cron jobs[/dim]")

                # 4. History
                if "history/cli_history" in file_list:
                    target = data_dir / "history" / "cli_history"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipf.open("history/cli_history") as source, open(target, "wb") as f:
                        shutil.copyfileobj(source, f)
                    console.print("  [dim]Restored history[/dim]")

                # 5. Sessions
                for member in file_list:
                    if member.startswith("sessions/"):
                        target = data_dir / member
                        if member.endswith("/"):
                            target.mkdir(parents=True, exist_ok=True)
                            continue
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zipf.open(member) as source, open(target, "wb") as f:
                            shutil.copyfileobj(source, f)
                console.print("  [dim]Restored sessions[/dim]")

        console.print("[green]✓[/green] Import complete")

    except Exception as e:
        console.print(f"[red]Import failed: {e}[/red]")
        raise typer.Exit(1)
