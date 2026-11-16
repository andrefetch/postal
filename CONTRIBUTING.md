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

The interactive interface uses Textual: orchestration is in `ui/textual_app.py`, the prompt bar and its pickers in `ui/prompt_bar.py`, shared widgets and dialogs in `ui/textual_widgets.py`, and layout/styles in `ui/postal.tcss`. Use neutral charcoal surfaces with a restrained lavender accent for prompt controls. Use `App.run_test()` with a Pilot for keyboard, modal, streaming, and shutdown regressions. `tests/test_textual_ui.py` provides examples with mocked model responses, so no API key is required.

Postal uses a component-based UI system where each visual element is a separate, reusable component. This design makes it easier to:

- **Create new UI elements:** Add new components following the existing patterns in `ui/components/`
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
