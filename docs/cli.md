# CLI reference

## Install

```bash
pip install postalcli
```

To check for and install the latest release:

```bash
postal upgrade
```

Postal needs Python 3.11 or newer. A `Dockerfile` and Compose file live in [`docker/`](../docker/) if you would rather run the agent sandboxed.

When a newer release is available, Postal displays a notice when the interactive TUI starts. It never upgrades automatically; run `postal upgrade` yourself to install it.

## Log in

```bash
postal login           # opens your browser to authorize with OpenRouter
postal login --paste   # paste an API key instead
postal logout          # remove the saved key
```

Browser login is OAuth 2.0 with PKCE against a loopback redirect; the key is written to your user config directory. `--base-url` saves a different API base URL alongside it.

The `API_KEY` environment variable always takes precedence over the saved key, which makes CI and one-off overrides easy:

```bash
API_KEY=sk-... postal "run the test suite and fix what fails"
```

## Commands

| Command | What it does |
| --- | --- |
| `postal` | Start the interactive TUI |
| `postal "your prompt"` | Single-shot mode: run one prompt, print the answer, exit |
| `postal run [prompt]` | The explicit form of the two above |
| `postal login` | Authorize with OpenRouter |
| `postal logout` | Remove the saved API key |
| `postal upgrade` | Check PyPI and upgrade Postal if a newer release is available |
| `postal sessions` | List saved sessions for this directory |
| `postal sessions --all` | List sessions from every directory |
| `postal sessions rm <id>` | Delete a saved session |
| `postal --version` | Print the installed version |

## Global flags

These go before the command, or on their own with the bare `postal`.

| Flag | Short | What it does |
| --- | --- | --- |
| `--cwd <path>` | `-c` | Run against a different working directory |
| `--resume <id>` | `-r` | Resume a saved session; an id prefix is enough |
| `--continue` | `-C` | Resume the most recent session for this directory |

## Examples

```bash
postal                          # interactive TUI in the current repo
postal "fix the failing test"   # one-shot, good for scripting
postal --cwd ~/code/api         # work in another checkout
postal --continue               # pick up where you left off
postal --resume 3f2a1c          # resume one specific session
```

Single-shot mode runs the same agent loop as the TUI, including tools and approvals — so pair it with an approval policy that will not block on a prompt nobody is there to answer. See [Approvals](approvals.md).

Sessions started from either mode land in the same place. See [Sessions](sessions.md).
