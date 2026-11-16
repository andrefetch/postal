from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from config.config import Config
from ui.textual_widgets import Composer


class PromptControl(Button):
    def render(self) -> Content:
        label = self.label.plain
        width = self.content_size.width
        if label.endswith((" ▾", " ×")) and width >= 3:
            return Content(label[:-2]).truncate(width - 2, ellipsis=True).append(label[-2:])
        return Content(label).truncate(width, ellipsis=True)


class PromptBar(Vertical):
    """A growing input with a compact row of keyboard-accessible controls."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="prompt-sources"):
            yield PromptControl("Files ×", id="file-chip", compact=True)
            yield PromptControl("◎ Web ×", id="web-chip", compact=True)
        yield Composer(
            id="composer", placeholder="Ask anything", disabled=True,
            show_line_numbers=False, highlight_cursor_line=False,
        )
        with Horizontal(id="prompt-toolbar"):
            yield Button("+", id="prompt-add", compact=True, tooltip="Add context or browse commands")
            yield Static(id="prompt-spacer")
            yield PromptControl("Model ▾", id="prompt-model", compact=True, tooltip="Choose a model")
            yield PromptControl("Auto ▾", id="prompt-effort", compact=True, tooltip="Reasoning effort")
            yield Button("↑", id="prompt-send", compact=True, disabled=True, tooltip="Send message")

    def on_mount(self) -> None:
        self.update_sources([], False)
        for button in self.query(Button):
            button.active_effect_duration = 0.12

    @staticmethod
    def set_label(button: Button, label: str) -> None:
        if button.label.plain != label:
            button.label = Text(label)
            button.refresh(layout=True)

    def update_sources(self, files: list[Path], web: bool) -> None:
        self.query_one("#prompt-sources").display = bool(files or web)
        chip = self.query_one("#file-chip", Button)
        chip.display = bool(files)
        label = files[0].name if len(files) == 1 else f"{len(files)} files"
        self.set_label(chip, f"{label} ×")
        chip.tooltip = "Remove file references: " + ", ".join(map(str, files))
        self.query_one("#web-chip").display = web
        self.query_one("#web-chip").tooltip = "Remove web search from this prompt"
        self.call_after_refresh(self.query_one(Composer).resize_to_content)

    def update_controls(self, config: Config, *, busy: bool, ready: bool) -> None:
        model = self.query_one("#prompt-model", Button)
        self.set_label(model, f"{config.model_name.rsplit('/', 1)[-1] or 'Model'} ▾")
        model.tooltip = f"Model: {config.model_name or 'not selected'}"
        reasoning = config.reasoning
        effort = (
            "Off" if not reasoning.enabled else
            "Custom" if reasoning.max_tokens is not None else
            (reasoning.effort or "auto").title()
        )
        self.set_label(self.query_one("#prompt-effort", Button), f"{effort} ▾")
        for selector in ("#prompt-add", "#prompt-model", "#prompt-effort"):
            self.query_one(selector).disabled = not ready or busy
        send = self.query_one("#prompt-send", Button)
        self.set_label(send, "■" if busy else "↑")
        send.tooltip = "Stop response" if busy else "Send message"
        send.disabled = not ready or (not busy and not self.query_one(Composer).text.strip())
        send.set_class(busy, "busy")


class PromptPicker(ModalScreen[str | None]):
    """Small menus and editable values shared by the prompt-bar controls."""

    BINDINGS = [Binding("escape", "close", "Close", priority=True)]

    def __init__(
        self, title: str, choices: Sequence[tuple[str, str, str]] = (), *,
        value: str | None = None, placeholder: str = "",
        validate: Callable[[str], str | None] | None = None,
    ):
        super().__init__()
        self.picker_title = title
        self.choices = choices
        self.value = value
        self.placeholder = placeholder
        self.validate_value = validate

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Static(self.picker_title, id="picker-title")
            if self.value is not None:
                yield Input(value=self.value, placeholder=self.placeholder, id="picker-input")
            if self.choices:
                yield OptionList(*(
                    Option(Text.assemble((label, "bold"), (f"  {detail}", "#a1a1aa")), id=key)
                    for key, label, detail in self.choices
                ), id="picker-options")
            yield Static("", id="picker-error", markup=False)
            yield Static("Enter select · Esc close", id="picker-hint")

    def on_mount(self) -> None:
        self.query_one("#picker-error").display = False
        self.query_one("#picker-input" if self.value is not None else "#picker-options").focus()

    def on_resize(self, event: events.Resize) -> None:
        self.set_class(event.size.height < 20, "compact")

    def action_close(self) -> None:
        self.dismiss(None)

    def choose(self, value: str) -> None:
        value = value.strip()
        error = self.validate_value(value) if self.validate_value else None
        if not value or error:
            message = self.query_one("#picker-error", Static)
            message.update(error or "Enter a value first.")
            message.display = True
            return
        self.dismiss(value)

    @on(Input.Submitted, "#picker-input")
    def input_submitted(self, event: Input.Submitted) -> None:
        self.choose(event.value)

    @on(OptionList.OptionSelected, "#picker-options")
    def option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            self.choose(event.option.id)
