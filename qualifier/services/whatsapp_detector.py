import re
from typing import List, Dict, Any, Optional

WA_LINK_REGEX = re.compile(
    r'(?:https?:\/\/)?(?:wa\.me\/|api\.whatsapp\.com\/send\?(?:[^&]*&)*phone=)(\+?\d{8,15})',
    re.IGNORECASE
)

# Detect Brazilian and international phone numbers near keywords
# Example: "Whatsapp: (11) 98765-4321", "Zap: 11 98888 8888", "Contato: +55 21 99999-9999"
CONTEXT_PHONE_REGEX = re.compile(
    r'(?:whatsapp|whats|zap|contato|wpp|telefone|celular|fone)\s*[:=-]?\s*(\+?\d{1,3}[-.\s]?)?\(?\d{2,3}\)?[-.\s]?\d{4,5}[-.\s]?\d{4}',
    re.IGNORECASE
)

class WhatsAppDetector:

    @staticmethod
    def detect_whatsapp(texts_with_sources: List[Dict[str, str]], extracted_links: Optional[Dict[str, Any]] = None) -> Dict[str, Optional[str]]:
        """
        Detects WhatsApp numbers and links from texts and classified URLs.
        texts_with_sources is: [{"text": "...", "source": "channel_description"}, ...]
        """
        # 1. Check extracted links first (direct wa.me links)
        if extracted_links and extracted_links.get("whatsapp_link"):
            link_url = extracted_links["whatsapp_link"]
            source = extracted_links.get("whatsapp_source") or "link"
            match = WA_LINK_REGEX.search(link_url)
            if match:
                num = match.group(1).replace("+", "")
                return {"whatsapp": num, "whatsapp_source": source}
            return {"whatsapp": link_url, "whatsapp_source": source}

        # 2. Search texts for direct wa.me links
        for item in texts_with_sources:
            text = item.get("text") or ""
            source = item.get("source") or "unknown"

            wa_match = WA_LINK_REGEX.search(text)
            if wa_match:
                num = wa_match.group(1).replace("+", "")
                return {"whatsapp": num, "whatsapp_source": source}

        # 3. Search texts for numbers accompanied by keywords ("whatsapp", "zap", "contato")
        for item in texts_with_sources:
            text = item.get("text") or ""
            source = item.get("source") or "unknown"

            phone_match = CONTEXT_PHONE_REGEX.search(text)
            if phone_match:
                raw_match = phone_match.group(0)
                # Extract only digits and leading plus from the match
                digits = re.sub(r'[^\d+]', '', raw_match)
                if len(digits) >= 10:
                    return {"whatsapp": digits, "whatsapp_source": source}

        return {"whatsapp": None, "whatsapp_source": None}
