from client.response import TokenUsage
from config.config import Config
from prompts import get_system_prompt
from dataclasses import dataclass, field
from tools.base import Tool
from utils.text import count_tokens
from typing import Any
from datetime import datetime

EMPTY_TOOL_OUTPUT = "(no output)"

INTERRUPTED_TOOL_OUTPUT = "[interrupted before this tool ran]"

@dataclass
class MessageItem:
    role: str
    content: str
    token_count: int | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pruned_at: datetime | None = None

    def to_storage(self) -> dict[str, Any]:
        """The full item, including bookkeeping the model never sees."""
        return {
            "role": self.role,
            "content": self.content,
            "token_count": self.token_count,
            "tool_call_id": self.tool_call_id,
            "tool_calls": self.tool_calls,
            "pruned_at": self.pruned_at.isoformat() if self.pruned_at else None,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> "MessageItem":
        pruned_at = data.get("pruned_at")
        if isinstance(pruned_at, str):
            try:
                pruned_at = datetime.fromisoformat(pruned_at)
            except ValueError:
                pruned_at = None
        else:
            pruned_at = None

        return cls(
            role=str(data.get("role", "user")),
            content=str(data.get("content") or ""),
            token_count=data.get("token_count"),
            tool_call_id=data.get("tool_call_id"),
            tool_calls=list(data.get("tool_calls") or []),
            pruned_at=pruned_at,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
           "role": self.role
        }

        if self.tool_call_id:
            result['tool_call_id'] = self.tool_call_id
        
        if self.tool_calls:
            result['tool_calls'] = self.tool_calls

        if self.role == 'tool':
            result['content'] = self.content or EMPTY_TOOL_OUTPUT
        elif self.content:
            result['content'] = self.content

        return result

class ContextManager:

    PRUNE_PROTECT_TOKENS = 40_000
    PRUNE_MINIMUM_TOKENS = 20_000

    def __init__(
            self,
            config: Config,
            user_memory: str | None,
            tools: list[Tool] | None = None,
            ) -> None:
        self._system_prompt = get_system_prompt(config, user_memory, tools)
        self.config = config
        self._model_name = self.config.model_name
        self._messages: list[MessageItem] = []
        self._latest_usage = TokenUsage()
        self._total_usage = TokenUsage()
    
    def add_user_message(self, content: str):
        item = MessageItem(
            role = 'user', 
            content = content,
            token_count=count_tokens(content, self._model_name)
        )

        self._messages.append(item)
    
    def add_assistant_message(
            self, 
            content: str, 
            tool_calls: list[dict[str, Any]] | None = None,
            ) -> None:
        item = MessageItem(
            role = 'assistant', 
            content = content or "",
            token_count=count_tokens(
                content or "",
                self._model_name
            ),
            tool_calls=tool_calls or []
        )

        self._messages.append(item)
    
    def clear(self) -> None:
        self._messages.clear()
        self._latest_usage = TokenUsage()

    @property
    def history(self) -> list[MessageItem]:
        """The conversation, system prompt excluded."""
        return list(self._messages)

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def export_messages(self) -> list[dict[str, Any]]:
        return [item.to_storage() for item in self._messages]

    def restore_messages(self, messages: list[dict[str, Any]]) -> int:
        """Replace the conversation with a saved one.

        The system prompt is deliberately not restored: it is rebuilt from the
        current config and tool set, so a resumed session picks up whatever has
        changed since it was saved.
        """

        self._messages = [MessageItem.from_storage(item) for item in messages]
        self.answer_dangling_tool_calls()

        # There is no provider usage report for a restored transcript, so the
        # stored token counts stand in. Pruning and compaction both read this.
        restored = sum(
            item.token_count if item.token_count is not None
            else count_tokens(item.content, self._model_name)
            for item in self._messages
        )
        self._latest_usage = TokenUsage(
            prompt_tokens=restored,
            total_tokens=restored,
        )

        return len(self._messages)

    def set_total_usage(self, usage: TokenUsage) -> None:
        self._total_usage = usage

    def answer_dangling_tool_calls(self) -> int:
        """Give every tool call a result, inventing one where it is missing.

        A turn cut short between the model asking for a tool and the tool
        answering leaves a call with no result, which providers reject on the
        next request. Filling the gap keeps an interrupted turn resumable.
        """

        answered = {
            item.tool_call_id
            for item in self._messages
            if item.role == 'tool' and item.tool_call_id
        }

        repaired: list[MessageItem] = []
        added = 0
        index = 0

        while index < len(self._messages):
            item = self._messages[index]
            repaired.append(item)
            index += 1

            if item.role != 'assistant' or not item.tool_calls:
                continue

            # Keep the results that did arrive where they are, and fill the
            # gaps in after them so the order still matches the call order.
            while index < len(self._messages) and self._messages[index].role == 'tool':
                repaired.append(self._messages[index])
                index += 1

            for tool_call in item.tool_calls:
                call_id = tool_call.get('id')
                if not call_id or call_id in answered:
                    continue

                repaired.append(
                    MessageItem(
                        role='tool',
                        content=INTERRUPTED_TOOL_OUTPUT,
                        tool_call_id=call_id,
                        token_count=count_tokens(INTERRUPTED_TOOL_OUTPUT, self._model_name),
                    )
                )
                answered.add(call_id)
                added += 1

        self._messages = repaired
        return added

    def get_messages(self) -> list[dict[str, Any]]:
        messages = []

        if self._system_prompt:
            messages.append(
                {
                'role': 'system',
                'content': self._system_prompt
                }
            )
        
        for item in self._messages:
            messages.append(item.to_dict())
        
        return messages
    
    def add_tool_result(
            self, 
            tool_call_id: str, 
            content: str
            ) -> None:
        item = MessageItem(
            role='tool',
            content=content,
            tool_call_id=tool_call_id,
            token_count=count_tokens(content, self._model_name)
        )

        self._messages.append(item)

    def set_latest_usage(self, usage: TokenUsage) -> None:
        self._latest_usage = usage

    def add_usage(self, usage: TokenUsage):
        self._total_usage += usage

    @property
    def total_usage(self) -> TokenUsage:
        return self._total_usage

    def needs_compression(self) -> bool:

        context_lim = self.config.model.context_window
        current_tokens = self._latest_usage.total_tokens

        return current_tokens > (context_lim * 0.8)

    def replace_with_summary(self, summary: str) -> None:

        self._messages = []

        continuation_content = f"""# Context Restoration (Previous Session Compacted)

        The previous conversation was compacted due to context length limits. Below is a detailed summary of the work done so far. 

        **CRITICAL: Actions listed under "COMPLETED ACTIONS" are already done. DO NOT repeat them.**

        ---

        {summary}

        ---

        Resume work from where we left off. Focus ONLY on the remaining tasks."""

        summary_item = MessageItem(
            role="user",
            content=continuation_content,
            token_count=count_tokens(continuation_content, self._model_name),
        )
        self._messages.append(summary_item)

        ack_content = """I've reviewed the context from the previous session. I understand:
- The original goal and what was requested
- Which actions are ALREADY COMPLETED (I will NOT repeat these)
- The current state of the project
- What still needs to be done

I'll continue with the REMAINING tasks only, starting from where we left off."""
        ack_item = MessageItem(
            role="assistant",
            content=ack_content,
            token_count=count_tokens(ack_content, self._model_name),
        )
        self._messages.append(ack_item)

        continue_content = (
            "Continue with the REMAINING work only. Do NOT repeat any completed actions. "
            "Proceed with the next step as described in the context above."
        )

        continue_item = MessageItem(
            role="user",
            content=continue_content,
            token_count=count_tokens(continue_content, self._model_name),
        )
        self._messages.append(continue_item)

    def prune_tool_outputs(self) -> int:

        user_message_count = sum(1 for message in self._messages if message.role == 'user')

        if user_message_count < 2:
            return 0

        total_tokens = 0
        pruned_tokens = 0
        to_prune: list[MessageItem] = []

        for message in reversed(self._messages):
            if message.role == 'tool' and message.tool_call_id:

                if message.pruned_at:
                    break

                tokens = message.token_count or count_tokens(message.content, self._model_name)
                total_tokens += tokens

                if total_tokens > self.PRUNE_PROTECT_TOKENS:
                    pruned_tokens += tokens
                    to_prune.append(message)

        if pruned_tokens < self.PRUNE_MINIMUM_TOKENS:
            return 0

        pruned_count = 0
        reclaimed_tokens = 0

        for message in to_prune:
            before = message.token_count or 0
            message.content = '[Old tool result content cleared]'
            message.token_count = count_tokens(message.content, self._model_name)
            message.pruned_at = datetime.now()
            reclaimed_tokens += before - message.token_count
            pruned_count += 1

        # The last reported usage still reflects the unpruned payload. Discount it
        # so needs_compression() doesn't compact away context that pruning just freed.
        self._latest_usage = TokenUsage(
            prompt_tokens=max(0, self._latest_usage.prompt_tokens - reclaimed_tokens),
            completion_tokens=self._latest_usage.completion_tokens,
            total_tokens=max(0, self._latest_usage.total_tokens - reclaimed_tokens),
            cached_tokens=self._latest_usage.cached_tokens,
        )

        return pruned_count

