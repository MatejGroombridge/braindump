"""Braindump CLI - Manage your markdown journal entries."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pyperclip
import typer
import yaml
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

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


def edit_in_terminal(filepath: Path) -> None:
    """Open a file for editing in the terminal with bullet point indentation."""
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
    
    # Parse existing body into lines
    lines = []
    if body:
        for line in body.split("\n"):
            lines.append(line)
    
    console.print()
    
    # Show formatted frontmatter
    if frontmatter_data:
        file_id, display_text = format_frontmatter_display(filepath, frontmatter_data)
        console.print(Panel(display_text, title=f"Brain Dump #{file_id}", style=MONOKAI['violet'], expand=False))
        console.print()
    
    # Bullet point editor
    BULLET = "\u2022 "
    INDENT = "  "
    
    edited_lines = []
    current_level = 1
    pending_exit = False  # Track if user pressed enter on empty level 1 bullet
    
    # Load existing content and display it (convert - to •)
    if lines:
        for line in lines:
            if line.strip():
                edited_lines.append(line)
                # Display with • instead of -
                display_line = line.replace("- ", "\u2022 ")
                console.print(f"[{MONOKAI['white']}]{display_line}[/{MONOKAI['white']}]")
    
    try:
        while True:
            # Build the prompt with current indentation
            if pending_exit:
                # Waiting for save confirmation - show empty line
                prompt_display = ""
            else:
                indent_str = INDENT * (current_level - 1)
                prompt_display = f"{indent_str}{BULLET}"
            
            # Create key bindings
            kb = KeyBindings()
            action = [None]  # Track what action was taken: 'tab', 'enter', or None
            
            @kb.add(Keys.Tab)
            def handle_tab(event):
                """Tab increases indentation immediately."""
                action[0] = 'tab'
                event.current_buffer.validate_and_handle()
            
            @kb.add(Keys.Enter)
            def handle_enter(event):
                """Enter submits or handles indentation."""
                if event.current_buffer.text == "":
                    action[0] = 'enter_empty'
                else:
                    action[0] = 'enter_text'
                event.current_buffer.validate_and_handle()
            
            @kb.add(Keys.ControlX)
            def handle_cancel(event):
                """Ctrl+X cancels."""
                action[0] = 'cancel'
                event.current_buffer.validate_and_handle()
            
            # Create session for single line input
            session = PromptSession(key_bindings=kb)
            
            try:
                user_input = session.prompt(prompt_display)
            except EOFError:
                break
            
            # Handle actions
            if action[0] == 'cancel':
                # Ctrl+X - cancel and exit immediately
                sys.stdout.write('\033[A\033[K')
                sys.stdout.flush()
                console.print()
                console.print(f"[{MONOKAI['yellow']}]Cancelled. No changes saved.[/{MONOKAI['yellow']}]")
                console.print()
                return
            
            if action[0] == 'tab':
                if pending_exit:
                    # If in pending exit state and tab pressed, cancel exit and start new bullet
                    pending_exit = False
                    current_level = 2
                    sys.stdout.write('\033[A\033[K')
                    sys.stdout.flush()
                    continue
                # Tab - increase indentation, redraw on same line
                current_level = min(current_level + 1, 5)
                # Clear current line and continue (will redraw with new indent)
                sys.stdout.write('\033[A\033[K')  # Move up and clear line
                sys.stdout.flush()
                continue
            
            elif action[0] == 'enter_empty':
                if pending_exit:
                    # Second enter - save and exit
                    sys.stdout.write('\033[A\033[K')
                    sys.stdout.flush()
                    break
                elif current_level == 1:
                    # First enter on empty level 1 bullet - clear bullet, wait for confirm
                    pending_exit = True
                    sys.stdout.write('\033[A\033[K')
                    sys.stdout.flush()
                    continue
                else:
                    # Decrease indentation, redraw on same line
                    current_level = max(1, current_level - 1)
                    sys.stdout.write('\033[A\033[K')  # Move up and clear line
                    sys.stdout.flush()
                    continue
            
            elif action[0] == 'enter_text':
                if pending_exit:
                    # User typed something while in pending exit - cancel exit, add as L1 bullet
                    pending_exit = False
                    edited_lines.append(f"\u2022 {user_input}")
                else:
                    # Add the line with proper markdown formatting
                    md_indent = "  " * (current_level - 1)
                    edited_lines.append(f"{md_indent}\u2022 {user_input}")
            
            else:
                # Fallback - treat as text entry
                if user_input:
                    pending_exit = False
                    md_indent = "  " * (current_level - 1)
                    edited_lines.append(f"{md_indent}\u2022 {user_input}")
        
        # Build final content
        new_body = "\n".join(edited_lines)
        
        # Get original lines (stripped of empty lines)
        original_lines = [l for l in lines if l.strip()]
        
        # Check if content is unchanged
        if edited_lines == original_lines:
            if len(original_lines) == 0:
                # This was a new empty file - delete it
                filepath.unlink()
                console.print()
                console.print(f"[{MONOKAI['yellow']}]Empty dump deleted.[/{MONOKAI['yellow']}]")
                console.print()
            else:
                # No changes made to existing file
                console.print()
            return
        
        if frontmatter_raw:
            new_content = frontmatter_raw + "\n\n" + new_body + "\n"
        else:
            new_content = new_body + "\n"
        
        filepath.write_text(new_content, encoding="utf-8")
        console.print()
        console.print(f"[{MONOKAI['green']}]Saved[/{MONOKAI['green']}] [{MONOKAI['cyan']}]{filepath.name}[/{MONOKAI['cyan']}]")
        console.print()
        
    except (KeyboardInterrupt, EOFError):
        console.print()
        console.print(f"[{MONOKAI['yellow']}]Cancelled. No changes saved.[/{MONOKAI['yellow']}]")
        console.print()


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
    console.print(f"  [{MONOKAI['cyan']}]copy[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Copy entries to clipboard[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]tag[/{MONOKAI['cyan']}]        [{MONOKAI['grey']}]Add or remove tags[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]synth[/{MONOKAI['cyan']}]      [{MONOKAI['grey']}]Toggle synthesised status[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]delete[/{MONOKAI['cyan']}]     [{MONOKAI['grey']}]Delete an entry[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['cyan']}]sync[/{MONOKAI['cyan']}]       [{MONOKAI['grey']}]Synchronise with git[/{MONOKAI['grey']}]")
    console.print()
    console.print(f"[{MONOKAI['grey']}]Editor Controls:[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Enter[/{MONOKAI['orange']}]      [{MONOKAI['grey']}]New bullet at same level[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Tab[/{MONOKAI['orange']}]        [{MONOKAI['grey']}]Increase indentation[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Enter[/{MONOKAI['orange']}]      [{MONOKAI['grey']}](on empty) - Decrease indentation[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Enter[/{MONOKAI['orange']}]      [{MONOKAI['grey']}](twice at empty dot point) - Save and exit[/{MONOKAI['grey']}]")
    console.print(f"  [{MONOKAI['orange']}]Ctrl+X[/{MONOKAI['orange']}]     [{MONOKAI['grey']}]Cancel without saving[/{MONOKAI['grey']}]")
    console.print()


@app.command()
def sync() -> None:
    """Synchronise journal entries with git remote."""
    ensure_journal_dir()
    
    # Check if journal directory is a git repository
    git_dir = JOURNAL_DIR / ".git"
    if not git_dir.exists():
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Journal directory is not a git repository.")
        console.print(f"  Initialise with: [{MONOKAI['cyan']}]cd {JOURNAL_DIR} && git init[/{MONOKAI['cyan']}]")
        console.print()
        raise typer.Exit(1)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    commit_message = f"Log: {date_str}"
    
    try:
        with console.status(f"[bold {MONOKAI['blue']}]Synchronising...[/bold {MONOKAI['blue']}]", spinner="dots"):
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
        console.print(f"[{MONOKAI['green']}]Successfully synchronised with remote.[/{MONOKAI['green']}]")
        console.print(f"  Commit message: [{MONOKAI['cyan']}]{commit_message}[/{MONOKAI['cyan']}]")
        console.print()
        
    except Exception as e:
        console.print()
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Synchronisation failed: {e}")
        console.print()
        raise typer.Exit(1)


@app.command()
def copy(
    n: int = typer.Argument(
        1,
        help="Number of files to copy (default: 1)",
    ),
) -> None:
    """Copy the latest n journal entries to clipboard."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        print_padded(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    # Take top n files
    files_to_copy = files[:n]
    
    # Concatenate content with horizontal rules and add ID metadata
    contents = []
    for idx, f in enumerate(files_to_copy, start=1):
        content = f.read_text(encoding="utf-8")
        # Insert ID into frontmatter
        if content.startswith("---"):
            end_index = content.find("---", 3)
            if end_index != -1:
                # Insert id after the opening ---
                frontmatter_content = content[3:end_index]
                rest_of_file = content[end_index:]
                content = f"---\nid: {idx}{frontmatter_content}{rest_of_file}"
        contents.append(content)
    
    # Add intro text and combine with horizontal rules
    intro = f"Here is a copy of my {n} latest journalling brain dumps:"
    combined = intro + "\n\n---\n\n" + "\n\n---\n\n".join(contents)
    
    # Copy to clipboard
    try:
        pyperclip.copy(combined)
        print_padded(f"[{MONOKAI['green']}]Copied latest {n} file{'s' if n > 1 else ''} to clipboard.[/{MONOKAI['green']}]")
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
    """Open a journal entry by its ID from the status list."""
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
    
    # Open in terminal editor
    edit_in_terminal(filepath)


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
