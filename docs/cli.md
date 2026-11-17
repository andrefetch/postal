# CLI reference

## Install

```bash
pip install postalcli
```

To check for and install the latest release:

```bash
postal upgrade
```

Postal needs Python 3.11 or newer and Node.js 22 or newer (the interactive TUI is a bundled TypeScript program that runs on `node`). The npm dependencies are bundled into the package, so you never need to run `npm install` to use Postal. A `Dockerfile` and Compose file live in [`docker/`](../docker/) if you would rather run the agent sandboxed.

When a newer release is available, Postal displays a notice when the interactive TUI starts. It never upgrades automatically; run `postal upgrade` yourself to install it.

On macOS (`darwin`), `postal upgrade` detects pipx-managed installations and runs
`pipx upgrade <environment>`, preserving any installation suffix.
For pip installations, it runs `python -m pip install --upgrade postalcli` using
Postal's current Python interpreter. Pip works on macOS as well as Windows and
Linux. If a macOS installation is managed by pipx but `pipx` is missing from
`PATH`, Postal asks you to restore it before upgrading. Restart Postal afterward
to load the updated code.

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

## Interactive terminal

`postal` opens a full-screen Ink interface with a centered cloud logo and prompt bar. The bar moves below the conversation after the first message. Its input grows to five visible text rows, then scrolls. Tools and reasoning are collapsed until expanded. Agent activity opens in an overlay.

The prompt bar's `+` menu adds workspace text/code file references, requests web search for the next prompt, or opens slash commands. File and web chips can be removed before sending. The model picker accepts a model ID and lists models used during the session; the effort picker uses the supported reasoning levels. The arrow sends the prompt and becomes a stop button while Postal is working. Use `Tab` to reach these controls or click them. Settings changes preserve the current draft.

| Key | Action |
| --- | --- |
| `Enter` | Send a prompt or completed command |
| `Ctrl+J`, `Shift+Enter` | Insert a newline (`Ctrl+J` works in terminals without modified Enter support) |
| `Alt+Up` / `Alt+Down` | Recall earlier prompts, including multiline prompts |
| `/`, `Ctrl+P` | Open slash commands; type to filter, arrows to select, `Tab` or `Enter` to complete |
| `Ctrl+G` | Open or close nested agent activity |
| `Ctrl+O` | Expand or collapse the latest tool or reasoning block |
| `Ctrl+End` | Scroll to the latest message |
| `PageUp` / `PageDown` | Scroll the conversation |
| `Esc`, `Ctrl+C` | Interrupt a running turn; close a menu; reject an open approval request |
| `Ctrl+Q` | Cancel active work, save the conversation, and exit |

In agent activity, arrows select an agent, `Enter` runs its slash-command choice, and `c` cancels the selected agent's subtree. The selected agent's goal, status, and result appear underneath. Approval overlays show the command or diff before execution: `y` approves, while `n` or `Esc` rejects. The reject button is focused by default.

Scrolling up keeps your place while a response streams. Scroll back to the bottom or press `Ctrl+End` to follow new output again. Tool output and reasoning are collapsible with a click or `Ctrl+O`.

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
