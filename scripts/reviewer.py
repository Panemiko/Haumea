import csv
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

def detect_csv_format(file_path: Path):
    """Detects encoding and dialect of the CSV file."""
    encoding = 'utf-8'
    try:
        with open(file_path, mode='r', encoding=encoding, newline='') as f:
            f.readline()
    except UnicodeDecodeError:
        encoding = 'utf-8-sig'
        try:
            with open(file_path, mode='r', encoding=encoding, newline='') as f:
                f.readline()
        except UnicodeDecodeError:
            encoding = 'latin-1'
            
    try:
        with open(file_path, mode='r', encoding=encoding, newline='') as infile:
            sample = infile.read(2048)
            infile.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = 'excel'
            return encoding, dialect
    except Exception as e:
        print(f"Error reading file for format detection: {e}", file=sys.stderr)
        sys.exit(1)


def save_csv(file_path: Path, fieldnames: list, rows: list, encoding: str, dialect):
    """Saves rows to a temporary file and replaces the original file atomically."""
    temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
    try:
        with open(temp_path, mode='w', encoding=encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, dialect=dialect)
            writer.writeheader()
            writer.writerows(rows)
        # Atomic replacement
        temp_path.replace(file_path)
    except Exception as e:
        print(f"\nError saving CSV file: {e}", file=sys.stderr)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def format_url(url_str: str) -> str:
    """Formats a URL to ensure it starts with http:// or https://."""
    url_str = url_str.strip()
    if not url_str:
        return ""
    if not url_str.startswith(("http://", "https://")):
        return "https://" + url_str
    return url_str


def open_urls(urls: list, chrome_bin: str = None):
    """Opens a list of URLs in a new Chromium/Chrome window or falls back to webbrowser."""
    valid_urls = [u for u in urls if u]
    if not valid_urls:
        print(" No links to open.")
        return

    if chrome_bin:
        try:
            # Open all valid URLs in a new window using Chromium
            subprocess.Popen([chrome_bin, '--new-window'] + valid_urls, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(" Done!")
        except Exception as e:
            print(f" Failed opening in Chromium: {e}. Falling back to default browser...")
            _fallback_open(valid_urls)
    else:
        _fallback_open(valid_urls)


def _fallback_open(urls: list):
    try:
        webbrowser.open_new(urls[0])
        for u in urls[1:]:
            webbrowser.open_new_tab(u)
        print(" Done!")
    except Exception as e:
        print(f" Failed! (Error: {e})")


def review_csv(input_file: Path, screenshot_dir: Path = None, output_file: Path = None) -> Path:
    """Interactive CLI loop that opens websites in a new browser window and saves website quality feedback."""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: File '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"--- STARTING WEBSITE REVIEW ---")
    
    # Determine output path
    if output_file:
        output_path = Path(output_file)
    elif input_path.stem.endswith("_qualified"):
        output_path = input_path
    else:
        output_path = input_path.parent / f"{input_path.stem}_qualified{input_path.suffix}"

    # If the output file already exists, read from it to resume progress.
    # Otherwise, read from the input file.
    read_path = output_path if output_path.exists() else input_path
    
    print(f"Reading data from: {read_path}")
    if output_path.exists() and read_path == output_path:
        print("Resuming progress from existing qualified CSV file.")
    else:
        print(f"Qualifying new data. Output will be saved to: {output_path}")

    # Detect format & read
    encoding, dialect = detect_csv_format(read_path)
    
    rows = []
    fieldnames = []
    with open(read_path, mode='r', encoding=encoding, newline='') as f:
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = reader.fieldnames
        if not fieldnames:
            print("Error: Empty CSV or invalid headers.", file=sys.stderr)
            sys.exit(1)
        fieldnames = [fn.strip() for fn in fieldnames]
        
        # Verify required columns exist
        for col in ["website", "observations", "title"]:
            if col not in fieldnames:
                print(f"Error: Required column '{col}' is missing in CSV.", file=sys.stderr)
                print("Make sure this CSV has been cleaned via clean-and-parse.", file=sys.stderr)
                sys.exit(1)
                
        f.seek(0)
        reader = csv.DictReader(f, fieldnames=fieldnames, dialect=dialect)
        next(reader) # skip header
        for r in reader:
            rows.append(r)

    # Find Chromium/Chrome
    chrome_bin = (
        shutil.which('chromium') or
        shutil.which('chromium-browser') or
        shutil.which('google-chrome') or 
        shutil.which('google-chrome-stable')
    )
    if not chrome_bin:
        common_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chrome"
        ]
        for path in common_paths:
            if Path(path).exists():
                chrome_bin = path
                break

    # Filter businesses with website or instagram
    businesses_with_website = [
        r for r in rows 
        if (r.get("website") and r["website"].strip()) or (r.get("instagram") and r["instagram"].strip())
    ]
    
    if not businesses_with_website:
        print("No businesses with a website or instagram found in this CSV.")
        print(f"---------------------------------\n")
        return output_path

    # Filter out already reviewed ones
    to_review = businesses_with_website
    
    total_with_website = len(businesses_with_website)
    total_with_obs = len([r for r in to_review if r.get("observations", "").strip()])
    
    print("=" * 60)
    print(f"Total businesses:               {total_with_website}")
    print(f"Items with observations:        {total_with_obs}")
    print("=" * 60)

    if not to_review:
        print("No businesses with websites/instagram found!")
        print(f"---------------------------------\n")
        return output_path

    # Review Loop
    idx = 0
    while idx < len(to_review):
        row = to_review[idx]
        title = row["title"]
        website = row.get("website", "").strip() if "website" in row else ""
        instagram = row.get("instagram", "").strip() if "instagram" in row else ""
        
        urls_to_open = []
        if website:
            urls_to_open.append(format_url(website))
        if instagram:
            urls_to_open.append(format_url(instagram))

        print(f"\n[{idx+1}/{len(to_review)}] {title}")
        if website:
            print(f"Website: {format_url(website)}")
        if instagram:
            print(f"Instagram: {format_url(instagram)}")
        
        current_obs = row.get("observations", "").strip()
        if current_obs:
            print(f"Current Observations: {current_obs}")

        print("Opening links in a new Chromium window..." if chrome_bin else "Opening links in default browser...", end="", flush=True)
        open_urls(urls_to_open, chrome_bin)

        # Ask user for judgment
        jumped = False
        while True:
            print("\nCommands:")
            print("  [Type review]   -> Append comment to observations and proceed")
            print("  <Enter>         -> Skip this business for now (ask again next time)")
            print("  skip            -> Append 'skipped' to observations")
            print("  goto <number>   -> Jump to a specific item")
            print("  remove / del    -> Remove this business from the CSV list entirely")
            print("  open            -> Re-open links in browser")
            print("  exit / quit     -> Save progress and exit script")
            
            try:
                review = input("\nReview/Comment: ").strip()
            except (EOFError, KeyboardInterrupt):
                review = 'exit'
            
            if review.lower() in ('exit', 'quit'):
                print("\nExiting script. Progress saved.")
                print(f"---------------------------------\n")
                sys.exit(0)
            
            elif review.lower().startswith('goto '):
                try:
                    target = int(review.split(' ')[1])
                    if 1 <= target <= len(to_review):
                        idx = target - 1
                        jumped = True
                        break
                    else:
                        print(f"Invalid range. Please enter 1 to {len(to_review)}.")
                        continue
                except (ValueError, IndexError):
                    print("Usage: goto <number>")
                    continue

            elif review.lower() in ('remove', 'del', 'delete'):
                rows.remove(row)
                to_review.remove(row) # Also remove from current session list
                print(f"Removed '{title}' from the list.")
                break
                
            elif review.lower() == 'open':
                print("Re-opening links...")
                open_urls(urls_to_open, chrome_bin)
                continue
                
            elif review.lower() == 'skip':
                if current_obs:
                    row['observations'] = f"{current_obs} | skipped"
                else:
                    row['observations'] = 'skipped'
                print(f"Marked '{title}' as skipped (appended).")
                break
                
            elif review == '':
                print(f"Skipped '{title}' for now (will prompt next run).")
                break
                
            else:
                if current_obs:
                    row['observations'] = f"{current_obs} | {review}"
                else:
                    row['observations'] = review
                print(f"Recorded comment: '{review}' (appended)")
                break
        
        if jumped:
            continue

        # Save CSV progress
        save_csv(output_path, fieldnames, rows, encoding, dialect)
        idx += 1

    print("\nAll remaining businesses have been processed!")
    print(f"---------------------------------\n")
    return output_path


