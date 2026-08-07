import os
import re
import zipfile
import unicodedata
import concurrent.futures
from pathlib import Path

# Set up paths relative to project root
project_root = Path(__file__).parent.parent.resolve()
cnpj_dir = project_root / "cnpj"

# Mappings for Empresas starting CNPJ Básicos to determine target zip file
# (Since Empresas zip files are sorted sequentially)
EMPRESAS_RANGES = [
    (0, "41273589"), # Empresas0 starts here and goes to end
    (1, "00000000"),
    (2, "04631961"),
    (3, "09253554"),
    (4, "13846068"),
    (5, "18421567"),
    (6, "22967211"),
    (7, "27499601"),
    (8, "32066824"),
    (9, "36627969")
]

def clean_digits(val: str) -> str:
    """Removes all non-digit characters from a string."""
    return re.sub(r'\D', '', val) if val else ""

def normalize_text(text: str) -> str:
    """Normalizes text for matching: uppercase, no accents, alphanumeric and spaces only."""
    if not text:
        return ""
    text = str(text).strip().upper()
    # Remove accents
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    # Replace non-alphanumeric with spaces
    text = re.sub(r'[^A-Z0-9\s]', ' ', text)
    return " ".join(text.split())

def to_title_case(text: str) -> str:
    """Converts a string to Title Case, preserving Portuguese prepositions and special characters."""
    if not text:
        return ""
    words = text.strip().split()
    prepositions = {'de', 'da', 'do', 'dos', 'das', 'e', 'em', 'para', 'com', 'por', 'a', 'o'}
    title_words = []
    for i, word in enumerate(words):
        word_lower = word.lower()
        if word_lower in prepositions and i > 0 and i < len(words) - 1:
            title_words.append(word_lower)
        else:
            if '&' in word:
                parts = word.split('&')
                title_words.append('&'.join(p.capitalize() for p in parts))
            elif '/' in word:
                parts = word.split('/')
                title_words.append('/'.join(p.capitalize() for p in parts))
            elif '.' in word:
                parts = word.split('.')
                title_words.append('.'.join(p.capitalize() if p else '' for p in parts))
            else:
                title_words.append(word.capitalize())
    return " ".join(title_words)

def extract_cep(address_str: str, complete_address_json_str: str = None) -> str:
    """Extracts a clean 8-digit CEP from address string or complete address JSON."""
    if complete_address_json_str:
        try:
            import json
            addr_data = json.loads(complete_address_json_str)
            if isinstance(addr_data, dict):
                cep = addr_data.get('postal_code', '').strip()
                cep_digits = clean_digits(cep)
                if len(cep_digits) == 8:
                    return cep_digits
        except Exception:
            pass
    if address_str:
        match = re.search(r'\b\d{5}-?\d{3}\b', address_str)
        if match:
            return clean_digits(match.group(0))
    return ""

def get_municipality_codes(cities: list) -> dict:
    """Reads Municipios.zip and returns a map of normalized city names to their list of codes."""
    codes_map = {}
    normalized_cities = {normalize_text(c) for c in cities if c}
    if not normalized_cities:
        return codes_map
        
    municipios_path = cnpj_dir / "Municipios.zip"
    if not municipios_path.exists():
        return codes_map
        
    with zipfile.ZipFile(municipios_path) as z:
        for name in z.namelist():
            with z.open(name) as f:
                for line_bytes in f:
                    line = line_bytes.decode('latin-1').strip()
                    if not line:
                        continue
                    parts = [p.replace('"', '').strip() for p in line.split(';')]
                    if len(parts) >= 2:
                        code = parts[0]
                        name_val = normalize_text(parts[1])
                        if name_val in normalized_cities:
                            if name_val not in codes_map:
                                codes_map[name_val] = []
                            codes_map[name_val].append(code)
    return codes_map

def scan_single_establishments_zip(zip_path: Path, target_cities: set, target_states: set) -> list:
    """Scans a single Estabelecimentos ZIP file for records matching city codes and states."""
    results = []
    if not zip_path.exists():
        return results
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) < 21:
                            continue
                        
                        uf = parts[19]
                        city_code = parts[20]
                        
                        if uf in target_states and city_code in target_cities:
                            est = {
                                "cnpj_basico": parts[0],
                                "cnpj_ordem": parts[1],
                                "cnpj_dv": parts[2],
                                "matriz_filial": parts[3],
                                "nome_fantasia": parts[4],
                                "situacao_cadastral": parts[5],
                                "data_situacao_cadastral": parts[6],
                                "data_inicio_atividade": parts[10],
                                "cnae_principal": parts[11],
                                "tipo_logradouro": parts[13],
                                "logradouro": parts[14],
                                "numero": parts[15],
                                "complemento": parts[16],
                                "bairro": parts[17],
                                "cep": parts[18],
                                "uf": parts[19],
                                "municipio_code": parts[20],
                                "ddd_1": parts[21],
                                "telefone_1": parts[22],
                                "ddd_2": parts[23],
                                "telefone_2": parts[24],
                                "email": parts[27]
                            }
                            results.append(est)
    except Exception as e:
         print(f"Error scanning {zip_path.name}: {e}")
    return results

def scan_single_empresas_zip(zip_path: Path, candidate_basicos: set) -> dict:
    """Scans a single Empresas ZIP file for company details corresponding to candidates."""
    results = {}
    if not zip_path.exists():
        return results
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) < 5:
                            continue
                        cnpj_basico = parts[0]
                        if cnpj_basico in candidate_basicos:
                            results[cnpj_basico] = {
                                "razao_social": parts[1],
                                "natureza_juridica": parts[2],
                                "capital_social": parts[4].replace(',', '.')
                            }
    except Exception as e:
        print(f"Error scanning {zip_path.name}: {e}")
    return results

def scan_single_socios_zip(zip_path: Path, candidate_basicos: set) -> dict:
    """Scans a single Socios ZIP file for partner details (names and qualification codes)."""
    results = {}
    if not zip_path.exists():
        return results
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) < 5:
                            continue
                        cnpj_basico = parts[0]
                        if cnpj_basico in candidate_basicos:
                            partner_name = parts[2]
                            qual_code = parts[4]
                            if cnpj_basico not in results:
                                results[cnpj_basico] = []
                            results[cnpj_basico].append({
                                "nome": partner_name,
                                "qual_code": qual_code
                            })
    except Exception as e:
        print(f"Error scanning {zip_path.name}: {e}")
    return results

def load_simples(candidate_basicos: set) -> dict:
    """Scans Simples.zip for MEI and Simples Nacional details corresponding to candidates."""
    results = {}
    simples_path = cnpj_dir / "Simples.zip"
    if not simples_path.exists():
        return results
    try:
        with zipfile.ZipFile(simples_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) < 6:
                            continue
                        cnpj_basico = parts[0]
                        if cnpj_basico in candidate_basicos:
                            results[cnpj_basico] = {
                                "opcao_simples": parts[1],
                                "opcao_mei": parts[4]
                            }
    except Exception as e:
        print(f"Error scanning Simples.zip: {e}")
    return results

def load_cnae_descriptions() -> dict:
    """Reads Cnaes.zip and maps CNAE codes to description text."""
    results = {}
    cnaes_path = cnpj_dir / "Cnaes.zip"
    if not cnaes_path.exists():
        return results
    try:
        with zipfile.ZipFile(cnaes_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) >= 2:
                            results[parts[0]] = parts[1]
    except Exception as e:
        print(f"Error scanning Cnaes.zip: {e}")
    return results

def load_qualifications() -> dict:
    """Reads Qualificacoes.zip and maps qualification codes to description text."""
    results = {}
    quals_path = cnpj_dir / "Qualificacoes.zip"
    if not quals_path.exists():
        return results
    try:
        with zipfile.ZipFile(quals_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) >= 2:
                            results[parts[0]] = parts[1]
    except Exception as e:
        print(f"Error scanning Qualificacoes.zip: {e}")
    return results

def load_all_rfb_data(cities: list, states: list) -> dict:
    """Loads all relevant RFB (Receita Federal) data for given cities/states in memory."""
    print("Resolving city codes from Municipios.zip...")
    city_codes_map = get_municipality_codes(cities)
    
    target_cities = set()
    for c_codes in city_codes_map.values():
        target_cities.update(c_codes)
        
    target_states = set(states)
    
    if not target_cities or not target_states:
        print("No valid target cities or states identified.")
        return {"establishments": [], "companies": {}, "partners": {}, "simples": {}, "cnaes": {}, "qualifications": {}}
        
    print(f"Scanning Estabelecimentos ZIP files in parallel for: {cities} in {states}...")
    est_zip_files = [cnpj_dir / f"Estabelecimentos{i}.zip" for i in range(10)]
    est_zip_files = [f for f in est_zip_files if f.exists()]
    
    establishments = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(scan_single_establishments_zip, f, target_cities, target_states): f
            for f in est_zip_files
        }
        for future in concurrent.futures.as_completed(futures):
            establishments.extend(future.result())
            
    print(f"Found {len(establishments)} establishments in target region.")
    if not establishments:
        return {"establishments": [], "companies": {}, "partners": {}, "simples": {}, "cnaes": {}, "qualifications": {}}
        
    candidate_basicos = {e["cnpj_basico"] for e in establishments}
    
    print("Scanning Empresas ZIP files in parallel for details...")
    emp_zip_files = [cnpj_dir / f"Empresas{i}.zip" for i in range(10)]
    emp_zip_files = [f for f in emp_zip_files if f.exists()]
    companies = {}
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(scan_single_empresas_zip, f, candidate_basicos): f
            for f in emp_zip_files
        }
        for future in concurrent.futures.as_completed(futures):
            companies.update(future.result())
            
    print("Scanning Socios ZIP files in parallel for partner details...")
    soc_zip_files = [cnpj_dir / f"Socios{i}.zip" for i in range(10)]
    soc_zip_files = [f for f in soc_zip_files if f.exists()]
    partners = {}
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(scan_single_socios_zip, f, candidate_basicos): f
            for f in soc_zip_files
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            for k, v in res.items():
                if k not in partners:
                    partners[k] = []
                partners[k].extend(v)
                
    print("Scanning Simples.zip for MEI status...")
    simples = load_simples(candidate_basicos)
    
    print("Reading Cnaes.zip for activity definitions...")
    cnaes = load_cnae_descriptions()
    
    print("Reading Qualificacoes.zip for role qualifications...")
    quals = load_qualifications()
    
    print("CNPJ reference data pre-loaded successfully.")
    return {
        "establishments": establishments,
        "companies": companies,
        "partners": partners,
        "simples": simples,
        "cnaes": cnaes,
        "qualifications": quals
    }

# --- Matching Heuristics ---

def phone_match(lead_phone: str, ddd: str, tel: str) -> bool:
    """Determines if a lead phone number matches a CNPJ phone number."""
    l_digits = clean_digits(lead_phone)
    ddd_digits = clean_digits(ddd)
    tel_digits = clean_digits(tel)
    if not l_digits or not ddd_digits or not tel_digits:
        return False
        
    if l_digits.startswith("55") and len(l_digits) > 10:
        l_digits = l_digits[2:]
        
    rfb_full = ddd_digits + tel_digits
    if l_digits == rfb_full:
        return True
        
    # Handle mobile phone leading 9 mismatch (e.g. 11988887777 vs 1188887777)
    if len(l_digits) == 11 and len(rfb_full) == 10:
        if l_digits[:2] == rfb_full[:2] and l_digits[3:] == rfb_full[2:]:
            return True
            
    # Suffix matching for safety
    if len(tel_digits) >= 8 and tel_digits in l_digits:
        if ddd_digits in l_digits[:3]:
            return True
            
    return False

def email_match(lead_email: str, rfb_email: str) -> bool:
    """Checks if a lead email matches a CNPJ email, ignoring whitespace and casing."""
    if not lead_email or not rfb_email:
        return False
    return lead_email.strip().lower() == rfb_email.strip().lower()

def name_similarity(name1: str, name2: str, city: str = None, state: str = None) -> float:
    """Computes Jaccard token similarity between two sanitized corporate names, ignoring location words."""
    n1 = normalize_text(name1)
    n2 = normalize_text(name2)
    if not n1 or not n2:
        return 0.0
        
    # Standard ignore list
    ignore_tokens = {
        'LTDA', 'LIMITADA', 'EIRELI', 'ME', 'EPP', 'SA', 'S/A', 'SOCIEDADE',
        'ANONIMA', 'CIA', 'COMPANHIA', 'CLINICA', 'CONSULTORIO', 'DRA', 'DR',
        'NUTRI', 'NUTRICIONISTA', 'PSICOLOGA', 'PSICOLOGO', 'PSICO', 'DE', 'DA', 'DO', 'EM'
    }
    # Add target city/state to ignore list dynamically to avoid false matching location-only names (e.g. Banco do Brasil "Lajeado RS")
    if city:
        ignore_tokens.add(normalize_text(city))
    if state:
        ignore_tokens.add(normalize_text(state))
        
    w1 = {w for w in n1.split() if w not in ignore_tokens}
    w2 = {w for w in n2.split() if w not in ignore_tokens}
    if not w1 or not w2:
        return 0.0
        
    intersection = w1.intersection(w2)
    union = w1.union(w2)
    
    # Sub-token match heuristic: if one is a clean subset of the other
    if (w1.issubset(w2) and len(w1) >= 2) or (w2.issubset(w1) and len(w2) >= 2):
        return 0.95
        
    return len(intersection) / len(union)

def address_similarity(lead_address: str, est_logradouro: str) -> float:
    """Calculates address street name token similarity."""
    if not lead_address or not est_logradouro:
        return 0.0
    n1 = normalize_text(lead_address)
    n2 = normalize_text(est_logradouro)
    w1 = set(n1.split())
    w2 = set(n2.split())
    
    # Ignore common address descriptors
    ignore = {'RUA', 'AVENIDA', 'AV', 'R', 'TRAVESSA', 'RODOVIA', 'CENTRO', 'ESTRADA'}
    w1 = w1 - ignore
    w2 = w2 - ignore
    if not w1 or not w2:
        return 0.0
    intersection = w1.intersection(w2)
    if intersection:
        return len(intersection) / min(len(w1), len(w2))
    return 0.0

def partner_match(lead_title: str, partners: list) -> bool:
    """Checks if the lead title matches a partner name (for individual doctor/clinic leads)."""
    n1 = normalize_text(lead_title)
    w1 = {w for w in n1.split() if w not in {'CLINICA', 'CONSULTORIO', 'DRA', 'DR', 'NUTRICIONISTA', 'PSICOLOGA', 'PSICOLOGO'}}
    if len(w1) < 2:
        return False
        
    for p in partners:
        p_name = p.get("nome", "")
        n2 = normalize_text(p_name)
        w2 = set(n2.split())
        if w1.issubset(w2):
            return True
    return False

def calculate_match_score(lead: dict, est: dict, comp: dict, partners: list) -> float:
    """Evaluates the suitability of a CNPJ establishment match using weighted scores."""
    
    # First, verify identifying matches
    has_phone = False
    if lead.get("phone") and est.get("telefone_1"):
        if phone_match(lead["phone"], est.get("ddd_1", ""), est["telefone_1"]):
            has_phone = True
        elif est.get("telefone_2") and phone_match(lead["phone"], est.get("ddd_2", ""), est["telefone_2"]):
            has_phone = True
            
    has_email = False
    if lead.get("emails") and est.get("email"):
        lead_emails = [e.strip() for e in lead["emails"].split(",") if e.strip()]
        for le in lead_emails:
            if email_match(le, est["email"]):
                has_email = True
                break
                
    sim_fantasia = 0.0
    if est.get("nome_fantasia"):
        sim_fantasia = name_similarity(lead["title"], est["nome_fantasia"], lead.get("city"), lead.get("state"))
        
    sim_razao = 0.0
    if comp.get("razao_social"):
        sim_razao = name_similarity(lead["title"], comp["razao_social"], lead.get("city"), lead.get("state"))
        
    has_partner = False
    if partners:
        if partner_match(lead["title"], partners):
            has_partner = True
            
    # Require at least one identifying match to prevent unrelated businesses sharing same street/CEP
    # (e.g. Banco do Brasil matching psychologists in Lajeado RS)
    if not (has_phone or has_email or sim_fantasia >= 0.15 or sim_razao >= 0.15 or has_partner):
        return 0.0
        
    score = 0.0
    if has_phone:
        score += 0.8
    if has_email:
        score += 0.6
    score += sim_fantasia * 0.5
    score += sim_razao * 0.4
    if has_partner:
        score += 0.5
        
    # CEP match (highly specific location)
    if lead.get("cep") and est.get("cep"):
        l_cep = clean_digits(lead["cep"])
        e_cep = clean_digits(est["cep"])
        if l_cep and e_cep and l_cep == e_cep:
            score += 0.4
            
    # Address similarity (Street names)
    if lead.get("address") and est.get("logradouro"):
        addr_sim = address_similarity(lead["address"], est["logradouro"])
        score += addr_sim * 0.3
        
    return score

def find_best_cnpj_match(lead: dict, rfb_data: dict) -> dict:
    """Searches the preloaded RFB dataset for the best matching establishment record."""
    establishments = rfb_data.get("establishments", [])
    companies = rfb_data.get("companies", {})
    partners_map = rfb_data.get("partners", {})
    
    best_est = None
    best_score = 0.0
    
    for est in establishments:
        cnpj_basico = est["cnpj_basico"]
        comp = companies.get(cnpj_basico, {})
        partners = partners_map.get(cnpj_basico, [])
        
        score = calculate_match_score(lead, est, comp, partners)
        if score > best_score:
            best_score = score
            best_est = est
            
    # Requiring threshold
    if best_est and best_score >= 0.4:  # Increased threshold to 0.4 for higher precision with CEP/Address matching
        cnpj_basico = best_est["cnpj_basico"]
        comp = companies.get(cnpj_basico, {})
        partners = partners_map.get(cnpj_basico, [])
        simples_data = rfb_data.get("simples", {}).get(cnpj_basico, {"opcao_simples": "N", "opcao_mei": "N"})
        return {
            "est": best_est,
            "comp": comp,
            "partners": partners,
            "simples": simples_data,
            "match_score": best_score
        }
        
    return None

# --- Targeted Single CNPJ Fallback Lookups ---

def targeted_scan_estabelecimentos(zip_path: Path, cnpj_basico: str, cnpj_ordem: str, cnpj_dv: str) -> dict:
    """Searches a specific zip file for an exact CNPJ base matching."""
    if not zip_path.exists():
        return None
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                with z.open(name) as f:
                    for line_bytes in f:
                        line = line_bytes.decode('latin-1').strip()
                        if not line:
                            continue
                        if cnpj_basico not in line:
                            continue
                        parts = [p.replace('"', '').strip() for p in line.split(';')]
                        if len(parts) < 21:
                            continue
                        if parts[0] == cnpj_basico and parts[1] == cnpj_ordem and parts[2] == cnpj_dv:
                            return {
                                "cnpj_basico": parts[0],
                                "cnpj_ordem": parts[1],
                                "cnpj_dv": parts[2],
                                "matriz_filial": parts[3],
                                "nome_fantasia": parts[4],
                                "situacao_cadastral": parts[5],
                                "data_situacao_cadastral": parts[6],
                                "data_inicio_atividade": parts[10],
                                "cnae_principal": parts[11],
                                "tipo_logradouro": parts[13],
                                "logradouro": parts[14],
                                "numero": parts[15],
                                "complemento": parts[16],
                                "bairro": parts[17],
                                "cep": parts[18],
                                "uf": parts[19],
                                "municipio_code": parts[20],
                                "ddd_1": parts[21],
                                "telefone_1": parts[22],
                                "ddd_2": parts[23],
                                "telefone_2": parts[24],
                                "email": parts[27]
                            }
    except Exception as e:
        print(f"Error scanning {zip_path.name}: {e}")
    return None

def lookup_single_cnpj(cnpj_14: str) -> dict:
    """Queries the entire RFB ZIP filesystem for a single exact 14-digit CNPJ."""
    digits = clean_digits(cnpj_14)
    if len(digits) != 14:
        return None
        
    cnpj_basico = digits[:8]
    cnpj_ordem = digits[8:12]
    cnpj_dv = digits[12:]
    
    print(f"Searching ZIP files for CNPJ: {cnpj_basico}/{cnpj_ordem}-{cnpj_dv}...")
    
    # 1. Look up Establishment details
    est_zip_files = [cnpj_dir / f"Estabelecimentos{i}.zip" for i in range(10)]
    est_zip_files = [f for f in est_zip_files if f.exists()]
    est = None
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(targeted_scan_estabelecimentos, f, cnpj_basico, cnpj_ordem, cnpj_dv): f
            for f in est_zip_files
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                est = res
                break
                
    if not est:
        print("CNPJ not found in Estabelecimentos database.")
        return None
        
    # 2. Look up Company details (using range sorting of zip files)
    comp = {}
    target_empresas_zip = None
    val_basico = int(cnpj_basico)
    
    candidates = [r for r in EMPRESAS_RANGES if int(r[1]) <= val_basico]
    if candidates:
        best_candidate = max(candidates, key=lambda x: int(x[1]))
        target_num = best_candidate[0]
    else:
        target_num = 0
        
    emp_zip_path = cnpj_dir / f"Empresas{target_num}.zip"
    if emp_zip_path.exists():
        emp_res = scan_single_empresas_zip(emp_zip_path, {cnpj_basico})
        comp = emp_res.get(cnpj_basico, {})
        
    if not comp:
        print("Fallback search in all Empresas ZIPs...")
        emp_zip_files = [cnpj_dir / f"Empresas{i}.zip" for i in range(10) if i != target_num]
        emp_zip_files = [f for f in emp_zip_files if f.exists()]
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(scan_single_empresas_zip, f, {cnpj_basico}): f
                for f in emp_zip_files
            }
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res.get(cnpj_basico):
                    comp = res[cnpj_basico]
                    break
                    
    # 3. Look up Partners
    partners = []
    soc_zip_files = [cnpj_dir / f"Socios{i}.zip" for i in range(10)]
    soc_zip_files = [f for f in soc_zip_files if f.exists()]
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(scan_single_socios_zip, f, {cnpj_basico}): f
            for f in soc_zip_files
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res.get(cnpj_basico):
                partners.extend(res[cnpj_basico])
                
    # 4. Look up Simples
    simples = load_simples({cnpj_basico}).get(cnpj_basico, {"opcao_simples": "N", "opcao_mei": "N"})
    
    # 5. Get CNAE Description
    cnaes = load_cnae_descriptions()
    
    # 6. Get role qualifications
    quals = load_qualifications()
    
    return {
        "est": est,
        "comp": comp,
        "partners": partners,
        "simples": simples,
        "cnaes": cnaes,
        "qualifications": quals
    }
