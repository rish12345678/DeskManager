import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import shutil

def load_config(config_path):
    """Loads the rules from a JSON configuration file."""
    try:
        with open(config_path, 'r') as f:
            rules = json.load(f)
        return rules
    except FileNotFoundError:
        print(f"Error: Configuration file not found at '{config_path}'")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in configuration file at '{config_path}'")
        sys.exit(1)

def scan_directory(dir_path):
    """Scans the target directory for top-level files."""
    try:
        directory = Path(dir_path)
        if not directory.is_dir():
            print(f"Error: Target directory '{dir_path}' does not exist or is not a directory.")
            sys.exit(1)
        
        # List files in the directory, excluding subdirectories
        files = [f for f in directory.iterdir() if f.is_file()]
        return files
    except PermissionError:
        print(f"Error: Permission denied to access directory '{dir_path}'.")
        sys.exit(1)

def filter_files(files, rules):
    """Filters files based on the provided rules."""
    matched_files = []
    for file in files:
        for rule in rules:
            # A file must match ALL conditions in a rule to be considered a match.
            
            # 1. Check file type
            if 'types' in rule:
                file_extension = file.suffix.lower().lstrip('.')
                if file_extension not in [t.lower() for t in rule['types']]:
                    continue  # Does not match type, try next rule

            # 2. Check date range
            if 'date_range' in rule:
                try:
                    date_config = rule['date_range']
                    
                    # Check for modified date
                    if 'modified' in date_config:
                        file_date = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
                        start_str = date_config['modified'].get('start')
                        end_str = date_config['modified'].get('end')

                        start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc) if start_str else None
                        end_date = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc) if end_str else None

                        if (start_date and file_date < start_date) or (end_date and file_date > end_date):
                            continue # File's modified date is outside the range

                    # Check for created date
                    if 'created' in date_config:
                        file_date = datetime.fromtimestamp(file.stat().st_ctime, tz=timezone.utc)
                        start_str = date_config['created'].get('start')
                        end_str = date_config['created'].get('end')

                        start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc) if start_str else None
                        end_date = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc) if end_str else None

                        if (start_date and file_date < start_date) or (end_date and file_date > end_date):
                            continue # File's created date is outside the range
                
                except (ValueError, TypeError) as e:
                    print(f"Warning: Skipping invalid date range in rule: {rule}. Error: {e}")
                    continue

            # If all conditions passed, we have a match.
            matched_files.append({'file': file, 'rule': rule})
            break  # Move to the next file since we found a matching rule
            
    return matched_files

def execute_actions(matched_files, base_dir, dry_run):
    """Executes the actions defined in the rules for the matched files."""
    summary = {'moved': 0, 'deleted': 0, 'compressed': 0}
    
    if not matched_files:
        return summary

    print(f"\n--- {'DRY RUN' if dry_run else 'EXECUTING ACTIONS'} ---")

    for match in matched_files:
        action = match['rule'].get('action')
        file_path = match['file']

        if action == 'move':
            destination = match['rule'].get('destination')
            if not destination:
                print(f"Warning: Skipping move for '{file_path.name}' due to missing 'destination' in rule.")
                continue

            dest_dir = Path(base_dir) / destination
            dest_file = dest_dir / file_path.name
            
            print(f"[MOVE] '{file_path.name}' -> '{dest_dir}/'")
            if not dry_run:
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(file_path), str(dest_file))
                    summary['moved'] += 1
                except (OSError, PermissionError) as e:
                    print(f"  -> ERROR: Could not move file: {e}")
        
        elif action == 'delete':
            print(f"[DELETE] '{file_path.name}'")
            if not dry_run:
                try:
                    file_path.unlink()
                    summary['deleted'] += 1
                except (OSError, PermissionError) as e:
                    print(f"  -> ERROR: Could not delete file: {e}")
        
        elif action == 'compress':
            print(f"[COMPRESS] '{file_path.name}' (not yet implemented).")
            # In a future step, this would be implemented
            # summary['compressed'] += 1

    return summary

def main():
    parser = argparse.ArgumentParser(description="DeskManager - Smart Desktop Organizer")
    parser.add_argument(
        "--dir",
        type=str,
        required=True,
        help="The target directory to organize."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="rules.json",
        help="Path to the rules configuration file (default: rules.json)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the organization process without making any changes."
    )

    args = parser.parse_args()

    print("DeskManager CLI")
    print(f"Target Directory: {args.dir}")
    print(f"Config File: {args.config}")
    print(f"Dry Run: {args.dry_run}")

    rules = load_config(args.config)
    print("\nLoaded Rules:")
    print(json.dumps(rules, indent=2))

    files_to_process = scan_directory(args.dir)
    print("\nFound Files to Scan:")
    if not files_to_process:
        print("No files found in the target directory.")
    for f in files_to_process:
        print(f" - {f.name}")

    matched_files = filter_files(files_to_process, rules)
    print("\nMatched Files for Processing:")
    if not matched_files:
        print("No files matched any rules.")
    else:
        for match in matched_files:
            print(f" - File: {match['file'].name}, Action: {match['rule']['action']}")

    execute_actions(matched_files, args.dir, args.dry_run)


if __name__ == "__main__":
    main()
