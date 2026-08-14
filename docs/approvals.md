# Approvals

Before Postal runs anything that changes state, the approval policy decides whether it goes ahead, asks you, or is refused outright. Read-only tools (`read`, `grep`, `glob`, `list_directories`, `plan`) never prompt, so a policy only affects writes, bash commands, network calls, memory writes, MCP tools, and sub-agent runs.

Set it with `approval` in [the config](configuration.md), or switch mid-session with `/approval <mode>`.

## Policies

| Value | Badge | Behaviour |
| --- | --- | --- |
| `on_request` *(default)* | `ask` | Confirm every mutating tool call. Commands matched as known-safe (`ls`, `git status`, `grep`, …) run without asking. |
| `auto_edit` | `auto-edit` | File edits and writes inside the working directory go through unprompted; bash commands still need confirmation unless known-safe. |
| `auto` | `auto` | Everything runs except dangerous commands, which are rejected. |
| `on_fail` | `on fail` | Currently identical to `auto`. Reserved for prompting after a failed tool call, which is not implemented yet. |
| `never` | `read-only` | Rejects anything that isn't a known-safe command. Nothing gets written, and you are never prompted. |
| `yolo` | `yolo` | Approves everything, including commands matched as dangerous. Only use this in a sandbox or container. |

## The two rules on top

These apply whatever the policy is, and no policy except `yolo` overrides them:

- **Dangerous commands are rejected.** `rm -rf /`, `dd if=`, `mkfs`, `shutdown`, `curl … | bash`, fork bombs, and similar patterns are refused before bash ever sees them (the full list is `DANGEROUS_PATTERNS` in `safety/approval.py`).
- **Anything touching a path outside the working directory is confirmed**, however permissive the policy is (`never` rejects it instead).

## Where you see it

The active policy is printed at startup and shown in the prompt badge, color-coded by risk: normal for `ask`, `auto-edit` and `read-only`, amber for `auto` and `on fail`, red for `yolo`.

## Picking one

Interactive work in a repo you care about is what `on_request` is for. Once you trust a task, `auto_edit` removes the file-write prompts while still stopping at bash commands. `never` is a good fit for letting a model explore a codebase it should not be able to change.

For unattended runs — single-shot mode, CI, anything with nobody at the keyboard — use `auto`, and prefer running it in a container. `yolo` disables the dangerous-command check entirely, so it only belongs somewhere disposable.
