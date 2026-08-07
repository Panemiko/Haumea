#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

def clean_title(title: str) -> str:
    if not title:
        return ""
    
    # Normalize spaces around separators
    cleaned = re.sub(r'\s*([-\|–:])\s*', r' \1 ', title)
    
    # Split by standard separators
    parts = [p.strip() for p in re.split(r'\s+[-\|–:]\s+', cleaned)]
    
    # Common description words in Portuguese
    desc_words = {
        "nutricionista", "nutri", "emagrecimento", "performance", "esportiva", "longevidade",
        "clínica", "clinica", "consultório", "consultorio", "bariátrica", "bariatrica",
        "estética", "estetica", "fonoaudióloga", "fonoaudiologa", "saúde", "saude", 
        "lajeado", "rs", "vale do taquari", "ayurveda", "estúdio", "studio"
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
        r'^\s*clínica\s+de\s+',
        r'^\s*clinica\s+de\s+',
        r'^\s*nutricionista\s+',
        r'^\s*nutri\s+',
        r'^\s*dra?\.\s+',
        r'^\s*fonoaudióloga\s+',
        r'^\s*fonoaudiologa\s+'
    ]
    
    cleaned_result = candidate
    for prefix in prefixes:
        cleaned_result = re.sub(prefix, '', cleaned_result, flags=re.IGNORECASE).strip()
        
    # Suffixes
    suffixes = [
        r'\s+nutricionista\s*$',
        r'\s+nutri\s*$',
        r'\s+estética\s*$',
        r'\s+estetica\s*$',
        r'\s+lajeado\s*$',
        r'\s+rs\s*$'
    ]
    for suffix in suffixes:
        cleaned_result = re.sub(suffix, '', cleaned_result, flags=re.IGNORECASE).strip()
        
    # Remove LTDA and variations
    cleaned_result = re.sub(r'\bLTDA\b\.?', '', cleaned_result, flags=re.IGNORECASE)
    
    # Normalize spaces
    cleaned_result = re.sub(r'\s+', ' ', cleaned_result).strip()
    return cleaned_result

def clean_file(file_path: Path):
    if not file_path.exists():
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Reading file: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}", file=sys.stderr)
        sys.exit(1)
        
    if not isinstance(data, list):
        print("Error: Expected a JSON array of items.", file=sys.stderr)
        sys.exit(1)
        
    changed_count = 0
    for idx, item in enumerate(data):
        old_title = item.get("maps_title", "")
        if old_title:
            new_title = clean_title(old_title)
            if new_title != old_title:
                item["maps_title"] = new_title
                changed_count += 1
                if changed_count <= 5:
                    print(f"Cleaned #{idx+1}: '{old_title}' -> '{new_title}'")
                    
    if changed_count > 5:
        print(f"... and {changed_count - 5} more items.")
        
    print(f"Total items processed: {len(data)}")
    print(f"Total items cleaned: {changed_count}")
    
    if changed_count > 0:
        backup_path = file_path.with_name(f"{file_path.stem}_backup{file_path.suffix}")
        print(f"Saving backup to: {backup_path}")
        try:
            # Overwrite original
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("Successfully updated file in-place!")
        except Exception as e:
            print(f"Error saving updated file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("No titles needed cleaning.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/clean_titles.py <path_to_json_file>")
        sys.exit(1)
    clean_file(Path(sys.argv[1]))
