import re
import unicodedata
from datetime import datetime
from typing import Optional

def normalize_name(name: Optional[str]) -> str:
    """
    Normalizes names according to PRD duplicate prevention rules:
    - Converting to lowercase
    - Removing leading and trailing spaces
    - Treating repeated spaces as a single space
    - Applying consistent Unicode NFKD normalization (stripping accents/diacritics)
    """
    if not name:
        return ""
    # Unicode NFKD normalization and remove combining diacritic marks
    decomposed = unicodedata.normalize('NFKD', str(name))
    stripped_accents = ''.join(c for c in decomposed if not unicodedata.combining(c))
    # Convert to lowercase
    norm = stripped_accents.lower()
    # Replace repeated spaces with single space and strip edges
    norm = re.sub(r'\s+', ' ', norm).strip()
    return norm

def generate_unique_student_id(cursor, year: int = None) -> str:
    """
    Generates a safe sequential unique student ID, e.g. STU-2026-000001
    """
    if not year:
        year = datetime.now().year
    prefix = f"STU-{year}-"
    
    # Query highest sequential ID for current prefix
    cursor.execute("""
        SELECT user_id FROM users 
        WHERE user_id LIKE ? 
        ORDER BY LENGTH(user_id) DESC, user_id DESC 
        LIMIT 50
    """, (f"{prefix}%",))
    rows = cursor.fetchall()
    
    max_num = 0
    for r in rows:
        uid = r["user_id"] if hasattr(r, "__getitem__") else r[0]
        if uid.startswith(prefix):
            suffix = uid[len(prefix):]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
                
    next_num = max_num + 1
    return f"{prefix}{next_num:06d}"

def extract_youtube_id(url_or_id: str) -> Optional[str]:
    """
    Extracts the 11-character YouTube video ID from various URL formats or returns the ID directly.
    """
    if not url_or_id:
        return None
    url_or_id = url_or_id.strip()
    
    # If it's already an 11-character alphanumeric/hyphen/underscore string
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
        
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
            
    return None
