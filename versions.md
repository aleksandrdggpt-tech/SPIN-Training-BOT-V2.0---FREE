# Versions: сравнение старой и V2.0 — FREE

Старая папка: `/Users/aleksandrdg/Projects/SPIN Training BOT` (репозиторий `SPIN-Training-Bot`).
Новая папка: `/Users/aleksandrdg/Projects/SPIN Training BOT V2.0 - FREE` (репозиторий `SPIN-Training-BOT-V2.0---FREE`).

Ссылки: `https://github.com/aleksandrdggpt-tech/SPIN-Training-Bot`, `https://github.com/aleksandrdggpt-tech/SPIN-Training-BOT-V2.0---FREE`.

## Версия 1 (legacy)
- Репозиторий/папка: `/Users/aleksandrdg/Projects/SPIN Training BOT` (`SPIN-Training-Bot`).
- Архитектура: монолитный `bot.py` с жёстко зашитой SPIN‑логикой.
- Деплой: развёрнут на виртуальной машине Railway (railway.app).
  - Используется контейнерный деплой (Docker/Nixpacks в Railway), переменные окружения задаются в Railway Dashboard.
  - Автоперезапуск процесса обеспечивается платформой Railway; логи и метрики доступны в консоли Railway.
- Интеграции: OpenAI; управление конфигурацией преимущественно через `.env` и код.

## Ключевые отличия
- Архитектура стала модульной:
  - Добавлен `engine/` (загрузчик сценариев, анализатор вопросов, генератор отчётов, генератор кейсов):
    - `engine/scenario_loader.py`
    - `engine/question_analyzer.py`
    - `engine/report_generator.py`
    - `engine/case_generator.py`
  - Вся доменная логика вынесена в конфиги сценариев (`scenarios/*/config.json`), код бота стал универсальным.
  - Есть готовые сценарии и шаблоны: `scenarios/spin_sales`, `scenarios/template`, `scenarios/example_scenario`.
- Функциональные изменения:
  - Конвейеры LLM с fallback (OpenAI/Anthropic) для ответов клиента, фидбека наставника и классификации вопросов.
  - Новые команды: `/help`, `/rank`, `/validate`, `/case`, `/stats` + улучшен `/start`.
  - Финальный отчёт расширен: уровни/ранги, достижения, метрики Active Listening.
- Документация/скрипты:
  - Появились `CHANGELOG.md`, обновлён `README.md`, добавлен `restart_bot.sh`.
  - `.gitignore` переработан под новые артефакты.

## Сводка по изменённым файлам
- Добавлено: `CHANGELOG.md`, `restart_bot.sh`, `engine/*`, `scenarios/*`, `logs/bot.out`.
- Существенно переработано: `bot.py`, `README.md`, `.gitignore`.

Источник: сравнение директорий (исключая `.git`, `venv`, `__pycache__`, `*.pyc`).

## Важные переменные окружения
Добавлены/стали обязательными (см. `README.md`):
- `SCENARIO_PATH` — путь к активному сценарию, напр. `scenarios/spin_sales/config.json`.
- LLM‑настройки: `LLM_TIMEOUT_SEC`, `LLM_MAX_RETRIES`.
- Конвейеры:
  - `RESPONSE_PRIMARY_PROVIDER/MODEL`, `RESPONSE_FALLBACK_PROVIDER/MODEL`
  - `FEEDBACK_PRIMARY_PROVIDER/MODEL`, `FEEDBACK_FALLBACK_PROVIDER/MODEL`
  - `CLASSIFICATION_PRIMARY_PROVIDER/MODEL`, `CLASSIFICATION_FALLBACK_PROVIDER/MODEL`

Примечание: в историю могли попасть локальные `.env` и `logs/bot.out`; убедитесь, что чувствительные данные удалены из истории и `.env` игнорируется.

## Миграция со старой версии
1) Перенесите контент сценария в JSON:
   - Скопируйте `scenarios/template` → `scenarios/my_spin` и заполните секции (`scenario_info`, `messages`, `prompts`, `question_types`, `game_rules`, `scoring`, `ui`).
2) Установите активный сценарий:
   - В `.env`: `SCENARIO_PATH=scenarios/my_spin/config.json`.
3) Заполните ключи и модели:
   - `OPENAI_API_KEY` (+ `ANTHROPIC_API_KEY` опционально), проверьте модели и таймауты.
4) Проверьте команды: `/start`, `/help`, `/stats`, `/rank`, `/case`, `/validate`.

## Что осталось совместимым
- Общая логика диалога и подсчёт метрик SPIN сохранены, но теперь конфигурируются через `scenarios/*/config.json`.


