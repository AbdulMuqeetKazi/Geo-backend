# app/utils/geocode_fallback.py
import os
import httpx
import logging
from typing import Optional, Dict, Any

# Setup logging
logger = logging.getLogger("app.geocode_fallback")
logging.basicConfig(level=logging.INFO)

# API URLs
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GOOGLE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Optional API key for Google fallback
GOOGLE_API_KEY = os.getenv("GOOGLE_GEOCODING_API_KEY")
USER_AGENT = "GeoFixer/1.0 (contact@geofixer.ai)"


async def geocode_fallback(address: str) -> Optional[Dict[str, Any]]:
    """
    Try to geocode an address using Nominatim first, then Google as fallback.
    Returns {lat, lon, source} or None if failed.
    """
    if not address:
        return None

    # 1️⃣ Try Nominatim (OpenStreetMap)
    params = {
        "q": address,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        "countrycodes": "in"
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(NOMINATIM_URL, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            if data:
                result = data[0]
                lat, lon = float(result.get("lat")), float(result.get("lon"))
                logger.info(f"✅ Nominatim geocode success: {lat}, {lon}")
                return {"lat": lat, "lon": lon, "source": "nominatim"}
    except Exception as e:
        logger.warning(f"⚠️ Nominatim geocode failed: {e}")

    # 2️⃣ Try Google Geocoding API (optional fallback)
    if GOOGLE_API_KEY:
        try:
            params = {"address": address, "key": GOOGLE_API_KEY}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(GOOGLE_URL, params=params)
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "OK":
                    location = data["results"][0]["geometry"]["location"]
                    lat, lon = location["lat"], location["lng"]
                    logger.info(f"✅ Google geocode success: {lat}, {lon}")
                    return {"lat": lat, "lon": lon, "source": "google"}
        except Exception as e:
            logger.warning(f"⚠️ Google geocode failed: {e}")

    logger.error("❌ Geocoding fallback failed for address")
    return None