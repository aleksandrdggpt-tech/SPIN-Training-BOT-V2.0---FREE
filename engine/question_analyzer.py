from typing import Dict, List, Any


class QuestionAnalyzer:
    """Analyzes questions using scenario-defined question types."""

    def analyze_type(self, question: str, question_types: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Determine question type by keyword presence.

        Returns the matching question type dict. Falls back to the first type if none match.
        """
        text = question.lower()
        for qtype in question_types:
            keywords = [kw.lower() for kw in qtype.get("keywords", [])]
            if any(kw in text for kw in keywords):
                return qtype
        return question_types[0]

    def calculate_clarity_increase(self, question_type: Dict[str, Any]) -> int:
        """Return clarity points from the question type definition."""
        return int(question_type.get("clarity_points", 0))

    def calculate_score(self, user_stats: Dict[str, Any], question_types: List[Dict[str, Any]]) -> int:
        """Compute a simple total score using per-type multipliers defined in the config."""
        total = 0
        per_type_counts = user_stats.get("per_type_counts", {})
        for qtype in question_types:
            qid = qtype.get("id")
            count = int(per_type_counts.get(qid, 0))
            total += count * int(qtype.get("score_multiplier", 0))
        return total


