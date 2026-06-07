"""Chat log widget with proper message layout matching the HTML mockup."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.containers import Horizontal, VerticalScroll  # type: ignore[import-not-found]
from textual.message import Message  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class _MessageWidget(Widget):
    """One chat message: header row (avatar+name left, timestamp right) + indented body."""

    DEFAULT_CSS = """
    _MessageWidget {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    ._msg-header {
        width: 100%;
        height: 1;
    }
    ._msg-name {
        width: 1fr;
    }
    ._msg-time {
        width: auto;
        color: #555555;
    }
    ._msg-body {
        width: 100%;
        height: auto;
        padding-left: 3;
        color: #cccccc;
    }
    ._msg-thought {
        width: 100%;
        height: auto;
        padding-left: 3;
        color: #666666;
    }
    ._msg-user ._msg-name {
        color: #888888;
    }
    ._msg-jules ._msg-name {
        color: #ff79c6;
    }
    """

    def __init__(self, avatar: str, name: str, timestamp: str, role_class: str) -> None:
        super().__init__(classes=role_class)
        self._avatar = avatar
        self._name = name
        self._timestamp = timestamp
        self._body_text = ""
        self._thought_text = ""
        self._body_widget: Static | None = None
        self._thought_widget: Static | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="_msg-header"):
            yield Static(f"{self._avatar} {self._name}", classes="_msg-name")
            yield Static(self._timestamp, classes="_msg-time")
        self._thought_widget = Static("", classes="_msg-thought", markup=True)
        self._thought_widget.display = False
        yield self._thought_widget
        self._body_widget = Static(self._body_text, classes="_msg-body", markup=False)
        yield self._body_widget

    def on_mount(self) -> None:
        if self._body_text and self._body_widget:
            self._body_widget.update(self._body_text)

    def set_body(self, text: str) -> None:
        self._body_text = text
        if self._body_widget:
            self._body_widget.update(text)

    def append_body(self, token: str, cursor: bool = True) -> None:
        self._body_text += token
        if self._body_widget:
            suffix = "▌" if cursor else ""
            self._body_widget.update(self._body_text + suffix)

    def append_thought(self, token: str) -> None:
        self._thought_text += token
        if self._thought_widget:
            self._thought_widget.display = True
            escaped = self._thought_text.replace("[", "\\[")
            self._thought_widget.update(f"[dim italic]{escaped}▌[/dim italic]")

    def finalize(self) -> None:
        # Hide thoughts once the final response is present; keep if no content
        if self._thought_widget and self._body_text:
            self._thought_widget.display = False
        elif self._thought_widget and self._thought_text:
            escaped = self._thought_text.replace("[", "\\[")
            self._thought_widget.update(f"[dim italic]{escaped}[/dim italic]")
        if self._body_widget:
            self._body_widget.update(self._body_text)


class ChatLog(Widget):
    """Scrollable chat transcript with properly laid out messages."""

    class AppendToken(Message):
        def __init__(self, token: str) -> None:
            super().__init__()
            self.token = token

    DEFAULT_CSS = """
    ChatLog {
        width: 100%;
        height: 1fr;
    }
    #_chat-scroll {
        width: 100%;
        height: 100%;
        padding: 1 1;
        scrollbar-size: 1 1;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._active_msg: _MessageWidget | None = None
        # Keep blocks list for test compatibility
        self._blocks: list[str] = []

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="_chat-scroll")

    def add_user_message(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        widget = _MessageWidget("👤", "tú", stamp, "_msg-user")
        widget.set_body(message)
        self._mount_message(widget)
        self._blocks.append(f"👤 tú  {stamp}\n{message}")

    def start_jules_message(self) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._active_msg = _MessageWidget("🌹", "jules", stamp, "_msg-jules")
        self._mount_message(self._active_msg)
        self._blocks.append(f"🌹 jules  {stamp}\n")

    def append_token(self, token: str, cursor: bool = True) -> None:
        if self._active_msg is None:
            self.start_jules_message()
        self._active_msg.append_body(token, cursor=cursor)  # type: ignore[union-attr]
        # Update blocks for test compatibility
        if self._blocks:
            header = self._blocks[-1].split("\n")[0]
            body = self._active_msg._body_text  # type: ignore[union-attr]
            self._blocks[-1] = f"{header}\n{body}"
        self.query_one("#_chat-scroll", VerticalScroll).scroll_end(animate=False)

    def append_thought(self, token: str) -> None:
        if self._active_msg is None:
            self.start_jules_message()
        self._active_msg.append_thought(token)  # type: ignore[union-attr]
        self.query_one("#_chat-scroll", VerticalScroll).scroll_end(animate=False)

    def finalize_message(self, refs: list[str] | None = None) -> None:
        if self._active_msg is not None:
            if refs:
                self._active_msg.append_body(f"\n\n📄 Referencias: {', '.join(refs)}", cursor=False)
            self._active_msg.finalize()
            self._active_msg = None

    def clear(self) -> None:
        scroll = self.query_one("#_chat-scroll", VerticalScroll)
        scroll.remove_children()
        self._active_msg = None
        self._blocks.clear()

    def on_chat_log_append_token(self, message: AppendToken) -> None:
        self.append_token(message.token)

    def _mount_message(self, widget: _MessageWidget) -> None:
        scroll = self.query_one("#_chat-scroll", VerticalScroll)
        scroll.mount(widget)
        scroll.scroll_end(animate=False)
