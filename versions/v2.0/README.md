# SPIN TRAINING BOT v.2.0 — Конструктор обучающих ботов

Универсальный Telegram-бот для обучающих сценариев. Вся логика вынесена в конфигурации сценариев, что позволяет создавать новые обучающие боты без изменения кода.

## Архитектура

```
engine/
  scenario_loader.py     # загрузка и валидация конфигов
  question_analyzer.py   # определение типа вопроса и очков ясности
  report_generator.py    # финальный отчёт, бейджи, рекомендации
scenarios/
  spin_sales/            # продакшн сценарий SPIN
  template/              # шаблон для копирования
  example_scenario/      # пример другого домена (переговоры)
bot.py                   # универсальный движок, без SPIN-хардкода
```

## Быстрый старт

1) Установить зависимости:
```bash
pip install -r requirements.txt
```

2) Настроить `.env`:
```
BOT_TOKEN=...            # токен Telegram-бота
OPENAI_API_KEY=...       # ключ OpenAI
SCENARIO_PATH=scenarios/spin_sales/config.json  # путь к сценарию

# (опционально) Anthropic для fallback
ANTHROPIC_API_KEY=...

# Таймаут/ретраи LLM
LLM_TIMEOUT_SEC=30
LLM_MAX_RETRIES=1

# Конвейер ответов клиента
RESPONSE_PRIMARY_PROVIDER=openai
RESPONSE_PRIMARY_MODEL=gpt-4o-mini
RESPONSE_FALLBACK_PROVIDER=anthropic
RESPONSE_FALLBACK_MODEL=claude-3-haiku-latest

# Конвейер фидбека наставника
FEEDBACK_PRIMARY_PROVIDER=openai
FEEDBACK_PRIMARY_MODEL=gpt-5-mini
FEEDBACK_FALLBACK_PROVIDER=anthropic
FEEDBACK_FALLBACK_MODEL=claude-3-5-sonnet-latest

# Конвейер классификации вопросов (SPIN)
CLASSIFICATION_PRIMARY_PROVIDER=openai
CLASSIFICATION_PRIMARY_MODEL=gpt-4o-mini
CLASSIFICATION_FALLBACK_PROVIDER=openai
CLASSIFICATION_FALLBACK_MODEL=gpt-3.5-turbo
```

3) Запуск:
```bash
python bot.py
```

Команды в чате: `/start`, `/help`, `/scenario`, `/stats`, `/rank`, `/case`, `/validate`, а также текстовые: "начать", "завершить", "ДА".

## Создание нового сценария

1) Скопируйте `scenarios/template` в новую папку, например `scenarios/my_course`.

2) Заполните `scenarios/my_course/config.json`:
- `scenario_info`: метаданные сценария
- `messages`: тексты интерфейса и прогресса
- `prompts`: системные промпты (генерация кейса, ответы клиента, обратная связь)
- `question_types`: типы вопросов/ходов (ключевые слова, очки ясности, множители)
- `game_rules`: правила сессии (максимум вопросов, цель ясности и т.п.)
- `scoring`: бейджи по шкале очков
- `ui`: формат прогресса, набор команд

3) Укажите путь к новому сценарию в `.env`:
```
SCENARIO_PATH=scenarios/my_course/config.json
```

4) Перезапустите бота.

## Структура config.json (обязательные секции)

```json
{
  "scenario_info": { "name": "...", "version": "1.0", "description": "..." },
  "messages": { "welcome": "...", "case_generated": "{client_case}", "training_complete": "{report}", "error_generic": "...", "progress": "...", "question_feedback": "...", "clarity_reached": "..." },
  "prompts": { "case_generation": "...", "client_response": "...", "feedback": "..." },
  "question_types": [ { "id": "...", "name": "...", "emoji": "", "keywords": ["..."], "clarity_points": 0, "score_multiplier": 0 } ],
  "game_rules": { "max_questions": 10, "min_questions_for_completion": 5, "target_clarity": 80, "short_question_threshold": 5 },
  "scoring": { "badges": [ { "min_score": 0, "max_score": 100, "name": "...", "emoji": "🥉" } ] },
  "ui": { "progress_format": "...", "commands": ["начать", "старт", "завершить"] }
}
```

## Совместимость и обработка ошибок
- Вся прежняя логика SPIN перенесена в `scenarios/spin_sales/config.json`.
- При ошибках загрузки сценария бот пишет понятные сообщения и логирует детали.

## Примечания
- Для смены домена обучения правьте только конфиг сценария — код бота менять не нужно.
- Добавьте мультиязычность, JSON Schema-валидацию и CLI-генератор сценариев при необходимости.

