import os
import logging
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.config import DATABASE_URL

# -------------------------------------------------------------------
# Logging setup
# -------------------------------------------------------------------
logger = logging.getLogger("app.normalizer")
logging.basicConfig(level=logging.INFO)

# -------------------------------------------------------------------
# Model Configuration
# -------------------------------------------------------------------
MODEL_NAME = "microsoft/Phi-3-mini-4k-instruct"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"🧠 Using model: {MODEL_NAME} on {DEVICE}")

# -------------------------------------------------------------------
# Database setup
# -------------------------------------------------------------------
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment.")
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Create normalized_cache table if it doesn't exist
async def _init_db():
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS normalized_cache (
                    raw_address TEXT PRIMARY KEY,
                    normalized_address TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            await session.commit()
            logger.info("✅ Normalized cache table ready")
        except Exception as e:
            logger.error(f"❌ Could not initialize cache table: {e}")

# Initialize the database table
import asyncio
try:
    asyncio.create_task(_init_db())
except Exception as e:
    logger.error(f"❌ Could not schedule table initialization: {e}")

# -------------------------------------------------------------------
# Load model
# -------------------------------------------------------------------
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, trust_remote_code=True)
    normalizer_pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device=0 if DEVICE == "cuda" else -1
    )
    logger.info("✅ Address Normalizer Model loaded successfully.")
except Exception as e:
    logger.error(f"❌ Model load failed: {e}")
    normalizer_pipe = None


# -------------------------------------------------------------------
# DB Cache: Fetch normalized result if exists
# -------------------------------------------------------------------
async def _get_cached_normalized_address(raw_text: str) -> str | None:
    async with AsyncSessionLocal() as session:
        query = text("SELECT normalized_address FROM normalized_cache WHERE raw_address = :addr LIMIT 1")
        res = await session.execute(query, {"addr": raw_text.strip().lower()})
        row = res.fetchone()
        return row[0] if row else None


# -------------------------------------------------------------------
# DB Cache: Store normalized result
# -------------------------------------------------------------------
async def _cache_normalized_address(raw_text: str, normalized: str):
    async with AsyncSessionLocal() as session:
        try:
            query = text("""
                INSERT INTO normalized_cache (raw_address, normalized_address)
                VALUES (:raw, :norm)
                ON CONFLICT (raw_address) DO NOTHING
            """)
            await session.execute(query, {"raw": raw_text.strip().lower(), "norm": normalized})
            await session.commit()
            logger.info("🧠 Cached normalized address to DB.")
        except Exception as e:
            logger.warning(f"⚠️ Could not cache address: {e}")


# -------------------------------------------------------------------
# Main Function
# -------------------------------------------------------------------
async def normalize_address(raw_text: str) -> str:
    """
    Normalize an Indian address using Phi-3-mini LLM.
    - Step 1: Check DB cache
    - Step 2: Generate with LLM if not cached
    - Step 3: Store in cache
    """
    if not raw_text:
        return raw_text

    # 1️⃣ Try DB cache
    cached = await _get_cached_normalized_address(raw_text)
    if cached:
        logger.info(f"⚡ Cache hit for address: {raw_text}")
        return cached

    # 2️⃣ Run LLM normalization
    if not normalizer_pipe:
        logger.warning("⚠️ Normalizer not loaded. Returning raw.")
        return raw_text

    prompt = f"""
    You are an expert Indian postal address normalizer.
    Format the following address into a proper postal standard:
    Input: {raw_text}
    Output:
    """

    try:
        outputs = normalizer_pipe(prompt, max_new_tokens=80, temperature=0.4, top_p=0.9, do_sample=True)
        text_out = outputs[0]["generated_text"]
        normalized = text_out.split("Output:")[-1].strip() if "Output:" in text_out else text_out.strip()

        logger.info(f"✅ Generated normalized address: {normalized}")

        # 3️⃣ Save to DB cache
        await _cache_normalized_address(raw_text, normalized)

        return normalized

    except Exception as e:
        logger.error(f"❌ Normalization failed: {e}")
        return raw_text