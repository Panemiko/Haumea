"""Registro de leads do Haumea no CRM Antessala (API v1).

A API v1 trabalha com uma única entidade, a oportunidade, aceita escrita
parcial por PUT e criação em lote por POST. Este módulo converte o JSON do
Haumea para esse formato, envia os leads em lotes idempotentes e oferece as
ferramentas auxiliares de conferência de duplicados e normalização de nomes.
"""

import json
import sys
import urllib.request
import urllib.parse
import urllib.error
import re
import os
import time
import unicodedata
import uuid
from datetime import datetime, timezone
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
                            # Variáveis já exportadas no ambiente têm prioridade.
                            os.environ.setdefault(key, val)
                break
            except Exception:
                pass

def map_market(category: str) -> str:
    """Maps Google Maps scraper categories to the Antessala market enum values."""
    if not category:
        return None
    cat = category.lower().strip()
    
    # Strictly allow only these enums (from the Antessala market schema)
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
    
    # Common mappings (Português/Inglês -> Antessala Enum)
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
        "imobiliaria": "REAL_ESTATE",
        "corretor": "REAL_ESTATE",

        # Common Brazilian categories
        "padaria": "BAKERY",
        "panificadora": "BAKERY",
        "confeitaria": "BAKERY",
        "barbearia": "BARBERSHOP",
        "barber": "BARBERSHOP",
        "salão de beleza": "BEAUTICIAN",
        "salao de beleza": "BEAUTICIAN",
        "cabeleireiro": "BEAUTICIAN",
        "cabeleireira": "BEAUTICIAN",
        "esteticista": "BEAUTICIAN",
        "estética": "BEAUTICIAN",
        "estetica": "BEAUTICIAN",
        "clínica de estética": "BEAUTICIAN",
        "clinica de estetica": "BEAUTICIAN",
        "academia": "GYM",
        "personal trainer": "PERSONAL_TRAINER",
        "veterinário": "VETERINARIAN",
        "veterinaria": "VETERINARIAN",
        "veterinária": "VETERINARIAN",
        "pet shop": "VETERINARIAN",
        "petshop": "VETERINARIAN",
        "oficina mecânica": "MECHANICAL",
        "oficina mecanica": "MECHANICAL",
        "advocacia": "LAWYER",
        "escritório de advocacia": "LAWYER",
        "escritorio de advocacia": "LAWYER",
        "construtora": "CONSTRUCTION",
        "construção civil": "CONSTRUCTION",
        "construcao civil": "CONSTRUCTION",
        "odontologia": "DENTIST",
        "clínica odontológica": "DENTIST",
        "clinica odontologica": "DENTIST",
        "fisioterapia": "PHYSICAL_THERAPY_CLINIC",
        "clínica de fisioterapia": "PHYSICAL_THERAPY_CLINIC",
        "clinica de fisioterapia": "PHYSICAL_THERAPY_CLINIC",
        "pilates": "PILATES_STUDIO",
        "quiroprata": "CHIROPRACTOR",
        "quiropraxia": "CHIROPRACTOR",
        "dermatologista": "DERMATOLOGIST",
        "tricologista": "TRICHOLOGIST",
        "endocrinologista": "ENDOCRINOLOGIST",
        "proctologista": "PROCTOLOGIST",
        "cirurgião plástico": "PLASTIC_SURGEON",
        "cirurgiao plastico": "PLASTIC_SURGEON",
        "designer de interiores": "INTERIOR_DESIGNER",
        "paisagismo": "LANDSCAPING",
        "telhados": "ROOFING",
        "encanador": "PLUMBER",
        "eletricista": "ELECTRICIAN",
        "consultoria": "CONSULTING",
        "assessor financeiro": "FINANCIAL_ADVISOR",
        "corretor de seguros": "INSURANCE_BROKER",
        "agência de viagens": "TRAVEL_AGENCY",
        "agencia de viagens": "TRAVEL_AGENCY",
        "chaveiro": "LOCKSMITH",
        "dedetização": "PEST_CONTROL",
        "dedetizacao": "PEST_CONTROL",
        "energia solar": "SOLAR_ENERGY",
        "ar-condicionado": "HVAC",
        "ar condicionado": "HVAC",
        "limpeza": "CLEANING_SERVICE",
        "mudança": "MOVING_COMPANY",
        "mudanca": "MOVING_COMPANY",
        "segurança": "SECURITY_COMPANY",
        "seguranca": "SECURITY_COMPANY",
        "logística": "LOGISTICS",
        "logistica": "LOGISTICS",
        "locadora": "CAR_RENTAL",
        "locação de veículos": "CAR_RENTAL",
        "locacao de veiculos": "CAR_RENTAL",
        "guincho": "TOWING_SERVICE",
        "fotógrafo": "PHOTOGRAPHER",
        "fotografo": "PHOTOGRAPHER",
        "fotógrafa": "PHOTOGRAPHER",
        "fotografa": "PHOTOGRAPHER",
        "ótica": "OPTOMETRIST",
        "otica": "OPTOMETRIST",
        "optometrista": "OPTOMETRIST",
        "creche": "DAYCARE",
        "spa": "SPA",
        "tatuagem": "TATTOO_PARLOR",
        "estúdio de tatuagem": "TATTOO_PARLOR",
        "estudio de tatuagem": "TATTOO_PARLOR",
        "buffet": "CATERING",
        "assessoria de casamento": "WEDDING_PLANNER",
        "planejador de eventos": "EVENT_PLANNER",
        "professor particular": "PRIVATE_TUTOR",
        "terapeuta": "THERAPIST",
        "loja de orgânicos": "ORGANIC_FOOD_STORE",
        "loja de organicos": "ORGANIC_FOOD_STORE",
        "loja maternal": "MATERNITY_STORE",
        "genealogista": "GENEALOGIST",
        "transplante capilar": "HAIR_REPLACEMENT_SERVICE",

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
            elif len(w_clean) == 2 and w_clean.upper() in _UFS:
                # Preserva siglas de estado (RS, SP, MG...) em maiúsculas.
                title_words.append(w.upper())
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
    """Maps the lead qualification score to the Antessala funnel stage. Always returns LEAD."""
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
    orig_name = (lead.get("maps_title") or "").strip()
    if orig_name:
        paragraphs.append(f"Lead coletado originalmente no Google Maps sob o nome '{orig_name}'.")

    # 1.1 Endereço (o Antessala não tem campo estruturado para endereço)
    raw_address = (lead.get("maps_address") or lead.get("cnpj_endereco") or "").strip()
    if raw_address:
        address = normalize_address(raw_address, lead.get("maps_city"))
        if address:
            paragraphs.append(f"Endereço registrado: {address}.")

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

# ---------------------------------------------------------------------------
# Integração com o CRM Antessala (API v1)
# ---------------------------------------------------------------------------
# A API v1 tem uma única entidade de contato: a oportunidade (lead). Não
# existem empresas nem pessoas separadas, não existe PATCH e não existe rota
# de exclusão. Tudo o que este módulo grava passa por POST/PUT em
# /api/v1/opportunities. Referência: documentação da API v1 do Antessala.
# ---------------------------------------------------------------------------

API_PREFIX = "/api/v1"
DEFAULT_BASE_URL = "https://antessala.panemiko.com"
DEFAULT_VALUE_CENTS = 130000  # R$ 1.300,00, valor padrão histórico do Haumea
BATCH_MAX_ITEMS = 1000        # limite de itens por lote da API
BATCH_MAX_BYTES = 7_500_000   # o limite da API é 8 MB; mantemos margem
NOTES_MAX_CHARS = 10_000      # limite do campo notes
REQUEST_TIMEOUT = 60
MAX_RETRIES = 5

_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}

_STATE_NAME_TO_UF = {
    "acre": "AC",
    "alagoas": "AL",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceara": "CE",
    "distrito federal": "DF",
    "espirito santo": "ES",
    "goias": "GO",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "para": "PA",
    "paraiba": "PB",
    "parana": "PR",
    "pernambuco": "PE",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}


def _normalize_key(value: str) -> str:
    """Normaliza texto para comparação: sem acento, minúsculo e sem pontuação."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _short_text(value, max_len: int):
    """Colapsa espaços e limita o tamanho. Vazio vira None, como a API espera."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text[:max_len]


def _digits(value) -> str:
    if not value:
        return ""
    return "".join(char for char in str(value) if char.isdigit())


def _normalize_state(value):
    """Aceita UF ou nome por extenso e devolve a UF de duas letras."""
    text = _short_text(value, 40)
    if not text:
        return None
    upper = text.upper()
    if upper in _UFS:
        return upper
    key = re.sub(r"^state of\s+", "", text, flags=re.IGNORECASE)
    return _STATE_NAME_TO_UF.get(_normalize_key(key), text[:40])


def _city_state_from_address(address: str) -> tuple:
    """Tenta extrair cidade e UF de um endereço no formato do Google Maps."""
    if not address:
        return "", ""
    for part in reversed(str(address).split(",")):
        left, separator, right = part.rpartition("-")
        if not separator:
            continue
        candidate = right.strip().upper()
        if candidate in _UFS:
            return left.strip(), candidate
    return "", ""


def _first_email(value):
    """Pega o primeiro e-mail válido de uma lista separada por vírgula ou ponto e vírgula."""
    if not value:
        return None
    for candidate in re.split(r"[,;\s]+", str(value)):
        candidate = candidate.strip().lower()
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", candidate):
            return candidate[:320]
    return None


def _with_scheme(url: str) -> str:
    if not url:
        return url
    return url if re.match(r"^https?://", url, re.IGNORECASE) else f"https://{url}"


def _lead_id(lead: dict, name: str, city: str, phone: str) -> str:
    """Gera um UUID determinístico para servir de chave de idempotência.

    Reenviar o mesmo lead gera o mesmo id e a API responde com conflito em vez
    de duplicar o registro. A prioridade é CNPJ, depois telefone e, por fim,
    nome + cidade.
    """
    cnpj = _digits(lead.get("cnpj_cnpj"))
    phone_digits = _digits(phone)
    if len(cnpj) == 14:
        key = f"cnpj:{cnpj}"
    elif len(phone_digits) >= 10:
        key = f"telefone:{phone_digits}"
    else:
        key = f"nome:{_normalize_key(name)}|{_normalize_key(city or '')}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"haumea-antessala:{key}"))


def _response_json(body: str):
    if not body:
        return {}
    try:
        return json.loads(body)
    except Exception:
        return body


def _get_header(headers: dict, name: str):
    if not headers:
        return None
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return value
    return None


def _build_url(base_url: str, endpoint: str, query: dict = None) -> str:
    url = f"{base_url.rstrip('/')}{API_PREFIX}/{endpoint.lstrip('/')}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url = f"{url}?{urllib.parse.urlencode(clean_query)}"
    return url


def make_api_request(endpoint: str, method: str = "GET", payload: dict = None,
                     query: dict = None, token: str = None, base_url: str = None) -> tuple:
    """Executa uma requisição na API v1 do Antessala.

    Devolve (status, corpo, cabeçalhos). Repete apenas o que é seguro repetir:
    429 respeitando o Retry-After, 5xx com espera exponencial e falhas de
    conexão. Erros de validação, autenticação e permissão não são repetidos.
    """
    base_url = base_url or DEFAULT_BASE_URL
    url = _build_url(base_url, endpoint, query)
    data = None

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Haumea/1.0",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, _response_json(body), dict(response.headers)
        except urllib.error.HTTPError as error:
            try:
                body = error.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            status = error.code
            response_headers = dict(error.headers) if error.headers else {}

            if status == 429 and attempt < MAX_RETRIES:
                retry_after = _get_header(response_headers, "retry-after")
                try:
                    wait = float(retry_after)
                except (TypeError, ValueError):
                    wait = 5.0
                print(f"  -> Limite de requisições atingido (429). Aguardando {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
                continue

            if status in (500, 502, 503, 504) and attempt < MAX_RETRIES:
                print(f"  -> Falha temporária no servidor ({status}). Nova tentativa em {delay:.0f}s...", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue

            return status, _response_json(body), response_headers
        except Exception as error:
            if attempt < MAX_RETRIES:
                print(f"  -> Erro de conexão: {error}. Nova tentativa em {delay:.0f}s...", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            return 0, {"error": {"code": "connection_error", "message": str(error)}}, {}

    return 0, {"error": {"code": "retry_exhausted", "message": "Limite de tentativas atingido."}}, {}


def _print_api_error(label: str, status: int, data, headers: dict = None) -> None:
    error = data.get("error", {}) if isinstance(data, dict) else {}
    code = error.get("code") or "unknown"
    message = error.get("message") or (data if isinstance(data, str) else "")
    print(f"  -> {label}: HTTP {status} ({code}) {message}", file=sys.stderr)
    details = error.get("details")
    if details:
        print(f"     detalhes: {json.dumps(details, ensure_ascii=False)}", file=sys.stderr)
    request_id = _get_header(headers or {}, "x-request-id")
    if request_id:
        print(f"     x-request-id: {request_id}", file=sys.stderr)


def probe_health(base_url: str = DEFAULT_BASE_URL) -> bool:
    """Consulta a sonda pública /api/health antes de qualquer carga."""
    url = f"{base_url.rstrip('/')}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            data = _response_json(body)
            if response.status == 200 and isinstance(data, dict) and data.get("status") == "ok":
                print(f"  Saúde da API: ok ({data.get('opportunities', '?')} leads, {data.get('migrations', '?')} migrações)")
                return True
            print(f"  -> A sonda de saúde respondeu HTTP {response.status}: {body}", file=sys.stderr)
            return False
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        print(f"  -> A sonda de saúde respondeu HTTP {error.code}: {body}", file=sys.stderr)
        return False
    except Exception as error:
        print(f"  -> Não foi possível consultar a sonda de saúde: {error}", file=sys.stderr)
        return False


def load_api_config() -> tuple:
    """Lê token e URL base do Antessala do ambiente ou do .env."""
    load_env()
    token = os.environ.get("ANTESSALA_TOKEN")
    base_url = os.environ.get("ANTESSALA_API_URL") or DEFAULT_BASE_URL
    return token, base_url.rstrip("/")


def lead_to_opportunity(lead: dict, marker: str = None,
                        value_cents: int = None) -> tuple:
    """Converte um lead do JSON do Haumea em um item da API do Antessala.

    Devolve (payload, None) quando o lead é válido ou (None, motivo) quando
    falta o campo obrigatório `name`.
    """
    raw_name = lead.get("maps_title") or lead.get("name") or ""
    name = _short_text(raw_name, 200)
    if not name or len(name) < 2:
        return None, "nome ausente ou com menos de 2 caracteres"

    simplified = _short_text(get_simplified_name(name), 200) or name
    city = _short_text(lead.get("maps_city"), 120)
    state = _normalize_state(lead.get("maps_state"))

    address = lead.get("maps_address") or lead.get("cnpj_endereco") or ""
    if not city or not state:
        address_city, address_state = _city_state_from_address(address)
        city = city or _short_text(address_city, 120)
        state = state or _normalize_state(address_state)

    phone = _short_text(lead.get("maps_phone") or lead.get("cnpj_telefone"), 40)
    email = _first_email(lead.get("maps_emails") or lead.get("cnpj_email"))

    website = _short_text(lead.get("maps_website"), 500)
    instagram = _short_text(lead.get("maps_instagram"), 500)
    current_website = None
    if website:
        if is_social_media(website):
            if "instagram.com" in website.lower() and not instagram:
                instagram = website[:500]
        else:
            current_website = _with_scheme(website)[:500]

    notes = format_observations(lead)

    if value_cents is None:
        raw_value = lead.get("value_cents", lead.get("valueCents"))
        try:
            value_cents = int(raw_value) if raw_value not in (None, "") else DEFAULT_VALUE_CENTS
        except (TypeError, ValueError):
            value_cents = DEFAULT_VALUE_CENTS
    value_cents = max(0, int(value_cents))

    created_at = _now_iso()
    payload_id = _lead_id(lead, name, city, phone)

    if marker:
        tag = f"[{marker}]"
        name = _short_text(f"{tag} {name}", 200)
        simplified = _short_text(f"{tag} {simplified}", 200) or name
        notes = f"{tag} Lead de teste criado pelo Haumea em {created_at}. Pode excluir.\n\n{notes or ''}".rstrip()

    if notes:
        notes = notes[:NOTES_MAX_CHARS]
    else:
        notes = None

    payload = {
        "id": payload_id,
        "name": name,
        "simplifiedName": simplified,
        "city": city,
        "state": state,
        "phone": phone,
        "email": email,
        "instagram": instagram,
        "currentWebsite": current_website,
        "market": map_market(lead.get("maps_category")),
        "status": "LEAD",
        "messageStage": "NO_CONTACT",
        "leadCreatedAt": created_at,
        "valueCents": value_cents,
        "notes": notes,
    }
    return payload, None


def prepare_opportunities(leads: list, marker: str = None) -> tuple:
    """Converte e valida todos os leads antes de enviar qualquer coisa."""
    prepared = []
    skipped = []
    seen_ids = {}

    for index, lead in enumerate(leads, 1):
        if not isinstance(lead, dict):
            skipped.append((index, None, "o item não é um objeto JSON"))
            continue

        payload, reason = lead_to_opportunity(lead, marker=marker)
        if payload is None:
            skipped.append((index, lead.get("maps_title"), reason))
            continue

        if payload["id"] in seen_ids:
            skipped.append((
                index,
                payload["name"],
                f"id repetido no arquivo (igual ao item {seen_ids[payload['id']]})",
            ))
            continue

        seen_ids[payload["id"]] = index
        prepared.append(payload)

    return prepared, skipped


def _chunks(items: list, max_items: int = BATCH_MAX_ITEMS, max_bytes: int = BATCH_MAX_BYTES):
    """Divide os itens em lotes que respeitam o limite de itens e de corpo."""
    chunk = []
    chunk_bytes = 0
    for item in items:
        item_bytes = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if chunk and (len(chunk) >= max_items or chunk_bytes + item_bytes > max_bytes):
            yield chunk
            chunk = []
            chunk_bytes = 0
        chunk.append(item)
        chunk_bytes += item_bytes
    if chunk:
        yield chunk


def post_batch(items: list, token: str, base_url: str) -> tuple:
    """Envia um lote e trata conflito de id removendo apenas os itens repetidos.

    Devolve (criados, já_existentes, falhados, status, corpo_do_erro).
    O lote da API é atômico: um item inválido derruba o lote inteiro.
    """
    pending = list(items)
    created = []
    conflicts = []

    while pending:
        status, data, headers = make_api_request(
            "opportunities", "POST", {"items": pending}, token=token, base_url=base_url
        )

        if status in (200, 201):
            if isinstance(data, dict):
                created.extend(data.get("data") or [])
            return created, conflicts, [], status, None

        if status == 400 and isinstance(data, dict):
            details = data.get("error", {}).get("details") or []
            conflict_indexes = set()
            for detail in details:
                match = re.match(r"corpo\.items\.(\d+)\.id$", str(detail.get("campo", "")))
                if match:
                    conflict_indexes.add(int(match.group(1)))

            if conflict_indexes:
                for index in sorted(conflict_indexes):
                    if 0 <= index < len(pending):
                        conflicts.append(pending[index])
                pending = [item for index, item in enumerate(pending) if index not in conflict_indexes]
                if pending:
                    print(f"  -> {len(conflict_indexes)} lead(s) já existem no CRM e foram pulados; reenviando o restante.")
                else:
                    print(f"  -> {len(conflict_indexes)} lead(s) já existem no CRM; nada novo para enviar.")
                continue

            _print_api_error("Lote rejeitado", status, data, headers)
            return created, conflicts, pending, status, data

        if status == 413 and len(pending) > 1:
            middle = len(pending) // 2
            print(f"  -> Corpo grande demais (413); dividindo o lote em {middle} e {len(pending) - middle} itens.")
            first = post_batch(pending[:middle], token, base_url)
            second = post_batch(pending[middle:], token, base_url)
            merged_status = first[3] if first[3] not in (200, 201) else second[3]
            return (
                first[0] + second[0],
                first[1] + second[1],
                first[2] + second[2],
                merged_status,
                first[4] or second[4],
            )

        _print_api_error("Falha no lote", status, data, headers)
        return created, conflicts, pending, status, data

    return created, conflicts, [], 201, None


def save_registration_state(json_file: Path, base_url: str, marker: str,
                            created: list, conflicts: list) -> Path:
    """Grava ao lado do JSON os ids criados, para conferência e idempotência."""
    output_path = json_file.with_suffix(".registered.json")
    payload = {
        "baseUrl": base_url,
        "registeredAt": _now_iso(),
        "marker": marker,
        "created": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "simplifiedName": item.get("simplifiedName"),
            }
            for item in created
        ],
        "skippedExisting": [
            {"id": item.get("id"), "name": item.get("name")}
            for item in conflicts
        ],
    }
    try:
        with open(output_path, "w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, ensure_ascii=False, indent=2)
        print(f"Estado da carga salvo em: {output_path}")
    except Exception as error:
        print(f"  -> Aviso: não foi possível salvar o estado da carga: {error}", file=sys.stderr)
    return output_path


def fetch_all_opportunities(token: str, base_url: str) -> list:
    """Percorre todas as páginas de leads não arquivados."""
    everyone = []
    page = 1
    while True:
        status, data, headers = make_api_request(
            "opportunities",
            query={"page": page, "pageSize": 1000, "sort": "leadCreatedAt", "dir": "asc"},
            token=token,
            base_url=base_url,
        )
        if status == 403:
            print("  -> Este token não tem escopo de leitura, então não é possível listar os leads.", file=sys.stderr)
            print("     Use um token com escopo read ou full para esta operação.", file=sys.stderr)
            return everyone
        if status != 200 or not isinstance(data, dict):
            _print_api_error("Falha ao listar leads", status, data, headers)
            return everyone

        chunk = data.get("data") or []
        everyone.extend(chunk)
        page_count = data.get("pageCount") or 1
        print(f"  ... página {page}/{page_count} ({len(chunk)} leads)")
        if page >= page_count or not chunk:
            break
        page += 1

    return everyone


def check_duplicates(token: str = None, base_url: str = None) -> bool:
    """Procura leads repetidos por telefone e por nome + cidade."""
    if not token or not base_url:
        token, base_url = load_api_config()

    if not token:
        print("Erro: ANTESSALA_TOKEN não está configurado.", file=sys.stderr)
        return False

    print("\n--- VERIFICANDO LEADS DUPLICADOS NO ANTESSALA ---")
    print(f"API URL: {base_url}")
    print("-------------------------------------------------\n")

    opportunities = fetch_all_opportunities(token, base_url)
    if not opportunities:
        print("Nenhum lead pôde ser lido (ou a base está vazia).")
        return False

    print(f"Total de leads lidos: {len(opportunities)}")

    by_phone = {}
    by_name = {}

    for opportunity in opportunities:
        phone = _digits(opportunity.get("phone"))
        if len(phone) >= 10:
            by_phone.setdefault(phone, []).append(opportunity)

        name_key = _normalize_key(opportunity.get("name"))
        city_key = _normalize_key(opportunity.get("city"))
        if name_key:
            by_name.setdefault(f"{name_key}|{city_key}", []).append(opportunity)

    has_duplicates = False
    printed_groups = 0

    phone_duplicates = {key: value for key, value in by_phone.items() if len(value) > 1}
    if phone_duplicates:
        has_duplicates = True
        print("\n[AVISO] Leads repetidos por telefone:")
        for phone, group in phone_duplicates.items():
            if printed_groups >= 30:
                print("  ... saída limitada a 30 grupos.")
                break
            print(f"  Telefone: {phone}")
            for opportunity in group:
                print(f"    - {opportunity.get('name')} (ID: {opportunity.get('id')})")
            printed_groups += 1

    printed_groups = 0
    name_duplicates = {key: value for key, value in by_name.items() if len(value) > 1}
    if name_duplicates:
        has_duplicates = True
        print("\n[AVISO] Leads repetidos por nome + cidade:")
        for key, group in name_duplicates.items():
            if printed_groups >= 30:
                print("  ... saída limitada a 30 grupos.")
                break
            label = key.split("|")[0].title()
            print(f"  Nome: {label}")
            for opportunity in group:
                print(f"    - {opportunity.get('name')} (ID: {opportunity.get('id')})")
            printed_groups += 1

    if not has_duplicates:
        print("\nNenhum lead duplicado encontrado.")

    print("\n-------------------------------------------------")
    print("Verificação de duplicados concluída.")
    print("-------------------------------------------------\n")
    return has_duplicates


def register_json(json_file_path: Path, limit: int = None, dry_run: bool = False,
                  marker: str = None, check_dups: bool = False) -> list:
    """Lê os leads qualificados do JSON e cria as oportunidades no Antessala.

    - O lote é atômico na API; aqui os itens são deduplicados e divididos em
      lotes de até 1000 itens / 8 MB.
    - O `id` de cada lead é determinístico (CNPJ, telefone ou nome + cidade),
      então repetir a carga não duplica registros: a API devolve conflito e o
      script segue apenas com os leads que ainda faltam.
    - `marker` demarca os leads criados no nome e nas observações, útil para
      cargas de teste que serão excluídas depois na tela do CRM.
    """
    json_file_path = Path(json_file_path)
    if not json_file_path.exists():
        print(f"Erro: o arquivo JSON '{json_file_path}' não existe.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(json_file_path, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except json.JSONDecodeError as error:
        print(f"Erro: falha ao interpretar o JSON de '{json_file_path}': {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        print(f"Erro ao ler o JSON: {error}", file=sys.stderr)
        sys.exit(1)

    if isinstance(data, dict):
        data = data.get("items") or data.get("data") or [data]
    if not isinstance(data, list):
        data = [data]

    token, base_url = load_api_config()
    if not token or token == "your_token_here":
        print("Erro: a variável ANTESSALA_TOKEN não está configurada corretamente.", file=sys.stderr)
        print("Configure no .env da raiz do projeto:", file=sys.stderr)
        print("  ANTESSALA_TOKEN=\"crm_...\"", file=sys.stderr)
        print("  ANTESSALA_API_URL=\"https://antessala.panemiko.com\"", file=sys.stderr)
        sys.exit(1)

    if marker:
        marker = " ".join(str(marker).split())[:60]

    total_read = len(data)
    if limit is not None:
        if limit <= 0:
            print("Erro: --limit precisa ser maior que zero.", file=sys.stderr)
            sys.exit(1)
        data = data[:limit]

    print("\n--- REGISTRANDO LEADS NO CRM ANTESSALA ---")
    print(f"Arquivo:  {json_file_path}")
    print(f"API URL:  {base_url}")
    print(f"Lidos:    {total_read} lead(s)")
    if limit is not None:
        print(f"Limite:   {len(data)} lead(s) nesta execução")
    print(f"Marcador: {marker or '(nenhum)'}")
    print(f"Modo:     {'simulação (nada será gravado)' if dry_run else 'gravação'}")
    print("-------------------------------------------\n")

    opportunities, skipped = prepare_opportunities(data, marker=marker)

    for index, name, reason in skipped:
        print(f"  -> Item {index} ignorado ({name or 'sem nome'}): {reason}", file=sys.stderr)

    print(f"Leads prontos para envio: {len(opportunities)}")
    if skipped:
        print(f"Leads ignorados na validação: {len(skipped)}")

    if not opportunities:
        print("\nNada para enviar.")
        return []

    if dry_run:
        print("\n--- PAYLOAD QUE SERIA ENVIADO ---")
        for opportunity in opportunities:
            print(json.dumps(opportunity, ensure_ascii=False, indent=2))
        print("\nSimulação concluída. Nenhum lead foi gravado.")
        return []

    if not probe_health(base_url):
        print("\nA API não está saudável. Abortando para não deixar carga pela metade.", file=sys.stderr)
        return []

    created = []
    conflicts = []
    failed = []
    batches = list(_chunks(opportunities))
    print(f"\nEnviando {len(opportunities)} lead(s) em {len(batches)} lote(s)...\n")

    for batch_number, batch in enumerate(batches, 1):
        print(f"[Lote {batch_number}/{len(batches)}] {len(batch)} lead(s)")
        batch_created, batch_conflicts, batch_failed, status, _ = post_batch(batch, token, base_url)
        created.extend(batch_created)
        conflicts.extend(batch_conflicts)
        failed.extend(batch_failed)

        if status in (200, 201):
            print(f"  -> {len(batch_created)} criado(s), {len(batch_conflicts)} já existente(s).")
        else:
            print(f"  -> Lote não concluído (HTTP {status}): {len(batch_failed)} lead(s) não gravado(s).", file=sys.stderr)
            if status in (401, 403):
                print("  -> Token inválido ou sem permissão de escrita. Abortando os lotes restantes.", file=sys.stderr)
                break

        if batch_number < len(batches):
            time.sleep(0.3)

    state_file = save_registration_state(json_file_path, base_url, marker, created, conflicts)

    print("\n-------------------------------------------")
    print("Carga concluída.")
    print(f"Criados:            {len(created)}")
    print(f"Já existiam:        {len(conflicts)}")
    print(f"Não gravados:       {len(failed)}")
    print(f"Estado da carga:    {state_file}")
    print("-------------------------------------------\n")

    if created:
        print("LEADS CRIADOS NESTA EXECUÇÃO:")
        for opportunity in created:
            print(f"  - {opportunity.get('id')}  {opportunity.get('name')}")
        print()

    if conflicts:
        print("LEADS PULADOS POR JÁ EXISTIREM (mesmo id):")
        for opportunity in conflicts:
            print(f"  - {opportunity.get('id')}  {opportunity.get('name')}")
        print()

    if failed:
        print("LEADS NÃO GRAVADOS:", file=sys.stderr)
        for opportunity in failed:
            print(f"  - {opportunity.get('id')}  {opportunity.get('name')}", file=sys.stderr)
        print(file=sys.stderr)

    if marker and created:
        print(f"ATENÇÃO: os leads acima estão marcados com [{marker}].")
        print("Eles foram criados para teste e podem ser excluídos pela tela do CRM.\n")

    if check_dups:
        check_duplicates(token=token, base_url=base_url)
    else:
        print("Dica: rode 'python haumea duplicates' (token com leitura) para conferir repetidos.\n")

    return [opportunity.get("id") for opportunity in created]


def normalize_crm_names(token: str = None, base_url: str = None, dry_run: bool = False) -> None:
    """Apara espaços nos nomes dos leads e preenche nomes simplificados vazios.

    A API v1 não tem empresa nem PATCH: cada ajuste é um PUT parcial em
    /api/v1/opportunities, um lead por requisição, respeitando o limite de
    120 requisições por minuto do token.
    """
    if not token or not base_url:
        token, base_url = load_api_config()

    if not token or token == "your_token_here":
        print("[ERRO] ANTESSALA_TOKEN não está configurado corretamente.", file=sys.stderr)
        print("Confira o .env na raiz do projeto.", file=sys.stderr)
        sys.exit(1)

    print("\n--- NORMALIZAÇÃO DE NOMES NO ANTESSALA ---")
    print(f"API URL: {base_url}")
    print(f"Modo:    {'simulação (nada será gravado)' if dry_run else 'gravação'}")
    print("------------------------------------------\n")

    opportunities = fetch_all_opportunities(token, base_url)
    if not opportunities:
        print("Nenhum lead pôde ser lido. Nada a normalizar.")
        return

    processed = 0
    changed = 0
    failures = 0

    for index, opportunity in enumerate(opportunities, 1):
        processed += 1
        opportunity_id = opportunity.get("id")
        changes = {}

        for field in ("name", "simplifiedName", "city", "phone", "instagram", "currentWebsite"):
            current = opportunity.get(field)
            if isinstance(current, str):
                cleaned = " ".join(current.split())
                if cleaned != current:
                    changes[field] = cleaned or None

        name = changes.get("name", opportunity.get("name"))
        simplified = changes.get("simplifiedName", opportunity.get("simplifiedName"))
        if name and not simplified:
            changes["simplifiedName"] = name

        if not changes:
            continue

        changed += 1
        print(f"[{index}/{len(opportunities)}] {opportunity.get('name')} ({opportunity_id})")
        print(f"  -> campos: {', '.join(sorted(changes))}")

        if dry_run:
            continue

        status, data, headers = make_api_request(
            "opportunities", "PUT", {"id": opportunity_id, **changes},
            token=token, base_url=base_url
        )
        if status == 200:
            print("  -> Atualizado.")
        else:
            failures += 1
            _print_api_error("Falha ao atualizar", status, data, headers)
            if status in (401, 403):
                print("  -> Abortando: token sem permissão.", file=sys.stderr)
                break

        time.sleep(0.55)

    print("\n------------------------------------------")
    print(f"Leads analisados:       {processed}")
    print(f"Leads com ajuste:       {changed}")
    print(f"Falhas:                 {failures}")
    print("------------------------------------------\n")
