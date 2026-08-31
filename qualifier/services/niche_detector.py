import re
import unicodedata
from typing import List, Dict, Any, Tuple, Optional
from qualifier.config.qualification_config import qualification_config

def strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

class NicheDetector:

    @staticmethod
    def detect_niche(
        texts_with_sources: List[Dict[str, str]],
        channel_name: str = "",
        video_tags: Optional[List[str]] = None
    ) -> Tuple[Optional[str], float]:
        """
        Detects primary niche from combined texts, channel name and video tags using weighted keyword frequencies.
        Returns (detected_niche, niche_confidence).
        """
        niche_map = qualification_config.NICHES_KEYWORDS_MAP
        
        # Combine all text
        all_raw_text = channel_name + " "
        if video_tags:
            all_raw_text += " ".join(video_tags) + " "
        for item in texts_with_sources:
            all_raw_text += (item.get("text") or "") + " "

        normalized_corpus = strip_accents(all_raw_text.lower())

        scores: Dict[str, int] = {}
        for niche, keywords in niche_map.items():
            score = 0
            for kw in keywords:
                kw_norm = strip_accents(kw.lower())
                pattern = r'\b' + re.escape(kw_norm) + r'\b'
                matches = re.findall(pattern, normalized_corpus)
                score += len(matches)
            if score > 0:
                scores[niche] = score

        if not scores:
            return (None, 0.0)

        # Sort niches by score descending
        sorted_niches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_niche, best_score = sorted_niches[0]
        total_score = sum(scores.values())

        # Confidence: proportion of the top niche relative to all matched niche keywords (max 0.95 without AI)
        confidence = round(min(0.95, (best_score / total_score) * min(1.0, best_score / 3)), 2)
        if confidence < 0.2:
            confidence = 0.2

        return (best_niche, confidence)
