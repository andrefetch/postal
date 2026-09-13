from pathlib import Path
from agent.agent import Agent
from agent.store import SessionStore
from config.config import Config
from config.loader import load_config
from config.credentials import (
    clear_credentials,
    get_credentials_path,
    load_credentials,
    save_credentials,
)
from config.oauth import OAuthError, login_with_oauth
from ui import TUI, Repl, get_console, stream_turn
import asyncio
import click
import json
import subprocess
import sys
from importlib.metadata import version as installed_version
from urllib.error import URLError
from urllib.request import urlopen

from packaging.version import InvalidVersion, Version

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

console = get_console()


def _latest_version() -> Version:
    with urlopen("https://pypi.org/pypi/postalcli/json", timeout=5) as response:
        data = json.load(response)
    return Version(data["info"]["version"])


def _upgrade_notice() -> str | None:
    try:
        current = Version(installed_version("postalcli"))
        latest = _latest_version()
    except (InvalidVersion, KeyError, TypeError, URLError, TimeoutError, OSError, ValueError):
        return None

    if latest > current:
        return f"Postal {latest} is available (you have {current}). Use `postal upgrade` to update."
    return None

async def run_once(config: Config, message: str, resume: str | None = None) -> str | None:
    tui = TUI(config)
    async with Agent(
        config, confirmation_callback=tui.confirm_tool, resume=resume
    ) as agent:
        tui.render_approval_mode()
        if resume and agent.resumed is None:
            console.print(f"[warning]No saved session matched '{resume}'.[/warning]")
        return await stream_turn(tui, agent, message)


def _resolve_resume(
    config: Config,
    resume: str | None,
    continue_last: bool,
) -> str | None:
    """Turn --resume / --continue into a session id, or None to start fresh."""

    if resume:
        return resume

    if not continue_last:
        return None

    latest = SessionStore().latest(config.cwd)
    if latest is None:
        console.print("[warning]No saved session for this directory, starting a new one.[/warning]")
        return None

    return latest.session_id


class DefaultGroup(click.Group):

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            return "run", self.get_command(ctx, "run"), args


@click.group(
    cls=DefaultGroup,
    invoke_without_command=True,
    epilog="""\b
Examples:
  postal                    Start the interactive TUI
  postal "fix the bug"      Run a single prompt and exit
  postal --continue         Resume the last session in this directory
  postal --resume 123456    Resume a specific session by ID
"""
)
@click.version_option(package_name="postalcli", prog_name="postal")
@click.option(
    '--cwd',
    '-c',
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    help='Current Working Directory'
)
@click.option(
    "--resume",
    "-r",
    "resume",
    default=None,
    metavar="SESSION",
    help="Resume a saved session by id (a prefix is enough).",
)
@click.option(
    "--continue",
    "-C",
    "continue_last",
    is_flag=True,
    help="Resume the most recent session for this directory.",
)
@click.pass_context
def main(ctx: click.Context, cwd: Path | None, resume: str | None, continue_last: bool):
    ctx.obj = {"cwd": cwd, "resume": resume, "continue": continue_last}
    # Bare `postal` with no subcommand launches the interactive TUI.
    if ctx.invoked_subcommand is None:
        ctx.invoke(run, prompt=None)


@main.command(
    epilog="""\b
Examples:
  postal run                       Launch the interactive TUI (same as just `postal`)
  postal run "write a hello world" Run a one-shot prompt
"""
)
@click.argument("prompt", required=False)
@click.pass_context
def run(ctx: click.Context, prompt: str | None):
    """Run a one-shot prompt, or launch the TUI when no prompt is given."""
    cwd = ctx.obj.get("cwd") if ctx.obj else None

    try:
        config = load_config(cwd=cwd)
    except Exception as e:
        console.print(f"[error]Config Error: {e}[/error]")
        sys.exit(1)

    errors = config.validate()

    if errors:
        for error in errors:
            console.print(f'[error]Config Error: {error}[/error]')

        sys.exit(1)

    resume = _resolve_resume(
        config,
        ctx.obj.get("resume") if ctx.obj else None,
        bool(ctx.obj.get("continue")) if ctx.obj else False,
    )

    if prompt:
        result = asyncio.run(run_once(config, prompt, resume=resume))
        if result is None:
            sys.exit(1)
    else:
        asyncio.run(Repl(config, resume=resume, upgrade_notice=_upgrade_notice()).run())


@main.command(
    epilog="""\b
Examples:
  postal login          Open your browser to securely authorize with OpenRouter
  postal login --paste  Paste an API key directly in the terminal
"""
)
@click.option(
    "--base-url",
    default=None,
    help=f"API base URL to save (default: {DEFAULT_BASE_URL})",
)
@click.option(
    "--paste",
    is_flag=True,
    help="Paste an API key manually instead of authorizing in the browser.",
)
def login(base_url: str | None, paste: bool):
    """Log in to OpenRouter via your browser (or --paste an API key)."""
    if load_credentials().get("api_key"):
        if not click.confirm("You're already logged in. Overwrite the saved key?", default=False):
            console.print("[warning]Login cancelled.[/warning]")
            return

    resolved_base_url = base_url or DEFAULT_BASE_URL

    if paste:
        api_key = click.prompt("Paste your OpenRouter API key", hide_input=True).strip()
        if not api_key:
            console.print("[error]No key entered, nothing saved.[/error]")
            sys.exit(1)
    else:
        console.print("Opening your browser to authorize postal with OpenRouter...")
        try:
            api_key = login_with_oauth(resolved_base_url)
        except OAuthError as e:
            console.print(f"[error]Login failed:[/error] {e}")
            console.print("[warning]You can retry, or run `postal login --paste` to enter a key manually.[/warning]")
            sys.exit(1)

    path = save_credentials(api_key, resolved_base_url)
    console.print(f"[success]Logged in.[/success] Key saved to {path}")
    console.print("[warning]The API_KEY environment variable, if set, still takes precedence.[/warning]")


@main.group(
    invoke_without_command=True,
    epilog="""\b
Examples:
  postal sessions        List all saved sessions for the current directory
  postal sessions --all  List all saved sessions across all directories
"""
)
@click.option(
    "--all",
    "all_projects",
    is_flag=True,
    help="List sessions from every directory, not just this one.",
)
@click.pass_context
def sessions(ctx: click.Context, all_projects: bool):
    """List saved sessions."""

    if ctx.invoked_subcommand is not None:
        return

    cwd = (ctx.obj.get("cwd") if ctx.obj else None) or Path.cwd()
    saved = SessionStore().list(None if all_projects else cwd)

    if not saved:
        scope = "" if all_projects else f" for {cwd}"
        console.print(f"[warning]No saved sessions{scope}.[/warning]")
        return

    for meta in saved:
        turns = f"{meta.turns} turn{'s' if meta.turns != 1 else ''}"
        console.print(
            f"[info]{meta.short_id}[/info]  "
            f"{meta.updated_at:%Y-%m-%d %H:%M}  "
            f"{turns:>9}  {meta.title}"
        )
        if all_projects:
            console.print(f"[muted]{' ' * 10}{meta.cwd}[/muted]")

    console.print()
    console.print("[muted]Resume one with postal --resume <id>[/muted]")


@sessions.command(
    "rm",
    epilog="""\b
Examples:
  postal sessions rm 123456    Delete the session matching the ID prefix
"""
)
@click.argument("session_id")
def sessions_rm(session_id: str):
    """Delete a saved session."""

    store = SessionStore()
    resolved = store.resolve(session_id)

    if resolved is None:
        console.print(f"[error]No saved session matching '{session_id}'.[/error]")
        sys.exit(1)

    meta = store.read_meta(resolved)
    if store.delete(resolved):
        title = f" - {meta.title}" if meta else ""
        console.print(f"[success]Deleted session {resolved[:8]}[/success]{title}")
    else:
        console.print(f"[error]Could not delete {resolved[:8]}.[/error]")
        sys.exit(1)


@main.command()
def logout():
    """Remove the saved OpenRouter API key."""
    if clear_credentials():
        console.print(f"[success]Logged out.[/success] Removed {get_credentials_path()}")
    else:
        console.print("[warning]No saved credentials to remove.[/warning]")


@main.command()
def upgrade():
    current = Version(installed_version("postalcli"))

    try:
        latest = _latest_version()
    except (InvalidVersion, KeyError, TypeError, URLError, TimeoutError, OSError, ValueError) as error:
        raise click.ClickException(f"Could not check for updates: {error}") from error

    if latest <= current:
        console.print(f"[success]Postal is already up to date ({current}).[/success]")
        return

    console.print(f"Updating postal from {current} to {latest}...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "postalcli"],
        check=False,
    )
    if result.returncode:
        raise click.ClickException("postal upgrade failed")
    console.print(f"[success]Postal upgraded to {latest}.[/success]")


@main.command("/help")
@click.pass_context
def cli_help(ctx: click.Context):
    """Alias for --help."""
    click.echo(ctx.parent.get_help())


if __name__ == "__main__": # better than just main() ngl
    main()
