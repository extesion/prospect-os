import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from qualifier.config.qualification_config import qualification_config

def strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

class KeywordAnalyzer:

    @staticmethod
    def extract_keywords_with_sources(
        texts_with_sources: List[Dict[str, str]],
        custom_keywords: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
        """
        Scans texts specifically for commercial keywords, extracts occurrence contexts,
        and builds an exact mapping of keyword -> [sources_found].
        """
        keywords_to_check = custom_keywords or qualification_config.COMMERCIAL_KEYWORDS
        found: List[Dict[str, Any]] = []
        sources_map: Dict[str, List[str]] = {}
        seen_pairs = set()

        for item in texts_with_sources:
            original_text = item.get("text") or ""
            source = item.get("source") or "unknown"
            if not original_text.strip():
                continue

            normalized_text = strip_accents(original_text.lower())

            for kw in keywords_to_check:
                kw_norm = strip_accents(kw.lower())
                pattern = r'\b' + re.escape(kw_norm) + r'\b'
                matches = list(re.finditer(pattern, normalized_text))

                if matches:
                    # Register source mapping
                    if kw not in sources_map:
                        sources_map[kw] = []
                    if source not in sources_map[kw]:
                        sources_map[kw].append(source)

                    pair_key = (kw.lower(), source)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    # Get snippet from original text around the first match
                    first_match = matches[0]
                    start_idx = max(0, first_match.start() - 30)
                    end_idx = min(len(original_text), first_match.end() + 40)
                    context_snippet = original_text[start_idx:end_idx].strip()
                    if start_idx > 0:
                        context_snippet = "..." + context_snippet
                    if end_idx < len(original_text):
                        context_snippet = context_snippet + "..."

                    found.append({
                        "keyword": kw,
                        "source": source,
                        "context": context_snippet
                    })

        return found, sources_map

    @staticmethod
    def extract_keywords(
        texts_with_sources: List[Dict[str, str]],
        custom_keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        found, _ = KeywordAnalyzer.extract_keywords_with_sources(texts_with_sources, custom_keywords)
        return found
