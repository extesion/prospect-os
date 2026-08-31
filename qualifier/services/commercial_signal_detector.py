from typing import List, Dict, Any, Optional

class CommercialSignalDetector:

    @staticmethod
    def detect_signals(
        extracted_links: Dict[str, Any],
        extracted_email: Dict[str, Optional[str]],
        extracted_whatsapp: Dict[str, Optional[str]],
        keywords_found: List[Dict[str, Any]],
        texts_with_sources: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Synthesizes multiple extractions into structured commercial signals.
        Each signal has: {type: str, source: str, value: str}
        """
        signals: List[Dict[str, str]] = []
        seen_types = set()

        # 1. Own Website
        if extracted_links.get("website"):
            signals.append({
                "type": "own_website",
                "source": extracted_links.get("website_source") or "links",
                "value": extracted_links["website"]
            })
            seen_types.add("own_website")

        # 2. Commercial Email
        if extracted_email.get("email"):
            signals.append({
                "type": "commercial_email",
                "source": extracted_email.get("email_source") or "description",
                "value": extracted_email["email"]
            })
            seen_types.add("commercial_email")

        # 3. WhatsApp Contact
        if extracted_whatsapp.get("whatsapp"):
            signals.append({
                "type": "whatsapp_contact",
                "source": extracted_whatsapp.get("whatsapp_source") or "description",
                "value": str(extracted_whatsapp["whatsapp"])
            })
            seen_types.add("whatsapp_contact")

        # 4. Sales Platforms (Hotmart, Kiwify, Stan, Eduzz, etc.)
        if extracted_links.get("sales_platforms"):
            for sp in extracted_links["sales_platforms"]:
                sig_type = f"sales_platform_{sp['platform']}"
                if sig_type not in seen_types:
                    signals.append({
                        "type": "sales_platform",
                        "source": sp.get("source") or "links",
                        "value": f"{sp['platform']}: {sp['url']}"
                    })
                    seen_types.add(sig_type)

        # 5. Link Aggregators (Linktree, Beacons, etc.)
        if extracted_links.get("link_aggregators"):
            for agg in extracted_links["link_aggregators"]:
                sig_type = f"link_aggregator_{agg['platform']}"
                if sig_type not in seen_types:
                    signals.append({
                        "type": "link_aggregator",
                        "source": agg.get("source") or "links",
                        "value": f"{agg['platform']}: {agg['url']}"
                    })
                    seen_types.add(sig_type)

        # 6. Keyword-driven commercial signals
        kw_map = {
            "curso": "course_sale",
            "cursos": "course_sale",
            "treinamento": "course_sale",
            "hotmart": "course_sale",
            "kiwify": "course_sale",
            "eduzz": "course_sale",
            "consultoria": "consulting_service",
            "mentoria": "mentorship_service",
            "assessoria": "agency_service",
            "agência": "agency_service",
            "loja": "store_merch",
            "produto": "product_sale",
            "produtos": "product_sale",
            "orçamento": "budget_inquiry",
            "contrate": "hire_service",
            "parceria": "sponsorship_partnerships",
            "parcerias": "sponsorship_partnerships",
            "patrocínio": "sponsorship_partnerships",
            "patrocinador": "sponsorship_partnerships",
            "anuncie": "sponsorship_partnerships",
            "mídia kit": "sponsorship_partnerships",
            "media kit": "sponsorship_partnerships",
            "link na bio": "call_to_action",
            "compre": "call_to_action",
            "inscreva-se": "call_to_action"
        }

        for kitem in keywords_found:
            kw = kitem.get("keyword", "").lower()
            sig_type = kw_map.get(kw)
            if sig_type and sig_type not in seen_types:
                signals.append({
                    "type": sig_type,
                    "source": kitem.get("source") or "text",
                    "value": f"Keyword: {kw} (Context: {kitem.get('context', '')})"
                })
                seen_types.add(sig_type)

        return signals
