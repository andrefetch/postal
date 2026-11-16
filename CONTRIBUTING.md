# Contributing

Hey, thanks for wanting to contribute!


## Getting started

Postal is a Python project (3.11+). To get set up locally:

```bash
git clone https://github.com/andrefetch/postal.git
cd postal
uv sync
```

You can also install the dependencies with `pip install -r requirements.txt` if you prefer pip over uv.

## Workflow

1. Fork the repo (or create a branch if you have access).
2. Create a branch for your change, for example `fix/token-usage` or `feat/new-tool`.
3. Make your changes and test them locally.
4. Open a PR against `main` with a clear description of what you changed and why.

Keep PRs focused. Smaller, single-purpose PRs are easier to review and get merged faster.

## UI Component-Based System

The interactive interface is the TypeScript program in `ui/terminal/`. Keep Python responsible for the agent, tools, sessions, and approvals, and the frontend for rendering and input. The boundary is the JSON-lines protocol in `ui/bridge.py` (`BridgeSession`) and `ui/terminal/src/protocol.ts`; changing one side means changing the other, plus `tests/test_ui_bridge.py`.

Layout conventions: neutral charcoal surfaces with a restrained lavender accent for prompt controls. Keep the screen monochrome. Every visual element is a separate component: rendering lives in `ui/terminal/src/components.tsx`, the line editor in `editor.ts`, and screen state in the pure reducer in `state.ts`. Prefer adding a reducer case and a test over adding component-level state.

### Working on the frontend

```bash
cd ui/terminal
npm ci
npm run check     # tsc --noEmit
npm test          # node --test via tsx
npm run build     # bundles to ../terminal_bundle/postal.mjs
npm run preview   # run the UI against a local fake backend
```

Commit the rebuilt `ui/terminal_bundle/postal.mjs` whenever `ui/terminal/src` changes: the Python package ships the bundle, not the TypeScript sources, so an unbuilt change never reaches users. The `TypeScript terminal` job in CI rebuilds and fails if the committed bundle is stale. `tests/test_ui_bridge.py` exercises the protocol with a real `BridgeSession`, so no API key is required.

`POSTAL_UI=textual` still selects the previous Textual interface (`ui/textual_app.py`, `ui/textual_widgets.py`). Treat it as a maintained fallback: keep it importable and keep `tests/test_textual_ui.py` passing, but new interactive work goes in `ui/terminal/`.

Postal uses a component-based UI system where each visual element is a separate, reusable component. This design makes it easier to:

- **Create new UI elements:** Add new components following the existing patterns in `ui/components/` and `ui/terminal/src/`
- **Maintain and test components:** Each component is isolated and can be tested independently
- **Customize the appearance:** Modify individual components without affecting other parts
- **Understand the codebase:** Components are self-contained with clear purposes

### UI Component Structure

The shared Rich renderers and single-shot components are in `ui/components/`:

- **Base components:** `Gutter`, `Spinner`, `MarkdownStream`
- **UI elements:** `logo.py`, `thinking.py`, `shimmer.py`, `tool_call.py`
- **Interactive elements:** `confirmation.py`, `args_table.py`
- **Container components:** `plan.py`, `memory.py`, `transcript.py`
- **Visual utilities:** `theme/palette.py`, `theme/styles.py`

### Contributing to UI Components

When adding or modifying UI components:

1. **Follow existing patterns:** Look at similar components for examples
2. **Import from the right places:** Components in `ui/components/__init__.py` are the public API
3. **Use the theme system:** Styles are defined in `ui/theme/` and imported where needed
4. **Keep components focused:** Each component should have one clear responsibility
5. **Export if reusable:** Add components to `ui/components/__init__.py` if they might be used elsewhere

### Example Component: A Custom Spinner

```python
from rich.console import Console
from rich.live import Live

class CustomSpinner:
    def __init__(self, console: Console):
        self.console = console
        self.frames = ["⣾ ", "⣷ ", "⣯ ", "⣟ ", "⡿ ", "⢟ ", "⢯ ", "⣯ ", "⣷ "]
        self.current = 0

    def render(self):
        return self.frames[self.current]

    def advance(self):
        self.current = (self.current + 1) % len(self.frames)
```

### Development Tips

- **Run tests locally:** Use `uv sync` then `uv run --with pytest python -m pytest tests -q`. With pip, run `python -m pip install -e . pytest` then `python -m pytest tests -q`.
- **Check component imports:** Verify your changes don't break imports in `ui/components/__init__.py`
- **Test visually:** Run Postal with your changes to ensure the UI renders correctly
- **Follow the style guide:** Keep code clean and maintainable

GitHub Actions runs the Python suite on every pull request with Python 3.11 and 3.13. It installs the package and preloads the tokenizer data before testing. You can also start the **Python tests** workflow manually.

## Reporting bugs

If you run into a bug and are not ready to fix it yourself, open an issue. Please include:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your OS and Python version

## Code of conduct

Please be respectful. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.
