import json
import sys
import urllib.request
import urllib.parse
import urllib.error
import re
import os
import time
import unicodedata
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

def map_market(category: str) -> str:
    """Maps Google Maps scraper categories to Twenty's market enum values."""
    if not category:
        return None
    cat = category.lower().strip()
    
    # Strictly allow only these enums (from user's Twenty CRM schema)
    enum_values = [
        "PSYCHOLOGIST", "RESTAURANT", "MECHANICAL", "LAWYER", "ACCOUNTING",
        "DENTIST", "ARCHITECT", "REAL_ESTATE", "SOLAR_ENERGY", "PLASTIC_SURGEON",
        "EVENT_PLANNER", "PLUMBER", "ELECTRICIAN", "ROOFING", "PEST_CONTROL",
        "HVAC", "LANDSCAPING", "VETERINARIAN", "GYM", "PERSONAL_TRAINER",
        "CONSULTING", "INTERIOR_DESIGNER", "CATERING", "CHIROPRACTOR",
        "DERMATOLOGIST", "TRICHOLOGIST", "INSURANCE_BROKER", "MOVING_COMPANY",
        "CONSTRUCTION", "CLEANING_SERVICE", "SECURITY_COMPANY", "LOGISTICS",
        "TRAVEL_AGENCY", "CAR_RENTAL", "TOWING_SERVICE", "LOCKSMITH",
        "PHOTOGRAPHER", "OPTOMETRIST", "FINANCIAL_ADVISOR", "DAYCARE",
        "SPA", "TATTOO_PARLOR", "BAKERY", "BARBERSHOP", "WEDDING_PLANNER",
        "PRIVATE_TUTOR", "ENDOCRINOLOGIST", "PROCTOLOGIST", "BEAUTICIAN",
        "DOCTOR", "GENEALOGIST", "HAIR_REPLACEMENT_SERVICE", "HEALTH_AND_BEAUTY_SHOP",
        "MATERNITY_STORE", "MEDICAL_CLINIC", "NUTRITIONIST", "ORGANIC_FOOD_STORE",
        "PEDIATRICIAN", "PHYSICAL_THERAPY_CLINIC", "PILATES_STUDIO", "THERAPIST"
    ]
    
    # Common mappings (Português/Inglês -> Twenty Enum)
    mappings = {
        "psychologist": "PSYCHOLOGIST",
        "psicólogo": "PSYCHOLOGIST",
        "psicóloga": "PSYCHOLOGIST",
        "psicologo": "PSYCHOLOGIST",
        "psicologa": "PSYCHOLOGIST",
        "child psychologist": "PSYCHOLOGIST",
        "neuropsychologist": "PSYCHOLOGIST",
        "psychoanalyst": "PSYCHOLOGIST",
        "psicanalista": "PSYCHOLOGIST",
        "mental health clinic": "MEDICAL_CLINIC",
        "clínica de saúde mental": "MEDICAL_CLINIC",
        "mental health service": "PSYCHOLOGIST",
        "serviço de saúde mental": "PSYCHOLOGIST",
        
        "dentist": "DENTIST",
        "dentista": "DENTIST",
        
        "lawyer": "LAWYER",
        "advogado": "LAWYER",
        "advogada": "LAWYER",
        
        "accounting": "ACCOUNTING",
        "contabilidade": "ACCOUNTING",
        "contador": "ACCOUNTING",
        
        "mechanical": "MECHANICAL",
        "mecânica": "MECHANICAL",
        "mecânico": "MECHANICAL",
        "oficina": "MECHANICAL",
        
        "restaurant": "RESTAURANT",
        "restaurante": "RESTAURANT",
        "hamburgueria": "RESTAURANT",
        "pizzaria": "RESTAURANT",
        
        "architect": "ARCHITECT",
        "arquiteto": "ARCHITECT",
        "arquitetura": "ARCHITECT",
        
        "real estate": "REAL_ESTATE",
        "imobiliária": "REAL_ESTATE",
        "corretor": "REAL_ESTATE",

        # Medical / Health / Nutrition mappings
        "nutritionist": "NUTRITIONIST",
        "nutricionista": "NUTRITIONIST",
        "dietitian": "NUTRITIONIST",
        "nutrição": "NUTRITIONIST",
        "nutrição clínica": "NUTRITIONIST",
        "doctor": "DOCTOR",
        "médico": "DOCTOR",
        "médica": "DOCTOR",
        "medico": "DOCTOR",
        "medica": "DOCTOR",
        "pediatrician": "PEDIATRICIAN",
        "pediatra": "PEDIATRICIAN",
        "psychiatrist": "DOCTOR",
        "psiquiatra": "DOCTOR",
        "specialized clinic": "MEDICAL_CLINIC",
        "clínica especializada": "MEDICAL_CLINIC",
        "medical clinic": "MEDICAL_CLINIC",
        "clínica médica": "MEDICAL_CLINIC",
        "pilates studio": "PILATES_STUDIO",
        "estúdio de pilates": "PILATES_STUDIO",
        "studio de pilates": "PILATES_STUDIO",
        "health and beauty shop": "HEALTH_AND_BEAUTY_SHOP",
        "loja de saúde e beleza": "HEALTH_AND_BEAUTY_SHOP"
    }
    
    if cat in mappings:
        val = mappings[cat]
        if val in enum_values:
            return val
    
    # Direct match (case insensitive)
    cat_upper = cat.upper().replace(" ", "_")
    if cat_upper in enum_values:
        return cat_upper
        
    # Partial matches
    for ev in enum_values:
        if ev.lower() in cat or cat in ev.lower():
            return ev
            
    # Try normalizing accents and check again
    import unicodedata
    normalized = unicodedata.normalize('NFKD', category).encode('ASCII', 'ignore').decode('ASCII')
    normalized_enum = normalized.upper().replace(" ", "_").strip()
    if normalized_enum in enum_values:
        return normalized_enum
        
    # If the normalized version matches standard variants
    if normalized_enum in ("NUTRICIONISTA", "NUTRITIONIST", "DIETITIAN"):
        return "NUTRITIONIST"
        
    return None


def is_social_media(url: str) -> bool:
    """Checks if the URL belongs to a social media domain."""
    if not url:
        return False
    url_lower = url.lower()
    social_domains = [
        "instagram.com", "facebook.com", "linkedin.com", "twitter.com", 
        "x.com", "youtube.com", "linktr.ee", "wa.me", "whatsapp.com",
        "instagr.am", "fb.com", "t.me", "telegram.org", "pinterest.com"
    ]
    return any(domain in url_lower for domain in social_domains)

def clean_company_name(name: str) -> str:
    """Cleans up business titles, removing descriptors, prefixes, suffixes, and LTDA variations."""
    if not name:
        return name
        
    # Standard LTDA cleanup
    cleaned = re.sub(r'\bLTDA\b\.?', '', name, flags=re.IGNORECASE)
    
    # Normalize spaces around separators
    cleaned = re.sub(r'\s*([-\|–:])\s*', r' \1 ', cleaned)
    
    # Split by standard separators
    parts = [p.strip() for p in re.split(r'\s+[-\|–:]\s+', cleaned)]
    
    # Common description words in Portuguese
    desc_words = {
        "nutricionista", "nutri", "emagrecimento", "performance", "esportiva", "longevidade",
        "clínica", "clinica", "consultório", "consultorio", "bariátrica", "bariatrica",
        "estética", "estetica", "esteticista", "fonoaudióloga", "fonoaudiologa", "saúde", "saude", 
        "lajeado", "rs", "vale do taquari", "ayurveda", "estúdio", "studio",
        "psicóloga", "psicologa", "psicólogo", "psicologo", "psicologia", "psicoterapia",
        "psicanalista", "psicanálise", "psicanalise",
        "terapeuta", "terapeutas", "terapia", "terapias",
        "escanalista",
        "hipnose", "hipnoterapeuta", "hipnoterapia",
        "neuropsicóloga", "neuropsicologa", "neuropsicólogo", "neuropsicologo",
        "neuropsicologia", "neuropsicopedagoga", "neuropsicopedagogia",
        "consteladora", "constelador", "constelação", "constelacao",
        "coach", "coaching",
        "massoterapeuta", "massoterapia", "acupunturista", "acupuntura",
        "musicoterapeuta", "musicoterapia",
        "holística", "holistica", "holísticas", "holisticas",
        "integrativa", "integrativas", "integradas", "integrada",
        "integrado", "integrados",
        "sistêmica", "sistemica",
        "sistêmicas", "sistemicas",
        "cognitiva", "cognitivo", "comportamental", "infantil",
        "familiar", "vida",
        "online", "atendimento",
        "espaço", "terapêutico", "terapeutico", "centro",
        "crp", "dr", "dra"
    }
    
    filtered_parts = []
    for p in parts:
        p_lower = p.lower()
        words = re.findall(r'\b\w+\b', p_lower)
        if not words:
            continue
        
        desc_count = sum(1 for w in words if w in desc_words)
        is_descriptor = desc_count / len(words) >= 0.5
        
        if p_lower in ["rs", "sc", "pr", "sp", "rj", "mg"]:
            is_descriptor = True
            
        if not is_descriptor:
            filtered_parts.append(p)
            
    if not filtered_parts:
        candidate = parts[0]
    else:
        candidate = filtered_parts[0]
        
    # Reordered prefixes by specificity (most specific first)
    prefixes = [
        r'^\s*nutricionista\s+para\s+emagrecimento\s+em\s+lajeado\s+-\s+',
        r'^\s*nutricionista\s+bariátrica\s+',
        r'^\s*nutricionista\s+bariatrica\s+',
        r'^\s*consultório\s+de\s+nutrição\s+nutri\s+',
        r'^\s*consultorio\s+de\s+nutricao\s+nutri\s+',
        r'^\s*consultório\s+de\s+nutrição\s+',
        r'^\s*consultorio\s+de\s+nutricao\s+',
        r'^\s*consultório\s+nutri\s+',
        r'^\s*consultorio\s+nutri\s+',
        r'^\s*consultório\s+',
        r'^\s*consultorio\s+',
        r'^\s*clínica\s+de\s+psicologia\s+',
        r'^\s*clinica\s+de\s+psicologia\s+',
        r'^\s*clínica\s+de\s+',
        r'^\s*clinica\s+de\s+',
        r'^\s*clínica\s+',
        r'^\s*clinica\s+',
        r'^\s*de\s+vida\s+',
        r'^\s*espaço\s+terapêutico\s+',
        r'^\s*espaco\s+terapeutico\s+',
        r'^\s*espaço\s+',
        r'^\s*nutricionista\s+',
        r'^\s*nutri\s+',
        r'^\s*dra?\.\s+',
        r'^\s*dr\.\s+',
        r'^\s*dra?\s+',
        r'^\s*dr\s+',
        r'^\s*profa?\.\s+',
        r'^\s*prof\.\s+',
        r'^\s*profa?\s+',
        r'^\s*prof\s+',
        r'^\s*sra?\.\s+',
        r'^\s*sr\.\s+',
        r'^\s*sra?\s+',
        r'^\s*sr\s+',
        r'^\s*fonoaudióloga\s+',
        r'^\s*fonoaudiologa\s+',
        r'^\s*psicóloga\s+',
        r'^\s*psicologa\s+',
        r'^\s*psicólogo\s+',
        r'^\s*psicologo\s+',
        r'^\s*neuropsicóloga\s+',
        r'^\s*neuropsicologa\s+',
        r'^\s*neuropsicólogo\s+',
        r'^\s*neuropsicologo\s+',
        r'^\s*neuropsicologia\s+',
        r'^\s*terapeuta\s+',
        r'^\s*terapia\s+',
        r'^\s*terapias\s+',
        r'^\s*escanalista\s+',
        r'^\s*hipnoterapeuta\s+',
        r'^\s*hipnose\s+',
        r'^\s*consteladora\s+',
        r'^\s*constelador\s+',
        r'^\s*coach\s+',
        r'^\s*massoterapeuta\s+',
        r'^\s*acupunturista\s+',
        r'^\s*esteticista\s+',
        r'^\s*musicoterapeuta\s+',
        r'^\s*psicanalista\s+',
        r'^\s*psicologia\s+',
        r'^\s*cognitiva\s+',
        r'^\s*comportamental\s+',
        r'^\s*infantil\s+',
        r'^\s*integradas\s+',
        r'^\s*online\s+',
        r'^\s*familiar\s+',
        r'^\s*sistêmica\s+',
        r'^\s*sistemica\s+',
        r'^\s*sistêmicas\s+',
        r'^\s*sistemicas\s+',
        r'^\s*holística\s+',
        r'^\s*holistica\s+',
        r'^\s*holísticas\s+',
        r'^\s*holisticas\s+',
        r'^\s*integrativa\s+',
        r'^\s*integrativas\s+'
    ]
    
    cleaned_result = candidate
    # Repeat until stable so stacked descriptors ("Hipnose Clínica ...",
    # "Coach de Vida ...") are all stripped regardless of list order.
    prev = None
    while prev != cleaned_result:
        prev = cleaned_result
        for prefix in prefixes:
            cleaned_result = re.sub(prefix, '', cleaned_result, flags=re.IGNORECASE).strip()
        
    # Suffixes
    suffixes = [
        r'\s+nutricionista\s*$',
        r'\s+nutri\s*$',
        r'\s+estética\s*$',
        r'\s+estetica\s*$',
        r'\s+lajeado\s*$',
        r'\s+rs\s*$',
        r'\s+psicóloga\s*$',
        r'\s+psicologa\s*$',
        r'\s+psicólogo\s*$',
        r'\s+psicologo\s*$',
        r'\s+psicologia\s*$',
        r'\s+neuropsicóloga\s*$',
        r'\s+neuropsicologa\s*$',
        r'\s+neuropsicólogo\s*$',
        r'\s+neuropsicologo\s*$',
        r'\s+terapeuta\s*$',
        r'\s+escanalista\s*$',
        r'\s+hipnoterapeuta\s*$',
        r'\s+hipnose\s*$',
        r'\s+consteladora\s*$',
        r'\s+constelador\s*$',
        r'\s+coach\s*$',
        r'\s+massoterapeuta\s*$',
        r'\s+acupunturista\s*$',
        r'\s+esteticista\s*$',
        r'\s+musicoterapeuta\s*$',
        r'\s+psicanalista\s*$',
        r'\s+clínica\s*$',
        r'\s+clinica\s*$',
        r'\s+cognitiva\s*$',
        r'\s+comportamental\s*$',
        r'\s+infantil\s*$',
        r'\s+holistica\s*$',
        r'\s+holística\s*$',
        r'\s+integradas\s*$',
        r'\s+online\s*$'
    ]
    prev = None
    while prev != cleaned_result:
        prev = cleaned_result
        for suffix in suffixes:
            cleaned_result = re.sub(suffix, '', cleaned_result, flags=re.IGNORECASE).strip()
        
    cleaned_result = re.sub(r'\s+', ' ', cleaned_result).strip()
    return cleaned_result

def get_simplified_name(name: str) -> str:
    """Extracts a simplified name (first name + surname) after cleaning descriptors.
    Surname keeps Portuguese particles (de, da, do, dos, das), e.g. 'da Silva'."""
    cleaned = clean_company_name(name)
    if not cleaned:
        return ""
    words = cleaned.split()
    # Drop specific descriptors that may survive cleaning (e.g. as suffixes).
    drop_words = {
        "integrados", "integrativas", "psicologia", "e",
        "psicanalista", "psicanalise", "presencial", "psicoterapeuta",
        "sexologa", "neuropsicologa", "neuropsicologia", "constelacoes",
        "psicopedagoga", "organizacional", "terapias",
        "individual", "infantojuvenil", "adolescentes", "psi",
        "psicologico", "clinico", "ocupacional", "instituto",
        "neurocognitivo", "casais", "avaliacao", "psicoterapia",
        "constelacao", "infanto", "juvenil", "clinica", "infancia",
        "adolescencia", "centro", "psicologa", "psicologo",
    }
    def _norm_word(w: str) -> str:
        w = re.sub(r'[^\w]', '', w).lower()
        return unicodedata.normalize('NFKD', w).encode('ASCII', 'ignore').decode('ASCII')
    words = [w for w in words if _norm_word(w) not in drop_words]
    # Drop stray trailing particles (e.g. "Ana de" -> "Ana")
    particles = {"de", "da", "do", "dos", "das"}
    while len(words) > 1 and words[-1].lower() in particles:
        words.pop()
    if not words:
        return ""
    if len(words) == 1:
        return words[0].capitalize()
    # Build surname: last word plus any particles directly before it
    surname_parts = [words[-1]]
    i = len(words) - 2
    while i > 0 and words[i].lower() in particles:
        surname_parts.insert(0, words[i].lower())
        i -= 1
    surname = " ".join(
        w if w.lower() in particles else w.capitalize()
        for w in surname_parts
    )
    # First name: skip leading particles (e.g. "de Vida ..." -> "Vida")
    first = next((w for w in words[:i + 1] if w.lower() not in particles), words[0])
    return f"{first.capitalize()} {surname}"

def normalize_address(address_str: str, city_name: str = None) -> str:
    """Cleans up the street address string by removing CEP, City, State and normalizing spacing/case."""
    if not address_str:
        return ""
    # Remove CEP e.g. "CEP 95900-612"
    cleaned = re.sub(r'\bCEP\s*:?\s*[\d.-]+\b', '', address_str, flags=re.IGNORECASE)
    parts = [p.strip() for p in cleaned.split(",")]
    filtered_parts = []
    for p in parts:
        p_clean = p.strip()
        if not p_clean:
            continue
        # Filter out state abbreviation
        if re.match(r'^[A-Z]{2}$', p_clean.upper()):
            continue
        # Filter out city name
        if city_name and p_clean.lower() == city_name.lower():
            continue
        filtered_parts.append(p_clean)
    street = ", ".join(filtered_parts)
    street = re.sub(r'\s+', ' ', street).strip()
    street = street.strip(',. ')
    words = street.split()
    prepositions = {"de", "do", "da", "dos", "das", "e", "em"}
    title_words = []
    for i, w in enumerate(words):
        w_clean = re.sub(r'[^\w]', '', w).lower()
        if w_clean in prepositions and i > 0 and i < len(words) - 1:
            title_words.append(w.lower())
        else:
            if w.isdigit():
                title_words.append(w)
            else:
                if w.endswith(','):
                    title_words.append(w[:-1].capitalize() + ',')
                else:
                    title_words.append(w.capitalize())
    street_normalized = " ".join(title_words)
    street_normalized = re.sub(r'\s+,\s+', ', ', street_normalized)
    street_normalized = re.sub(r'\s+,', ', ', street_normalized)
    return street_normalized

def map_stage(review_score: str) -> str:
    """Maps the lead qualification score to Twenty's opportunity stage. Always returns LEAD."""
    return "LEAD"

def extract_socios(socios_str: str) -> list:
    """Parses CNPJ socios string into structured objects for Person creation."""
    if not socios_str:
        return []
    socios = []
    # If the string contains multiple socios separated by comma (or semicolon)
    for part in socios_str.split(","):
        part = part.strip()
        if not part:
            continue
        # Remove parenthetical details e.g. (Sócio-administrador)
        clean_name = part.split("(")[0].strip()
        if not clean_name:
            continue
        
        # Split first and last name
        name_parts = clean_name.split(" ")
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        
        # Role/position can be extracted from the parentheses
        role = ""
        if "(" in part and ")" in part:
            role = part.split("(")[1].split(")")[0].strip()
            
        socios.append({
            "firstName": first_name,
            "lastName": last_name,
            "role": role
        })
    return socios

def format_observations(lead: dict) -> str:
    """Formats all lead details and reviews into a readable block for initialObservations."""
    paragraphs = []
    
    # 1. Google Maps Name
    orig_name = lead.get("maps_title", "").strip()
    if orig_name:
        paragraphs.append(f"Lead coletado originalmente no Google Maps sob o nome '{orig_name}'.")
        
    # 2. Review checklist and score
    score = lead.get("review_score")
    if score:
        q1 = (lead.get("review_q1_site") or "").strip().lower()
        has_site = "possui um site profissional" if q1 == "s" else "não possui site cadastrado ou profissional" if q1 == "n" else "não teve a presença de site confirmada"
        
        q2 = (lead.get("review_q2_responsivo") or "").strip().lower()
        responsiveness = "sendo este responsivo e rápido" if q2 == "s" else "o qual não é responsivo ou apresenta problemas de carregamento" if q2 == "n" else ""
        
        q3 = (lead.get("review_q3_instagram") or "").strip().lower()
        insta_site = "há link direto para o Instagram no site" if q3 == "s" else "não há link para o Instagram no site" if q3 == "n" else ""
        
        q4 = (lead.get("review_q4_whatsapp") or "").strip().lower()
        wa_site = "há link direto e facilitado para o WhatsApp" if q4 == "s" else "não há link fácil para falar no WhatsApp" if q4 == "n" else ""
        
        q5 = (lead.get("review_q5_amador") or "").strip().lower()
        amador = "o design da sua presença digital foi classificado como amador" if q5 == "s" else "o design da sua presença digital é profissional" if q5 == "n" else ""
        
        q6 = (lead.get("review_q6_insta_qualidade") or "").strip().lower()
        insta_qual = "sua conta de Instagram tem qualidade ruim ou amadora" if q6 == "u" else "sua conta de Instagram tem qualidade regular" if q6 == "r" else "sua conta de Instagram tem boa qualidade" if q6 == "b" else ""
        
        review_parts = []
        
        # Only add score and website presence details if the score is greater than 1
        # (score 1 means no website, which is redundant/cluttered to report in observations)
        try:
            score_val = int(score)
        except (ValueError, TypeError):
            score_val = 0

        if score_val > 1:
            review_parts.append(f"Durante a avaliação de presença digital, o lead obteve um score de {score} de 5 pontos.")
            
            # Build sentences
            sentence_site = f"Verificou-se que a empresa {has_site}"
            if responsiveness:
                sentence_site += f", {responsiveness}"
            sentence_site += "."
            review_parts.append(sentence_site)
        
        channels = []
        if wa_site:
            channels.append(wa_site)
        if insta_site:
            channels.append(insta_site)
        if channels:
            review_parts.append(f"Sobre os canais de contato, { ' e '.join(channels) }.")
            
        design_parts = []
        if amador:
            design_parts.append(amador)
        if insta_qual:
            design_parts.append(insta_qual)
        if design_parts:
            review_parts.append(f"Em termos visuais, { ' e '.join(design_parts) }.")
            
        if review_parts:
            paragraphs.append(" ".join(review_parts))
        
    # 3. CNPJ info
    cnpj = lead.get("cnpj_cnpj")
    if cnpj:
        razao = lead.get("cnpj_razao_social")
        cnae = lead.get("cnpj_cnae_descricao")
        socios = lead.get("cnpj_socios")
        situacao = lead.get("cnpj_situacao_cadastral")
        idade = lead.get("cnpj_idade_empresa_anos")
        capital = lead.get("cnpj_capital_social")
        
        cnpj_text = f"Nos registros da Receita Federal, o CNPJ associado é o {cnpj}"
        if razao:
            cnpj_text += f", sob a razão social '{razao}'"
        if situacao:
            cnpj_text += f", estando atualmente na situação cadastral '{situacao}'"
        if idade:
            cnpj_text += f" com aproximadamente {idade} anos de fundação"
        if capital:
            try:
                cap_formatted = f"R$ {float(capital):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                cnpj_text += f" e capital social de {cap_formatted}"
            except ValueError:
                cnpj_text += f" e capital social de R$ {capital}"
        cnpj_text += "."
        
        cnpj_details = []
        if cnae:
            cnpj_details.append(f"Sua atividade econômica principal é '{cnae}'")
        if socios:
            cnpj_details.append(f"constando como sócios: {socios}")
            
        if cnpj_details:
            cnpj_text += " " + ", ".join(cnpj_details) + "."
            
        paragraphs.append(cnpj_text)
        
    return "\n\n".join(paragraphs)

def make_twenty_request(endpoint: str, method: str = "POST", payload: dict = None, token: str = None, base_url: str = None) -> tuple:
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


def check_duplicates():
    """Checks for duplicate records in the CRM by WhatsApp and CNPJ."""
    # Load environment variables from .env
    load_env()

    # Load API configuration from environment variables
    token = os.environ.get("TWENTY_API_TOKEN")
    base_url = os.environ.get("TWENTY_API_URL", "http://localhost:4000/rest")
    
    if not token or token == "your_token_here":
        print("Error: TWENTY_API_TOKEN environment variable is not set correctly.", file=sys.stderr)
        print("Please set it in the .env file in the project root:", file=sys.stderr)
        sys.exit(1)

    print("\n--- CHECKING FOR DUPLICATES IN TWENTY CRM ---")
    print(f"API URL: {base_url}")
    print("--------------------------------------------\n")

    print("Fetching companies from CRM...")
    all_companies = []
    starting_after = None
    while True:
        query_params = {
            "limit": 60,
        }
        if starting_after:
            query_params["starting_after"] = starting_after
            
        endpoint = f"companies?{urllib.parse.urlencode(query_params)}"
        status, response = make_twenty_request(endpoint, "GET", token=token, base_url=base_url)
        if status != 200:
            print(f"Error: Failed to fetch companies: Status {status}. Response: {response}", file=sys.stderr)
            return
            
        companies_chunk = response.get("data", {}).get("companies", [])
        if not companies_chunk:
            break
        all_companies.extend(companies_chunk)
        
        page_info = response.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            starting_after = page_info.get("endCursor")
        else:
            break

    print(f"Fetched {len(all_companies)} companies to verify.")

    def clean_digits(val: str) -> str:
        if not val:
            return ""
        return "".join(c for c in val if c.isdigit())

    by_whatsapp = {}
    by_cnpj = {}

    for comp in all_companies:
        comp_id = comp.get("id")
        comp_name = comp.get("name") or "Unnamed"
        
        # WhatsApp check
        whatsapp_data = comp.get("whatsapp")
        if isinstance(whatsapp_data, dict):
            phone = clean_digits(whatsapp_data.get("primaryPhoneNumber"))
            if phone:
                by_whatsapp.setdefault(phone, []).append((comp_name, comp_id))
                
        # CNPJ check
        cnpj = clean_digits(comp.get("cnpj"))
        if cnpj:
            by_cnpj.setdefault(cnpj, []).append((comp_name, comp_id))

    has_duplicates = False
    
    # 1. WhatsApp Duplicates
    whatsapp_duplicates = {k: v for k, v in by_whatsapp.items() if len(v) > 1}
    if whatsapp_duplicates:
        has_duplicates = True
        print("\n[WARNING] Duplicate companies by WhatsApp found in CRM:")
        for phone, companies in whatsapp_duplicates.items():
            print(f"  WhatsApp: {phone}")
            for name, comp_id in companies:
                print(f"    - {name} (ID: {comp_id})")
                
    # 2. CNPJ Duplicates
    cnpj_duplicates = {k: v for k, v in by_cnpj.items() if len(v) > 1}
    if cnpj_duplicates:
        has_duplicates = True
        print("\n[WARNING] Duplicate companies by CNPJ found in CRM:")
        for cnpj, companies in cnpj_duplicates.items():
            formatted_cnpj = cnpj
            if len(cnpj) == 14:
                formatted_cnpj = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
            print(f"  CNPJ: {formatted_cnpj}")
            for name, comp_id in companies:
                print(f"    - {name} (ID: {comp_id})")

    if not has_duplicates:
        print("\nNo duplicate companies found in CRM.")
    
    print("\n--------------------------------------------")
    print("Duplicate check complete.")
    print("--------------------------------------------\n")


def register_json(json_file_path: Path):
    """Reads qualified leads from JSON and creates Company, Person, and Opportunity records in Twenty."""
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

    if not isinstance(data, list):
        data = [data]

    # Load environment variables from .env
    load_env()

    # Load API configuration from environment variables
    token = os.environ.get("TWENTY_API_TOKEN")
    base_url = os.environ.get("TWENTY_API_URL", "http://localhost:4000/rest")
    
    if not token or token == "your_token_here":
        print("Error: TWENTY_API_TOKEN environment variable is not set correctly.", file=sys.stderr)
        print("Please set it in the .env file in the project root:", file=sys.stderr)
        print("  TWENTY_API_TOKEN=\"your_twenty_api_token\"", file=sys.stderr)
        sys.exit(1)

    print(f"\n--- REGISTERING LEADS TO TWENTY CRM ---")
    print(f"File:     {json_file_path}")
    print(f"API URL:  {base_url}")
    print(f"Total:    {len(data)} leads")
    print(f"---------------------------------------\n")

    success_count = 0
    for idx, lead in enumerate(data, 1):
        raw_name = lead.get("maps_title") or f"Lead #{idx}"
        simplified_name = get_simplified_name(raw_name)
        print(f"[{idx}/{len(data)}] Registering: {raw_name} (Simplified: {simplified_name})")

        # Check if the CNPJ is closed ("baixado")
        cnpj_situacao = (lead.get("cnpj_situacao_cadastral") or "").strip().lower()
        is_baixado = "baixada" in cnpj_situacao or "baixado" in cnpj_situacao

        # 1. Map and Create Company
        # NOTE: cloud workspace has no cnpj/speciality fields and uses
        # "emails" (not "eMail"). CNPJ details are preserved in
        # initialObservations text via format_observations().
        company_payload = {
            "name": raw_name,
            "simplifiedName": simplified_name
        }
        
        # Domain name (ignoring social media links)
        website = lead.get("maps_website") or ""
        if website and not is_social_media(website):
            if not website.startswith("http"):
                website = "https://" + website
            company_payload["domainName"] = {
                "primaryLinkUrl": website,
                "primaryLinkLabel": ""
            }
            
        # Address
        address_str = lead.get("maps_address") or lead.get("cnpj_endereco") or ""
        maps_city = lead.get("maps_city") or ""
        cep = ""
        cep_match = re.search(r"CEP\s*([\d.-]+)", address_str, re.IGNORECASE)
        if cep_match:
            cep = cep_match.group(1).replace(".", "").replace("-", "").strip()
            
        company_payload["address"] = {
            "addressCity": maps_city,
            "addressState": lead.get("maps_state") or "",
            "addressCountry": "Brazil",
            "addressStreet1": normalize_address(address_str, maps_city),
            "addressPostcode": cep
        }
        
        # Phone / Whatsapp
        phone_raw = lead.get("maps_phone") or lead.get("cnpj_telefone") or ""
        if phone_raw:
            company_payload["whatsapp"] = {
                "primaryPhoneNumber": phone_raw,
                "primaryPhoneCallingCode": "+55",
                "primaryPhoneCountryCode": "BR"
            }
            
        # Email
        email = ""
        if lead.get("maps_emails"):
            emails_list = lead.get("maps_emails", "").split(",")
            if emails_list:
                email = emails_list[0].strip()
        if not email:
            email = lead.get("cnpj_email") or ""
        if email:
            company_payload["emails"] = {
                "primaryEmail": email
            }
            
        # Instagram
        instagram_raw = lead.get("maps_instagram") or ""
        if instagram_raw:
            company_payload["instagram"] = {
                "primaryLinkUrl": instagram_raw,
                "primaryLinkLabel": ""
            }
            
        # Market / Category
        market = map_market(lead.get("maps_category"))
        if market:
            company_payload["market"] = market

        status, response_data = make_twenty_request("companies", "POST", company_payload, token, base_url)
        if status not in (200, 201):
            print(f"  -> Error creating Company: Status {status}. Response: {response_data}", file=sys.stderr)
            continue
            
        company_id = response_data.get("data", {}).get("createCompany", {}).get("id")
        print(f"  -> Company created: ID {company_id}")

        # 2. Extract and Create Persons (SOCIOS)
        socios = [] if is_baixado else extract_socios(lead.get("cnpj_socios"))
        point_of_contact_id = None
        created_people_ids = []
        
        for idx_socio, socio in enumerate(socios):
            person_payload = {
                "name": {
                    "firstName": socio["firstName"],
                    "lastName": socio["lastName"]
                },
                "companyId": company_id,
                "jobTitle": socio["role"] or "Sócio"
            }
            
            # Copy email/phone contact only to the first person to avoid unique constraint conflicts
            if idx_socio == 0:
                if email:
                    person_payload["emails"] = {
                        "primaryEmail": email
                    }
                if phone_raw:
                    person_payload["phones"] = {
                        "primaryPhoneNumber": phone_raw,
                        "primaryPhoneCallingCode": "+55",
                        "primaryPhoneCountryCode": "BR"
                    }

            p_status, p_response = make_twenty_request("people", "POST", person_payload, token, base_url)
            if p_status in (200, 201):
                person_id = p_response.get("data", {}).get("createPerson", {}).get("id")
                print(f"  -> Person '{socio['firstName']} {socio['lastName']}' created: ID {person_id}")
                created_people_ids.append(person_id)
                if not point_of_contact_id:
                    point_of_contact_id = person_id
            else:
                print(f"  -> Warning: Failed to create Person '{socio['firstName']} {socio['lastName']}': Status {p_status}. Response: {p_response}", file=sys.stderr)

        # 3. Create Opportunity
        opp_payload = {
            "name": raw_name,
            "companyId": company_id,
            "stage": map_stage(lead.get("review_score")),
            "amount": {
                "amountMicros": 1300000000,
                "currencyCode": "BRL"
            },
            "initialObservations": format_observations(lead)
        }
        if point_of_contact_id:
            opp_payload["pointOfContactId"] = point_of_contact_id

        o_status, o_response = make_twenty_request("opportunities", "POST", opp_payload, token, base_url)
        if o_status in (200, 201):
            opp_id = o_response.get("data", {}).get("createOpportunity", {}).get("id")
            print(f"  -> Opportunity created: ID {opp_id}")
            success_count += 1
        else:
            print(f"  -> Error creating Opportunity: Status {o_status}. Response: {o_response}", file=sys.stderr)
            # Cleanup Company and People to ensure no company without opportunity exists
            print(f"  -> Cleaning up created Company and People to prevent orphaned records...")
            # 1. Delete People
            for p_id in created_people_ids:
                del_p_status, del_p_resp = make_twenty_request(f"people/{p_id}", "DELETE", token=token, base_url=base_url)
                if del_p_status in (200, 204):
                    print(f"     -> Deleted Person ID {p_id}")
                else:
                    print(f"     -> Warning: Failed to delete Person ID {p_id}: Status {del_p_status}", file=sys.stderr)
            # 2. Delete Company
            del_c_status, del_c_resp = make_twenty_request(f"companies/{company_id}", "DELETE", token=token, base_url=base_url)
            if del_c_status in (200, 204):
                print(f"     -> Deleted Company ID {company_id}")
            else:
                print(f"     -> Warning: Failed to delete Company ID {company_id}: Status {del_c_status}", file=sys.stderr)

    # 4. Check for duplicate records in the CRM
    check_duplicates()

    print(f"\n---------------------------------------")
    print(f"Completed! Successfully registered {success_count}/{len(data)} leads in Twenty.")
    print(f"---------------------------------------\n")


def normalize_crm_names():
    """Trims leading/trailing whitespace from all company names in Twenty CRM,
    and synchronizes the name of all opportunities associated with each company
    so they match the company's normalized (trimmed) name.
    """
    # Load environment variables from .env
    load_env()

    # Load API configuration from environment variables
    token = os.environ.get("TWENTY_API_TOKEN")
    base_url = os.environ.get("TWENTY_API_URL", "http://localhost:4000/rest")

    if not token or token == "your_token_here":
        print("[ERROR] TWENTY_API_TOKEN environment variable is not set correctly.", file=sys.stderr)
        print("Please check your .env file in the project root.", file=sys.stderr)
        sys.exit(1)

    print("\n--- CRM NAME NORMALIZATION & SYNC ---")
    print(f"API URL: {base_url}")
    print("-------------------------------------\n")

    # 1. Fetch all companies
    print("[INFO] Fetching all companies from CRM...")
    all_companies = []
    starting_after = None
    page = 1
    while True:
        query_params = {"limit": 60}
        if starting_after:
            query_params["starting_after"] = starting_after

        endpoint = f"companies?{urllib.parse.urlencode(query_params)}"
        print(f"[DEBUG] Fetching companies page {page} (starting_after: {starting_after})...")
        status, response = make_twenty_request(endpoint, "GET", token=token, base_url=base_url)
        if status != 200:
            print(f"[ERROR] Failed to fetch companies: Status {status}. Response: {response}", file=sys.stderr)
            return

        companies_chunk = response.get("data", {}).get("companies", [])
        print(f"[DEBUG] Received {len(companies_chunk)} companies in page {page}.")
        if not companies_chunk:
            break
        all_companies.extend(companies_chunk)

        page_info = response.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            starting_after = page_info.get("endCursor")
            page += 1
        else:
            break

    print(f"[INFO] Successfully fetched {len(all_companies)} total companies from CRM.")

    # 2. Fetch all opportunities
    print("[INFO] Fetching all opportunities from CRM...")
    all_opportunities = []
    starting_after = None
    page = 1
    while True:
        query_params = {"limit": 60}
        if starting_after:
            query_params["starting_after"] = starting_after

        endpoint = f"opportunities?{urllib.parse.urlencode(query_params)}"
        print(f"[DEBUG] Fetching opportunities page {page} (starting_after: {starting_after})...")
        status, response = make_twenty_request(endpoint, "GET", token=token, base_url=base_url)
        if status != 200:
            print(f"[ERROR] Failed to fetch opportunities: Status {status}. Response: {response}", file=sys.stderr)
            return

        opportunities_chunk = response.get("data", {}).get("opportunities", [])
        print(f"[DEBUG] Received {len(opportunities_chunk)} opportunities in page {page}.")
        if not opportunities_chunk:
            break
        all_opportunities.extend(opportunities_chunk)

        page_info = response.get("pageInfo", {})
        if page_info.get("hasNextPage") and page_info.get("endCursor"):
            starting_after = page_info.get("endCursor")
            page += 1
        else:
            break

    print(f"[INFO] Successfully fetched {len(all_opportunities)} total opportunities from CRM.")

    # 3. Group opportunities by companyId
    print("[INFO] Grouping opportunities by their companyId...")
    opps_by_company = {}
    for opp in all_opportunities:
        company_id = opp.get("companyId")
        if company_id:
            opps_by_company.setdefault(company_id, []).append(opp)
    
    print(f"[DEBUG] Grouped {len(all_opportunities)} opportunities under {len(opps_by_company)} unique companyIds.")

    comp_processed = 0
    comp_trimmed = 0
    opp_processed = 0
    opp_synced = 0

    print("\n[INFO] Starting company name trim and opportunity name synchronization...")
    for idx, comp in enumerate(all_companies, 1):
        comp_id = comp.get("id")
        current_name = comp.get("name")
        
        if not current_name:
            print(f"[DEBUG] Company #{idx} has no name (ID: {comp_id}). Skipping.")
            continue

        comp_processed += 1
        trimmed_name = current_name.strip()

        # Update company name if leading/trailing whitespace was removed
        if trimmed_name != current_name:
            print(f"[ACTION] Company name requires trim: '{current_name}' -> '{trimmed_name}' (ID: {comp_id})")
            payload = {"name": trimmed_name}
            c_status, c_response = make_twenty_request(f"companies/{comp_id}", "PATCH", payload, token, base_url)
            if c_status in (200, 201):
                print(f"[SUCCESS] Company '{trimmed_name}' (ID: {comp_id}) updated successfully.")
                comp_trimmed += 1
                # Update current_name to trimmed_name for opportunity matching
                current_name = trimmed_name
            else:
                print(f"[ERROR] Failed to update company (ID: {comp_id}). Status: {c_status}. Response: {c_response}", file=sys.stderr)

        # Sync opportunities for this company to match the trimmed name
        associated_opps = opps_by_company.get(comp_id, [])
        if associated_opps:
            print(f"[DEBUG] Company '{trimmed_name}' (ID: {comp_id}) has {len(associated_opps)} associated opportunities.")
        
        for opp in associated_opps:
            opp_id = opp.get("id")
            opp_name = opp.get("name")
            opp_processed += 1

            # Sync opportunity name to match the parent company name
            if opp_name != trimmed_name:
                print(f"[ACTION] Syncing opportunity name: '{opp_name}' -> '{trimmed_name}' (Opp ID: {opp_id}, Comp ID: {comp_id})")
                payload = {"name": trimmed_name}
                o_status, o_response = make_twenty_request(f"opportunities/{opp_id}", "PATCH", payload, token, base_url)
                if o_status in (200, 201):
                    print(f"[SUCCESS] Opportunity ID {opp_id} updated successfully to '{trimmed_name}'.")
                    opp_synced += 1
                else:
                    print(f"[ERROR] Failed to update opportunity (ID: {opp_id}). Status: {o_status}. Response: {o_response}", file=sys.stderr)
            else:
                print(f"[DEBUG] Opportunity '{opp_name}' (ID: {opp_id}) is already in sync with company '{trimmed_name}'.")

    print("\n--------------------------------------------")
    print("Normalization and synchronization complete.")
    print(f"Companies processed:        {comp_processed}")
    print(f"Companies actually trimmed: {comp_trimmed}")
    print(f"Opportunities parsed:       {opp_processed}")
    print(f"Opportunities synced:       {opp_synced}")
    print("--------------------------------------------\n")


