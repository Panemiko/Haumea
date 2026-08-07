import os
import json
import datetime
import urllib.request
import urllib.parse
import urllib.error
import time
import sys
from pathlib import Path

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
        "Content-Type": "application/json"
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

def get_next_recontact_date(current_date_str: str) -> str:
    """Calculates: current date + 1 day. If weekend (Saturday/Sunday), moves to Monday."""
    curr_date = datetime.date.fromisoformat(current_date_str)
    new_date = curr_date + datetime.timedelta(days=1)
    
    # weekday() return: 0 is Monday, ..., 5 is Saturday, 6 is Sunday
    wday = new_date.weekday()
    if wday == 5:  # Saturday
        new_date += datetime.timedelta(days=2)  # Go to Monday
    elif wday == 6:  # Sunday
        new_date += datetime.timedelta(days=1)  # Go to Monday
        
    return new_date.isoformat()

def main():
    load_env()
    
    token = os.environ.get("TWENTY_API_TOKEN")
    base_url = os.environ.get("TWENTY_API_URL", "http://localhost:4000/rest")
    
    if not token:
        print("Error: TWENTY_API_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
        
    print(f"--- OPPORTUNITY RECONTACT DATE UPDATER ---")
    print(f"API URL: {base_url}")
    
    # 1. Fetch opportunities
    print("Fetching opportunities in stage LEAD...")
    all_opps = []
    starting_after = None
    
    while True:
        query_params = {
            "limit": 60,
            "filter": 'stage[eq]:"LEAD"'
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
        all_opps.extend(opps)
        
        page_info = response.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            starting_after = page_info.get("endCursor")
        else:
            break
            
    print(f"Fetched {len(all_opps)} total opportunities in LEAD stage.")
    
    # 2. Filter for those with defined messageRecontactDate
    opps_to_update = [o for o in all_opps if o.get("messageRecontactDate") is not None]
    
    if not opps_to_update:
        print("No opportunities in stage LEAD have a messageRecontactDate set. Nothing to update.")
        sys.exit(0)
        
    print(f"Found {len(opps_to_update)} opportunities to update.")
    
    # 3. Create JSON backup
    backup_data = []
    for opp in opps_to_update:
        backup_data.append({
            "opportunityId": opp["id"],
            "name": opp.get("name"),
            "messageRecontactDate": opp["messageRecontactDate"]
        })
        
    backup_file = Path.cwd() / "backup_recontact_dates.json"
    try:
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        print(f"Backup successfully saved to: {backup_file}")
    except Exception as e:
        print(f"Critical error: Failed to save backup to file {backup_file}: {e}", file=sys.stderr)
        print("Aborting updates for safety.", file=sys.stderr)
        sys.exit(1)
        
    # 4. Perform updates
    success_count = 0
    failure_count = 0
    
    for idx, opp in enumerate(opps_to_update, 1):
        opp_id = opp["id"]
        opp_name = opp.get("name") or "Unnamed"
        old_date = opp["messageRecontactDate"]
        new_date = get_next_recontact_date(old_date)
        
        print(f"[{idx}/{len(opps_to_update)}] Updating '{opp_name}' ({opp_id}): {old_date} -> {new_date}")
        
        payload = {
            "messageRecontactDate": new_date
        }
        status, response = make_twenty_request(f"opportunities/{opp_id}", "PATCH", payload, token, base_url)
        
        if status in (200, 201):
            print(f"  -> Successfully updated.")
            success_count += 1
        else:
            print(f"  -> Error: Failed to update opportunity. Status {status}. Response: {response}", file=sys.stderr)
            failure_count += 1
            
    print("\n--- UPDATE COMPLETED ---")
    print(f"Successfully updated: {success_count}")
    print(f"Failed to update:     {failure_count}")

if __name__ == "__main__":
    main()
