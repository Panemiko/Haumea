import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from scripts.utils import sanitize_filename

def locate_scraper_binary() -> Path:
    """Locates the scraper binary in the project root directory."""
    project_root = Path(__file__).parent.parent.resolve()
    exact_binary = project_root / "google_maps_scraper-1.3.0-linux-amd64"
    if exact_binary.exists():
        if not os.access(exact_binary, os.X_OK):
            try:
                os.chmod(exact_binary, 0o755)
            except Exception:
                pass
        return exact_binary
        
    # Fallback: search for any file starting with 'google_maps_scraper'
    for item in project_root.iterdir():
        if item.is_file() and item.name.startswith("google_maps_scraper"):
            if not os.access(item, os.X_OK):
                try:
                    os.chmod(item, 0o755)
                except Exception:
                    pass
            return item
                
    # Fallback: search in PATH
    path_binary = shutil.which("google_maps_scraper-1.3.0-linux-amd64") or shutil.which("google_maps_scraper")
    if path_binary:
        return Path(path_binary)
        
    return exact_binary


def run_scraper(keywords_str: str, output_path: Path = None, depth: int = 10) -> Path:
    """Runs the Google Maps Scraper on the provided keywords."""
    if ',' in keywords_str:
        queries = [q.strip() for q in keywords_str.split(',') if q.strip()]
    elif '\n' in keywords_str:
        queries = [q.strip() for q in keywords_str.split('\n') if q.strip()]
    else:
        queries = [keywords_str.strip()]
        
    if not queries or not queries[0]:
        print("Error: No valid keywords/queries provided.", file=sys.stderr)
        sys.exit(1)
        
    binary_path = locate_scraper_binary()
    if not binary_path.exists():
        print(f"Error: Scraper binary not found at '{binary_path}'.", file=sys.stderr)
        print("Please make sure the google-maps-scraper binary is in the same directory as this script.", file=sys.stderr)
        sys.exit(1)
        
    project_root = Path(__file__).parent.parent.resolve()
    if not output_path:
        base_name = sanitize_filename(queries[0])
        if len(queries) > 1:
            base_name += "_multi"
        output_path = project_root / f"{base_name}.csv"
    else:
        output_path = Path(output_path)
        
    print(f"\n--- STARTING GOOGLE MAPS SCRAPER ---")
    print(f"Scraper binary: {binary_path}")
    print(f"Queries:        {queries}")
    print(f"Depth:          {depth}")
    print(f"Output raw CSV: {output_path}")
    
    temp_query_file = project_root / f"temp_queries_{int(time.time())}.txt"
    try:
        with open(temp_query_file, "w", encoding="utf-8") as f:
            for q in queries:
                f.write(f"{q}\n")
                
        cmd = [
            str(binary_path),
            "-input", str(temp_query_file),
            "-results", str(output_path),
            "-depth", str(depth),
            "-email"
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        res = subprocess.run(cmd, check=True)
        
        if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            print(f"Scraper completed successfully.")
            print(f"---------------------------------\n")
            return output_path
        else:
            print("Error: Scraper did not produce any output or exited with an error.", file=sys.stderr)
            sys.exit(1)
            
    except subprocess.CalledProcessError as e:
        print(f"Error: Scraper command failed with exit code {e.returncode}.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error running scraper: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if temp_query_file.exists():
            try:
                temp_query_file.unlink()
            except Exception:
                pass
