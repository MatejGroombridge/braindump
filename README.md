# Braindump

A CLI tool for managing markdown journal entries with a terminal-based bullet point editor.

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
## Update
```bash
pip install --force-reinstall git+https://github.com/MatejGroombridge/braindump.git   
```

After installation, ensure the Python Scripts folder is on your PATH:

| OS          | Typical location                     |
| ----------- | ------------------------------------ |
| Windows     | `%APPDATA%\Python\Python3XX\Scripts` |
| macOS/Linux | `~/.local/bin`                       |

## Usage

The tool is invoked using the `dump` command. Run `dump help` for full command list and editor controls.

### Commands

| Command  | Description                    |
| -------- | ------------------------------ |
| `new`    | Create a new journal entry     |
| `list`   | View recent entries            |
| `open`   | Open entry in terminal editor  |
| `edit`   | Open entry in external editor  |
| `copy`   | Copy entries to clipboard      |
| `tag`    | Add or remove tags             |
| `synth`  | Toggle synthesised status      |
| `delete` | Delete an entry                |
| `sync`   | Pull, commit and push with git |
| `pull`   | Pull remote changes only       |
| `help`   | Show all commands and controls |

### Create a new entry

```bash
dump new                        # Create entry with no tags
dump new health career          # Create entry with tags
```

Creates a file like `2026012201.md` with YAML frontmatter. Files are named `YYYYMMDDXX.md` where `XX` auto-increments for multiple entries on the same day.

### Editor Controls

| Key      | Action                                         |
| -------- | ---------------------------------------------- |
| `Enter`  | New bullet at same indentation level           |
| `Tab`    | Increase indentation                           |
| `Enter`  | (on empty bullet) Decrease indentation         |
| `Enter`  | (twice at empty bullet, level 1) Save and exit |
| `Ctrl+X` | Cancel without saving                          |

### List entries

```bash
dump list                       # Show last 10 entries
dump list 5                     # Show last 5 entries
```

### Open/Edit entries

```bash
dump open                       # Open latest in terminal editor
dump open 3                     # Open entry #3 in terminal editor
dump edit                       # Open latest in external editor
dump edit 3                     # Open entry #3 in external editor
```

### Manage tags

```bash
dump tag 1 add health exercise
dump tag 1 remove fitness
dump tag 1 add health remove old
```

### Copy entries to clipboard

```bash
dump copy                       # Copy latest entry to clipboard
dump copy 3                     # Copy last 3 entries to clipboard
```

Copied entries include an intro line and are separated by horizontal rules.

### Toggle synthesised status

```bash
dump synth 1                    # Toggle synthesised status of entry #1
```

### Delete an entry

```bash
dump delete 1                   # Delete entry #1
```

### Sync with git

```bash
dump sync                       # Pull remote, commit local changes, push
dump pull                       # Pull remote changes only
```

The `sync` command performs a full bidirectional sync:
1. Fetches and pulls remote changes (stashing local changes if needed)
2. Commits all local changes with message format: `Log: YYYY-MM-DD`
3. Pushes to remote

**Auto-sync:** Commands like `new`, `list`, `open`, and `edit` automatically pull remote changes before running, keeping your dumps synced across devices.

### Show help

```bash
dump help                       # Show all commands and editor controls
```

## Configuration

- Journal entries stored in `~/dumps/`
- Date format: Jan 22, 2026
- Monokai Pro colour scheme

## Requirements

- Python 3.9+
- typer, rich, pyperclip, pyyaml, prompt_toolkit
