import csv
import json
import sys
from pathlib import Path

# Fields we want to keep from the input CSV
REQUIRED_FIELDS = [
    "title",
    "category",
    "address",
    "website",
    "phone",
    "emails"
]

# Mapping standard/alternative field names in the input CSV to our target output fields
FIELD_MAPPINGS = {}

# New columns to add
NEW_FIELDS = [
    "observations"
]

def extract_city_state(address_str: str, complete_address_json_str: str = None) -> tuple:
    """Extracts city and state from an address string or complete_address JSON string."""
    city = ""
    state = ""
    
    # 1. Attempt extraction from the address string
    if address_str:
        # Split address by comma to analyze components from the right
        parts = [p.strip() for p in address_str.split(',')]
        for part in reversed(parts):
            if '-' in part:
                subparts = [s.strip() for s in part.split('-')]
                if len(subparts) >= 2:
                    state_candidate = subparts[-1]
                    # Check if the state is a 2-letter uppercase abbreviation (like RS, SP, RJ)
                    if len(state_candidate) == 2 and state_candidate.isupper():
                        city = subparts[-2]
                        state = state_candidate
                        break
                        
    # 2. Fallback: Parse complete_address JSON if city/state not found
    if (not city or not state) and complete_address_json_str:
        try:
            addr_data = json.loads(complete_address_json_str)
            if isinstance(addr_data, dict):
                if not city:
                    city = addr_data.get('city', '').strip()
                if not state:
                    state_val = addr_data.get('state', '').strip()
                    # Map full Brazilian state names to standard 2-letter abbreviations
                    state_abbrs = {
                        "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM", "Bahia": "BA",
                        "Ceará": "CE", "Distrito Federal": "DF", "Espírito Santo": "ES", "Goiás": "GO",
                        "Maranhão": "MA", "Mato Grosso": "MT", "Mato Grosso do Sul": "MS", "Minas Gerais": "MG",
                        "Pará": "PA", "Paraíba": "PB", "Paraná": "PR", "Pernambuco": "PE", "Piauí": "PI",
                        "Rio de Janeiro": "RJ", "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS",
                        "Rondônia": "RO", "Roraima": "RR", "Santa Catarina": "SC", "São Paulo": "SP",
                        "Sergipe": "SE", "Tocantins": "TO"
                    }
                    state = state_abbrs.get(state_val, state_val)
        except Exception:
            pass
            
    return city, state


def clean_csv(input_path: Path, output_path: Path = None) -> Path:
    """Cleans the input CSV by keeping only specified fields and parsing address details."""
    input_path = Path(input_path)
    if not output_path:
        output_path = input_path.parent / f"{input_path.stem}_cleaned{input_path.suffix}"
    else:
        output_path = Path(output_path)
        
    print(f"--- STARTING DATA CLEANING ---")
    print(f"Reading input CSV: {input_path}")
    
    # Try reading with utf-8 first, fall back to utf-8-sig or latin-1 if needed
    encoding = 'utf-8'
    try:
        with open(input_path, mode='r', encoding=encoding, newline='') as f:
            f.readline()
    except UnicodeDecodeError:
        encoding = 'utf-8-sig'
        try:
            with open(input_path, mode='r', encoding=encoding, newline='') as f:
                f.readline()
        except UnicodeDecodeError:
            encoding = 'latin-1'
            
    print(f"Detected/Using encoding: {encoding}")
    
    try:
        with open(input_path, mode='r', encoding=encoding, newline='') as infile:
            # Read a sample to detect CSV dialect (delimiter, quote character, etc.)
            sample = infile.read(2048)
            infile.seek(0)
            
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = 'excel'  # Default to standard Excel-style CSV
                
            reader = csv.DictReader(infile, dialect=dialect)
            
            # Get original headers
            fieldnames = reader.fieldnames
            if not fieldnames:
                print("Error: The CSV file has no headers.", file=sys.stderr)
                sys.exit(1)
                
            # Strip whitespace from headers for robust matching
            stripped_fieldnames = [f.strip() for f in fieldnames]
            
            # We recreate DictReader mapping to cleaned headers
            infile.seek(0)
            reader = csv.DictReader(infile, fieldnames=stripped_fieldnames, dialect=dialect)
            # Skip the first row which is the header row
            next(reader)
            
            # Prepare output fieldnames (statically defined to match exact user request)
            output_fieldnames = [
                "title",
                "category",
                "city",
                "state",
                "website",
                "instagram",
                "facebook",
                "phone",
                "observations",
                "emails"
            ]
            
            # Inform the user if any required fields are missing in input CSV (considering fallback mappings)
            missing_fields = []
            for field in REQUIRED_FIELDS:
                possible_fields = FIELD_MAPPINGS.get(field, [field])
                if not any(f in stripped_fieldnames for f in possible_fields):
                    missing_fields.append(field)
            
            if missing_fields:
                print(f"Warning: The following fields were not found in the input CSV and will be empty: {missing_fields}")
                
            print(f"Writing cleaned CSV to: {output_path}")
            
            with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=output_fieldnames)
                writer.writeheader()
                
                rows_written = 0
                for row in reader:
                    # Temporary storage for fields we need to extract from but might not keep in output
                    address_val = ""
                    raw_website = ""
                    
                    # Find address field for city/state extraction
                    for f in FIELD_MAPPINGS.get("address", ["address"]):
                        if f in row:
                            address_val = row[f].strip()
                            break
                            
                    # Find website field for website/social extraction
                    for f in FIELD_MAPPINGS.get("website", ["website"]):
                        if f in row:
                            raw_website = row[f].strip()
                            break
                    
                    cleaned_row = {}
                    
                    # Title
                    title_val = ""
                    for f in FIELD_MAPPINGS.get("title", ["title"]):
                        if f in row:
                            title_val = row[f].strip()
                            break
                    cleaned_row["title"] = title_val
                    
                    # Category
                    category_val = ""
                    for f in FIELD_MAPPINGS.get("category", ["category"]):
                        if f in row:
                            category_val = row[f].strip()
                            break
                    cleaned_row["category"] = category_val
                    
                    # City & State
                    complete_address_str = row.get('complete_address')
                    city, state = extract_city_state(address_val, complete_address_str)
                    cleaned_row["city"] = city
                    cleaned_row["state"] = state
                    
                    # Website & Socials
                    instagram_val = ""
                    facebook_val = ""
                    actual_website = ""
                    
                    if raw_website:
                        raw_website_lower = raw_website.lower()
                        if "instagram.com" in raw_website_lower:
                            instagram_val = raw_website
                        elif "facebook.com" in raw_website_lower or "fb.com" in raw_website_lower:
                            facebook_val = raw_website
                        elif "wa.me" in raw_website_lower:
                            pass
                        else:
                            actual_website = raw_website
                            
                    cleaned_row["website"] = actual_website
                    cleaned_row["instagram"] = instagram_val
                    cleaned_row["facebook"] = facebook_val
                    
                    # Phone
                    phone_val = ""
                    for f in FIELD_MAPPINGS.get("phone", ["phone"]):
                        if f in row:
                            phone_val = row[f].strip()
                            break
                    cleaned_row["phone"] = phone_val
                    
                    # observations
                    observations_val = ""
                    for f in FIELD_MAPPINGS.get("observations", ["observations"]):
                        if f in row:
                            observations_val = row[f].strip()
                            break

                    # Google Business Profile Completeness Check
                    missing_score = 0
                    missing_fields = []
                    
                    # 1. Phone
                    if not phone_val or phone_val.lower() == "null":
                        missing_score += 1
                        missing_fields.append("telefone")
                        
                    # 2. Website
                    if not raw_website or raw_website.lower() == "null":
                        missing_score += 1
                        missing_fields.append("website")
                        
                    # 3. Open Hours
                    open_hours = row.get("open_hours", "").strip().lower()
                    if not open_hours or open_hours == "{}" or open_hours == '"{}"' or open_hours == "null":
                        missing_score += 1
                        missing_fields.append("horário de funcionamento")
                        
                    # 4. Thumbnail / Image
                    thumbnail = row.get("thumbnail", "").strip()
                    if not thumbnail or thumbnail.lower() == "null" or "streetviewpixels-pa.googleapis.com" in thumbnail:
                        missing_score += 1
                        missing_fields.append("foto de capa")
                        
                    # 5. About
                    about = row.get("about", "").strip().lower()
                    if not about or about == "null" or about == "[]":
                        missing_score += 0.5
                        missing_fields.append("sobre")
                        
                    # 6. Order Online
                    order_online = row.get("order_online", "").strip().lower()
                    if not order_online or order_online == "null" or order_online == "false":
                        missing_score += 0.5
                        missing_fields.append("pedido online")
                        
                    if missing_score >= 3:
                        if len(missing_fields) > 1:
                            missing_str = ", ".join(missing_fields[:-1]) + " e " + missing_fields[-1]
                        else:
                            missing_str = missing_fields[0]
                            
                        obs_addition = f"Perfil no Google faltando {missing_str}."
                        if observations_val:
                            observations_val = f"{observations_val} | {obs_addition}"
                        else:
                            observations_val = obs_addition
                    
                    cleaned_row["observations"] = observations_val
                    
                    # Emails
                    emails_val = ""
                    for f in FIELD_MAPPINGS.get("emails", ["emails"]):
                        if f in row:
                            emails_val = row[f].strip()
                            break
                    cleaned_row["emails"] = emails_val
                    
                    writer.writerow(cleaned_row)
                    rows_written += 1
                    
            print(f"Successfully cleaned CSV! Processed {rows_written} rows.")
            print(f"---------------------------------\n")
            return output_path
            
    except FileNotFoundError:
        print(f"Error: The file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing CSV: {e}", file=sys.stderr)
        sys.exit(1)
