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
from rich.console import Console
from rich.table import Table
from rich.spinner import Spinner
from rich import print as rprint

app = typer.Typer(
    name="dump",
    help="A CLI tool for managing markdown journal entries.",
    no_args_is_help=True,
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
JOURNAL_DIR = Path.home() / "braindump"


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


def get_sorted_files(descending: bool = True) -> List[Path]:
    """Get all markdown files sorted by filename."""
    ensure_journal_dir()
    files = list(JOURNAL_DIR.glob("*.md"))
    return sorted(files, key=lambda f: f.name, reverse=descending)


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
    
    # Build tags list - default to 'general' if no tags provided
    tag_list = tags if tags else ["general"]
    
    # Create YAML frontmatter
    frontmatter = f"""---
date: {date_formatted}
synthesised: false
tags: [{', '.join(tag_list)}]
---

"""
    
    # Write the file
    filepath.write_text(frontmatter, encoding="utf-8")
    
    console.print(f"[{MONOKAI['green']}]✓[/{MONOKAI['green']}] Created [bold]{filename}[/bold]")
    
    if tag_list:
        console.print(f"  Tags: [{MONOKAI['cyan']}]{', '.join(tag_list)}[/{MONOKAI['cyan']}]")
    
    # Open in default editor
    editor = os.environ.get("EDITOR", "")
    
    if sys.platform == "win32":
        # On Windows, try to open with associated application
        os.startfile(filepath)
    elif editor:
        os.system(f'{editor} "{filepath}"')
    else:
        # Fallback for Unix-like systems without EDITOR set
        console.print(f"[{MONOKAI['yellow']}]No $EDITOR set. File created at:[/{MONOKAI['yellow']}] {filepath}")


@app.command()
def sync() -> None:
    """Synchronise journal entries with git remote."""
    ensure_journal_dir()
    
    # Check if journal directory is a git repository
    git_dir = JOURNAL_DIR / ".git"
    if not git_dir.exists():
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Journal directory is not a git repository.")
        console.print(f"  Initialise with: [{MONOKAI['cyan']}]cd {JOURNAL_DIR} && git init[/{MONOKAI['cyan']}]")
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
        
        console.print(f"[{MONOKAI['green']}]✓[/{MONOKAI['green']}] Successfully synchronised with remote.")
        console.print(f"  Commit message: [{MONOKAI['cyan']}]{commit_message}[/{MONOKAI['cyan']}]")
        
    except Exception as e:
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Synchronisation failed: {e}")
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
        console.print(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
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
        console.print(f"[{MONOKAI['green']}]✓[/{MONOKAI['green']}] Copied latest [bold]{n}[/bold] file{'s' if n > 1 else ''} to clipboard.")
    except pyperclip.PyperclipException as e:
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Failed to copy to clipboard: {e}")
        raise typer.Exit(1)


@app.command()
def status(
    n: int = typer.Argument(
        10,
        help="Number of entries to display (default: 10)",
    ),
) -> None:
    """Display the status of the last n journal entries."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        console.print(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        return
    
    # Take last n files
    files_to_show = files[:n]
    
    # Create table
    table = Table(title="Journal Status", show_header=True, header_style=f"bold {MONOKAI['violet']}")
    table.add_column("ID", style=f"bold {MONOKAI['orange']}", justify="right")
    table.add_column("Date", style=MONOKAI["white"])
    table.add_column("Tags", style=MONOKAI["cyan"])
    table.add_column("Synthesised", style=MONOKAI["yellow"], justify="centre")
    
    for idx, f in enumerate(files_to_show, start=1):
        content = f.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)
        
        # Parse date from filename (YYYYMMDDXX.md)
        stem = f.stem
        if len(stem) >= 8:
            try:
                year = stem[0:4]
                month = stem[4:6]
                day = stem[6:8]
                date_str = f"{day}/{month}/{year}"
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
    
    console.print(table)


@app.command(name="open")
def open_file(
    n: Optional[int] = typer.Argument(
        None,
        help="ID of the file to open (from 'dump status'). Opens latest if not provided.",
    ),
) -> None:
    """Open a journal entry by its ID from the status list."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        console.print(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    # Default to 1 (latest file) if n not provided
    file_id = n if n is not None else 1
    
    if file_id < 1 or file_id > len(files):
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get file by ID (1-indexed)
    filepath = files[file_id - 1]
    
    console.print(f"[{MONOKAI['green']}]✓[/{MONOKAI['green']}] Opening [bold]{filepath.name}[/bold]")
    
    # Open in default editor
    editor = os.environ.get("EDITOR", "")
    
    if sys.platform == "win32":
        os.startfile(filepath)
    elif editor:
        os.system(f'{editor} "{filepath}"')
    else:
        console.print(f"[{MONOKAI['yellow']}]No $EDITOR set. File location:[/{MONOKAI['yellow']}] {filepath}")


@app.command()
def synthesise(
    file_id: int = typer.Argument(
        ...,
        help="ID of the file to toggle synthesised status (from 'dump status').",
    ),
) -> None:
    """Toggle the synthesised status of a journal entry."""
    ensure_journal_dir()
    
    files = get_sorted_files(descending=True)
    
    if not files:
        console.print(f"[{MONOKAI['yellow']}]No journal files found.[/{MONOKAI['yellow']}]")
        raise typer.Exit(1)
    
    if file_id < 1 or file_id > len(files):
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Invalid ID: {file_id}. Valid range: 1-{len(files)}")
        raise typer.Exit(1)
    
    # Get file by ID (1-indexed)
    filepath = files[file_id - 1]
    content = filepath.read_text(encoding="utf-8")
    
    # Parse and toggle synthesised value
    if not content.startswith("---"):
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] File has no valid frontmatter.")
        raise typer.Exit(1)
    
    end_index = content.find("---", 3)
    if end_index == -1:
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] File has no valid frontmatter.")
        raise typer.Exit(1)
    
    yaml_content = content[3:end_index].strip()
    rest_of_file = content[end_index + 3:]
    
    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        console.print(f"[{MONOKAI['red']}]✗[/{MONOKAI['red']}] Failed to parse frontmatter.")
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
    console.print(f"[{MONOKAI['green']}]✓[/{MONOKAI['green']}] [{MONOKAI['orange']}]{filepath.name}[/{MONOKAI['orange']}] synthesised: {status_str}")


if __name__ == "__main__":
    app()
