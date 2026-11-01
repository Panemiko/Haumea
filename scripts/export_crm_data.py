import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import time
from pathlib import Path
import pandas as pd

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
                            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                                val = val[1:-1]
                            os.environ[key] = val
                break
            except Exception:
                pass

def make_twenty_request(endpoint: str, method: str = "GET", token: str = None, base_url: str = None) -> tuple:
    """Helper to perform requests against the Twenty REST API using urllib."""
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Haumea/1.0"
    }
    
    max_retries = 5
    retry_delay = 5.0
    
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
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
                
                time.sleep(0.3) # Avoid hitting limits too quickly
                return status, data
                
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  -> Rate limit hit (429) on attempt {attempt + 1}/{max_retries}. Waiting {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 1.5
                continue
            return e.code, None
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 1.5
                continue
            return 0, str(e)
            
    return 429, None

def fetch_all_records(object_name: str, token: str, base_url: str) -> list:
    """Fetches all records for a given object using pagination."""
    print(f"Fetching {object_name}...")
    all_records = []
    starting_after = None
    
    while True:
        query_params = {"limit": 100}
        if starting_after:
            query_params["starting_after"] = starting_after
            
        endpoint = f"{object_name}?{urllib.parse.urlencode(query_params)}"
        status, response = make_twenty_request(endpoint, "GET", token=token, base_url=base_url)
        
        if status != 200 or not response:
            print(f"Error fetching {object_name}: HTTP {status}")
            break
            
        # The records are inside data -> object_name (e.g. data -> companies)
        chunk = response.get("data", {}).get(object_name, [])
        if not chunk:
            break
            
        all_records.extend(chunk)
        print(f"  ... fetched {len(chunk)} records (Total so far: {len(all_records)})")
        
        page_info = response.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            starting_after = page_info.get("endCursor")
        else:
            break
            
    print(f"Total {object_name} fetched: {len(all_records)}\n")
    return all_records

def flatten_dict(d, parent_key='', sep='_'):
    """Flattens a nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def main():
    # Load config
    load_env()
    token = os.environ.get("TWENTY_API_TOKEN")
    base_url = os.environ.get("TWENTY_API_URL", "http://localhost:4000/rest")
    
    if not token or token == "your_token_here":
        print("Error: TWENTY_API_TOKEN environment variable is not set correctly.")
        sys.exit(1)

    print("--- STARTING CRM DATA EXPORT ---")
    
    # Create export directory
    export_dir = Path(__file__).resolve().parent.parent / "exports"
    export_dir.mkdir(exist_ok=True)
    
    # Fetch data
    companies_data = fetch_all_records("companies", token, base_url)
    opportunities_data = fetch_all_records("opportunities", token, base_url)
    people_data = fetch_all_records("people", token, base_url)
    
    # Flatten data
    print("Flattening JSON structures...")
    flat_companies = [flatten_dict(c) for c in companies_data]
    flat_opportunities = [flatten_dict(o) for o in opportunities_data]
    flat_people = [flatten_dict(p) for p in people_data]
    
    # Convert to DataFrames
    df_companies = pd.DataFrame(flat_companies)
    df_opportunities = pd.DataFrame(flat_opportunities)
    df_people = pd.DataFrame(flat_people)
    
    # Save individual CSVs
    print(f"Saving individual CSVs to {export_dir}...")
    if not df_companies.empty:
        df_companies.to_csv(export_dir / "companies.csv", index=False, encoding="utf-8-sig")
    if not df_opportunities.empty:
        df_opportunities.to_csv(export_dir / "opportunities.csv", index=False, encoding="utf-8-sig")
    if not df_people.empty:
        df_people.to_csv(export_dir / "people.csv", index=False, encoding="utf-8-sig")
        
    # Correlation: Merge Opportunities with Companies
    if not df_opportunities.empty and not df_companies.empty and "companyId" in df_opportunities.columns:
        print("Correlating Opportunities and Companies...")
        # Add a prefix to company columns to avoid name collisions (except for the ID which we join on)
        company_cols = df_companies.columns
        rename_map = {col: f"company_{col}" for col in company_cols if col != "id"}
        df_companies_renamed = df_companies.rename(columns=rename_map)
        
        # Merge on opportunity.companyId = company.id
        df_merged = pd.merge(
            df_opportunities, 
            df_companies_renamed, 
            left_on="companyId", 
            right_on="id", 
            how="left",
            suffixes=("", "_from_company")
        )
        
        # Optionally merge with people if pointOfContactId exists
        if not df_people.empty and "pointOfContactId" in df_merged.columns:
            print("Correlating with People (Points of Contact)...")
            people_cols = df_people.columns
            rename_map_p = {col: f"person_{col}" for col in people_cols if col != "id"}
            df_people_renamed = df_people.rename(columns=rename_map_p)
            
            df_merged = pd.merge(
                df_merged,
                df_people_renamed,
                left_on="pointOfContactId",
                right_on="id",
                how="left",
                suffixes=("", "_from_person")
            )
            
        merged_file = export_dir / "merged_opportunities_companies.csv"
        df_merged.to_csv(merged_file, index=False, encoding="utf-8-sig")
        print(f"Merged CSV saved to {merged_file}")
    else:
        print("Not enough data to create correlations (missing opportunities, companies, or companyId field).")

    print("--- EXPORT COMPLETE ---")

if __name__ == "__main__":
    main()
