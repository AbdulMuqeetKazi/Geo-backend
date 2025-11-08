# app/ner_address.py
import logging
import re
from typing import Optional, Dict, Any, List

import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification
from rapidfuzz import process, fuzz

from app.config import REFERENCE_STATES, REFERENCE_DISTRICTS

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class IndianAddressNER:
    """
    Wrapper for the TinyBERT-based Indian Address NER model (shiprocket-ai).
    Extracts entities like city, pincode, state, landmarks etc from raw address text.
    """

    MODEL_NAME = "shiprocket-ai/open-tinybert-indian-address-ner"

    def __init__(self, device: Optional[torch.device] = None):
        self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
        self.model = AutoModelForTokenClassification.from_pretrained(self.MODEL_NAME)
        if device is None:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.device = device
        self.model.to(self.device)
        self.model.eval()

        # mapping from id to entity label
        self.id2entity = {
            "0": "O",
            "1": "B-building_name",
            "2": "I-building_name",
            "3": "B-city",
            "4": "I-city",
            "5": "B-country",
            "6": "I-country",
            "7": "B-floor",
            "8": "I-floor",
            "9": "B-house_details",
            "10": "I-house_details",
            "11": "B-locality",
            "12": "I-locality",
            "13": "B-pincode",
            "14": "I-pincode",
            "15": "B-road",
            "16": "I-road",
            "17": "B-state",
            "18": "I-state",
            "19": "B-sub_locality",
            "20": "I-sub_locality",
            "21": "B-landmarks",
            "22": "I-landmarks"
        }

    def _fuzzy_correct(self, value: Optional[str], candidates: List[str], threshold: int = 80) -> Optional[str]:
        if not value:
            return None
        match = process.extractOne(value, candidates, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= threshold:
            return match[0]
        return value

    def parse(self, address: str) -> Dict[str, Any]:
        """Run the NER model on address text and build a structured dict."""
        if not address or not address.strip():
            return {}

        # Tokenize and get offsets
        inputs = self.tokenizer(
            address,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=128,
            return_offsets_mapping=True
        )
        offset_mapping = inputs.pop("offset_mapping")[0]
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            scores = torch.nn.functional.softmax(logits, dim=-1)
            pred_ids = torch.argmax(scores, dim=-1)[0]
            confidences = torch.max(scores, dim=-1)[0][0]

        entities: Dict[str, List[Dict[str, Any]]] = {}
        current_entity = None

        for idx, (pred_id, conf) in enumerate(zip(pred_ids.tolist(), confidences.tolist())):
            label = self.id2entity.get(str(pred_id), "O")
            start_char, end_char = offset_mapping[idx].tolist()
            if start_char == end_char == 0:
                continue

            token_text = address[start_char:end_char]

            if label.startswith("B-"):
                # start a new entity
                ent_type = label[2:]
                if current_entity:
                    # save previous entity
                    et = current_entity["type"]
                    entities.setdefault(et, []).append({
                        "text": current_entity["text"],
                        "confidence": current_entity["confidence"]
                    })
                current_entity = {
                    "type": ent_type,
                    "text": token_text,
                    "confidence": float(conf)
                }
            elif label.startswith("I-") and current_entity and current_entity["type"] == label[2:]:
                # continuation of same entity
                current_entity["text"] += token_text
                # average confidence
                current_entity["confidence"] = (current_entity["confidence"] + float(conf)) / 2.0
            else:
                # label is "O" or mismatch; close previous if exists
                if current_entity:
                    et = current_entity["type"]
                    entities.setdefault(et, []).append({
                        "text": current_entity["text"],
                        "confidence": current_entity["confidence"]
                    })
                    current_entity = None

        # if last entity still open
        if current_entity:
            et = current_entity["type"]
            entities.setdefault(et, []).append({
                "text": current_entity["text"],
                "confidence": current_entity["confidence"]
            })

        # build simplified output keys
        output: Dict[str, Any] = {
            "raw": address,
            "pincode": None,
            "state": None,
            "district": None,
            "city": None,
            "locality": None,
            "road": None,
            "village": None,
            "taluk": None,
            "ward": None,
            "landmarks": []
        }

        # Map entity types into these keys
        for etype, ent_list in entities.items():
            for ent in ent_list:
                text = ent["text"].strip()
                if etype == "pincode":
                    output["pincode"] = text
                elif etype == "state":
                    output["state"] = text
                elif etype == "city":
                    output["city"] = text
                elif etype == "locality":
                    output["locality"] = text
                elif etype == "road":
                    output["road"] = text
                elif etype == "ward":
                    output["ward"] = text
                elif etype == "landmarks":
                    output["landmarks"].append(text)
                elif etype == "house_details":
                    # could map to building or house_details field
                    output.setdefault("house_details", []).append(text)
                # you may expand further mappings as needed

        # Fuzzy-correct state & district fields using reference lists
        if output.get("state"):
            output["state"] = self._fuzzy_correct(output["state"], REFERENCE_STATES)
        if output.get("district"):
            output["district"] = self._fuzzy_correct(output["district"], REFERENCE_DISTRICTS)

        return output
