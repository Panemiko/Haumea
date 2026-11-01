import csv
import json
import shutil
import subprocess
import sys
import webbrowser
import urllib.parse
from datetime import datetime
from pathlib import Path
from scripts.cnpj_helper import lookup_single_cnpj, to_title_case, clean_digits
from scripts.cleaner import format_cnpj, format_phone, format_address, calculate_age_years

def detect_csv_format(file_path: Path):
    """Detects encoding and dialect of the CSV file."""
    encoding = 'utf-8'
    try:
        with open(file_path, 'rb') as f:
            first_bytes = f.read(3)
        if first_bytes == b'\xef\xbb\xbf':
            encoding = 'utf-8-sig'
        else:
            with open(file_path, mode='r', encoding='utf-8', newline='') as f:
                f.readline()
    except UnicodeDecodeError:
        encoding = 'latin-1'
            
    try:
        with open(file_path, mode='r', encoding=encoding, newline='') as infile:
            sample = infile.read(2048)
            infile.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=[',', ';', '\t'])
            except Exception:
                dialect = 'excel'
            return encoding, dialect
    except Exception as e:
        print(f"Error reading file for format detection: {e}", file=sys.stderr)
        sys.exit(1)

def save_csv(file_path: Path, fieldnames: list, rows: list, encoding: str, dialect):
    """Saves rows to a temporary file and replaces the original file atomically. Also saves a JSON copy alongside it."""
    temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
    try:
        with open(temp_path, mode='w', encoding=encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, dialect=dialect)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(file_path)
        
        # Also save structured JSON alongside
        json_path = file_path.with_suffix('.json')
        json_rows = []
        for r in rows:
            r_copy = dict(r)
            if r_copy.get("review_score_table"):
                try:
                    r_copy["review_score_table"] = json.loads(r_copy["review_score_table"])
                except Exception:
                    pass
            json_rows.append(r_copy)
        with open(json_path, mode='w', encoding='utf-8') as jf:
            json.dump(json_rows, jf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"\nError saving CSV/JSON files: {e}", file=sys.stderr)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

def format_url(url_str: str) -> str:
    """Formats a URL to ensure it starts with http:// or https://."""
    url_str = url_str.strip()
    if not url_str:
        return ""
    if not url_str.startswith(("http://", "https://")):
        return "https://" + url_str
    return url_str

def open_urls(urls: list, chrome_bin: str = None):
    """Opens a list of URLs in a new Chromium/Chrome window or falls back to webbrowser."""
    valid_urls = [u for u in urls if u]
    if not valid_urls:
        return

    if chrome_bin:
        try:
            subprocess.Popen([chrome_bin, '--new-window'] + valid_urls, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f" Failed opening in Chromium: {e}. Falling back to default browser...")
            _fallback_open(valid_urls)
    else:
        _fallback_open(valid_urls)

def _fallback_open(urls: list):
    try:
        webbrowser.open_new(urls[0])
        for u in urls[1:]:
            webbrowser.open_new_tab(u)
    except Exception as e:
        print(f" Failed to open browser: {e}")

class GoBackException(Exception):
    pass

def prompt_question(prompt_text: str, valid_options: list, default: str = None) -> str:
    """Prompts the user with a question and validates the response."""
    display_prompt = prompt_text
    if default is not None:
        if display_prompt.endswith(": "):
            display_prompt = display_prompt[:-2] + f" [{default}]: "
        elif display_prompt.endswith(":"):
            display_prompt = display_prompt[:-1] + f" [{default}]: "
        else:
            display_prompt = display_prompt + f" [{default}]"

    while True:
        try:
            val = input(display_prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            val = 'exit'
            
        if val == '' and default is not None:
            return default
        if val in ('back', 'voltar', 'menu'):
            raise GoBackException()
        if val in valid_options:
            return val
        if val in ('exit', 'quit'):
            print("\nExiting script. Progress saved.")
            sys.exit(0)
        print(f"Opção inválida. Por favor digite uma das opções: {', '.join(valid_options)} (ou 'back' para voltar ao menu)")

def calculate_gmn_reviews_score(row: dict) -> tuple:
    """
    Parses maps_user_reviews JSON to evaluate when the last review was.
    Returns: (score, details_string)
    Max score is 10 points.
    If historically active (>= 5 reviews) but has not received reviews
    for a long period (days_since_last > 180 and days_since_last > 3 * average_interval),
    it is considered an abrupt stop, and we apply a penalty (-5 points).
    """
    reviews_str = (row.get("maps_user_reviews") or row.get("user_reviews") or "").strip()
    if not reviews_str:
        return 0, "Sem avaliações registradas no Google Maps"
        
    try:
        reviews = json.loads(reviews_str)
    except Exception:
        return 0, "Erro ao analisar o JSON de avaliações"
        
    if not isinstance(reviews, list) or not reviews:
        return 0, "Sem avaliações registradas no Google Maps"
        
    timestamps = []
    for r in reviews:
        ts = None
        micros = r.get("posted_at_unix_micros")
        if micros:
            try:
                ts = datetime.fromtimestamp(float(micros) / 1000000)
            except Exception:
                pass
        if not ts:
            pub_at = r.get("published_at")
            if pub_at:
                try:
                    pub_at = pub_at.replace("Z", "")
                    ts = datetime.fromisoformat(pub_at)
                except Exception:
                    pass
        if ts:
            timestamps.append(ts)
            
    if not timestamps:
        return 0, "Sem avaliações com data válida"
        
    timestamps.sort()
    
    now = datetime.now()
    newest_ts = timestamps[-1]
    days_since_last = (now - newest_ts).days
    if days_since_last < 0:
        days_since_last = 0
        
    if days_since_last <= 30:
        base_score = 10
        desc = f"Última avaliação recente ({days_since_last} dias atrás) (+10)"
    elif days_since_last <= 90:
        base_score = 8
        desc = f"Última avaliação de 1 a 3 meses atrás ({days_since_last} dias) (+8)"
    elif days_since_last <= 180:
        base_score = 5
        desc = f"Última avaliação de 3 a 6 meses atrás ({days_since_last} dias) (+5)"
    elif days_since_last <= 365:
        base_score = 3
        desc = f"Última avaliação de 6 a 12 meses atrás ({days_since_last} dias) (+3)"
    else:
        base_score = 1
        desc = f"Última avaliação há mais de 1 ano ({days_since_last} dias) (+1)"
        
    abrupt_stop = False
    avg_interval = 0
    if len(timestamps) >= 5:
        intervals = []
        for i in range(1, len(timestamps)):
            diff = (timestamps[i] - timestamps[i-1]).days
            intervals.append(diff)
        avg_interval = sum(intervals) / len(intervals) if intervals else 1
        if avg_interval < 1:
            avg_interval = 1
            
        if days_since_last > 180 and days_since_last > 3 * avg_interval:
            abrupt_stop = True
            
    if abrupt_stop:
        penalty = 5
        final_score = max(0, base_score - penalty)
        desc += f" [SÚBITA PARADA: média era {avg_interval:.1f} dias, sem reviews há {days_since_last} dias] (-{penalty} pts)"
    else:
        final_score = base_score
        
    return final_score, desc

def score_area1_maps(row: dict) -> tuple:
    """Calculates Area 1 (Google Maps Data) score and returns (score, max_score, details_list)."""
    # Max points: 40
    details = []
    
    # 1. Website Presence (Max: 10)
    has_website = row.get("maps_website", "").strip()
    if "maps_website" not in row:
        pts_web = 5.0
        details.append(("Ausência de Website", pts_web, 10, "Dados ausentes (assumido média)"))
    elif not has_website:
        pts_web = 10
        details.append(("Ausência de Website", pts_web, 10, "Sem site cadastrado"))
    else:
        pts_web = 0
        details.append(("Ausência de Website", pts_web, 10, "Possui site cadastrado"))
        
    # 2. Instagram Presence in Maps (Max: 10)
    has_insta = row.get("maps_instagram", "").strip()
    if "maps_instagram" not in row:
        pts_insta = 5.0
        details.append(("Instagram no Maps", pts_insta, 10, "Dados ausentes (assumido média)"))
    elif has_insta:
        pts_insta = 10
        details.append(("Instagram no Maps", pts_insta, 10, "Instagram cadastrado"))
    else:
        pts_insta = 0
        details.append(("Instagram no Maps", pts_insta, 10, "Sem Instagram cadastrado"))
        
    # 3. Thumbnail is Street View (Max: 5)
    thumb_url = row.get("maps_thumbnail", "").strip()
    if "maps_thumbnail" not in row:
        pts_thumb = 2.5
        details.append(("Street View Thumbnail", pts_thumb, 5, "Dados ausentes (assumido média)"))
    else:
        is_sv = any(x in thumb_url.lower() for x in ["streetviewpixels", "panoid", "cb_client"])
        if is_sv or not thumb_url:
            pts_thumb = 5
            details.append(("Street View Thumbnail", pts_thumb, 5, "Foto do Street View / Sem fotos personalizadas"))
        else:
            pts_thumb = 0
            details.append(("Street View Thumbnail", pts_thumb, 5, "Foto personalizada do usuário"))
            
    # 4. Order Online (Max: 5)
    order_online = row.get("maps_order_online", "").strip()
    if "maps_order_online" not in row:
        pts_order = 2.5
        details.append(("Link de Pedido/Reserva", pts_order, 5, "Dados ausentes (assumido média)"))
    elif order_online and order_online != "[]" and order_online != "null":
        pts_order = 5
        details.append(("Link de Pedido/Reserva", pts_order, 5, "Possui recurso de agendamento/pedido online"))
    else:
        pts_order = 0
        details.append(("Link de Pedido/Reserva", pts_order, 5, "Sem agendamento/pedido online"))
        
    # 5. GMN Reviews Recency & Activity (Max: 10)
    pts_gmn_reviews, gmn_details = calculate_gmn_reviews_score(row)
    details.append(("Recência de Avaliações GMN", pts_gmn_reviews, 10, gmn_details))
        
    total_score = pts_web + pts_insta + pts_thumb + pts_order + pts_gmn_reviews
    return int(total_score), 40, details


def score_area2_review(row: dict) -> tuple:
    """Calculates Area 2 (Interactive Review Questions) score and returns (score, max_score, details_list)."""
    # Max points: 40
    q1 = row.get("review_q1_site", "").strip().lower()
    if not q1:
        details = [
            ("Site Profissional", 7.5, 15, "Não revisado (assumido média)"),
            ("Site Responsivo", 2.5, 5, "Não revisado (assumido média)"),
            ("Instagram Ativo (Post Recente)", 2.5, 5, "Não revisado (assumido média)"),
            ("WhatsApp Fácil", 2.5, 5, "Não revisado (assumido média)"),
            ("Presença Amadora", 2.5, 5, "Não revisado (assumido média)"),
            ("Qualidade do Instagram", 2.5, 5, "Não revisado (assumido média)")
        ]
        return 20, 40, details

    details = []
    
    # 1. Site Profissional (Max: 15)
    if q1 == 'n':
        pts_site = 15
        details.append(("Site Profissional", pts_site, 15, "Não possui site profissional (+15)"))
    elif q1 == 's':
        pts_site = 0
        details.append(("Site Profissional", pts_site, 15, "Possui site profissional"))
    else:
        pts_site = 7.5
        details.append(("Site Profissional", pts_site, 15, "Não respondido (assumido média)"))

    # 2. Site Responsivo (Max: 5)
    q2 = row.get("review_q2_responsivo", "").strip().lower()
    if not q2:
        pts_resp = 2.5
        details.append(("Site Responsivo", pts_resp, 5, "Não respondido (assumido média)"))
    elif q2 == 'n':
        pts_resp = 5
        details.append(("Site Responsivo", pts_resp, 5, "Site não responsivo/lento (+5)"))
    elif q2 == 's':
        pts_resp = 0
        details.append(("Site Responsivo", pts_resp, 5, "Site responsivo"))
    else:  # 'na' or empty
        pts_resp = 0
        details.append(("Site Responsivo", pts_resp, 5, "N/A (sem site)"))

    # 3. Instagram Ativo / Recente (Max: 5)
    q3 = row.get("review_q3_instagram", "").strip().lower()
    if not q3:
        pts_insta = 2.5
        details.append(("Instagram Ativo (Post Recente)", pts_insta, 5, "Não respondido (assumido média)"))
    elif q3 == 'na':
        pts_insta = 0
        details.append(("Instagram Ativo (Post Recente)", pts_insta, 5, "N/A (sem Instagram registrado)"))
    else:
        try:
            weeks = float(q3)
            if weeks <= 2:
                pts_insta = 5
                details.append(("Instagram Ativo (Post Recente)", pts_insta, 5, f"Postado recentemente ({weeks} semanas atrás) (+5)"))
            elif weeks <= 4:
                pts_insta = 3
                details.append(("Instagram Ativo (Post Recente)", pts_insta, 5, f"Postado moderadamente ({weeks} semanas atrás) (+3)"))
            else:
                pts_insta = 1
                details.append(("Instagram Ativo (Post Recente)", pts_insta, 5, f"Postado há mais de 4 semanas ({weeks} semanas atrás) (+1)"))
        except ValueError:
            pts_insta = 2.5
            details.append(("Instagram Ativo (Post Recente)", pts_insta, 5, f"Valor de semanas inválido '{q3}' (assumido média)"))

    # 4. WhatsApp Fácil (Max: 5)
    q4 = row.get("review_q4_whatsapp", "").strip().lower()
    if not q4:
        pts_wa = 2.5
        details.append(("WhatsApp Fácil", pts_wa, 5, "Não respondido (assumido média)"))
    elif q4 == 'n':
        pts_wa = 5
        details.append(("WhatsApp Fácil", pts_wa, 5, "Sem link fácil de WhatsApp (+5)"))
    else:
        pts_wa = 0
        details.append(("WhatsApp Fácil", pts_wa, 5, "Possui link fácil de WhatsApp"))

    # 5. Presença Amadora (Max: 5)
    q5 = row.get("review_q5_amador", "").strip().lower()
    if not q5:
        pts_amador = 2.5
        details.append(("Presença Amadora", pts_amador, 5, "Não respondido (assumido média)"))
    elif q5 == 's':
        pts_amador = 5
        details.append(("Presença Amadora", pts_amador, 5, "Presença digital amadora/desatualizada (+5)"))
    else:
        pts_amador = 0
        details.append(("Presença Amadora", pts_amador, 5, "Presença profissional"))

    # 6. Qualidade do Instagram (Max: 5)
    q6 = row.get("review_q6_insta_qualidade", "").strip().lower()
    if not q6:
        pts_q6 = 2.5
        details.append(("Qualidade do Instagram", pts_q6, 5, "Não respondido (assumido média)"))
    elif q6 == 'u':
        pts_q6 = 5
        details.append(("Qualidade do Instagram", pts_q6, 5, "Qualidade ruim/amador (+5)"))
    elif q6 == 'r':
        pts_q6 = 3
        details.append(("Qualidade do Instagram", pts_q6, 5, "Qualidade regular (+3)"))
    elif q6 == 'b':
        pts_q6 = 0
        details.append(("Qualidade do Instagram", pts_q6, 5, "Qualidade boa"))
    else:  # 'na'
        pts_q6 = 0
        details.append(("Qualidade do Instagram", pts_q6, 5, "N/A (sem Instagram)"))

    total_score = pts_site + pts_resp + pts_insta + pts_wa + pts_amador + pts_q6
    return int(total_score), 40, details


def score_area3_cnpj(row: dict) -> tuple:
    """Calculates Area 3 (CNPJ / Registration Data) score and returns (score, max_score, details_list)."""
    # Max points: 40
    cnpj_val = row.get("cnpj_cnpj", "").strip()
    if not cnpj_val:
        details = [
            ("Qualidade do E-mail", 5.0, 10, "CNPJ não encontrado (assumido média)"),
            ("Sala Fixa", 5.0, 10, "CNPJ não encontrado (assumido média)"),
            ("Idade da Empresa", 5.0, 10, "CNPJ não encontrado (assumido média)"),
            ("Decisão (Sócios)", 2.5, 5, "CNPJ não encontrado (assumido média)"),
            ("Capital Social", 2.5, 5, "CNPJ não encontrado (assumido média)")
        ]
        return 20, 40, details



    details = []
    
    # 1. Email Quality (Max: 10)
    email = row.get("cnpj_email", "").strip().lower()
    if not email:
        pts_email = 0
        details.append(("Qualidade do E-mail", pts_email, 10, "Sem e-mail cadastrado"))
    else:
        # Exclude accounting emails
        accounting_kws = ["contabil", "contabilidade", "assessoria", "escritorio", "auditoria", "contas"]
        if any(kw in email for kw in accounting_kws):
            pts_email = 0
            details.append(("Qualidade do E-mail", pts_email, 10, f"E-mail de contabilidade ignorado: {email}"))
        else:
            personal_domains = [
                "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", 
                "yahoo.com.br", "bol.com.br", "uol.com.br", "ig.com.br", 
                "terra.com.br", "live.com", "icloud.com"
            ]
            domain = email.split("@")[-1] if "@" in email else ""
            if domain in personal_domains:
                pts_email = 5
                details.append(("Qualidade do E-mail", pts_email, 10, f"E-mail pessoal: {email}"))
            else:
                pts_email = 10
                details.append(("Qualidade do E-mail", pts_email, 10, f"E-mail corporativo: {email}"))
                
    # 2. Fixed Office / Sala Fixa (Max: 10)
    address = row.get("cnpj_endereco", "").upper()
    has_sala = any(kw in address for kw in ["SALA", "SL", "CONJUNTO", "CONJ"])
    not_predio = any(kw in address for kw in ["CASA", "SOBRADO", "GALPAO", "CHACARA", "SITIO", "FAZENDA", "TERRENO"])
    if has_sala and not not_predio:
        pts_sala = 10
        details.append(("Sala Fixa", pts_sala, 10, "Possui sala comercial fixa (prédio)"))
    else:
        pts_sala = 0
        details.append(("Sala Fixa", pts_sala, 10, "Não possui sala fixa ou residência/galpão"))
        
    # 3. Company Age (Max: 10)
    try:
        age = float(row.get("cnpj_idade_empresa_anos", "0.0"))
    except ValueError:
        age = 0.0
        
    if age <= 0.0:
        pts_age = 0
        details.append(("Idade da Empresa", pts_age, 10, "Idade desconhecida"))
    elif 1.0 <= age <= 10.0:
        pts_age = 10
        details.append(("Idade da Empresa", pts_age, 10, f"Idade ideal ({age} anos)"))
    elif 0.5 <= age < 1.0 or 10.0 < age <= 20.0:
        pts_age = 5
        details.append(("Idade da Empresa", pts_age, 10, f"Idade moderada ({age} anos)"))
    else:
        pts_age = 1
        details.append(("Idade da Empresa", pts_age, 10, f"Muito nova ou muito antiga ({age} anos)"))
        
    # 4. Partners and Decision Cycle (Max: 5)
    try:
        partners_cnt = int(row.get("cnpj_quantidade_socios", "0"))
    except ValueError:
        partners_cnt = 0
        
    if partners_cnt <= 1:
        pts_partners = 5
        details.append(("Decisão (Sócios)", pts_partners, 5, f"Decisor único ({partners_cnt} sócios)"))
    elif partners_cnt == 2:
        pts_partners = 3
        details.append(("Decisão (Sócios)", pts_partners, 5, "Dois sócios (ciclo médio)"))
    else:
        pts_partners = 0
        details.append(("Decisão (Sócios)", pts_partners, 5, f"Múltiplos decisores ({partners_cnt} sócios)"))
        
    # 5. Capital Social (Max: 5)
    try:
        cap_social = float(row.get("cnpj_capital_social", "0.0"))
    except ValueError:
        cap_social = 0.0
        
    if cap_social >= 50000.0:
        pts_cap = 5
        details.append(("Capital Social", pts_cap, 5, f"Capital alto (R$ {cap_social:,.2f})"))
    elif 10000.0 <= cap_social < 50000.0:
        pts_cap = 3
        details.append(("Capital Social", pts_cap, 5, f"Capital médio (R$ {cap_social:,.2f})"))
    elif 0.0 < cap_social < 10000.0:
        pts_cap = 1
        details.append(("Capital Social", pts_cap, 5, f"Capital baixo (R$ {cap_social:,.2f})"))
    else:
        pts_cap = 0
        details.append(("Capital Social", pts_cap, 5, "Sem capital social registrado"))
        
    total_score = pts_email + pts_sala + pts_age + pts_partners + pts_cap
    return int(total_score), 40, details


def generate_markdown_table(score1, max1, details1, score2, max2, details2, score3, max3, details3) -> str:
    total_score = score1 + score2 + score3
    total_max = max1 + max2 + max3
    
    lines = [
        "| Área | Critério | Pontos | Máximo | Detalhes |",
        "| --- | --- | --- | --- | --- |"
    ]
    
    # Area 1
    for crit, pts, mx, det in details1:
        lines.append(f"| Google Maps | {crit} | {pts} | {mx} | {det} |")
    lines.append(f"| **Subtotal Maps** | | **{score1}** | **{max1}** | |")
    
    # Area 2
    for crit, pts, mx, det in details2:
        lines.append(f"| Review | {crit} | {pts} | {mx} | {det} |")
    lines.append(f"| **Subtotal Review** | | **{score2}** | **{max2}** | |")
    
    # Area 3
    for crit, pts, mx, det in details3:
        lines.append(f"| CNPJ | {crit} | {pts} | {mx} | {det} |")
    lines.append(f"| **Subtotal CNPJ** | | **{score3}** | **{max3}** | |")
    
    # Total
    lines.append(f"| **TOTAL** | | **{total_score}** | **{total_max}** | |")
    
    return "\n".join(lines)


def generate_review_score_json(score1, max1, details1, score2, max2, details2, score3, max3, details3) -> str:
    data = {
        "areas": {
            "google_maps": {
                "score": score1,
                "max_score": max1,
                "details": [
                    {"criterion": crit, "points": pts, "max_points": mx, "detail": det}
                    for crit, pts, mx, det in details1
                ]
            },
            "review": {
                "score": score2,
                "max_score": max2,
                "details": [
                    {"criterion": crit, "points": pts, "max_points": mx, "detail": det}
                    for crit, pts, mx, det in details2
                ]
            },
            "cnpj": {
                "score": score3,
                "max_score": max3,
                "details": [
                    {"criterion": crit, "points": pts, "max_points": mx, "detail": det}
                    for crit, pts, mx, det in details3
                ]
            }
        },
        "total": {
            "score": score1 + score2 + score3,
            "max_score": max1 + max2 + max3
        }
    }
    return json.dumps(data, ensure_ascii=False)


def print_lead_info_remover(row: dict, idx: int, total: int):
    title = row.get("maps_title", "").strip() or "Sem nome"
    category = row.get("maps_category", "").strip() or "Sem categoria"
    city = row.get("maps_city", "").strip()
    state = row.get("maps_state", "").strip()
    phone = row.get("maps_phone", "").strip()
    emails = row.get("maps_emails", "").strip()
    website = row.get("maps_website", "").strip()
    instagram = row.get("maps_instagram", "").strip()
    facebook = row.get("maps_facebook", "").strip()
    
    # CNPJ fields
    cnpj = row.get("cnpj_cnpj", "").strip()
    razao_social = row.get("cnpj_razao_social", "").strip()
    nome_fantasia = row.get("cnpj_nome_fantasia", "").strip()
    situacao_cadastral = row.get("cnpj_situacao_cadastral", "").strip()
    idade_anos = row.get("cnpj_idade_empresa_anos", "").strip()
    
    # Reviews
    review_rating = row.get("maps_review_rating", "").strip()
    review_count = row.get("maps_review_count", "").strip()

    print("\n" + "=" * 60)
    print(f" LEAD {idx + 1} DE {total}: {title}")
    print("=" * 60)
    print(f" 1. Categoria:      {category}")
    print(f" 2. Localização:    {city} - {state}" if (city or state) else " 2. Localização:    Não informada")
    print(f" 3. Telefone:       {phone}" if phone else " 3. Telefone:       Não informado")
    print(f" 4. E-mails:        {emails}" if emails else " 4. E-mails:        Não informado")
    print(f" 5. Website:        {website}" if website else " 5. Website:        Não registrado")
    print(f" 6. Instagram:      {instagram}" if instagram else " 6. Instagram:      Não registrado")
    print(f" 7. Facebook:       {facebook}" if facebook else " 7. Facebook:       Não registrado")
    
    if review_rating or review_count:
        rating_str = f"Nota: {review_rating}" if review_rating else ""
        count_str = f"{review_count} avaliações" if review_count else ""
        rev_str = " | ".join(filter(None, [rating_str, count_str]))
        print(f" 8. Google Maps:    {rev_str}")
    else:
        print(" 8. Google Maps:    Sem avaliações")
        
    cnpj_parts = []
    if cnpj:
        cnpj_parts.append(f"CNPJ: {cnpj}")
    if situacao_cadastral:
        cnpj_parts.append(f"Situação: {situacao_cadastral}")
    if nome_fantasia:
        cnpj_parts.append(f"Nome Fantasia: {nome_fantasia}")
    elif razao_social:
        cnpj_parts.append(f"Razão Social: {razao_social}")
    if idade_anos:
        cnpj_parts.append(f"Idade: {idade_anos} anos")
        
    if cnpj_parts:
        print(f" 9. Dados CNPJ:     {', '.join(cnpj_parts)}")
    else:
        print(" 9. Dados CNPJ:     Nenhum CNPJ associado")
    print("=" * 60)


def review_csv(input_file: Path, screenshot_dir: Path = None, output_file: Path = None, mode: str = "complete") -> Path:
    """Interactive CLI loop that handles CNPJ manual entry, presence checklist, and scoring."""
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: File '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"--- STARTING WEBSITE & DIGITAL PRESENCE REVIEW ---")
    
    if output_file:
        output_path = Path(output_file)
    elif input_path.stem.endswith("_qualified"):
        output_path = input_path
    else:
        output_path = input_path.parent / f"{input_path.stem}_qualified{input_path.suffix}"

    read_path = output_path if output_path.exists() else input_path
    
    print(f"Reading data from: {read_path}")
    encoding, dialect = detect_csv_format(read_path)
    
    rows = []
    fieldnames = []
    with open(read_path, mode='r', encoding=encoding, newline='') as f:
        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = [fn.strip().lstrip('\ufeff') for fn in reader.fieldnames] if reader.fieldnames else []
        
        # Ensure new fields are present dynamically
        for new_col in ["maps_thumbnail", "maps_order_online", "review_q6_insta_qualidade", "review_score_table", "review_status", "maps_review_count", "maps_review_rating", "maps_user_reviews"]:
            if new_col not in fieldnames:
                fieldnames.append(new_col)
        
        # Verify required columns exist
        for col in ["maps_title", "maps_city", "maps_state"]:
            if col not in fieldnames:
                print(f"Error: Required column '{col}' is missing in CSV.", file=sys.stderr)
                print("Make sure this CSV has been cleaned via the clean subcommand first.", file=sys.stderr)
                sys.exit(1)
                
        f.seek(0)
        reader = csv.DictReader(f, fieldnames=fieldnames, dialect=dialect)
        next(reader) # skip header
        for r in reader:
            extras = r.get(None)
            if extras:
                print(f"Warning: skipping {len(extras)} extra column(s) in row for '{r.get('maps_title', '?')}'", file=sys.stderr)
            cleaned_r = {
                k.strip().lstrip('\ufeff'): (v if v is not None else "")
                for k, v in r.items()
                if k is not None
            }
            rows.append(cleaned_r)

    # Find Chromium/Chrome
    chrome_bin = (
        shutil.which('chromium') or
        shutil.which('chromium-browser') or
        shutil.which('google-chrome') or 
        shutil.which('google-chrome-stable')
    )
    if not chrome_bin:
        common_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chrome"
        ]
        for path in common_paths:
            if Path(path).exists():
                chrome_bin = path
                break

    to_review = rows
    total_leads = len(to_review)
    total_reviewed = len([r for r in to_review if r.get("review_status", "").strip() == "Finalizado"])
    
    print("=" * 60)
    print(f"Total leads:               {total_leads}")
    print(f"Reviewed leads:            {total_reviewed}")
    print("=" * 60)

    if mode == "remover":
        print("\n--- INICIANDO MODO REMOVER (LIMPEZA DE LISTA) ---")
        print(f"Total de leads na lista: {len(to_review)}")
        print("Neste modo, você pode remover leads indesejados da planilha.")
        print("Pressione a tecla de atalho correspondente para abrir o link desejado.")
        print("-" * 60)

        # Deduplicar telefones no início do processo
        from collections import defaultdict
        phone_groups = defaultdict(list)
        for r in to_review:
            raw_phone = r.get("maps_phone", "")
            norm_phone = clean_digits(raw_phone)
            if norm_phone:
                phone_groups[norm_phone].append(r)
                
        duplicate_groups = {phone: group for phone, group in phone_groups.items() if len(group) > 1}
        
        if duplicate_groups:
            print("\n" + "=" * 60)
            print(f" DETECTADOS {len(duplicate_groups)} GRUPOS DE TELEFONES DUPLICADOS")
            print("=" * 60)
            print("Você pode revisar cada grupo e escolher qual lead manter.")
            print("-" * 60)
            
            for phone, group in list(duplicate_groups.items()):
                # Filter rows to make sure they are still present in rows
                active_group = [r for r in group if r in rows]
                if len(active_group) <= 1:
                    continue
                
                display_phone = active_group[0].get("maps_phone", "").strip()
                
                print(f"\nTelefone Duplicado: {display_phone} ({len(active_group)} empresas)")
                print("-" * 40)
                for idx_g, r in enumerate(active_group, 1):
                    title = r.get("maps_title", "").strip() or "Sem nome"
                    category = r.get("maps_category", "").strip() or "Sem categoria"
                    city = r.get("maps_city", "").strip()
                    state = r.get("maps_state", "").strip()
                    website = r.get("maps_website", "").strip() or "Nenhum"
                    cnpj = r.get("cnpj_cnpj", "").strip()
                    nome_fantasia = r.get("cnpj_nome_fantasia", "").strip()
                    razao_social = r.get("cnpj_razao_social", "").strip()
                    
                    cnpj_info = ""
                    if cnpj:
                        cnpj_info = f" | CNPJ: {cnpj}"
                        if nome_fantasia:
                            cnpj_info += f" ({nome_fantasia})"
                        elif razao_social:
                            cnpj_info += f" ({razao_social})"
                            
                    print(f" [{idx_g}] {title}")
                    print(f"     Categoria: {category} | Cidade: {city}-{state}")
                    print(f"     Website:   {website}{cnpj_info}")
                
                print(f" [m] Manter todos (pular este grupo)")
                print(f" [n] Remover todos do grupo")
                
                while True:
                    try:
                        choice = input(f"\nEscolha uma opção (1-{len(active_group)}, m, n): ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        choice = 'm'
                    
                    if choice == 'm':
                        print("Mantendo todos do grupo.")
                        break
                    elif choice == 'n':
                        for r in active_group:
                            if r in rows:
                                rows.remove(r)
                        save_csv(output_path, fieldnames, rows, encoding, dialect)
                        print("Todos os leads do grupo foram removidos.")
                        break
                    else:
                        try:
                            keep_idx = int(choice) - 1
                            if 0 <= keep_idx < len(active_group):
                                keep_row = active_group[keep_idx]
                                for r in active_group:
                                    if r != keep_row and r in rows:
                                        rows.remove(r)
                                save_csv(output_path, fieldnames, rows, encoding, dialect)
                                print(f"Mantido apenas: {keep_row.get('maps_title')}")
                                break
                            else:
                                print(f"Opção inválida. Digite um número de 1 a {len(active_group)}, ou 'm'/'n'.")
                        except ValueError:
                            print("Opção inválida. Digite um número, 'm' ou 'n'.")
            
            to_review = rows
            print("\n--- Concluído o tratamento de telefones duplicados! ---")
            print(f"Total de leads restante na lista: {len(to_review)}")
            print("=" * 60)
        
        idx = 0
        auto_open = True
        while idx < len(to_review):
            row = to_review[idx]
            
            # Print lead information in an ordered way
            print_lead_info_remover(row, idx, len(to_review))
            
            # Show opening shortcuts
            website = row.get("maps_website", "").strip()
            instagram = row.get("maps_instagram", "").strip()
            facebook = row.get("maps_facebook", "").strip()
            
            open_options = []
            if website:
                open_options.append("[w] Website")
            if instagram:
                open_options.append("[i] Instagram")
            if facebook:
                open_options.append("[f] Facebook")
            open_options.append("[g] Pesquisar no Google")
            if website or instagram or facebook:
                open_options.append("[o] Abrir todos")
            print(f"Atalhos de abertura: {', '.join(open_options)}")
            
            if auto_open:
                urls = []
                if website:
                    urls.append(format_url(website))
                
                # Google Search URL
                query = row.get("maps_title", "").strip()
                if row.get("maps_city", "").strip():
                    query += f" {row.get('maps_city', '').strip()}"
                if row.get("maps_state", "").strip():
                    query += f" {row.get('maps_state', '').strip()}"
                search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                urls.append(search_url)
                
                open_urls(urls, chrome_bin)
                auto_open = False
                
            print("Opções: [Enter] Próximo | [b] Voltar | [d] Excluir | [u] Deslinkar CNPJ | [goto N] Ir para N | [exit] Sair")
            
            try:
                cmd = input("\nEscolha: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                cmd = 'exit'
                
            if cmd in ('exit', 'quit'):
                print("\nSaindo. Alterações salvas.")
                sys.exit(0)
                
            elif cmd.startswith('goto '):
                try:
                    target = int(cmd.split(' ')[1])
                    if 1 <= target <= len(to_review):
                        idx = target - 1
                        auto_open = True
                    else:
                        print(f"Erro: Valor deve ser entre 1 e {len(to_review)}.")
                except (ValueError, IndexError):
                    print("Uso: goto <numero>")
                continue
                
            elif cmd in ('b', 'prev', 'back', 'voltar'):
                if idx > 0:
                    idx -= 1
                    auto_open = True
                else:
                    print("Você já está no primeiro lead.")
                continue
                
            elif cmd in ('d', 'del', 'delete', 'remove', 'excluir'):
                confirm = input(f"Tem certeza que deseja excluir o lead '{row['maps_title']}'? (s/n): ").strip().lower()
                if confirm in ('s', 'y', 'sim', 'yes'):
                    rows.remove(row)
                    save_csv(output_path, fieldnames, rows, encoding, dialect)
                    print(f"Lead '{row['maps_title']}' excluído com sucesso.")
                    # Do not increment idx because the list shifted.
                    auto_open = True
                else:
                    print("Exclusão cancelada.")
                continue
                
            elif cmd == 'u':
                for k in list(row.keys()):
                    if k.startswith("cnpj_"):
                        row[k] = ""
                save_csv(output_path, fieldnames, rows, encoding, dialect)
                print("CNPJ desvinculado com sucesso!")
                idx += 1
                auto_open = True
                continue
                
            elif cmd == 'g':
                title = row.get("maps_title", "").strip()
                city = row.get("maps_city", "").strip()
                state = row.get("maps_state", "").strip()
                if title:
                    query = title
                    if city:
                        query += f" {city}"
                    if state:
                        query += f" {state}"
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                    open_urls([search_url], chrome_bin)
                else:
                    print("Lead sem nome para pesquisar.")
                continue

            elif cmd == 'w':
                if website:
                    open_urls([format_url(website)], chrome_bin)
                else:
                    print("Website não cadastrado para este lead.")
                continue
                
            elif cmd == 'i':
                if instagram:
                    open_urls([format_url(instagram)], chrome_bin)
                else:
                    print("Instagram não cadastrado para este lead.")
                continue
                
            elif cmd == 'f':
                if facebook:
                    open_urls([format_url(facebook)], chrome_bin)
                else:
                    print("Facebook não cadastrado para este lead.")
                continue
                
            elif cmd == 'o':
                urls = []
                if website: urls.append(format_url(website))
                if instagram: urls.append(format_url(instagram))
                if facebook: urls.append(format_url(facebook))
                if urls:
                    open_urls(urls, chrome_bin)
                else:
                    print("Nenhum link disponível para abrir.")
                continue
                
            elif cmd == '':
                idx += 1
                auto_open = True
                continue
                
            else:
                print("Opção inválida. Digite um comando válido ou pressione Enter para avançar.")
                continue
                
        print("\nTodos os leads foram analisados/removidos!")
        print(f"---------------------------------\n")
        return output_path

    # Find the first unreviewed lead
    idx = 0
    found_unreviewed = False
    for i, r in enumerate(to_review):
        if r.get("review_status", "").strip() != "Finalizado":
            idx = i
            found_unreviewed = True
            break
            
    if not found_unreviewed and len(to_review) > 0:
        print("\nTodos os leads desta planilha já foram revisados/finalizados!")
        try:
            usr_choice = input("Deseja iniciar do primeiro lead novamente? (s/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            usr_choice = 'n'
        if usr_choice == 's':
            idx = 0
        else:
            print("Saindo do programa.")
            return output_path
    elif idx > 0:
        print(f"\nRetomando progresso: iniciando do lead {idx + 1} de {len(to_review)} (já finalizados: {idx} leads).")

    while idx < len(to_review):
        row = to_review[idx]
        title = row["maps_title"]
        city = row.get("maps_city", "")
        state = row.get("maps_state", "")
        website = row.get("maps_website", "").strip()
        instagram = row.get("maps_instagram", "").strip()
        facebook = row.get("maps_facebook", "").strip()
        
        print(f"\n[{idx+1}/{len(to_review)}] {title} ({city}-{state})")
        if website:
            print(f"Website: {format_url(website)}")
        if instagram:
            print(f"Instagram: {format_url(instagram)}")
        if facebook:
            print(f"Facebook: {format_url(facebook)}")
            
        current_score = row.get("review_score", "").strip()
        if current_score:
            print(f"Nota de Qualificação Atual: {current_score}")
            
        # 1. Interactive CNPJ override if missing (Commented out temporarily)
        # cnpj_val = row.get("cnpj_cnpj", "").strip()
        # if not cnpj_val:
        #     print(f"\n>>> CNPJ EM FALTA para '{title}'.")
        #     print("Abrindo navegador com busca no Google para encontrar o CNPJ...")
        #     
        #     search_query = f"{title} {city} {state} cnpj"
        #     search_url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}"
        #     open_urls([search_url], chrome_bin)
        #     
        #     while True:
        #         cnpj_input = input(f"Digite o CNPJ da empresa '{title}' (ou Enter para pular, exit para sair): ").strip()
        #         if not cnpj_input:
        #             print("CNPJ pulado.")
        #             break
        #         if cnpj_input.lower() in ('exit', 'quit'):
        #             print("\nExiting script. Progress saved.")
        #             sys.exit(0)
        #             
        #         digits = clean_digits(cnpj_input)
        #         if len(digits) == 14:
        #             match = lookup_single_cnpj(digits)
        #             if match:
        #                 est = match["est"]
        #                 comp = match["comp"]
        #                 partners = match["partners"]
        #                 simples_info = match["simples"]
        #                 
        #                 row["cnpj_cnpj"] = format_cnpj(digits)
        #                 row["cnpj_razao_social"] = to_title_case(comp.get("razao_social", ""))
        #                 row["cnpj_nome_fantasia"] = to_title_case(est.get("nome_fantasia", ""))
        #                 row["cnpj_situacao_cadastral"] = "Ativa"
        #                 
        #                 ini_date = est.get("data_inicio_atividade", "")
        #                 if len(ini_date) == 8:
        #                     row["cnpj_data_inicio_atividade"] = f"{ini_date[:4]}-{ini_date[4:6]}-{ini_date[6:]}"
        #                 else:
        #                     row["cnpj_data_inicio_atividade"] = ini_date
        #                     
        #                 row["cnpj_cnae_fiscal_principal"] = est.get("cnae_principal", "")
        #                 cnae_desc = match.get("cnaes", {}).get(est.get("cnae_principal", ""), "")
        #                 row["cnpj_cnae_descricao"] = to_title_case(cnae_desc)
        #                 
        #                 row["cnpj_capital_social"] = comp.get("capital_social", "0.0")
        #                 row["cnpj_opcao_pelo_simples"] = simples_info.get("opcao_simples", "N")
        #                 row["cnpj_opcao_pelo_mei"] = simples_info.get("opcao_mei", "N")
        #                 partner_descriptions = []
        #                 for p in partners:
        #                     p_name = to_title_case(p.get("nome", ""))
        #                     q_desc = match.get("qualifications", {}).get(p.get("qual_code", ""), "")
        #                     if q_desc:
        #                         partner_descriptions.append(f"{p_name} ({to_title_case(q_desc)})")
        #                     else:
        #                         partner_descriptions.append(p_name)
        #                 row["cnpj_socios"] = ", ".join(partner_descriptions)
        #                 row["cnpj_quantidade_socios"] = len(partners)
        #                 row["cnpj_idade_empresa_anos"] = calculate_age_years(ini_date)
        #                 row["cnpj_telefone"] = format_phone(est.get("ddd_1", ""), est.get("telefone_1", ""))
        #                 row["cnpj_email"] = est.get("email", "").lower()
        #                 row["cnpj_endereco"] = format_address(est, city)
        #                 
        #                 print(f"CNPJ preenchido com sucesso: {row['cnpj_razao_social']}")
        #                 break
        #             else:
        #                 print("Erro: CNPJ não localizado nos arquivos compactados.")
        #         else:
        #             print("Erro: Digite exatamente 14 números.")


        # Open presence links for user inspection
        urls_to_open = []
        if website:
            urls_to_open.append(format_url(website))
        if instagram:
            urls_to_open.append(format_url(instagram))
        if facebook:
            urls_to_open.append(format_url(facebook))
            
        # If no presence links exist, fallback to search query on Google
        if not website and not instagram and not facebook:
            search_query = f"{title} {city} {state}"
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}"
            urls_to_open.append(search_url)
            
        if urls_to_open:
            if not website and not instagram and not facebook:
                print("Nenhum link encontrado (Site/Instagram/Facebook). Abrindo busca no Google...")
            else:
                print("Abrindo links de presença no navegador...")
            open_urls(urls_to_open, chrome_bin)

        jumped = False
        while True:
            print("\nMenu:")
            print("  <Enter>         -> Responder as 6 perguntas de presença digital")
            print("  edit            -> Editar/adicionar meios de contato (site, instagram, telefone, email)")
            print("  skip            -> Pular este lead (sem qualificar por enquanto)")
            print("  goto <numero>   -> Pular para outro lead da lista")
            print("  remove / del    -> Remover este lead da planilha completamente")
            print("  unlink / u      -> Desvincular/deslinkar CNPJ deste lead")
            print("  open            -> Reabrir links no navegador")
            print("  exit / quit     -> Salvar e Sair")
            
            try:
                cmd = input("\nEscolha: ").strip()
            except (EOFError, KeyboardInterrupt):
                cmd = 'exit'
                
            if cmd.lower() in ('exit', 'quit'):
                print("\nSaindo. Progresso salvo.")
                sys.exit(0)
                
            elif cmd.lower().startswith('goto '):
                try:
                    target = int(cmd.split(' ')[1])
                    if 1 <= target <= len(to_review):
                        idx = target - 1
                        jumped = True
                        break
                    else:
                        print(f"Erro: Valor deve ser entre 1 e {len(to_review)}.")
                except (ValueError, IndexError):
                    print("Uso: goto <numero>")
                continue
                
            elif cmd.lower() in ('remove', 'del', 'delete'):
                if row in rows:
                    rows.remove(row)
                save_csv(output_path, fieldnames, rows, encoding, dialect)
                print(f"Lead '{title}' removido da planilha.")
                jumped = True
                break
                
            elif cmd.lower() in ('unlink', 'deslinkar', 'desvincular', 'u'):
                for k in list(row.keys()):
                    if k.startswith("cnpj_"):
                        row[k] = ""
                save_csv(output_path, fieldnames, rows, encoding, dialect)
                print("CNPJ desvinculado com sucesso!")
                continue
                
            elif cmd.lower() in ('edit', 'contato'):
                print("\n--- Editar Meios de Contato (Pressione Enter para manter, '-' para limpar) ---")
                
                web_in = input(f"Website [{row.get('maps_website', '')}]: ").strip()
                if web_in == '-':
                    row["maps_website"] = ""
                elif web_in:
                    row["maps_website"] = web_in
                    
                insta_in = input(f"Instagram [{row.get('maps_instagram', '')}]: ").strip()
                if insta_in == '-':
                    row["maps_instagram"] = ""
                elif insta_in:
                    row["maps_instagram"] = insta_in
                    
                phone_in = input(f"Telefone [{row.get('maps_phone', '')}]: ").strip()
                if phone_in == '-':
                    row["maps_phone"] = ""
                elif phone_in:
                    row["maps_phone"] = phone_in
                    
                email_in = input(f"E-mail [{row.get('maps_emails', '')}]: ").strip()
                if email_in == '-':
                    row["maps_emails"] = ""
                elif email_in:
                    row["maps_emails"] = email_in
                    
                save_csv(output_path, fieldnames, rows, encoding, dialect)
                print("Contato atualizado com sucesso!")
                
                # Reload variables for the current loop
                website = row.get("maps_website", "").strip()
                instagram = row.get("maps_instagram", "").strip()
                facebook = row.get("maps_facebook", "").strip()
                
                # Rebuild urls_to_open
                urls_to_open = []
                if website:
                    urls_to_open.append(format_url(website))
                if instagram:
                    urls_to_open.append(format_url(instagram))
                if facebook:
                    urls_to_open.append(format_url(facebook))
                if not website and not instagram and not facebook:
                    search_query = f"{title} {city} {state}"
                    search_url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}"
                    urls_to_open.append(search_url)
                
                print("\nDados atualizados:")
                if website:
                    print(f"  Website: {format_url(website)}")
                if instagram:
                    print(f"  Instagram: {format_url(instagram)}")
                if row.get("maps_phone", ""):
                    print(f"  Telefone: {row.get('maps_phone', '')}")
                if row.get("maps_emails", ""):
                    print(f"  E-mail: {row.get('maps_emails', '')}")
                continue
                
            elif cmd.lower() == 'open':
                open_urls(urls_to_open, chrome_bin)
                continue
                
            elif cmd.lower() == 'skip':
                print(f"Lead '{title}' pulado.")
                break
                
            elif cmd == '':
                try:
                    # Run the presence questions
                    print("\n--- Questionário de Presença Digital ---")
                    default_q1 = 's' if row.get("maps_website", "").strip() else 'n'
                    q1 = prompt_question("1. Tem um site profissional? (s/n): ", ['s', 'n'], default=default_q1)
                    
                    if q1 == 'n':
                        q2 = 'na'
                    else:
                        q2 = prompt_question("2. O site é responsivo e adaptado para celular? (s/n/na): ", ['s', 'n', 'na'], default='s')
                        
                    insta_url = row.get("maps_instagram", "").strip()
                    q3 = ""
                    if insta_url:
                        while True:
                            val = input("3. Semanas desde o último post no Instagram (ou Enter para pular): ").strip().lower()
                            if val in ('back', 'voltar', 'menu'):
                                raise GoBackException()
                            if val in ('exit', 'quit'):
                                print("\nExiting script. Progress saved.")
                                sys.exit(0)
                            if not val:
                                q3 = ""
                                break
                            try:
                                weeks = float(val)
                                if weeks >= 0:
                                    q3 = str(weeks)
                                    break
                                else:
                                    print("Por favor, digite um número maior ou igual a zero.")
                            except ValueError:
                                print("Por favor, digite um número válido (ou Enter para pular).")
                    else:
                        q3 = "na"
                        
                    q4 = prompt_question("4. Possui link/botão para WhatsApp visível/fácil? (s/n): ", ['s', 'n'], default='s')
                    q5 = prompt_question("5. A presença digital atual (GMN, redes, site) parece desatualizada ou amadora? (s/n): ", ['s', 'n'], default='n')
                    
                    if insta_url:
                        q6 = prompt_question("6. Qual a qualidade do Instagram? (b - bom / r - regular / u - ruim / na - n/a): ", ['b', 'r', 'u', 'na'], default='r')
                    else:
                        q6 = 'na'
                    
                    # Save answers
                    row["review_q1_site"] = q1
                    row["review_q2_responsivo"] = q2
                    row["review_q3_instagram"] = q3
                    row["review_q4_whatsapp"] = q4
                    row["review_q5_amador"] = q5
                    row["review_q6_insta_qualidade"] = q6
                    
                    # Score Calculation
                    score1, max1, details1 = score_area1_maps(row)
                    score2, max2, details2 = score_area2_review(row)
                    score3, max3, details3 = score_area3_cnpj(row)
                    recommended_score = score1 + score2 + score3
                    
                    # Generate markdown table
                    md_table = generate_markdown_table(score1, max1, details1, score2, max2, details2, score3, max3, details3)
                    # Generate JSON table
                    json_table = generate_review_score_json(score1, max1, details1, score2, max2, details2, score3, max3, details3)
                    row["review_score_table"] = json_table
                    
                    print(f"\nNota Recomendada de Qualificação: {recommended_score} / 120 pontos")
                    print("\nTabela de Fatores Considerados:")
                    print(md_table)
                    print()
                    
                    while True:
                        usr_score = input(f"Digite a nota final inteira (0 - 120) [Enter para confirmar {recommended_score}]: ").strip()
                        if not usr_score:
                            row["review_score"] = str(recommended_score)
                            break
                        try:
                            val = int(usr_score)
                            if 0 <= val <= 120:
                                row["review_score"] = str(val)
                                break
                            else:
                                print("Nota deve ser entre 0 e 120.")
                        except ValueError:
                            if usr_score.lower() in ('exit', 'quit'):
                                print("\nExiting script. Progress saved.")
                                sys.exit(0)
                            print("Valor inválido. Digite um número inteiro de 0 a 120.")
                    
                    print(f"Nota {row['review_score']} salva para '{title}'.")
                    row["review_status"] = "Finalizado"
                    break
                except GoBackException:
                    print("\nVoltando ao menu de comandos individuais...")
                    continue
                
        if jumped:
            continue
            
        save_csv(output_path, fieldnames, rows, encoding, dialect)
        idx += 1
        
    print("\nTodos os leads foram revisados!")
    print(f"---------------------------------\n")
    return output_path
