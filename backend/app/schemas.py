# app/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class RawAddressIn(BaseModel):
    raw: str = Field(..., example="opp bus depot, ward 3 gokak taluk, belgaum karnatka 591307")

class ParsedAddress(BaseModel):
    pincode: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    taluk: Optional[str] = None
    town: Optional[str] = None
    village: Optional[str] = None
    ward: Optional[str] = None
    landmarks: Optional[List[str]] = None
    normalized_address: Optional[str] = None
    raw: Optional[str] = None

class ValidationResponse(BaseModel):
    is_valid: bool
    confidence: float
    matched_levels: List[str] = []
    plus_code: Optional[str] = None
    qr_path: Optional[str] = None
    errors: List[str] = []
    details: Optional[Dict[str, Any]] = None
