import re

def sanitize_filename(name: str) -> str:
    """Sanitizes a string to make it safe for filenames."""
    sanitized = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized.strip('_')
