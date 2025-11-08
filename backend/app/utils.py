# app/utils.py
import os
import qrcode
from openlocationcode import openlocationcode as olc
from app.config import QR_DIR
import logging

logger = logging.getLogger(__name__)

os.makedirs(QR_DIR, exist_ok=True)

def generate_plus_code(lat: float, lon: float, code_len: int = 10) -> str:
    return olc.encode(lat, lon, codeLength=code_len)

def generate_qr(plus_code: str, url_template: str = "https://plus.codes/{code}") -> str:
    url = url_template.format(code=plus_code)
    filename = f"{plus_code.replace('+','_')}.png"
    path = os.path.join(QR_DIR, filename)
    img = qrcode.make(url)
    img.save(path)
    logger.info("Saved QR to %s", path)
    return path
