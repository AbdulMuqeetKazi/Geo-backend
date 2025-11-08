import re
from transformers import AutoTokenizer, AutoModelForTokenClassification
from transformers import pipeline
from rapidfuzz import fuzz
from app.config import REFERENCE_STATES, REFERENCE_DISTRICTS

class AddressParser:
    """
    Intelligent parser for messy Indian addresses.
    Combines IndianAddressNER + rule-based corrections.
    """

    def __init__(self):
        model_name = "shiprocket-ai/open-tinybert-indian-address-ner"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForTokenClassification.from_pretrained(model_name)
        self.nlp = pipeline("token-classification", model=self.model, tokenizer=self.tokenizer, aggregation_strategy="simple")

    def parse(self, raw_address: str):
        raw = raw_address.strip().replace("\n", " ")
        tokens = self.nlp(raw)

        parsed = {
            "pincode": "",
            "state": "",
            "district": "",
            "taluk": "",
            "town": "",
            "village": "",
            "ward": "",
            "landmarks": [],
            "normalized_address": "",
            "raw": raw,
        }

        for t in tokens:
            label = t["entity_group"].upper()
            word = t["word"].strip().replace(",", "")
            if label == "PINCODE" and re.match(r"^\d{6}$", word):
                parsed["pincode"] = word
            elif label in ["STATE", "STATENAME"]:
                parsed["state"] = word
            elif label in ["DISTRICT", "CITY_DISTRICT"]:
                parsed["district"] = word
            elif label in ["TALUK", "SUB_DISTRICT"]:
                parsed["taluk"] = word
            elif label in ["VILLAGE", "TOWN"]:
                parsed["village"] = word
            elif label == "WARD":
                parsed["ward"] = word
            else:
                parsed["landmarks"].append(word)

        # Fallback heuristics
        parsed = self._apply_fuzzy_fixes(parsed)
        parsed["normalized_address"] = self._normalize(parsed)
        return parsed

    def _apply_fuzzy_fixes(self, parsed):
        """Fix misclassifications using fuzzy match."""
        if not parsed["state"]:
            for s in REFERENCE_STATES:
                if fuzz.partial_ratio(s.lower(), parsed["raw"].lower()) > 70:
                    parsed["state"] = s
                    break

        if not parsed["district"]:
            for d in REFERENCE_DISTRICTS:
                if fuzz.partial_ratio(d.lower(), parsed["raw"].lower()) > 70:
                    parsed["district"] = d
                    break

        return parsed

    def _normalize(self, parsed):
        parts = [
            parsed.get("ward"),
            parsed.get("village") or parsed.get("town"),
            parsed.get("taluk"),
            parsed.get("district"),
            parsed.get("state"),
            parsed.get("pincode"),
        ]
        return ", ".join([p for p in parts if p])
