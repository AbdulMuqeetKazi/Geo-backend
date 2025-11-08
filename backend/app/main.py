import logging
from fastapi import FastAPI, HTTPException
from app.parser import AddressParser
from app.validator import GeoValidator
from app.normalizer import normalize_address

logger = logging.getLogger(__name__)

app = FastAPI(title="GeoFixers Address Parser + Validator")

parser = AddressParser()
validator = GeoValidator()

@app.get("/")
def home():
    return {"message": "GeoFixers API is running 🚀"}

@app.post("/normalize")
async def normalize_raw_address(payload: dict):
    try:
        raw = payload.get("raw")
        if not raw:
            raise HTTPException(status_code=400, detail="Missing 'raw' field")
        if not isinstance(raw, str):
            raise HTTPException(status_code=400, detail="'raw' field must be a string")

        normalized = await normalize_address(raw)
        if not normalized:
            raise HTTPException(status_code=422, detail="Could not normalize the address")
            
        return {
            "success": True,
            "raw": raw,
            "normalized": normalized
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Normalization error")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during normalization: {str(e)}"
        )

@app.post("/parse")
def parse_address(payload: dict):
    try:
        raw = payload.get("raw")
        if not raw:
            raise HTTPException(status_code=400, detail="Missing 'raw' field")
        parsed = parser.parse(raw)
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/validate")
async def validate_address(payload: dict):
    try:
        raw = payload.get("raw")
        if not raw:
            raise HTTPException(status_code=400, detail="Missing 'raw' field")

        # Optional normalization step if requested
        use_normalizer = payload.get("normalize", False)
        normalized_address = None
        address_to_parse = raw

        if use_normalizer:
            normalized_address = await normalize_address(raw)
            if normalized_address:
                address_to_parse = normalized_address

        parsed = parser.parse(address_to_parse)
        result = await validator.validate(parsed)
        return {
            "raw": raw,
            "normalized": normalized_address,
            "parsed": parsed,
            "validation": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
