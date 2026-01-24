"""Braindump CLI - Manage your markdown journal entries."""

import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pyperclip
import typer
import yaml
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, FormattedTextControl
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.layout.dimension import LayoutDimension
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Detect if running on macOS
IS_MACOS = platform.system() == "Darwin"

def show_main(ctx: typer.Context) -> None:
    """Show brief description when dump is called without a command."""
    if ctx.invoked_subcommand is None:
        console.print()
        console.print(f"[{MONOKAI['violet']}]Braindump[/{MONOKAI['violet']}] - A CLI tool for managing markdown journal entries. Type[{MONOKAI['cyan']}] dump help[/{MONOKAI['cyan']}] for instructions.")
        console.print()
        console.print(f"[bold {MONOKAI['grey']}]By Matej Groombridge, Jan 2026.[bold /{MONOKAI['grey']}]")
        console.print()


app = typer.Typer(
    name="dump",
    help="A CLI tool for managing markdown journal entries.",
    no_args_is_help=False,
    invoke_without_command=True,
    callback=show_main,
)

console = Console()

# Monokai Pro colour scheme
MONOKAI = {
    "yellow": "#FFD866",
    "orange": "#FC9867",
    "red": "#FF6188",
    "magenta": "#FF6188",
    "violet": "#AB9DF2",
    "blue": "#78DCE8",
    "cyan": "#78DCE8",
    "green": "#A9DC76",
    "grey": "#939293",
    "white": "#FCFCFA",
}

# Journal directory path
JOURNAL_DIR = Path.home() / "dumps"


def print_padded(*args, **kwargs) -> None:
    """Print with padding above and below."""
    console.print()
    console.print(*args, **kwargs)
    console.print()


def get_file_id(filepath: Path) -> int:
    """Get the display ID for a file based on sorted order."""
    files = get_sorted_files(descending=True)
    for idx, f in enumerate(files, start=1):
        if f == filepath:
            return idx
    return 0


def format_frontmatter_display(filepath: Path, frontmatter_data: dict) -> tuple:
    """Format frontmatter for display in the panel. Returns (file_id, display_text)."""
    file_id = get_file_id(filepath)
    
    # Parse date from filename (YYYYMMDDXX.md)
    stem = filepath.stem
    if len(stem) >= 8:
        try:
            year = stem[0:4]
            month = stem[4:6]
            day = stem[6:8]
            date_str = f"{day}/{month}/{year}"
        except (ValueError, IndexError):
            date_str = frontmatter_data.get("date", "Unknown")
    else:
        date_str = frontmatter_data.get("date", "Unknown")
    
    synthesised = frontmatter_data.get("synthesised", False)
    synthesised_str = "True" if synthesised else "False"
    
    tags = frontmatter_data.get("tags", [])
    
    lines = [f"Date: {date_str}", f"Synthesised: {synthesised_str}"]
    
    if tags and isinstance(tags, list) and len(tags) > 0:
        tags_str = ", ".join(str(t) for t in tags)
        lines.append(f"Tags: {tags_str}")
    elif tags and isinstance(tags, str):
        lines.append(f"Tags: {tags}")
    
    return (file_id, "\n".join(lines))


def edit_in_terminal(filepath: Path, all_files: List[Path] = None, current_index: int = 0) -> Optional[Path]:
    """Open a file for editing in a full-screen bullet point editor.
    
    Returns the next file to open if cycling, or None if done.
    """
    content = filepath.read_text(encoding="utf-8")
    
    # Parse frontmatter
    frontmatter_data = {}
    frontmatter_raw = ""
    body = content
    
    if content.startswith("---"):
        end_index = content.find("---", 3)
        if end_index != -1:
            frontmatter_raw = content[:end_index + 3]
            yaml_content = content[3:end_index].strip()
            try:
                frontmatter_data = yaml.safe_load(yaml_content) or {}
            except yaml.YAMLError:
                frontmatter_data = {}
            body = content[end_index + 3:].strip()
    
    # Stylized bullet characters for different indentation levels
    BULLET_CHARS = [
        "\u2022",  # Level 1: • (bullet)
        "\u25E6",  # Level 2: ◦ (white bullet)
        "\u2023",  # Level 3: ‣ (triangular bullet)
        "\u2043",  # Level 4: ⁃ (hyphen bullet)
        "\u25AA",  # Level 5: ▪ (black small square)
    ]
    INDENT = "  "
    MAX_LEVEL = 5
    
    def get_bullet_for_level(level: int) -> str:
        """Get the appropriate bullet character for an indentation level."""
        idx = min(level - 1, len(BULLET_CHARS) - 1)
        return BULLET_CHARS[idx] + " "
    
    def normalize_bullets(text: str) -> str:
        """Convert any bullet character to the appropriate one based on indent level."""
        lines = []
        for line in text.split("\n"):
            stripped = line.lstrip(" ")
            spaces = len(line) - len(stripped)
            level = (spaces // 2) + 1
            
            # Check if line starts with any bullet character
            for bullet_char in BULLET_CHARS + ["\u2022", "-"]:
                if stripped.startswith(bullet_char + " "):
                    content = stripped[len(bullet_char) + 1:]
                    new_bullet = get_bullet_for_level(level)
                    lines.append(" " * spaces + new_bullet + content)
                    break
            else:
                lines.append(line)
        return "\n".join(lines)
    
    # Parse existing body - convert markdown bullets to styled unicode bullets
    initial_text = ""
    if body:
        lines = []
        for line in body.split("\n"):
            stripped = line.lstrip(" ")
            spaces = len(line) - len(stripped)
            level = (spaces // 2) + 1
            
            # Convert - or • to styled bullet
            if stripped.startswith("- "):
                content = stripped[2:]
                bullet = get_bullet_for_level(level)
                lines.append(" " * spaces + bullet + content)
            elif stripped.startswith("\u2022 "):
                content = stripped[2:]
                bullet = get_bullet_for_level(level)
                lines.append(" " * spaces + bullet + content)
            else:
                lines.append(line)
        initial_text = "\n".join(lines)
    
    # If empty, start with a level 1 bullet
    if not initial_text.strip():
        initial_text = get_bullet_for_level(1)
    
    # State for the editor
    save_on_exit = [False]
    next_file = [None]  # For note cycling
    last_enter_was_empty = [False]  # Track for double-enter save
    
    # Create key bindings
    kb = KeyBindings()
    
    def get_current_line(buffer: Buffer) -> str:
        """Get the current line text."""
        doc = buffer.document
        return doc.current_line
    
    def get_line_bullet_info(line: str) -> tuple:
        """Extract bullet info from a line. Returns (indent_spaces, bullet_char, content)."""
        stripped = line.lstrip(" ")
        spaces = len(line) - len(stripped)
        
        for bullet_char in BULLET_CHARS:
            if stripped.startswith(bullet_char + " "):
                return (spaces, bullet_char, stripped[len(bullet_char) + 1:])
        
        # Fallback for markdown bullet
        if stripped.startswith("- "):
            return (spaces, "-", stripped[2:])
        
        return (spaces, None, stripped)
    
    def get_current_line_indent_level(buffer: Buffer) -> int:
        """Get the indentation level of the current line."""
        line = get_current_line(buffer)
        # Count leading spaces (2 spaces per level)
        stripped = line.lstrip(" ")
        spaces = len(line) - len(stripped)
        return (spaces // 2) + 1
    
    def set_line_indent(buffer: Buffer, new_level: int) -> None:
        """Set the indentation level of the current line with appropriate bullet."""
        doc = buffer.document
        line = doc.current_line
        
        # Get current bullet info
        spaces, old_bullet, content = get_line_bullet_info(line)
        
        # Build new line with correct bullet for new level
        new_indent = INDENT * (new_level - 1)
        new_bullet = get_bullet_for_level(new_level)
        
        if old_bullet is not None:
            new_line = new_indent + new_bullet + content
        else:
            # No bullet found, just adjust indent
            stripped = line.lstrip(" ")
            new_line = new_indent + stripped
        
        # Calculate new cursor position
        line_start = doc.cursor_position - doc.cursor_position_col
        line_end = line_start + len(line)
        
        # Calculate where cursor should be in the new line
        old_col = doc.cursor_position_col
        old_prefix_len = spaces + (len(old_bullet) + 1 if old_bullet else 0)
        new_prefix_len = len(new_indent) + len(new_bullet)
        
        if old_col <= old_prefix_len:
            # Cursor was in prefix area, move to after new prefix
            new_col = new_prefix_len
        else:
            # Cursor was in content, adjust by prefix difference
            new_col = old_col + (new_prefix_len - old_prefix_len)
        
        # Replace the line
        new_text = buffer.text[:line_start] + new_line + buffer.text[line_end:]
        new_cursor = line_start + max(0, min(new_col, len(new_line)))
        
        buffer.set_document(Document(new_text, new_cursor))
    
    @kb.add(Keys.Tab)
    def handle_tab(event):
        """Tab increases indentation of current line (max 5 levels)."""
        current_level = get_current_line_indent_level(event.current_buffer)
        if current_level < MAX_LEVEL:
            set_line_indent(event.current_buffer, current_level + 1)
    
    @kb.add(Keys.BackTab)  # Shift+Tab
    def handle_shift_tab(event):
        """Shift+Tab decreases indentation of current line."""
        current_level = get_current_line_indent_level(event.current_buffer)
        if current_level > 1:
            set_line_indent(event.current_buffer, current_level - 1)
    
    @kb.add(Keys.Enter)
    def handle_enter(event):
        """Enter creates a new bullet at the same indentation level.
        
        Double-enter on empty level 1 bullet exits and saves.
        """
        buffer = event.current_buffer
        doc = buffer.document
        current_line = doc.current_line
        
        # Get current indentation level
        spaces, bullet_char, content = get_line_bullet_info(current_line)
        current_level = (spaces // 2) + 1
        indent = " " * spaces
        
        # Check if current line is empty bullet
        is_empty_bullet = bullet_char is not None and content.strip() == ""
        
        if is_empty_bullet:
            if current_level > 1:
                # Decrease indent and reset double-enter tracker
                set_line_indent(buffer, current_level - 1)
                last_enter_was_empty[0] = False
                return
            else:
                # Level 1 empty bullet - check for double-enter
                if last_enter_was_empty[0]:
                    # Second enter on empty level 1 - save and exit
                    save_on_exit[0] = True
                    console.print()
                    console.print(f"[{MONOKAI['green']}]Exited[/{MONOKAI['green']}] [{MONOKAI['cyan']}]{filepath.name}[/{MONOKAI['cyan']}]")
                    console.print()
                    event.app.exit()
                    return
                else:
                    # First enter on empty level 1 - mark it
                    last_enter_was_empty[0] = True
                    return
        
        # Reset double-enter tracker since we're creating a new bullet
        last_enter_was_empty[0] = False
        
        # Insert newline with bullet at same indent level
        new_bullet_char = get_bullet_for_level(current_level)
        new_bullet = "\n" + indent + new_bullet_char
        buffer.insert_text(new_bullet)
    
    @kb.add(Keys.Backspace)
    def handle_backspace(event):
        """Backspace: delete char, or merge with previous line if at line start after bullet."""
        buffer = event.current_buffer
        doc = buffer.document
        
        # Reset double-enter tracker on any edit
        last_enter_was_empty[0] = False
        
        # If at the very beginning, do nothing
        if doc.cursor_position == 0:
            return
        
        current_line = doc.current_line
        col = doc.cursor_position_col
        
        # Check if we're right after the bullet on this line
        spaces, bullet_char, content = get_line_bullet_info(current_line)
        
        if bullet_char is not None:
            bullet_end = spaces + len(bullet_char) + 1  # +1 for the space after bullet
            
            if col == bullet_end:
                # At start of content after bullet - delete the entire line and merge up
                line_start = doc.cursor_position - col
                
                # Find the end of this line
                rest = buffer.text[doc.cursor_position:]
                newline_pos = rest.find("\n")
                if newline_pos == -1:
                    line_end = len(buffer.text)
                else:
                    line_end = doc.cursor_position + newline_pos
                
                # Get content after bullet on this line
                content_after_bullet = content
                
                if line_start > 0:
                    # There's a previous line - merge content to it
                    # Remove the newline before this line and the bullet
                    prev_newline = line_start - 1
                    new_text = buffer.text[:prev_newline] + content_after_bullet + buffer.text[line_end:]
                    
                    # Find where to put cursor (end of previous line)
                    prev_line_start = buffer.text.rfind("\n", 0, prev_newline)
                    if prev_line_start == -1:
                        prev_line_start = 0
                    else:
                        prev_line_start += 1
                    prev_line_end = prev_newline
                    new_cursor = prev_line_end
                    
                    buffer.set_document(Document(new_text, new_cursor))
                else:
                    # First line - just remove the bullet, keep content
                    if content_after_bullet:
                        new_text = content_after_bullet + buffer.text[line_end:]
                        buffer.set_document(Document(new_text, 0))
                    # If no content after bullet, don't delete the only bullet
                return
        
        # Normal backspace - delete previous character
        buffer.delete_before_cursor(1)
    
    # Save keybinding - Cmd+S on Mac, Ctrl+S elsewhere
    if IS_MACOS:
        @kb.add("c-s")  # Cmd+S maps to c-s in prompt_toolkit on macOS
        def handle_save_mac(event):
            """Cmd+S saves and exits."""
            save_on_exit[0] = True
            event.app.exit()
    else:
        @kb.add(Keys.ControlS)
        def handle_save(event):
            """Ctrl+S saves and exits."""
            save_on_exit[0] = True
            event.app.exit()
    
    # Cancel keybinding - Cmd+X on Mac, Ctrl+X elsewhere  
    if IS_MACOS:
        @kb.add("c-x")  # Cmd+X maps to c-x in prompt_toolkit on macOS
        def handle_cancel_mac(event):
            """Cmd+X cancels without saving."""
            save_on_exit[0] = False
            event.app.exit()
    else:
        @kb.add(Keys.ControlX)
        def handle_cancel(event):
            """Ctrl+X cancels without saving."""
            save_on_exit[0] = False
            event.app.exit()
    
    @kb.add(Keys.Escape)
    def handle_escape(event):
        """Escape cancels without saving."""
        save_on_exit[0] = False
        event.app.exit()
    
    # Note cycling - Ctrl+N/Ctrl+P for next/previous note
    if all_files and len(all_files) > 1:
        @kb.add("c-n")
        def handle_next_note(event):
            """Cycle to next note."""
            save_on_exit[0] = True
            next_idx = (current_index + 1) % len(all_files)
            next_file[0] = all_files[next_idx]
            event.app.exit()
        
        @kb.add("c-p")
        def handle_prev_note(event):
            """Cycle to previous note."""
            save_on_exit[0] = True
            next_idx = (current_index - 1) % len(all_files)
            next_file[0] = all_files[next_idx]
            event.app.exit()
    
    @kb.add(Keys.Down)
    def handle_down_arrow(event):
        """Down arrow - move down or create new bullet if at end."""
        buffer = event.current_buffer
        doc = buffer.document
        
        # Check if we're on the last line
        lines = buffer.text.split("\n")
        current_line_num = doc.text_before_cursor.count("\n")
        
        if current_line_num >= len(lines) - 1:
            # On the last line - create a new bullet
            current_line = doc.current_line
            spaces, bullet_char, _ = get_line_bullet_info(current_line)
            current_level = (spaces // 2) + 1
            indent = " " * spaces
            
            # Move cursor to end of line first
            buffer.cursor_position = len(buffer.text)
            
            # Insert newline with bullet at same indent level
            new_bullet_char = get_bullet_for_level(current_level)
            new_bullet = "\n" + indent + new_bullet_char
            buffer.insert_text(new_bullet)
        else:
            # Not on last line - use natural down navigation
            # Move down accounting for visual wrapping
            buffer.cursor_down()
    
    @kb.add(Keys.Up)
    def handle_up_arrow(event):
        """Up arrow - move up accounting for visual line wrapping."""
        buffer = event.current_buffer
        buffer.cursor_up()
    
    # Create buffer with initial content
    buffer = Buffer(
        document=Document(initial_text, len(initial_text)),
        multiline=True,
    )
    
    # Build header text
    if frontmatter_data:
        file_id = get_file_id(filepath)
        stem = filepath.stem
        if len(stem) >= 8:
            try:
                date_str = f"{stem[6:8]}/{stem[4:6]}/{stem[0:4]}"
            except (ValueError, IndexError):
                date_str = frontmatter_data.get("date", "Unknown")
        else:
            date_str = frontmatter_data.get("date", "Unknown")
        
        synthesised = frontmatter_data.get("synthesised", False)
        tags = frontmatter_data.get("tags", [])
        
        header_parts = [f"Brain Dump #{file_id}", f"Date: {date_str}"]
        if tags:
            if isinstance(tags, list):
                header_parts.append(f"Tags: {', '.join(str(t) for t in tags)}")
            else:
                header_parts.append(f"Tags: {tags}")
        header_text = "  |  ".join(header_parts)
    else:
        header_text = "New Brain Dump"
    
    # Status bar text with platform-appropriate keybindings
    if IS_MACOS:
        status_text = " ⌘S: Save  |  ⌘X/Esc: Cancel  |  Tab: Indent  |  ⇧Tab: Unindent "
        if all_files and len(all_files) > 1:
            status_text = " ⌘S: Save  |  ⌘X/Esc: Cancel  |  ^N/^P: Next/Prev Note  |  Tab/⇧Tab: Indent "
    else:
        status_text = " Ctrl+S: Save  |  Ctrl+X/Esc: Cancel  |  Tab: Indent  |  Shift+Tab: Unindent "
        if all_files and len(all_files) > 1:
            status_text = " Ctrl+S: Save  |  Ctrl+X/Esc: Cancel  |  Ctrl+N/P: Next/Prev  |  Tab: Indent "
    
    # Create the layout
    layout = Layout(
        HSplit([
            # Header bar
            Window(
                content=FormattedTextControl(lambda: header_text),
                height=1,
                style="class:header",
            ),
            # Separator
            Window(height=1, char="─", style="class:separator"),
            # Main editor area
            Window(
                content=BufferControl(buffer=buffer),
                wrap_lines=True,
            ),
            # Separator
            Window(height=1, char="─", style="class:separator"),
            # Status bar
            Window(
                content=FormattedTextControl(lambda: status_text),
                height=1,
                style="class:status",
            ),
        ])
    )
    
    # Define styles (using Monokai colors)
    style = Style.from_dict({
        "header": "bg:#AB9DF2 #1e1e1e bold",
        "separator": "#939293",
        "status": "bg:#3e3e3e #A9DC76",
    })
    
    # Create and run the application
    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=True,
    )
    
    console.print()
    
    try:
        app.run()
    except (KeyboardInterrupt, EOFError):
        save_on_exit[0] = False
    
    # Handle save
    if save_on_exit[0]:
        # Get final content from buffer
        final_text = buffer.text
        
        # Clean up: remove empty bullets and trailing whitespace per line
        edited_lines = []
        for line in final_text.split("\n"):
            stripped = line.rstrip()
            # Skip completely empty lines
            if not stripped:
                continue
            # Skip lines that are just a bullet with no content
            line_content = stripped.lstrip(" ")
            is_empty_bullet = False
            for bullet_char in BULLET_CHARS:
                if line_content == bullet_char or line_content == bullet_char + " ":
                    is_empty_bullet = True
                    break
            if is_empty_bullet:
                continue
            edited_lines.append(stripped)
        
        # Get original lines for comparison (normalize all bullet types)
        def normalize_line(ln: str) -> str:
            """Normalize a line for comparison by converting bullets to standard form."""
            s = ln.rstrip()
            content = s.lstrip(" ")
            spaces = len(s) - len(content)
            # Check for any bullet type and normalize to •
            for bc in BULLET_CHARS + ["-"]:
                if content.startswith(bc + " "):
                    return " " * spaces + "\u2022 " + content[len(bc) + 1:]
            return s
        
        original_lines = []
        if body:
            for line in body.split("\n"):
                stripped = line.rstrip()
                if stripped:
                    original_lines.append(normalize_line(stripped))
        
        edited_normalized = [normalize_line(ln) for ln in edited_lines]
        
        # Check if content is unchanged
        if edited_normalized == original_lines:
            if len(original_lines) == 0:
                # Empty new file - delete it
                filepath.unlink()
                console.print(f"[{MONOKAI['yellow']}]Empty dump deleted.[/{MONOKAI['yellow']}]")
            if not next_file[0]:
                console.print()
            return next_file[0]
        
        # Build final content
        new_body = "\n".join(edited_lines)
        
        if frontmatter_raw:
            new_content = frontmatter_raw + "\n\n" + new_body + "\n"
        else:
            new_content = new_body + "\n"
        
        filepath.write_text(new_content, encoding="utf-8")
        console.print(f"[{MONOKAI['green']}]Saved[/{MONOKAI['green']}] [{MONOKAI['cyan']}]{filepath.name}[/{MONOKAI['cyan']}]")
        if not next_file[0]:
            console.print()
    else:
        console.print(f"[{MONOKAI['yellow']}]Cancelled. No changes saved.[/{MONOKAI['yellow']}]")
        console.print()
    
    return next_file[0]


def get_sorted_files(descending: bool = True) -> List[Path]:
    """Get all markdown files sorted by filename."""
    ensure_journal_dir()
    files = list(JOURNAL_DIR.glob("*.md"))
    return sorted(files, key=lambda f: f.name, reverse=descending)


def ensure_journal_dir() -> None:
    """Ensure the journal directory exists."""
    if not JOURNAL_DIR.exists():
        JOURNAL_DIR.mkdir(parents=True)
        console.print(f"[{MONOKAI['green']}]Created journal directory at {JOURNAL_DIR}[/{MONOKAI['green']}]")


def get_today_date_prefix() -> str:
    """Get today's date in YYYYMMDD format."""
    return datetime.now().strftime("%Y%m%d")


def get_next_increment() -> str:
    """Determine the next increment number for today's entries."""
    ensure_journal_dir()
    today_prefix = get_today_date_prefix()
    
    existing_files = list(JOURNAL_DIR.glob(f"{today_prefix}*.md"))
    
    if not existing_files:
        return "01"
    
    # Extract increment numbers from existing files
    increments = []
    for f in existing_files:
        # Filename format: YYYYMMDDXX.md
        stem = f.stem
        if len(stem) == 10:
            try:
                increment = int(stem[8:10])
                increments.append(increment)
            except ValueError:
                continue
    
    if not increments:
        return "01"
    
    next_increment = max(increments) + 1
    return f"{next_increment:02d}"


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    
    try:
        # Find the closing ---
        end_index = content.find("---", 3)
        if end_index == -1:
            return {}
        
        yaml_content = content[3:end_index].strip()
        return yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        return {}


@app.command()
def new(
    tags: Optional[List[str]] = typer.Argument(
        None,
        help="Optional tags for the journal entry (e.g., health career)",
    ),
) -> None:
    """Create a new journal entry with optional tags."""
    ensure_journal_dir()
    
    today_prefix = get_today_date_prefix()
    increment = get_next_increment()
    filename = f"{today_prefix}{increment}.md"
    filepath = JOURNAL_DIR / filename
    
    # Format date for frontmatter
    date_formatted = datetime.now().strftime("%Y-%m-%d")
    
    # Build tags list - empty if no tags provided
    tag_list = tags if tags else []
    
    # Create YAML frontmatter
    if tag_list:
        frontmatter = f"""---
date: {date_formatted}
synthesised: false
tags: [{', '.join(tag_list)}]
---
"""
    else:
        frontmatter = f"""---
date: {date_formatted}
synthesised: false
---
"""
    
    # Write the file
    filepath.write_text(frontmatter, encoding="utf-8")
    
    # Open in terminal editor
    edit_in_terminal(filepath)


@app.command(name="help")
def show_help() -> None:
    """Show detailed help with all commands and editor controls."""
    console.print()
    console.print(f"[{MONOKAI['grey']}]Commands:[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]new[/{MONOKAI['cyan']}]        [{MONOKAI['grey']}]Create a new journal entry[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]open[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Open an entry in terminal editor[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]edit[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Open an entry in external editor[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]list[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]View recent entries[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]copy[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Copy specific entries by ID to clipboard[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]tag[/{MONOKAI['cyan']}]        [{MONOKAI['grey']}]Add or remove tags[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]synth[/{MONOKAI['cyan']}]      [{MONOKAI['grey']}]Toggle synthesised status[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]delete[/{MONOKAI['cyan']}]     [{MONOKAI['grey']}]Delete an entry[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]sync[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Pull remote changes, commit and push[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]pull[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Pull remote changes only[/{MONOKAI['grey']}]")
    console.print()
    console.print(f"[{MONOKAI['grey']}]Editor Controls:[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Arrow Keys[/{MONOKAI['orange']}]   [{MONOKAI['grey']}]Navigate (accounts for text wrapping)[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Down Arrow[/{MONOKAI['orange']}]   [{MONOKAI['grey']}]Move down, or create new bullet at end[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Enter[/{MONOKAI['orange']}]        [{MONOKAI['grey']}]New bullet (2x Enter on empty L1 bullet = save)[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Tab[/{MONOKAI['orange']}]          [{MONOKAI['grey']}]Increase indentation[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Shift+Tab[/{MONOKAI['orange']}]    [{MONOKAI['grey']}]Decrease indentation[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Backspace[/{MONOKAI['orange']}]    [{MONOKAI['grey']}]Delete character, or merge line at bullet start[/{MONOKAI['grey']}]")
    if IS_MACOS:
        console.print(f"  [{MONOKAI['orange']}]⌘S[/{MONOKAI['orange']}]           [{MONOKAI['grey']}]Save and exit[/{MONOKAI['grey']}]")
        console.print(f"  [{MONOKAI['orange']}]⌘X[/{MONOKAI['orange']}]           [{MONOKAI['grey']}]Cancel without saving[/{MONOKAI['grey']}]")
        console.print(f"  [{MONOKAI['orange']}]^N / ^P[/{MONOKAI['orange']}]      [{MONOKAI['grey']}]Cycle to next/previous note[/{MONOKAI['grey']}]")
    else:
        console.print(f"  [{MONOKAI['orange']}]Ctrl+S[/{MONOKAI['orange']}]       [{MONOKAI['grey']}]Save and exit[/{MONOKAI['grey']}]")
        console.print(f"  [{MONOKAI['orange']}]Ctrl+X[/{MONOKAI['orange']}]       [{MONOKAI['grey']}]Cancel without saving[/{MONOKAI['grey']}]")
        console.print(f"  [{MONOKAI['orange']}]Ctrl+N / P[/{MONOKAI['orange']}]   [{MONOKAI['grey']}]Cycle to next/previous note[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Escape[/{MONOKAI['orange']}]       [{MONOKAI['grey']}]Cancel without saving[/{MONOKAI['grey']}]")
    console.print()


def is_git_repo() -> bool:
    """Check if journal directory is a git repository."""
    git_dir = JOURNAL_DIR / ".git"
    return git_dir.exists()


def has_remote() -> bool:
    """Check if the git repository has a remote configured."""
    if not is_git_repo():
        return False
    result = subprocess.run(
        ["git", "remote"],
        cwd=JOURNAL_DIR,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() != ""


def has_uncommitted_changes() -> bool:
    """Check if there are uncommitted changes in the repository."""
    if not is_git_repo():
        return False
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=JOURNAL_DIR,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() != ""


def pull_remote(silent: bool = False) -> bool:
    """Pull changes from remote. Returns True if successful."""
    if not is_git_repo() or not has_remote():
        return True  # Nothing to pull from
    
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=JOURNAL_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if not silent:
                console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Failed to pull remote changes: {result.stderr}")
            return False
        return True
    except Exception:
        return False


def check_and_pull_remote(silent: bool = False) -> bool:
    """Check if remote has updates and pull them. Returns True if successful or no remote."""
    if not is_git_repo() or not has_remote():
        return True
    
    # Check for uncommitted changes first
    if has_uncommitted_changes():
        if not silent:
            console.print()
            console.print(f"[{MONOKAI['yellow']}]⚠[/{MONOKAI['yellow']}] You have uncommitted local changes. Run [{MONOKAI['cyan']}]dump sync[/{MONOKAI['cyan']}] to synchronise.")
            console.print()
        return True  # Continue anyway, but warn the user
    
    try:
        # Fetch remote to check for updates
        result = subprocess.run(
            ["git", "fetch"],
            cwd=JOURNAL_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return True  # Fetch failed, but continue anyway
        
        # Check if local is behind remote
        result = subprocess.run(
            ["git", "status", "-uno"],
            cwd=JOURNAL_DIR,
            capture_output=True,
            text=True,
        )
        
        if "Your branch is behind" in result.stdout:
            if not silent:
                console.print()
                console.print(f"[{MONOKAI['blue']}]↓[/{MONOKAI['blue']}] Pulling remote changes...")
            
            if not pull_remote(silent):
                return False
            
            if not silent:
                console.print(f"[{MONOKAI['green']}]✓[/{MONOKAI['green']}] Synced with remote.")
                console.print()
        
        return True
    except Exception:
        return True  # Continue anyway on any error


@app.command()
def sync() -> None:
    """Synchronise journal entries with git remote."""
    ensure_journal_dir()
    
    # Check if journal directory is a git repository
    if not is_git_repo():
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Journal directory is not a git repository.")
        console.print(f"  Initialise with: [{MONOKAI['cyan']}]cd {JOURNAL_DIR} && git init[/{MONOKAI['cyan']}]")
        console.print()
        raise typer.Exit(1)
    
    if not has_remote():
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] No remote configured for the repository.")
        console.print(f"  Add a remote with: [{MONOKAI['cyan']}]cd {JOURNAL_DIR} && git remote add origin <url>[/{MONOKAI['cyan']}]")
        console.print()
        raise typer.Exit(1)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    commit_message = f"Log: {date_str}"
    
    try:
        with console.status(f"[bold {MONOKAI['blue']}]Synchronising...[/bold {MONOKAI['blue']}]", spinner="dots"):
            # First, fetch and check for remote changes
            result = subprocess.run(
                ["git", "fetch"],
                cwd=JOURNAL_DIR,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(f"git fetch failed: {result.stderr}")
            
            # Check if we need to stash local changes before pulling
            has_changes = has_uncommitted_changes()
            stashed = False
            
            if has_changes:
                # Git add and stash
                result = subprocess.run(
                    ["git", "add", "."],
                    cwd=JOURNAL_DIR,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise Exception(f"git add failed: {result.stderr}")
                
                result = subprocess.run(
                    ["git", "stash", "push", "-m", "braindump-auto-stash"],
                    cwd=JOURNAL_DIR,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and "No local changes" not in result.stdout:
                    stashed = True
            
            # Pull remote changes with rebase
            result = subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=JOURNAL_DIR,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Try to restore stash if pull failed
                if stashed:
                    subprocess.run(
                        ["git", "stash", "pop"],
                        cwd=JOURNAL_DIR,
                        capture_output=True,
                        text=True,
                    )
                raise Exception(f"git pull failed: {result.stderr}")
            
            # Pop stash if we stashed
            if stashed:
                result = subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=JOURNAL_DIR,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise Exception(f"git stash pop failed (you may have conflicts): {result.stderr}")
            
            # Git add
            result = subprocess.run(
                ["git", "add", "."],
                cwd=JOURNAL_DIR,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(f"git add failed: {result.stderr}")
            
            # Git commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=JOURNAL_DIR,
                capture_output=True,
                text=True,
            )
            # Ignore "nothing to commit" errors
            if result.returncode != 0 and "nothing to commit" not in result.stdout:
                if "nothing to commit" not in result.stderr:
                    raise Exception(f"git commit failed: {result.stderr}")
            
            # Git push
            result = subprocess.run(
                ["git", "push"],
                cwd=JOURNAL_DIR,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(f"git push failed: {result.stderr}")
        
        console.print()
        console.print(f"[{MONOKAI['green']}]✓ Successfully synchronised with remote.[/{MONOKAI['green']}]")
        console.print(f"  [{MONOKAI['grey']}]Commit: {commit_message}[/{MONOKAI['grey']}]")
        console.print()
        
    except Exception as e:
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Synchronisation failed: {e}")
        console.print()
        raise typer.Exit(1)


@app.command()
def pull() -> None:
    """Pull latest changes from git remote without pushing."""
    ensure_journal_dir()
    
    if not is_git_repo():
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Journal directory is not a git repository.")
        console.print(f"  Initialise with: [{MONOKAI['cyan']}]cd {JOURNAL_DIR} && git init[/{MONOKAI['cyan']}]")
        console.print()
        raise typer.Exit(1)
    
    if not has_remote():
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] No remote configured for the repository.")
        console.print(f"  Add a remote with: [{MONOKAI['cyan']}]cd {JOURNAL_DIR} && git remote add origin <url>[/{MONOKAI['cyan']}]")
        console.print()
        raise typer.Exit(1)
    
    if has_uncommitted_changes():
        console.print()
        console.print(f"[{MONOKAI['yellow']}]⚠[/{MONOKAI['yellow']}] You have uncommitted local changes.")
        console.print(f"  Run [{MONOKAI['cyan']}]dump sync[/{MONOKAI['cyan']}] to commit and sync your changes first.")
        console.print()
        raise typer.Exit(1)
    
    try:
        with console.status(f"[bold {MONOKAI['blue']}]Pulling...[/bold {MONOKAI['blue']}]", spinner="dots"):
            result = subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=JOURNAL_DIR,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise Exception(f"git pull failed: {result.stderr}")
        
        console.print()
        console.print(f"[{MONOKAI['green']}]✓ Successfully pulled from remote.[/{MONOKAI['green']}]")
        console.print()
        
    except Exception as e:
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Pull failed: {e}")
        console.print()
        raise typer.Exit(1)


@app.command()
def copy(
    ids: List[int] = typer.Argument(
        None,
        help="IDs of files to copy (e.g., 'dump copy 1 3 6 7'). Copies latest if none provided.",
    ),
) -> None:
    """Copy specific journal entries by ID to clipboard."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    # If no IDs provided, default to copying the latest (ID 1)
    if not ids:
        ids = [1]
    
    # Validate all IDs
    invalid_ids = [i for i in ids if i < 1 or i > len(files)]
    if invalid_ids:
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID(s): {', '.join(map(str, invalid_ids))}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get files by IDs (1-indexed)
    files_to_copy = [files[i - 1] for i in ids]
    
    # Concatenate content with horizontal rules and add ID metadata
    contents = []
    for file_id, f in zip(ids, files_to_copy):
        content = f.read_text(encoding="utf-8")
        # Insert ID into frontmatter
        if content.startswith("---"):
            end_index = content.find("---", 3)
            if end_index != -1:
                # Insert id after the opening ---
                frontmatter_content = content[3:end_index]
                rest_of_file = content[end_index:]
                content = f"---\nid: {file_id}{frontmatter_content}{rest_of_file}"
        contents.append(content)
    
    # Add intro text and combine with horizontal rules
    id_str = ", ".join(map(str, ids))
    intro = f"Here is a copy of my brain dump(s) #{id_str}:"
    combined = intro + "\n\n---\n\n" + "\n\n---\n\n".join(contents)
    
    # Copy to clipboard
    try:
        pyperclip.copy(combined)
        if len(ids) == 1:
            print_padded(f"[{MONOKAI['green']}]Copied dump #{ids[0]} to clipboard.[/{MONOKAI['green']}]")
        else:
            print_padded(f"[{MONOKAI['green']}]Copied dumps #{id_str} to clipboard.[/{MONOKAI['green']}]")
    except pyperclip.PyperclipException as e:
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Failed to copy to clipboard: {e}")
        raise typer.Exit(1)


@app.command(name="list")
def list_entries(
    n: int = typer.Argument(
        10,
        help="Number of entries to display (default: 10)",
    ),
) -> None:
    """Display the last n journal entries."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        return
    
    # Take last n files
    files_to_show = files[:n]
    excluded_count = len(files) - len(files_to_show)
    
    # Create table
    table = Table(title="Brain Dumps", show_header=True, header_style=f"bold {MONOKAI['violet']}")
    table.add_column("ID", style=f"bold {MONOKAI['orange']}", justify="right")
    table.add_column("Date", style=MONOKAI["cyan"])
    table.add_column("Tags", style=MONOKAI["white"], max_width=20, overflow="ellipsis")
    table.add_column("Synthesised", style=MONOKAI["yellow"], justify="center")
    
    # Month names for formatting
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    for idx, f in enumerate(files_to_show, start=1):
        content = f.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)
        
        # Parse date from filename (YYYYMMDDXX.md)
        stem = f.stem
        if len(stem) >= 8:
            try:
                year = stem[0:4]
                month = int(stem[4:6])
                day = int(stem[6:8])
                date_str = f"{month_names[month - 1]} {day}, {year}"
            except (ValueError, IndexError):
                date_str = stem
        else:
            date_str = stem
        
        tags = frontmatter.get("tags", [])
        if isinstance(tags, list):
            tags_str = ", ".join(str(t) for t in tags)
        else:
            tags_str = str(tags)
        
        synthesised = frontmatter.get("synthesised", False)
        synthesised_str = f"[{MONOKAI['green']}]True[/{MONOKAI['green']}]" if synthesised else f"[{MONOKAI['red']}]False[/{MONOKAI['red']}]"
        
        table.add_row(str(idx), date_str, tags_str, synthesised_str)
    
    console.print()
    console.print(table)
    if excluded_count > 0:
        console.print(f"[{MONOKAI['grey']}]  +{excluded_count} more[/{MONOKAI['grey']}]")
    console.print()


@app.command(name="open")
def open_file(
    n: Optional[int] = typer.Argument(
        None,
        help="ID of the file to open (from 'dump list'). Opens latest if not provided.",
    ),
) -> None:
    """Open a journal entry by its ID from the status list.
    
    Use Ctrl+N/Ctrl+P to cycle between notes.
    """
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    # Default to 1 (latest file) if n not provided
    file_id = n if n is not None else 1
    
    if file_id < 1 or file_id > len(files):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get file by ID (1-indexed)
    filepath = files[file_id - 1]
    current_index = file_id - 1
    
    # Open in terminal editor with cycling support
    while filepath:
        next_filepath = edit_in_terminal(filepath, all_files=files, current_index=current_index)
        if next_filepath:
            filepath = next_filepath
            current_index = files.index(next_filepath)
        else:
            break


@app.command(name="synth")
def synth(
    file_id: int = typer.Argument(
        ...,
        help="ID of the file to toggle synthesised status (from 'dump list').",
    ),
) -> None:
    """Toggle the synthesised status of a journal entry."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    if file_id < 1 or file_id > len(files):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get file by ID (1-indexed)
    filepath = files[file_id - 1]
    content = filepath.read_text(encoding="utf-8")
    
    # Parse and toggle synthesised value
    if not content.startswith("---"):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] File has no valid frontmatter.")
        raise typer.Exit(1)
    
    end_index = content.find("---", 3)
    if end_index == -1:
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] File has no valid frontmatter.")
        raise typer.Exit(1)
    
    yaml_content = content[3:end_index].strip()
    rest_of_file = content[end_index + 3:]
    
    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Failed to parse frontmatter.")
        raise typer.Exit(1)
    
    # Toggle synthesised
    current_value = frontmatter.get("synthesised", False)
    new_value = not current_value
    frontmatter["synthesised"] = new_value
    
    # Rebuild the file
    new_yaml = yaml.dump(frontmatter, default_flow_style=None, allow_unicode=True, sort_keys=False)
    new_content = f"---\n{new_yaml}---{rest_of_file}"
    
    filepath.write_text(new_content, encoding="utf-8")
    
    status_str = f"[{MONOKAI['green']}]True[/{MONOKAI['green']}]" if new_value else f"[{MONOKAI['red']}]False[/{MONOKAI['red']}]"
    print_padded(f"[{MONOKAI['orange']}]{filepath.name}[/{MONOKAI['orange']}] synthesised: {status_str}")


@app.command()
def delete(
    file_id: int = typer.Argument(
        ...,
        help="ID of the file to delete (from 'dump list').",
    ),
) -> None:
    """Delete a journal entry."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    if file_id < 1 or file_id > len(files):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get file by ID (1-indexed)
    filepath = files[file_id - 1]
    filename = filepath.name
    
    # Delete the file
    filepath.unlink()
    
    print_padded(f"[{MONOKAI['green']}]Deleted[/{MONOKAI['green']}] [{MONOKAI['orange']}]{filename}[/{MONOKAI['orange']}]")


@app.command()
def edit(
    n: Optional[int] = typer.Argument(
        None,
        help="ID of the file to edit (from 'dump list'). Opens latest if not provided.",
    ),
) -> None:
    """Open a journal entry in your system's default editor."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    # Default to 1 (latest file) if n not provided
    file_id = n if n is not None else 1
    
    if file_id < 1 or file_id > len(files):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get file by ID (1-indexed)
    filepath = files[file_id - 1]
    
    # Open with system default editor
    if sys.platform == "win32":
        os.startfile(filepath)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(filepath)])
    else:
        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(filepath)])
    
    print_padded(f"[{MONOKAI['green']}]Opened[/{MONOKAI['green']}] [{MONOKAI['cyan']}]{filepath.name}[/{MONOKAI['cyan']}] in external editor")


@app.command()
def tag(
    file_id: int = typer.Argument(
        ...,
        help="ID of the file to modify tags (from 'dump list').",
    ),
    actions: List[str] = typer.Argument(
        ...,
        help="Tag actions: add/remove followed by tags (e.g., 'add health exercise remove fitness').",
    ),
) -> None:
    """Add or remove tags from a journal entry."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    if file_id < 1 or file_id > len(files):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Parse actions into add/remove lists
    tags_to_add = []
    tags_to_remove = []
    current_action = None
    
    for item in actions:
        item_lower = item.lower()
        if item_lower == "add":
            current_action = "add"
        elif item_lower == "remove":
            current_action = "remove"
        elif current_action == "add":
            tags_to_add.append(item_lower)
        elif current_action == "remove":
            tags_to_remove.append(item_lower)
        else:
            print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Expected 'add' or 'remove' before '{item}'")
            raise typer.Exit(1)
    
    if not tags_to_add and not tags_to_remove:
        print_padded(f"[{MONOKAI['yellow']}]No tags specified to add or remove.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    # Get file and parse frontmatter
    filepath = files[file_id - 1]
    content = filepath.read_text(encoding="utf-8")
    
    if not content.startswith("---"):
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] File has no valid frontmatter.")
        raise typer.Exit(1)
    
    end_index = content.find("---", 3)
    if end_index == -1:
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] File has no valid frontmatter.")
        raise typer.Exit(1)
    
    yaml_content = content[3:end_index].strip()
    rest_of_file = content[end_index + 3:]
    
    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        print_padded(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Failed to parse frontmatter.")
        raise typer.Exit(1)
    
    # Get current tags
    current_tags = frontmatter.get("tags", [])
    if isinstance(current_tags, str):
        current_tags = [current_tags]
    current_tags = [t.lower() for t in current_tags]
    
    # Apply changes
    added = []
    removed = []
    
    for t in tags_to_add:
        if t not in current_tags:
            current_tags.append(t)
            added.append(t)
    
    for t in tags_to_remove:
        if t in current_tags:
            current_tags.remove(t)
            removed.append(t)
    
    # Update frontmatter
    frontmatter["tags"] = current_tags
    
    # Rebuild the file
    new_yaml = yaml.dump(frontmatter, default_flow_style=None, allow_unicode=True, sort_keys=False)
    new_content = f"---\n{new_yaml}---{rest_of_file}"
    
    filepath.write_text(new_content, encoding="utf-8")
    
    # Build output message
    messages = []
    if added:
        messages.append(f"[{MONOKAI['green']}]+[/{MONOKAI['green']}] {', '.join(added)}")
    if removed:
        messages.append(f"[{MONOKAI['red']}]-[/{MONOKAI['red']}] {', '.join(removed)}")
    
    print_padded(f"[{MONOKAI['orange']}]{filepath.name}[/{MONOKAI['orange']}] " + " ".join(messages))
    if current_tags:
        console.print(f"  Tags: [{MONOKAI['cyan']}]{', '.join(current_tags)}[/{MONOKAI['cyan']}]")
    console.print()


if __name__ == "__main__":
    app()
