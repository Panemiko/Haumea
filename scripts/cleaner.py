import csv
import sys
import json
import re
from datetime import datetime
from pathlib import Path
from scripts.cnpj_helper import load_all_rfb_data, find_best_cnpj_match, to_title_case, clean_digits, extract_cep

# Mapping standard/alternative field names in the input CSV to our target maps fields
FIELD_MAPPINGS = {
    "title": ["title", "name", "business_name"],
    "category": ["category", "type", "sub_category"],
    "address": ["address", "formatted_address", "location"],
    "website": ["website", "site", "url"],
    "phone": ["phone", "telephone", "phone_number"],
    "emails": ["emails", "email", "email_address"]
}

def extract_city_state(address_str: str, complete_address_json_str: str = None) -> tuple:
    """Extracts city and state from an address string or complete_address JSON string."""
    city = ""
    state = ""
    
    # 1. Attempt extraction from the address string
    if address_str:
        parts = [p.strip() for p in address_str.split(',')]
        for part in reversed(parts):
            if '-' in part:
                subparts = [s.strip() for s in part.split('-')]
                if len(subparts) >= 2:
                    state_candidate = subparts[-1]
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

def format_cnpj(digits: str) -> str:
    """Formats a 14-digit CNPJ string to standard format."""
    digits = clean_digits(digits)
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

def format_phone(ddd: str, number: str) -> str:
    """Formats a Brazilian phone number."""
    ddd = clean_digits(ddd)
    number = clean_digits(number)
    if not ddd or not number:
        return ""
    if len(number) == 9:
        return f"({ddd}) {number[:5]}-{number[5:]}"
    elif len(number) == 8:
        return f"({ddd}) {number[:4]}-{number[4:]}"
    return f"({ddd}) {number}"

def format_address(est: dict, city_name: str) -> str:
    """Formats a full CNPJ address string."""
    parts = []
    logradouro = est.get("logradouro", "").strip()
    tipo = est.get("tipo_logradouro", "").strip()
    if tipo:
        logradouro = f"{tipo} {logradouro}"
    if logradouro:
        parts.append(logradouro)
        
    numero = est.get("numero", "").strip()
    if numero:
        parts.append(numero)
        
    compl = est.get("complemento", "").strip()
    if compl:
        parts.append(compl)
        
    bairro = est.get("bairro", "").strip()
    if bairro:
        parts.append(bairro)
        
    cep = est.get("cep", "").strip()
    if cep:
        if len(cep) == 8:
            cep = f"{cep[:5]}-{cep[5:]}"
        parts.append(f"CEP {cep}")
        
    if city_name:
        parts.append(city_name)
    uf = est.get("uf", "").strip()
    if uf:
        parts.append(uf)
        
    return ", ".join(parts)

def calculate_age_years(date_str: str) -> float:
    """Computes age in years from activity start date (YYYYMMDD)."""
    if not date_str:
        return 0.0
    try:
        start_date = datetime.strptime(date_str, "%Y%m%d")
        delta = datetime.now() - start_date
        return round(delta.days / 365.25, 1)
    except Exception:
        return 0.0

def clean_csv(input_path: Path, output_path: Path = None, skip_cnpj: bool = False) -> Path:
    """Loads scraped CSV, resolves city/states, loads and matches CNPJ details in parallel, cleans rows and normalizes schema."""
    input_path = Path(input_path)
    if not output_path:
        output_path = input_path.parent / f"{input_path.stem}_cleaned{input_path.suffix}"
    else:
        output_path = Path(output_path)
        
    print(f"--- STARTING DATA CLEANING & ENRICHMENT ---")
    print(f"Reading input CSV: {input_path}")
    
    # Encoding fallback detection
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
            
    print(f"Detected/Using encoding: {encoding}")
    
    rows = []
    try:
        with open(input_path, mode='r', encoding=encoding, newline='') as infile:
            sample = infile.read(2048)
            infile.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
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
                    rows.append({k.strip().lstrip('\ufeff'): v for k, v in r.items() if k})
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)
        
    if not rows:
        print("Error: Input CSV is empty.", file=sys.stderr)
        sys.exit(1)
        
    # Phase 1: Identify unique cities and states from leads
    locations = set()
    for row in rows:
        address_val = ""
        for f in FIELD_MAPPINGS["address"]:
            if f in row:
                address_val = row[f].strip() if row[f] else ""
                break
        comp_addr = row.get("complete_address", "")
        city, state = extract_city_state(address_val, comp_addr)
        if city and state:
            locations.add((city, state))
            
    cities = [loc[0] for loc in locations]
    states = [loc[1] for loc in locations]
    
    # Phase 2: Load RFB CNPJ databases for the regions
    rfb_data = {}
    if not skip_cnpj:
        rfb_data = load_all_rfb_data(cities, states)
    
    # Schema configuration
    output_fieldnames = [
        # Maps fields
        "maps_title",
        "maps_category",
        "maps_city",
        "maps_state",
        "maps_website",
        "maps_instagram",
        "maps_facebook",
        "maps_phone",
        "maps_emails",
        "maps_observations",
        "maps_thumbnail",
        "maps_order_online",
        "maps_review_count",
        "maps_review_rating",
        "maps_user_reviews",
        
        # CNPJ fields
        "cnpj_cnpj",
        "cnpj_razao_social",
        "cnpj_nome_fantasia",
        "cnpj_situacao_cadastral",
        "cnpj_data_inicio_atividade",
        "cnpj_cnae_fiscal_principal",
        "cnpj_cnae_descricao",
        "cnpj_capital_social",
        "cnpj_opcao_pelo_simples",
        "cnpj_opcao_pelo_mei",
        "cnpj_socios",
        "cnpj_quantidade_socios",
        "cnpj_idade_empresa_anos",
        "cnpj_telefone",
        "cnpj_email",
        "cnpj_endereco",
        
        # Review fields
        "review_q1_site",
        "review_q2_responsivo",
        "review_q3_instagram",
        "review_q4_whatsapp",
        "review_q5_amador",
        "review_q6_insta_qualidade",
        "review_score",
        "review_status",
        "review_score_table"
    ]
    
    cleaned_rows = []
    flagged_inactive = 0
    skipped_no_contact = 0
    
    # Phase 3: Match and clean leads
    for row in rows:
        lead = {}
        
        # Extract title
        for f in FIELD_MAPPINGS["title"]:
            if f in row:
                lead["title"] = row[f].strip() if row[f] else ""
                break
        if not lead.get("title"):
            continue
            
        # Extract category
        for f in FIELD_MAPPINGS["category"]:
            if f in row:
                lead["category"] = row[f].strip() if row[f] else ""
                break
                
        # Extract address and location details
        address_val = ""
        for f in FIELD_MAPPINGS["address"]:
            if f in row:
                address_val = row[f].strip() if row[f] else ""
                break
        comp_addr = row.get("complete_address", "")
        city, state = extract_city_state(address_val, comp_addr)
        lead["city"] = city
        lead["state"] = state
        lead["address"] = address_val
        lead["cep"] = extract_cep(address_val, comp_addr)
        
        # Extract website and social URLs
        raw_website = ""
        for f in FIELD_MAPPINGS["website"]:
            if f in row:
                raw_website = row[f].strip() if row[f] else ""
                break
                
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
                
        lead["website"] = actual_website
        lead["instagram"] = instagram_val
        lead["facebook"] = facebook_val
        
        # Extract phone
        for f in FIELD_MAPPINGS["phone"]:
            if f in row:
                lead["phone"] = row[f].strip() if row[f] else ""
                break
                
        # Extract emails
        for f in FIELD_MAPPINGS["emails"]:
            if f in row:
                lead["emails"] = row[f].strip() if row[f] else ""
                break
                
        # Extract observations
        lead["observations"] = (row.get("observations") or "").strip()
        
        # Assemble standard Maps cleaned row
        cleaned_row = {
            "maps_title": lead["title"],
            "maps_category": lead.get("category", ""),
            "maps_city": lead["city"],
            "maps_state": lead["state"],
            "maps_website": lead["website"],
            "maps_instagram": lead["instagram"],
            "maps_facebook": lead["facebook"],
            "maps_phone": lead.get("phone", ""),
            "maps_emails": lead.get("emails", ""),
            "maps_observations": lead.get("observations", ""),
            "maps_thumbnail": (row.get("thumbnail") or "").strip(),
            "maps_order_online": (row.get("order_online") or "").strip(),
            "maps_review_count": (row.get("review_count") or "").strip(),
            "maps_review_rating": (row.get("review_rating") or "").strip(),
            "maps_user_reviews": (row.get("user_reviews") or "").strip()
        }
        
        # Try matching with CNPJ
        match = None
        if not skip_cnpj:
            match = find_best_cnpj_match(lead, rfb_data)
        
        if match:
            est = match["est"]
            comp = match["comp"]
            partners = match["partners"]
            simples_info = match["simples"]
            
            # Check and flag inactive companies (do not delete automatically)
            # RFB status code '02' is ATIVA. All other statuses (like '08' baixada) are inactive.
            status_code = est.get("situacao_cadastral", "")
            status_map = {
                "01": "Nula",
                "02": "Ativa",
                "03": "Suspensa",
                "04": "Inapta",
                "08": "Baixada"
            }
            situacao = status_map.get(status_code, f"Inativa (Código {status_code})")
            if status_code != "02":
                flagged_inactive += 1
                print(f"Flagging '{lead['title']}' - CNPJ status is inactive: {situacao}")
                
            # Populate CNPJ details with Title Case conversions and formatting
            cleaned_row["cnpj_cnpj"] = format_cnpj(est["cnpj_basico"] + est["cnpj_ordem"] + est["cnpj_dv"])
            cleaned_row["cnpj_razao_social"] = to_title_case(comp.get("razao_social", ""))
            cleaned_row["cnpj_nome_fantasia"] = to_title_case(est.get("nome_fantasia", ""))
            cleaned_row["cnpj_situacao_cadastral"] = situacao
            
            # Date formatting (YYYYMMDD to YYYY-MM-DD)
            ini_date = est.get("data_inicio_atividade", "")
            if len(ini_date) == 8:
                cleaned_row["cnpj_data_inicio_atividade"] = f"{ini_date[:4]}-{ini_date[4:6]}-{ini_date[6:]}"
            else:
                cleaned_row["cnpj_data_inicio_atividade"] = ini_date
                
            cleaned_row["cnpj_cnae_fiscal_principal"] = est.get("cnae_principal", "")
            cnae_desc = rfb_data.get("cnaes", {}).get(est.get("cnae_principal", ""), "")
            cleaned_row["cnpj_cnae_descricao"] = to_title_case(cnae_desc)
            
            # Capital Social parsing
            cleaned_row["cnpj_capital_social"] = comp.get("capital_social", "0.0")
            
            # Simples/MEI maps
            cleaned_row["cnpj_opcao_pelo_simples"] = simples_info.get("opcao_simples", "N")
            cleaned_row["cnpj_opcao_pelo_mei"] = simples_info.get("opcao_mei", "N")
            
            # Partners formatting
            partner_descriptions = []
            for p in partners:
                p_name = to_title_case(p.get("nome", ""))
                q_desc = rfb_data.get("qualifications", {}).get(p.get("qual_code", ""), "")
                if q_desc:
                    partner_descriptions.append(f"{p_name} ({to_title_case(q_desc)})")
                else:
                    partner_descriptions.append(p_name)
            cleaned_row["cnpj_socios"] = ", ".join(partner_descriptions)
            cleaned_row["cnpj_quantidade_socios"] = len(partners)
            cleaned_row["cnpj_idade_empresa_anos"] = calculate_age_years(ini_date)
            
            cleaned_row["cnpj_telefone"] = format_phone(est.get("ddd_1", ""), est.get("telefone_1", ""))
            cleaned_row["cnpj_email"] = est.get("email", "").lower()
            
            # Resolve city name from codes
            c_name = lead["city"]
            cleaned_row["cnpj_endereco"] = format_address(est, c_name)
        else:
            # Not matched, leave empty
            for k in output_fieldnames:
                if k.startswith("cnpj_"):
                    cleaned_row[k] = ""
                    
        # Check for useless leads (no contacts whatsoever)
        has_contact = (
            (cleaned_row["maps_phone"] and cleaned_row["maps_phone"].strip()) or
            (cleaned_row["maps_emails"] and cleaned_row["maps_emails"].strip()) or
            (cleaned_row["maps_website"] and cleaned_row["maps_website"].strip()) or
            (cleaned_row["maps_instagram"] and cleaned_row["maps_instagram"].strip()) or
            (cleaned_row["maps_facebook"] and cleaned_row["maps_facebook"].strip())
        )
        if not has_contact:
            skipped_no_contact += 1
            print(f"Flagging '{lead['title']}' - has no contact options (phone, email, website, instagram, facebook).")
            
        # Initialize review fields as blank
        for rf in ["review_q1_site", "review_q2_responsivo", "review_q3_instagram", "review_q4_whatsapp", "review_q5_amador", "review_q6_insta_qualidade", "review_score", "review_status", "review_score_table"]:
            cleaned_row[rf] = ""
            
        cleaned_rows.append(cleaned_row)
        
    print(f"Cleaning statistics:")
    print(f" - Flagged inactive (non-ATIVA) companies:   {flagged_inactive}")
    print(f" - Contactless leads flagged:                {skipped_no_contact}")
    print(f" - Active leads remaining:                    {len(cleaned_rows)}")
    
    print(f"Writing cleaned CSV to: {output_path}")
    try:
        with open(output_path, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=output_fieldnames)
            writer.writeheader()
            writer.writerows(cleaned_rows)
        print(f"Successfully wrote cleaned CSV data!")
    except Exception as e:
        print(f"Error writing output CSV: {e}", file=sys.stderr)
        sys.exit(1)

    # Also save structured JSON alongside
    json_path = output_path.with_suffix('.json')
    print(f"Writing cleaned JSON to: {json_path}")
    try:
        json_rows = []
        for r in cleaned_rows:
            r_copy = dict(r)
            if r_copy.get("review_score_table"):
                try:
                    r_copy["review_score_table"] = json.loads(r_copy["review_score_table"])
                except Exception:
                    pass
            json_rows.append(r_copy)
        with open(json_path, mode='w', encoding='utf-8') as jf:
            json.dump(json_rows, jf, ensure_ascii=False, indent=2)
        print(f"Successfully wrote cleaned JSON data!")
    except Exception as e:
        print(f"Error writing output JSON: {e}", file=sys.stderr)
        sys.exit(1)
        
    return output_path
