#!/bin/bash

echo "🛑 Останавливаю SPIN Training Bot..."

# Найти все процессы бота
echo "🔍 Поиск процессов бота..."
ps aux | grep "python3 bot.py" | grep -v grep

# Остановить все процессы бота
echo "💀 Останавливаю процессы..."
pkill -f "python3 bot.py"

# Проверить результат
sleep 1
echo "✅ Проверяю результат..."
ps aux | grep "python3 bot.py" | grep -v grep

if [ $? -eq 1 ]; then
    echo "🎉 Бот успешно остановлен!"
else
    echo "⚠️  Некоторые процессы все еще работают, принудительно останавливаю..."
    pkill -9 -f "python3 bot.py"
fi

echo "🏁 Готово!"
