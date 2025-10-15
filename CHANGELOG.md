# Changelog

## 2.1.0 — 2025-10-15

- Case generation: local generator (engine/case_generator.py) with validation/compatibility, uniqueness, logging.
- Scenario config (scenarios/spin_sales/config.json):
  - case_variants expanded (companies, products with volume_range/frequency_options, sizes, regions, base situations with description_short)
  - ranking.levels, achievements; prompts question_classification, context_check
  - scoring.question_weights with contextual_bonus
- Bot core (bot.py):
  - call_llm(kind) with fallback; supports response, feedback, classification, context; OpenAI + Anthropic
  - env-driven models/timeouts/retries; /help, /rank, /validate, /case, /stats; improved /start
  - Final report: rank, level-up, achievements, Active Listening stats; stats update before report
  - Enhanced logging (payload keys, fallback reasons, case stats)
- Question analyzer: async LLM classification with validation + keyword fallback; Active Listening (LLM + heuristic)
- Dev scripts: restart_bot.sh (foreground logs), improved stop_bot.sh
- README updates: env keys, commands, pipelines, cost notes

## 2.0.0 — Initial v2 foundation
- Base SPIN scenario, question types, scoring, and bot skeleton.
