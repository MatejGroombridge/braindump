# Braindump

A CLI tool for managing markdown journal entries.

## Installation

### From source

```bash
git clone https://github.com/MatejGroombridge/braindump.git
cd braindump
pip install -e .
```

### Direct from GitHub

```bash
pip install git+https://github.com/MatejGroombridge/braindump.git
```

After installation, ensure the Python Scripts folder is on your PATH:

| OS          | Typical location                     |
| ----------- | ------------------------------------ |
| Windows     | `%APPDATA%\Python\Python3XX\Scripts` |
| macOS/Linux | `~/.local/bin`                       |

## Usage

The tool is invoked using the `dump` command.

### Create a new entry

```bash
# Create a new entry (defaults to tag 'general')
dump new

# Create a new entry with tags
dump new health career personal
```

This creates a file like `2024012201.md` with YAML frontmatter:

```yaml
---
date: 2024-01-22
synthesised: false
tags: [health, career, personal]
---
```

Files are named `YYYYMMDDXX.md` where `XX` is an auto-incrementing number for multiple entries on the same day.

### View status

```bash
# Show last 10 entries (default)
dump status

# Show last 5 entries
dump status 5
```

Displays a table with columns: ID | Date | Tags | Synthesised

### Open an entry

```bash
# Open the latest entry
dump open

# Open entry by ID (from status list)
dump open 3
```

### Copy entries to clipboard

```bash
# Copy the latest entry
dump copy

# Copy the latest 3 entries
dump copy 3
```

Entries are separated by horizontal rules when copying multiple files.

### Synchronise with git

```bash
dump sync
```

Runs `git add`, `commit` (with message "Log: YYYY-MM-DD"), and `push`.

## Configuration

- Journal entries are stored in `~/dumps/`
- On Windows, files open with the default application
- On macOS/Linux, set the `$EDITOR` environment variable for the `new` and `open` commands
- The dumps directory should be initialised as a git repository for the `sync` command

## Requirements

- Python 3.9+
- typer
- rich
- pyperclip
- pyyaml
