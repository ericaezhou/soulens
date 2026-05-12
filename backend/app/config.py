import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
INSTAGRAM_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
PROFILES_DIR = Path(os.getenv("PROFILES_DIR", "data/profiles"))
PHASE1_CACHE_DIR = Path(os.getenv("PHASE1_CACHE_DIR", "cache/phase1"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
PHASE1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
