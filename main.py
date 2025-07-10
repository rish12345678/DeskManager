import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import shutil
import logging

class DeskManager:
    """A class to organize files in a directory based on a set of rules."""

    def __init__(self, target_dir, config_path, dry_run=False, auto_confirm=False):
        """Initializes the DeskManager."""
        self.target_dir = Path(target_dir)
        self.config_path = config_path
        self.dry_run = dry_run
        self.auto_confirm = auto_confirm
        self.rules = self._load_config()
        self.summary = {'moved': 0, 'deleted': 0, 'compressed': 0, 'total_size_bytes': 0}

    def _load_config(self):
        """Loads and validates the rules from the JSON configuration file."""
        logging.info(f"Loading rules from '{self.config_path}'...")
        try:
            with open(self.config_path, 'r') as f:
                rules = json.load(f)
            logging.info(f"Successfully loaded {len(rules)} rules.")
            return rules
        except FileNotFoundError:
            logging.error(f"Configuration file not found at '{self.config_path}'")
            sys.exit(1)
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in configuration file at '{self.config_path}'")
            sys.exit(1)

    def _scan_directory(self):
        """Scans the target directory for top-level files."""
        logging.info(f"Scanning directory: '{self.target_dir}'")
        if not self.target_dir.is_dir():
            logging.error(f"Target directory '{self.target_dir}' does not exist or is not a directory.")
            sys.exit(1)
        
        try:
            files = [f for f in self.target_dir.iterdir() if f.is_file()]
            logging.info(f"Found {len(files)} top-level files to process.")
            return files
        except PermissionError:
            logging.error(f"Permission denied to access directory '{self.target_dir}'.")
            sys.exit(1)

    def _filter_files(self, files):
        """Filters files based on the provided rules."""
        matched_files = []
        for file in files:
            for rule in self.rules:
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
                        stat_info = file.stat() # Get file stats once

                        # Check for modified date
                        if 'modified' in date_config:
                            file_date = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc)
                            start_str = date_config['modified'].get('start')
                            end_str = date_config['modified'].get('end')
                            
                            start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc) if start_str else None
                            end_date = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc) if end_str else None

                            if (start_date and file_date < start_date) or \
                               (end_date and file_date > end_date):
                                continue

                        # Check for created date (using birthtime for correctness)
                        if 'created' in date_config:
                            # st_birthtime is the correct "creation" time on supported systems (macOS, BSD)
                            # st_ctime is "metadata change" time on Linux. We default to it if birthtime is unavailable.
                            created_timestamp = getattr(stat_info, 'st_birthtime', stat_info.st_ctime)
                            file_date = datetime.fromtimestamp(created_timestamp, tz=timezone.utc)

                            start_str = date_config['created'].get('start')
                            end_str = date_config['created'].get('end')

                            start_date = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc) if start_str else None
                            end_date = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc) if end_str else None

                            if (start_date and file_date < start_date) or \
                               (end_date and file_date > end_date):
                                continue
                    
                    except (ValueError, TypeError) as e:
                        logging.warning(f"Skipping invalid date range in rule: {rule}. Error: {e}")
                        continue

                # If all conditions passed, we have a match.
                matched_files.append({'file': file, 'rule': rule})
                break
                
        logging.info(f"Matched {len(matched_files)} files to rules.")
        return matched_files

    def _execute_actions(self, matched_files):
        """Executes the actions for the matched files."""
        if not matched_files:
            return

        # --- Deletion Confirmation ---
        files_to_delete = [m['file'] for m in matched_files if m['rule'].get('action') == 'delete']
        deletions_approved = True

        if files_to_delete and not self.dry_run and not self.auto_confirm:
            logging.warning("The following files are scheduled for permanent deletion:")
            for f in files_to_delete:
                logging.warning(f"  - {f.name}")
            
            try:
                confirm = input("Are you sure you want to delete these files? Type 'yes' to confirm: ")
                if confirm.lower() != 'yes':
                    logging.info("Deletion cancelled by user.")
                    deletions_approved = False
                else:
                    logging.info("Deletion confirmed by user.")
            except (EOFError, KeyboardInterrupt):
                logging.warning("\nDeletion prompt cancelled. No files will be deleted.")
                deletions_approved = False

        logging.info(f"--- {'DRY RUN' if self.dry_run else 'EXECUTING ACTIONS'} ---")

        for match in matched_files:
            action = match['rule'].get('action')
            file_path = match['file']

            if action == 'move':
                destination = match['rule'].get('destination')
                if not destination:
                    logging.warning(f"Skipping move for '{file_path.name}' due to missing 'destination' in rule.")
                    continue

                dest_dir = self.target_dir / destination
                dest_file = dest_dir / file_path.name
                
                log_msg = f"[MOVE] '{file_path.name}' -> '{dest_dir}/'"
                logging.info(log_msg)

                if not self.dry_run:
                    try:
                        file_size = file_path.stat().st_size
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(file_path), str(dest_file))
                        self.summary['moved'] += 1
                        self.summary['total_size_bytes'] += file_size
                    except (OSError, PermissionError, FileNotFoundError) as e:
                        logging.error(f"Could not move file '{file_path.name}': {e}")
            
            elif action == 'delete':
                if deletions_approved:
                    log_msg = f"[DELETE] '{file_path.name}'"
                    logging.info(log_msg)

                    if not self.dry_run:
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            self.summary['deleted'] += 1
                            self.summary['total_size_bytes'] += file_size
                        except (OSError, PermissionError, FileNotFoundError) as e:
                            logging.error(f"Could not delete file '{file_path.name}': {e}")
                else:
                    logging.warning(f"Skipping deletion of '{file_path.name}' due to user cancellation.")

            elif action == 'compress':
                logging.info(f"[COMPRESS] '{file_path.name}' (not yet implemented).")

    def _print_summary_report(self, matched_files):
        """Prints a formatted summary of the operations."""
        logging.info("--- OPERATION SUMMARY ---")

        if self.dry_run:
            planned_summary = {'moved': 0, 'deleted': 0, 'compressed': 0, 'total_size_bytes': 0}
            for match in matched_files:
                action = match['rule'].get('action', 'none')
                if action in planned_summary:
                    planned_summary[action] += 1
                try:
                    # Ensure we are checking a file that exists for stat
                    if Path(match['file']).exists():
                        planned_summary['total_size_bytes'] += match['file'].stat().st_size
                except (FileNotFoundError, PermissionError):
                    logging.warning(f"Could not calculate size for '{match['file'].name}', file may have been moved or permission denied.")

            logging.info("Dry run complete. The following actions were planned:")
            logging.info(f"  - Files to be Moved: {planned_summary['moved']}")
            logging.info(f"  - Files to be Deleted: {planned_summary['deleted']}")
            logging.info(f"  - Files to be Compressed: {planned_summary['compressed']}")
            total_size_formatted = format_bytes(planned_summary['total_size_bytes'])
            logging.info(f"  - Total Size of Affected Files: {total_size_formatted}")

        else:
            logging.info("Execution complete. The following actions were performed:")
            logging.info(f"  - Files Moved: {self.summary['moved']}")
            logging.info(f"  - Files Deleted: {self.summary['deleted']}")
            logging.info(f"  - Files Compressed: {self.summary['compressed']}")
            total_size_formatted = format_bytes(self.summary['total_size_bytes'])
            logging.info(f"  - Total Size of Affected Files: {total_size_formatted}")

        logging.info("DeskManager session finished.")

    def run(self):
        """Runs the complete organization process."""
        files_to_process = self._scan_directory()
        matched_files = self._filter_files(files_to_process)
        
        if matched_files:
            logging.info("--- Matched Files Summary ---")
            for match in matched_files:
                logging.info(f"  - File: {match['file'].name}, Action: {match['rule']['action']}")
        
        self._execute_actions(matched_files)
        self._print_summary_report(matched_files)

    def run_interactive(self):
        """Runs the program in interactive mode, prompting the user to build a rule."""
        logging.info("Starting interactive session...")
        print("\n--- DeskManager Interactive Mode ---\n")
        print("Let's build a rule to organize your files.")

        try:
            # 1. Get Action
            action = self._prompt_for_action()
            rule = {"action": action}

            # 2. Get Destination (if moving)
            if action == 'move':
                destination = input("Enter the destination folder (e.g., 'images' or 'Archive/PDFs'): ")
                if not destination.strip():
                    print("Destination cannot be empty. Aborting.")
                    return
                rule['destination'] = destination

            # 3. Get File Types
            types_str = input("Enter file types to target, separated by spaces (e.g., 'png jpg pdf').\nLeave blank to target ALL file types: ")
            if types_str.strip():
                rule['types'] = types_str.lower().split()

            # 4. Get Date Range
            if self._prompt_for_date_filter():
                rule['date_range'] = self._prompt_for_date_details()

            # --- Rule creation is complete ---
            self.rules = [rule] # Overwrite any existing rules with our new dynamic one
            print("\nRule created successfully:")
            print(json.dumps(self.rules, indent=2))

            # Use the existing logic to run the process
            self.run()

        except (KeyboardInterrupt, EOFError):
            print("\n\nInteractive session cancelled by user. Exiting.")
            sys.exit(0)
    
    def _prompt_for_action(self):
        """Prompts the user to select an action."""
        while True:
            action = input("Choose an action: [M]ove or [D]elete? ").lower().strip()
            if action in ['m', 'move']:
                return 'move'
            elif action in ['d', 'delete']:
                return 'delete'
            print("Invalid input. Please enter 'm' or 'd'.")

    def _prompt_for_date_filter(self):
        """Asks the user if they want to filter by date."""
        while True:
            choice = input("Filter by date? [Y]es or [N]o? ").lower().strip()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                return False
            print("Invalid input. Please enter 'y' or 'n'.")

    def _prompt_for_date_details(self):
        """Prompts for the specifics of the date filter."""
        date_range = {}
        
        # Get date type
        while True:
            date_type = input("Filter by [C]reated or [M]odified date? ").lower().strip()
            if date_type in ['c', 'created']:
                date_key = 'created'
                break
            elif date_type in ['m', 'modified']:
                date_key = 'modified'
                break
            print("Invalid input. Please enter 'c' or 'm'.")
        
        date_range[date_key] = {}

        # Get start/end date
        while True:
            bounds = input("Filter by [S]tart date, [E]nd date, or [B]oth? ").lower().strip()
            if bounds in ['s', 'start', 'e', 'end', 'b', 'both']:
                break
            print("Invalid input. Please enter 's', 'e', or 'b'.")

        if bounds in ['s', 'start', 'b', 'both']:
            start_date_str = self._prompt_for_valid_date("Enter the start date (YYYY-MM-DD): ")
            date_range[date_key]['start'] = f"{start_date_str}T00:00:00"
            
        if bounds in ['e', 'end', 'b', 'both']:
            end_date_str = self._prompt_for_valid_date("Enter the end date (YYYY-MM-DD): ")
            date_range[date_key]['end'] = f"{end_date_str}T23:59:59"
            
        return date_range

    def _prompt_for_valid_date(self, prompt_text):
        """Prompts the user until a valid YYYY-MM-DD date is entered."""
        while True:
            date_str = input(prompt_text).strip()
            try:
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            except ValueError:
                print("Invalid format. Please use YYYY-MM-DD.")


def setup_logging():
    """Sets up a timestamped log file in the 'logs' directory."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_filename = f"deskmanager_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    log_path = log_dir / log_filename

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout) # Also print logs to console
        ]
    )
    logging.info("DeskManager session started.")
    logging.info(f"Log file created at: {log_path}")
    return log_path

def format_bytes(size_bytes):
    """Converts bytes to a human-readable format (KB, MB, GB)."""
    if size_bytes == 0:
        return "0B"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_bytes >= power and n < len(power_labels) -1:
        size_bytes /= power
        n += 1
    return f"{size_bytes:.2f}{power_labels[n]}B"

def main():
    """Main function to parse arguments and run the DeskManager."""
    setup_logging()

    parser = argparse.ArgumentParser(description="DeskManager - Smart Desktop Organizer")
    parser.add_argument("--dir", type=str, required=True, help="The target directory to organize.")
    parser.add_argument("--config", type=str, default="rules.json", help="Path to the rules configuration file.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the process without making changes.")
    parser.add_argument("--yes", action="store_true", help="Automatically confirm all prompts.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run the program in interactive mode to build a rule on the fly."
    )
    
    args = parser.parse_args()

    # Create a DeskManager instance and run the process
    manager = DeskManager(
        target_dir=args.dir,
        config_path=args.config,
        dry_run=args.dry_run,
        auto_confirm=args.yes
    )
    
    if args.interactive:
        manager.run_interactive()
    else:
        manager.run()

if __name__ == "__main__":
    main()
