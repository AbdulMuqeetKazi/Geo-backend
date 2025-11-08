import os
import logging
import qrcode
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from openlocationcode import openlocationcode as olc
from app.config import DATABASE_URL, QR_DIR

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
logger = logging.getLogger("app.validator")
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# Database setup
# -----------------------------------------------------------------------------
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set in environment")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# -----------------------------------------------------------------------------
# QR directory setup
# -----------------------------------------------------------------------------
if not os.path.exists(QR_DIR):
    os.makedirs(QR_DIR)


class GeoValidator:
    """GeoValidator: Validates parsed addresses, adds geospatial context, plus code & QR."""

    def __init__(self):
        logger.info("✅ GeoValidator initialized with Supabase/PostGIS connection")

    # -------------------------------------------------------------------------
    async def _get_pincode_info(self, pincode: str, session: AsyncSession):
        """Fetch pincode details from pincode_directory."""
        if not pincode:
            return None

        try:
            query = text("""
                SELECT pincode, district, statename, latitude, longitude
                FROM pincode_directory
                WHERE pincode = :pin
                LIMIT 1
            """)
            res = await session.execute(query, {"pin": pincode})
            row = res.fetchone()
            if row:
                logger.info(f"✅ Found pincode {pincode} in database")
                return {
                    "pincode": row[0],
                    "district": row[1],
                    "state": row[2],
                    "latitude": float(row[3]) if row[3] else None,
                    "longitude": float(row[4]) if row[4] else None,
                }
        except Exception as e:
            logger.error(f"❌ Pincode lookup failed: {e}")
        return None

    # -------------------------------------------------------------------------
    async def _find_ward_from_coords_db(self, lat: float, lon: float, session: AsyncSession):
        """Find ward name from merged_wards table using fuzzy spatial match."""
        try:
            query = text("""
                SELECT id, "KGISWardNa"
                FROM merged_wards
                WHERE ST_DWithin(
                    ST_Transform(geom, 4326)::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    200
                )
                LIMIT 1
            """)
            res = await session.execute(query, {"lon": lon, "lat": lat})
            row = res.fetchone()
            if not row:
                logger.warning("⚠ No ward found near given coordinates")
                return None
            logger.info(f"✅ Found ward: {row[1]}")
            return {"id": str(row[0]), "ward_name": str(row[1])}
        except Exception as e:
            logger.error(f"❌ Ward lookup failed: {e}")
            return None

    # -------------------------------------------------------------------------
    async def _find_town_or_village_fallback(self, lat: float, lon: float, session: AsyncSession):
        """If ward not found, fallback to nearby town or village."""
        tables = [
            ("merged_towns", '"KGISTownNa"', "town"),
            ("merged_villages", '"KGISVillag"', "village"),
        ]

        for table, field, label in tables:
            try:
                query = text(f"""
                    SELECT id, {field}
                    FROM {table}
                    WHERE ST_DWithin(
                        ST_Transform(geom, 4326)::geography,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        200
                    )
                    LIMIT 1
                """)
                res = await session.execute(query, {"lon": lon, "lat": lat})
                row = res.fetchone()
                if row:
                    logger.info(f"✅ Found nearby {label}: {row[1]}")
                    return {"type": label, "id": str(row[0]), "name": str(row[1])}
            except Exception as e:
                logger.error(f"❌ {label.title()} lookup failed: {e}")
        logger.warning("⚠ No nearby town/village found within 200m")
        return None

    # -------------------------------------------------------------------------
    def _generate_plus_code(self, lat: float, lon: float):
        """Generate Plus Code (Open Location Code)."""
        try:
            plus_code = olc.encode(lat, lon)
            logger.info(f"🌍 Generated Plus Code: {plus_code}")
            return plus_code
        except Exception as e:
            logger.error(f"❌ Plus Code generation failed: {e}")
            return None

    # -------------------------------------------------------------------------
    def _generate_qr_code(self, data: str, filename_prefix: str = "location"):
        """Generate a QR code for the given data."""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            filename = os.path.join(QR_DIR, f"{filename_prefix}_qr.png")
            img.save(filename)
            logger.info(f"🖼 QR Code saved to {filename}")
            return filename
        except Exception as e:
            logger.error(f"❌ QR code generation failed: {e}")
            return None

    # -------------------------------------------------------------------------
    async def validate(self, parsed_data: dict):
        """Validate parsed address and return enriched geographic data."""
        async with AsyncSessionLocal() as session:
            pincode = parsed_data.get("pincode")
            lat = parsed_data.get("lat")
            lon = parsed_data.get("lon")

            result = {
                "is_valid": False,
                "matched_pincode": None,
                "matched_ward": None,
                "matched_region": None,
                "plus_code": None,
                "qr_path": None,
                "message": "",
            }

            # Step 1: Validate pincode
            pin_info = await self._get_pincode_info(pincode, session)
            if not pin_info:
                result["message"] = f"Pincode {pincode} not found ❌"
                return result

            result["matched_pincode"] = pin_info
            lat = lat or pin_info.get("latitude")
            lon = lon or pin_info.get("longitude")

            # 🧭 Step 1.5: Fallback geocoding if coordinates are missing
            if not lat or not lon:
                try:
                    from app.utils.geocode_fallback import geocode_fallback
                    logger.info("🌍 Coordinates missing, using geocoding fallback...")
                    geo_result = await geocode_fallback(
                        parsed_data.get("normalized_address") or parsed_data.get("raw")
                    )
                    if geo_result:
                        lat, lon = geo_result["lat"], geo_result["lon"]
                        result["geo_source"] = geo_result["source"]
                        logger.info(f"✅ Coordinates fetched via {geo_result['source']}: {lat}, {lon}")
                    else:
                        logger.warning("⚠️ No coordinates found even after fallback")
                except Exception as e:
                    logger.error(f"❌ Fallback geocoding failed: {e}")

            # Step 2: Try to match ward or fallback region
            ward_info = None
            if lat and lon:
                ward_info = await self._find_ward_from_coords_db(lat, lon, session)

            if not ward_info and lat and lon:
                region_info = await self._find_town_or_village_fallback(lat, lon, session)
                if region_info:
                    result["matched_region"] = region_info

            # Step 3: Plus Code + QR generation
            if lat and lon:
                plus_code = self._generate_plus_code(lat, lon)
                result["plus_code"] = plus_code
                if plus_code:
                    qr_file = self._generate_qr_code(plus_code, f"loc_{pincode}")
                    result["qr_path"] = qr_file

            # Step 4: Build final result
            if ward_info or result["matched_region"] or result["plus_code"]:
                result["is_valid"] = True
                result["matched_ward"] = ward_info
                result["message"] = "Validation successful ✅"
            else:
                result["message"] = "Could not find matching region ❌"

            return result