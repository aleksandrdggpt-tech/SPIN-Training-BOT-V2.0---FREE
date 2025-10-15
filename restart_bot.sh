#!/bin/bash

echo "🔁 Перезапуск SPIN Training Bot..."

# --- Остановка (как в stop_bot.sh) ---
echo "🛑 Останавливаю SPIN Training Bot..."
echo "🔍 Поиск процессов бота..."
# Перечень возможных команд запуска (python/python3, venv, абсолютные пути)
PIDS=$(pgrep -f "[p]ython.*bot.py" || true)
if [ -n "$PIDS" ]; then
  echo "Найдены PID: $PIDS"
  echo "💀 Останавливаю процессы (TERM)..."
  pkill -f "[p]ython.*bot.py" || true
  sleep 1
  # Повторная проверка
  PIDS2=$(pgrep -f "[p]ython.*bot.py" || true)
  if [ -n "$PIDS2" ]; then
    echo "⚠️  Всё ещё запущены: $PIDS2 — останавливаю (KILL)..."
    pkill -9 -f "[p]ython.*bot.py" || true
    sleep 1
  fi
else
  echo "Не найдено активных процессов бота."
fi

# --- Запуск ---
echo "🚀 Запускаю бота..."

# Переходим в директорию скрипта
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Выбираем интерпретатор (если есть venv — используем его)
PY_BIN="python3"
if [ -x "venv/bin/python3" ]; then
  PY_BIN="venv/bin/python3"
fi

# Запускаем в ПЕРЕДНЕМ плане (логи в терминал)
echo "📜 Логи будут выведены в этот терминал. Нажмите Ctrl+C для остановки."
exec "$PY_BIN" bot.py


