from typing import Dict, Any, Optional

class AIAnalyzerInterface:
    """
    Conceptual interface for future optional AI analysis (e.g. Gemini, OpenAI, Claude).
    Left disabled in the first version.
    """
    enabled: bool = False

    @classmethod
    def analyze_intermediate_lead(cls, lead_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not cls.enabled:
            return None
        # Future implementation for score 40-69 leads
        return None
