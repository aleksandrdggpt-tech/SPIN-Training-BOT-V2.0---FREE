from typing import Dict, List, Any, Callable, Awaitable
import logging

logger = logging.getLogger(__name__)


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

    # Fallback (старый метод)
    def classify_question_fallback(self, question: str, question_types: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.analyze_type(question, question_types)

    async def classify_question_with_llm(
        self,
        question: str,
        case_context: str,
        call_llm_func: Callable[[str, str, str], Awaitable[str]],
        prompts: Dict[str, Any]
    ) -> str:
        """Классификация через LLM. Возвращает один из id: situational/problem/implication/need_payoff."""
        prompt = str(prompts.get("question_classification", "")).format(
            question=question,
            context=case_context or ""
        )
        raw = await call_llm_func('classification', prompt, 'Classify SPIN question')
        label = (raw or "").strip().lower()
        # Нормализация и валидация
        allowed = {"situational", "problem", "implication", "need_payoff"}
        if label not in allowed:
            # Частые варианты: need-payoff, need payoff
            label = label.replace("-", "_").replace(" ", "_")
        if label not in allowed:
            raise ValueError(f"Unrecognized classification label: {raw}")
        return label

    async def classify_question(
        self,
        question: str,
        question_types: List[Dict[str, Any]],
        case_context: str,
        call_llm_func: Callable[[str, str, str], Awaitable[str]] = None,
        prompts: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Основной метод классификации: LLM → fallback."""
        if call_llm_func is not None:
            try:
                label = await self.classify_question_with_llm(question, case_context, call_llm_func, prompts)
                for qt in question_types:
                    if qt.get('id') == label:
                        logger.info(f"LLM classification success: {label}")
                        return qt
                logger.warning("LLM label not in question_types; fallback")
            except Exception as e:
                logger.warning(f"LLM classification failed ({type(e).__name__}): {e}; using fallback")
        return self.classify_question_fallback(question, question_types)

    async def check_context_usage(
        self,
        question: str,
        last_response: str,
        call_llm_func: Callable[[str, str, str], Awaitable[str]] = None,
        prompts: Dict[str, Any] = None
    ) -> bool:
        """Определяет, использует ли вопрос факты из последнего ответа клиента."""
        if not last_response:
            return False
        # Попытка через LLM
        if call_llm_func and prompts and prompts.get('context_check'):
            try:
                prompt = str(prompts.get('context_check', '')).format(
                    last_response=last_response,
                    question=question
                )
                raw = await call_llm_func('context', prompt, 'Check context usage')
                label = (raw or '').strip().lower()
                if 'yes' in label and not 'no' in label:
                    logger.info("LLM context check: yes")
                    return True
                if 'no' in label:
                    logger.info("LLM context check: no")
                    return False
                raise ValueError(f"Unrecognized context label: {raw}")
            except Exception as e:
                logger.warning(f"LLM context check failed ({type(e).__name__}): {e}; fallback heuristic")
        # Fallback эвристика
        return self.check_context_usage_fallback(question, last_response)

    def check_context_usage_fallback(self, question: str, last_response: str) -> bool:
        q = question.lower()
        resp = last_response.lower()
        # Числа из ответа
        import re
        numbers = re.findall(r"\b\d+[\d\s.,]*\b", resp)
        if any(n.strip() and n.strip() in q for n in numbers):
            return True
        # Ключевые маркеры ссылок на сказанное
        markers = ["как вы сказали", "уточните", "по поводу", "вы упомянули", "этих", "этой проблемы", "этой ситуации"]
        if any(m in q for m in markers):
            return True
        return False

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


