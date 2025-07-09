# DeskManager

A Python command-line utility that organizes files in a target directory (such as your Desktop) based on user-defined rules. It can move, delete, or compress files based on their type, creation/modification date, and more.

## Features

*   **Rule-Based Organization**: Configure actions using a simple `rules.json` file.
*   **Flexible Actions**: Supports moving, deleting, and (in the future) compressing files.
*   **Powerful Filtering**: Filter files by extension, creation date, or modification date.
*   **Safety First**: Includes a dry-run mode to preview changes and requires confirmation for deletions.
*   **Detailed Logging**: All operations are logged to a timestamped file in the `logs/` directory for auditing.

## Installation

No installation is required beyond having Python 3.6+ installed. All required libraries are part of the standard library.

## Usage

The script is run from the command line and accepts several arguments to control its behavior.

```bash
python DeskManager/main.py --dir <path_to_directory> [options]
```

### Arguments

*   `--dir`: (Required) The path to the directory you want to organize.
*   `--config`: (Optional) The path to your rules configuration file. Defaults to `rules.json`.
*   `--dry-run`: (Optional) A flag to simulate the organization process without making any actual changes to your files. Highly recommended for the first run.
*   `--yes`: (Optional) A flag to automatically confirm all prompts, such as the confirmation required for deleting files. Use with caution.

### Example Commands

**1. Perform a dry run to see what actions would be taken:**
```bash
python DeskManager/main.py --dir ~/Desktop --dry-run
```

**2. Execute the organization, which will prompt for confirmation before deleting files:**
```bash
python DeskManager/main.py --dir ~/Desktop
```

**3. Execute the organization and automatically approve all deletions:**
```bash
python DeskManager/main.py --dir ~/Desktop --yes
```

**4. Use a custom rules file located in a different directory:**
```bash
python DeskManager/main.py --dir ~/Downloads --config /path/to/my_custom_rules.json
```

## Creating Rules

Rules are defined in a JSON file (e.g., `rules.json`). Each rule is an object in a list and specifies an action and the criteria for files to match.

### Rule Properties

*   `action`: The action to perform. Can be `"move"` or `"delete"`.
*   `types`: A list of file extensions to match (case-insensitive).
*   `destination`: (Required for `move` action) The folder to move matched files to. It can be a relative path (e.g., `"images"`) or a nested path (e.g., `"Archive/PDFs"`).
*   `date_range`: (Optional) An object to filter files by date.
    *   Can contain `"created"` or `"modified"` keys.
    *   Each can have a `"start"` and/or `"end"` date in `YYYY-MM-DDTHH:MM:SS` format.

See the provided `rules.json` file for a detailed template with examples.
