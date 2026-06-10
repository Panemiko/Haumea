import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

def register_json(json_file_path: Path):
    """Reads a JSON file and POSTs its content to the webhook API."""
    if not json_file_path.exists():
        print(f"Error: JSON file '{json_file_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON from '{json_file_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading JSON file: {e}", file=sys.stderr)
        sys.exit(1)

    url = "http://localhost:4000/webhooks/workflows/eeb1747d-ca2f-42ba-8763-c061cd92d718/2c1a82b0-0d26-4afb-a991-c2566d0b828c"
    print(f"\n--- REGISTERING DATA TO WEBHOOK ---")
    print(f"File: {json_file_path}")
    print(f"URL:  {url}")

    payload = {"entries": data}
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="ignore")
            print(f"Success! Status Code: {status}")
            if body:
                print(f"Response: {body}")
            print(f"---------------------------------\n")
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP Request failed with status code {e.code}.", file=sys.stderr)
        try:
            error_body = e.read().decode("utf-8", errors="ignore")
            if error_body:
                print(f"Response: {error_body}", file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Failed to reach the server. Reason: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error sending request: {e}", file=sys.stderr)
        sys.exit(1)
