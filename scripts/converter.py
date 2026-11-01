import csv
import json
import sys
from pathlib import Path
from scripts.cleaner import extract_city_state, format_phone, format_cnpj
from scripts.cnpj_helper import clean_digits

# Mapping case-insensitive aliases to standard Register keys
MAPPING_ALIASES = {
    "maps_title": ["title", "name", "business_name", "nome", "razão social", "razao social", "empresa", "nome fantasia"],
    "maps_category": ["category", "type", "sub_category", "categoria", "ramo", "atividade"],
    "maps_website": ["website", "site", "url", "página", "pagina"],
    "maps_phone": ["phone", "telephone", "phone_number", "telefone", "celular", "whatsapp", "whats"],
    "maps_emails": ["email", "emails", "e-mail", "e_mail", "contato"],
    "maps_address": ["address", "formatted_address", "location", "endereço", "endereco", "logradouro"],
    "maps_instagram": ["instagram", "insta", "instagram_url"],
    "maps_facebook": ["facebook", "fb", "facebook_url"],
    "maps_city": ["city", "cidade"],
    "maps_state": ["state", "uf", "estado"],
    "cnpj_cnpj": ["cnpj", "cnpj_number"]
}

def convert_csv_to_json(input_path: Path, output_path: Path = None, apply_mapping: bool = True) -> Path:
    input_path = Path(input_path)
    if not output_path:
        output_path = input_path.with_suffix('.json')
    else:
        output_path = Path(output_path)
        
    print(f"--- STARTING CSV TO JSON CONVERSION ---")
    print(f"Reading input CSV: {input_path}")
    
    # Encoding detection
    encoding = 'utf-8'
    try:
        with open(input_path, 'rb') as f:
            first_bytes = f.read(3)
        if first_bytes == b'\xef\xbb\xbf':
            encoding = 'utf-8-sig'
        else:
            with open(input_path, mode='r', encoding='utf-8', newline='') as f:
                f.readline()
    except UnicodeDecodeError:
        encoding = 'latin-1'
            
    print(f"Detected encoding: {encoding}")
    
    rows = []
    try:
        with open(input_path, mode='r', encoding=encoding, newline='') as infile:
            sample = infile.read(2048)
            infile.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=[',', ';', '\t'])
            except Exception:
                dialect = 'excel'
                
            reader = csv.DictReader(infile, dialect=dialect)
            fieldnames = [f.strip().lstrip('\ufeff') for f in reader.fieldnames] if reader.fieldnames else []
            
            # Re-read with stripped headers
            infile.seek(0)
            reader = csv.DictReader(infile, fieldnames=fieldnames, dialect=dialect)
            next(reader) # skip header
            
            for r in reader:
                if r:
                    rows.append({k.strip().lstrip('\ufeff'): v.strip() if v else "" for k, v in r.items() if k})
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)
        
    if not rows:
        print("Error: Input CSV is empty.", file=sys.stderr)
        sys.exit(1)
        
    converted_rows = []
    for r in rows:
        converted_row = {}
        
        if apply_mapping:
            # 1. First copy original values to standard keys using alias map
            for std_key, aliases in MAPPING_ALIASES.items():
                val = ""
                # Try standard key first
                if std_key in r:
                    val = r[std_key]
                else:
                    # Look for case-insensitive alias match
                    for k, v in r.items():
                        if k.lower() in aliases or k.lower().replace(" ", "_") == std_key:
                            val = v
                            break
                converted_row[std_key] = val
            
            # 2. Keep any extra fields from original row that don't match standard keys or aliases
            mapped_keys_and_aliases = set(MAPPING_ALIASES.keys())
            for aliases in MAPPING_ALIASES.values():
                mapped_keys_and_aliases.update(aliases)
                
            for k, v in r.items():
                k_lower = k.lower()
                if k_lower not in mapped_keys_and_aliases and k_lower.replace(" ", "_") not in mapped_keys_and_aliases:
                    converted_row[k] = v
                    
            # 3. Apply normalization/formatting for Brazilian formats if mapped
            
            # Formatting CNPJ
            if converted_row.get("cnpj_cnpj"):
                cleaned_cnpj = clean_digits(converted_row["cnpj_cnpj"])
                if len(cleaned_cnpj) == 14:
                    converted_row["cnpj_cnpj"] = format_cnpj(cleaned_cnpj)
                    
            # Formatting phone numbers
            if converted_row.get("maps_phone"):
                cleaned_ph = clean_digits(converted_row["maps_phone"])
                # If phone has 10 or 11 digits (DDD + number)
                if len(cleaned_ph) in (10, 11):
                    ddd = cleaned_ph[:2]
                    num = cleaned_ph[2:]
                    converted_row["maps_phone"] = format_phone(ddd, num)
            
            # Extract city and state from address if not present
            if not converted_row.get("maps_city") or not converted_row.get("maps_state"):
                extracted_city, extracted_state = extract_city_state(converted_row.get("maps_address"))
                if extracted_city and not converted_row.get("maps_city"):
                    converted_row["maps_city"] = extracted_city
                if extracted_state and not converted_row.get("maps_state"):
                    converted_row["maps_state"] = extracted_state
                    
            # Default review status/score if not present so it registers nicely
            if "review_score" not in converted_row or not converted_row["review_score"]:
                converted_row["review_score"] = "1" # default qualification
        else:
            # Keep as-is if mapping not applied
            converted_row = r
            
        converted_rows.append(converted_row)
        
    print(f"Writing JSON output to: {output_path}")
    try:
        with open(output_path, 'w', encoding='utf-8') as jf:
            json.dump(converted_rows, jf, ensure_ascii=False, indent=2)
        print(f"Successfully converted CSV to JSON! Total records: {len(converted_rows)}")
    except Exception as e:
        print(f"Error writing JSON: {e}", file=sys.stderr)
        sys.exit(1)
        
    return output_path
