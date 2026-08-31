import re
from typing import List, Dict, Any, Optional

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    re.IGNORECASE
)

# Common non-lead or generic/system emails to ignore
IGNORED_EMAIL_DOMAINS = {
    "example.com", "test.com", "domain.com", "email.com", "sentry.io",
    "wixpress.com", "googleapis.com"
}

INVALID_EMAIL_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".js", ".css", ".html"
}

class EmailExtractor:

    @staticmethod
    def extract_emails(texts_with_sources: List[Dict[str, str]]) -> Dict[str, Optional[str]]:
        """
        Extracts public contact email from texts, tracking source and filtering false positives.
        texts_with_sources is: [{"text": "...", "source": "channel_description"}, ...]
        """
        found_emails: List[Dict[str, str]] = []

        for item in texts_with_sources:
            text = item.get("text") or ""
            source = item.get("source") or "unknown"

            # Normalize potential obfuscated patterns like "contato [at] site [dot] com"
            cleaned_text = (
                text.replace(" [at] ", "@")
                .replace(" [arroba] ", "@")
                .replace("(at)", "@")
                .replace(" [dot] ", ".")
                .replace(" [ponto] ", ".")
                .replace("(dot)", ".")
            )

            matches = EMAIL_REGEX.findall(cleaned_text)
            for raw_email in matches:
                email = raw_email.lower().strip()
                
                # Check for invalid image/asset extensions
                if any(email.endswith(ext) for ext in INVALID_EMAIL_EXTENSIONS):
                    continue

                domain = email.split("@")[-1]
                if domain in IGNORED_EMAIL_DOMAINS:
                    continue

                # Valid email found
                found_emails.append({
                    "email": email,
                    "source": source
                })

        if not found_emails:
            return {"email": None, "email_source": None}

        # Prioritize commercial emails if multiple found (e.g., starts with contato, comercial, parceria, contato@)
        commercial_prefixes = ("contato", "comercial", "parceria", "assessoria", "atendimento", "info", "business")
        for item in found_emails:
            if item["email"].startswith(commercial_prefixes):
                return {"email": item["email"], "email_source": item["source"]}

        # Default to the first found email
        return {"email": found_emails[0]["email"], "email_source": found_emails[0]["source"]}
