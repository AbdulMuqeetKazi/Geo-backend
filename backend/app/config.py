# app/config.py
import os
from dotenv import load_dotenv

# Find project root (where .env is located)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Load .env explicitly from root directory
if os.path.exists(ENV_PATH):
    load_dotenv(dotenv_path=ENV_PATH)
else:
    print(f"⚠️ .env file not found at: {ENV_PATH}")

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
QR_DIR = os.getenv("QR_DIR", "qr_codes")
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "shiprocket-ai/open-tinybert-indian-address-ner")

REFERENCE_STATES = ["Karnataka"]
REFERENCE_DISTRICTS = ["Belagavi", "Mysuru", "Dharwad", "Davangere", "Hubballi", "Kalaghatagi"]

# Debug print
if not DATABASE_URL:
    print("❌ DATABASE_URL not loaded. Check .env path or syntax.")
else:
    print("✅ DATABASE_URL successfully loaded from .env")
