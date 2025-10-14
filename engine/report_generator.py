from typing import Any, Dict, List


class ReportGenerator:
    """Generates final report, badge, and recommendations based on stats and config."""

    def get_badge(self, score: int, badges: List[Dict[str, Any]]) -> str:
        for b in badges:
            min_score = int(b.get("min_score", 0))
            max_score = int(b.get("max_score", 999999))
            if min_score <= score <= max_score:
                name = b.get("name", "")
                emoji = b.get("emoji", "")
                return f"{emoji} {name}".strip()
        return ""

    def get_recommendations(self, user_stats: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
        recs: List[str] = []
        per_type = user_stats.get("per_type_counts", {})
        clarity = int(user_stats.get("clarity_level", 0))

        # Basic heuristics similar to the legacy implementation
        if per_type.get("situational", 0) > (per_type.get("problem", 0) or 0) * 2:
            recs.append("• Сокращайте количество ситуационных вопросов")
        if (per_type.get("problem", 0) or 0) == 0:
            recs.append("• Обязательно задавайте проблемные вопросы для выявления потребностей")
        if (per_type.get("implication", 0) or 0) == 0:
            recs.append("• Используйте извлекающие вопросы для развития проблем")
        if (per_type.get("need_payoff", 0) or 0) == 0:
            recs.append("• Добавьте направляющие вопросы для обсуждения выгод решения")
        if clarity < 50:
            recs.append("• Глубже исследуйте потребности клиента")

        if not recs:
            recs.append("• Отличная работа! Все типы вопросов использованы правильно.")
        return recs

    def generate_final_report(self, user_stats: Dict[str, Any], config: Dict[str, Any]) -> str:
        ui = config.get("ui", {})
        scoring = config.get("scoring", {})
        badges = scoring.get("badges", [])
        analyzer = user_stats.get("analyzer")  # optional injected analyzer result
        total_score = int(user_stats.get("total_score", 0))

        badge = self.get_badge(total_score, badges)
        recs = self.get_recommendations(user_stats, config)

        # Compose report similar to legacy but generic
        lines: List[str] = []
        lines.append("🏁 ТРЕНИРОВКА ЗАВЕРШЕНА!")
        lines.append("")
        lines.append("📊 РЕЗУЛЬТАТЫ:")
        lines.append(f"Задано вопросов: {user_stats.get('question_count', 0)}/{config['game_rules']['max_questions']}")
        lines.append(f"Уровень ясности: {user_stats.get('clarity_level', 0)}%")
        lines.append("")
        lines.append("📈 ПО ТИПАМ:")

        per_type_counts = user_stats.get("per_type_counts", {})
        type_names = {t["id"]: t.get("name", t["id"]) for t in config.get("question_types", [])}
        type_emojis = {t["id"]: t.get("emoji", "") for t in config.get("question_types", [])}
        for tid, count in per_type_counts.items():
            name = type_names.get(tid, tid)
            emoji = type_emojis.get(tid, "")
            lines.append(f"{emoji} {name}: {count}")

        lines.append("")
        lines.append(f"🏅 Ваш результат: {badge}")
        lines.append(f"Общий балл: {total_score}")
        lines.append("")
        lines.append("💡 РЕКОМЕНДАЦИИ:")
        lines.append("\n".join(recs))
        lines.append("")
        lines.append("🎯 Для новой тренировки напишите \"начать\"")

        return "\n".join(lines)


