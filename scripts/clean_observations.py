import os
import json
import urllib.request
import urllib.parse
import urllib.error
import time
import sys
from pathlib import Path

# Set to True to only update the single newest opportunity for testing.
# Set to False to run on all opportunities in the CRM.
TEST_ONLY = False

def load_env():
    """Manually load environment variables from the .env file in the project root if it exists."""
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, script_dir.parent, Path.cwd()]:
        env_path = parent / ".env"
        if env_path.exists():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip()
                            # Strip quotes if present
                            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                                val = val[1:-1]
                            os.environ[key] = val
                break
            except Exception:
                pass

def make_twenty_request(endpoint: str, method: str = "GET", payload: dict = None, token: str = None, base_url: str = None) -> tuple:
    """Helper to perform requests against the Twenty REST API using urllib."""
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    req_data = json.dumps(payload).encode("utf-8") if payload else None
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Haumea/1.0"
    }
    
    max_retries = 5
    retry_delay = 5.0  # seconds
    
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            data=req_data,
            headers=headers,
            method=method
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                status = response.status
                body_str = response.read().decode("utf-8", errors="ignore")
                try:
                    data = json.loads(body_str)
                except Exception:
                    data = body_str
                
                # Introduce a small delay after a successful request to space them out
                time.sleep(0.65)
                
                return status, data
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            
            if e.code == 429:
                print(f"  -> Rate limit hit (429) on attempt {attempt + 1}/{max_retries}. Waiting {retry_delay} seconds before retrying...", file=sys.stderr)
                time.sleep(retry_delay)
                retry_delay *= 1.5
                continue
                
            return e.code, error_body
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  -> Connection error: {e}. Retrying in {retry_delay} seconds...", file=sys.stderr)
                time.sleep(retry_delay)
                retry_delay *= 1.5
                continue
            return 0, str(e)
            
    return 429, "Rate limit retry limit exceeded"

def main():
    load_env()
    
    token = os.environ.get("TWENTY_API_TOKEN")
    base_url = os.environ.get("TWENTY_API_URL", "http://localhost:4000/rest")
    
    if not token:
        print("Error: TWENTY_API_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
        
    print("--- CRM OPPORTUNITY OBSERVATIONS CLEANER ---")
    print(f"API URL:   {base_url}")
    print(f"Mode:      {'TESTING (Newest only)' if TEST_ONLY else 'PRODUCTION (All opportunities)'}")
    print("--------------------------------------------\n")
    
    # 1. Fetch all opportunities from Twenty
    print("Fetching opportunities from CRM...")
    all_opps = []
    starting_after = None
    
    while True:
        query_params = {
            "limit": 60,
        }
        if starting_after:
            query_params["starting_after"] = starting_after
            
        endpoint = f"opportunities?{urllib.parse.urlencode(query_params)}"
        status, response = make_twenty_request(endpoint, "GET", token=token, base_url=base_url)
        if status != 200:
            print(f"Error fetching opportunities: {status}. Response: {response}", file=sys.stderr)
            sys.exit(1)
            
        data = response.get("data", {})
        opps = data.get("opportunities", [])
        if not opps:
            break
        all_opps.extend(opps)
        
        page_info = response.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            starting_after = page_info.get("endCursor")
        else:
            break
            
    print(f"Fetched {len(all_opps)} total opportunities.")
    
    if not all_opps:
        print("No opportunities found in CRM.")
        sys.exit(0)
        
    # Sort by createdAt descending (newest first)
    all_opps.sort(key=lambda o: o.get("createdAt", ""), reverse=True)
    
    target_str = "Durante a avaliação de presença digital, o lead obteve um score de 1 de 5 pontos. Verificou-se que a empresa não teve a presença de site confirmada."
    
    opps_to_process = all_opps if not TEST_ONLY else [all_opps[0]]
    
    updated_count = 0
    skipped_count = 0
    
    for idx, opp in enumerate(opps_to_process, 1):
        opp_id = opp["id"]
        opp_name = opp.get("name") or "Unnamed"
        obs = opp.get("initialObservations") or ""
        
        if target_str in obs:
            # Clean up target string and tidy any extra spacing/newlines
            new_obs = obs.replace(target_str, "").strip()
            new_obs = new_obs.replace("\n\n\n", "\n\n").strip()
            
            print(f"[{idx}/{len(opps_to_process)}] Cleaning observations for '{opp_name}' ({opp_id}):")
            print(f"  Old: {repr(obs)}")
            print(f"  New: {repr(new_obs)}")
            
            payload = {
                "initialObservations": new_obs
            }
            
            status, response = make_twenty_request(f"opportunities/{opp_id}", "PATCH", payload, token, base_url)
            if status in (200, 201):
                print("  -> Updated successfully.")
                updated_count += 1
            else:
                print(f"  -> Error updating: Status {status}. Response: {response}", file=sys.stderr)
        else:
            print(f"[{idx}/{len(opps_to_process)}] Skipped '{opp_name}' (target text not found).")
            skipped_count += 1
            
    print("\n--------------------------------------------")
    print("Execution complete.")
    print(f"Total processed: {len(opps_to_process)}")
    print(f"Updated:         {updated_count}")
    print(f"Skipped:         {skipped_count}")
    print("--------------------------------------------\n")

if __name__ == "__main__":
    main()
