Template Scenario

How to create a new scenario:
- Copy this folder and rename it (e.g., `scenarios/my_course`).
- Edit `config.json`:
  - `scenario_info`: basic metadata.
  - `messages`: user-facing texts, progress line, clarity reached.
  - `prompts`: LLM system prompts with placeholders.
  - `question_types`: ids, names, emojis, keywords, clarity_points, score_multiplier.
  - `game_rules`: max/min questions, target clarity, short question threshold.
  - `scoring`: badge scale.
  - `ui`: progress format and commands.
- Set `.env`:
```
SCENARIO_PATH=scenarios/my_course/config.json
```
- Restart the bot.


