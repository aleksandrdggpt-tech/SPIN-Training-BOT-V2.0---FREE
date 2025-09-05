import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import httpx

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Отладочная информация
print(f"BOT_TOKEN: {BOT_TOKEN}")
print(f"OPENAI_API_KEY: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else 'None'}...")

# Хранилище данных пользователей
user_data: Dict[int, Dict[str, Any]] = {}

# Промпты
CASE_GENERATION_PROMPT = """Вы телеграмм бот, который изображает Нила Рекхем, автора метода SPIN-продаж. Генерируйте клиентский кейс в формате:

🎯 КЛИЕНТСКИЙ КЕЙС:

Должность клиента: [Директор по закупкам/Собственник компании/Главный механик/Главный инженер/Начальник производства/Технический директор]
Компания: [ЖБИ завод/Машиностроительный завод/Металлоторговая компания/Строительная компания/Производство металлоконструкций], [размер]

📦 ВЫ ПРОДАЕТЕ: [Листовой металл/Арматуру/Трубы/Метизы/Сварочные материалы/Металлообрабатывающие станки/Промышленную химию]

ℹ️ БАЗОВАЯ СИТУАЦИЯ: 
[ТОЛЬКО конкретные нейтральные факты с цифрами - объемы, количества, сроки, процессы. БЕЗ проблем и сложностей!]

Теперь можете задать первый вопрос клиенту.


Если нужна обратная связь от наставника — напишите ДА. Для завершения напишите "завершить". Если готовы к следующему вопросу — продолжайте."""

WELCOME_MESSAGE = """🎯 ДОБРО ПОЖАЛОВАТЬ В ТРЕНАЖЕР SPIN-ПРОДАЖ!

Привет! Ты находишься в тренажере вопросов по теории SPIN-продаж Нила Рекхема. Здесь ты научишься задавать правильные вопросы клиентам!

📚 ТИПЫ ВОПРОСОВ SPIN:

🔍 Ситуационные - собрать факты о текущей ситуации клиента
⚠️ Проблемные - выявить проблемы, неудовлетворённость, скрытые потребности  
💥 Извлекающие - показать последствия выявленных проблем, усилить их важность
✨ Направляющие - подчеркнуть ценность решения, перевести беседу в зону пользы

🎮 ПРАВИЛА ТРЕНИРОВКИ:
До 10 вопросов | Цель: выяснить потребности и проблемы клиента | Задача: задать все 4 типа SPIN-вопросов

Готов начать тренировку? Напиши "начать"! 
Чтобы закончить тренировку в любой момент тренировки, напиши "завершить"."""

def get_user_data(user_id: int) -> Dict[str, Any]:
    """Получение данных пользователя"""
    if user_id not in user_data:
        user_data[user_id] = {
            'question_count': 0,
            'clarity_level': 0,
            'situational_q': 0,
            'problem_q': 0,
            'implication_q': 0,
            'need_payoff_q': 0,
            'client_case': '',
            'last_question_type': '',
            'chat_state': 'new'
        }
    return user_data[user_id]

async def call_openai(system_prompt: str, user_message: str) -> str:
    """Вызов OpenAI API"""
    try:
        print(f"🔍 Начинаем вызов OpenAI API...")
        print(f"📝 System prompt: {system_prompt[:100]}...")
        print(f"💬 User message: {user_message[:100]}...")
        print(f"🔑 API Key: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else 'None'}...")
        
        # Создаем клиент с минимальными параметрами
        print(f"🏗️ Создаем AsyncOpenAI клиент...")
        client = openai.AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1)
            )
        )
        print(f"✅ Клиент создан успешно")
        
        # Создаем запрос
        print(f"📤 Отправляем запрос к OpenAI...")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=400,
            temperature=0.7
        )
        print(f"✅ Ответ получен от OpenAI")
        
        result = response.choices[0].message.content.strip()
        print(f"📄 Результат: {result[:100]}...")
        return result
        
    except Exception as e:
        print(f"❌ ОШИБКА в call_openai:")
        print(f"   Тип ошибки: {type(e).__name__}")
        print(f"   Сообщение: {str(e)}")
        print(f"   Полный traceback:")
        import traceback
        traceback.print_exc()
        
        logger.error(f"Ошибка OpenAI: {e}")
        return f"Произошла ошибка при генерации ответа: {str(e)}"

def analyze_question_type(question: str) -> str:
    """Определение типа вопроса"""
    question_lower = question.lower()
    
    problem_keywords = ['проблем', 'сложност', 'трудност', 'недовольн', 'жалоб', 'беспокои']
    implication_keywords = ['влия', 'последств', 'стоимост', 'убыт', 'потер', 'риск', 'результат']
    need_payoff_keywords = ['помож', 'польз', 'выгод', 'важно', 'ценност', 'экономи']
    
    if any(keyword in question_lower for keyword in problem_keywords):
        return 'Проблемный'
    elif any(keyword in question_lower for keyword in implication_keywords):
        return 'Извлекающий'
    elif any(keyword in question_lower for keyword in need_payoff_keywords):
        return 'Направляющий'
    else:
        return 'Ситуационный'

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    print(f"🚀 Команда /start вызвана пользователем {update.effective_user.id}")
    user_id = update.effective_user.id
    
    # Инициализация данных пользователя
    user_data[user_id] = {
        'question_count': 0,
        'clarity_level': 0,
        'situational_q': 0,
        'problem_q': 0,
        'implication_q': 0,
        'need_payoff_q': 0,
        'client_case': '',
        'last_question_type': '',
        'chat_state': 'started'
    }
    
    await update.message.reply_text(WELCOME_MESSAGE)
    
    # Генерируем кейс
    try:
        client_case = await call_openai(CASE_GENERATION_PROMPT, 'Создай новый кейс')
        user_data[user_id]['client_case'] = client_case
        user_data[user_id]['chat_state'] = 'waiting_question'
        await update.message.reply_text(client_case)
    except Exception as e:
        logger.error(f"Ошибка генерации кейса: {e}")
        await update.message.reply_text('Произошла ошибка при генерации кейса. Попробуйте позже.')

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса обратной связи"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if not user['last_question_type']:
        await update.message.reply_text('Сначала задайте вопрос клиенту.')
        return
    
    feedback_prompt = f"""Вы наставник SPIN-продаж. Проанализируйте ситуацию и дайте обратную связь:

Тип последнего вопроса: {user['last_question_type']}
Количество заданных вопросов: {user['question_count']}
Текущий уровень ясности: {user['clarity_level']}%

Типы уже заданных вопросов:
- Ситуационных: {user['situational_q']}
- Проблемных: {user['problem_q']}  
- Извлекающих: {user['implication_q']}
- Направляющих: {user['need_payoff_q']}

Дайте:
1. Оценку корректности последнего вопроса (0-100%)
2. Совет по улучшению формулировки
3. Пример следующего вопроса подходящего типа для продвижения диалога"""

    try:
        feedback = await call_openai(feedback_prompt, 'Проанализируй ситуацию')
        await update.message.reply_text(f"""📊 ОБРАТНАЯ СВЯЗЬ ОТ НАСТАВНИКА:

{feedback}

Теперь попробуйте задать улучшенный вопрос.""")
    except Exception as e:
        logger.error(f"Ошибка получения обратной связи: {e}")
        await update.message.reply_text('Ошибка получения обратной связи. Продолжайте задавать вопросы.')

async def send_final_report(update: Update, user: Dict[str, Any]):
    """Отправка финального отчета"""
    total_score = user['situational_q'] * 10 + user['problem_q'] * 15 + user['implication_q'] * 25 + user['need_payoff_q'] * 20
    
    if total_score <= 100:
        badge = '🥉 Начинающий искатель'
    elif total_score <= 200:
        badge = '🥈 Наставник-студент'
    elif total_score <= 300:
        badge = '🥇 Стратег SPIN'
    else:
        badge = '🏆 Маэстро SPIN-продаж'
    
    recommendations = []
    if user['situational_q'] > user['problem_q'] * 2:
        recommendations.append('• Сокращайте количество ситуационных вопросов')
    if user['problem_q'] == 0:
        recommendations.append('• Обязательно задавайте проблемные вопросы для выявления потребностей')
    if user['implication_q'] == 0:
        recommendations.append('• Используйте извлекающие вопросы для развития проблем')
    if user['need_payoff_q'] == 0:
        recommendations.append('• Добавьте направляющие вопросы для обсуждения выгод решения')
    if user['clarity_level'] < 50:
        recommendations.append('• Глубже исследуйте потребности клиента')
    
    recommendations_text = '\n'.join(recommendations) if recommendations else '• Отличная работа! Все типы вопросов использованы правильно.'
    
    report = f"""🏁 ТРЕНИРОВКА ЗАВЕРШЕНА!

📊 РЕЗУЛЬТАТЫ:
Задано вопросов: {user['question_count']}/10
Уровень ясности: {user['clarity_level']}%

📈 ПО ТИПАМ:
🔍 Ситуационных: {user['situational_q']}
⚠️ Проблемных: {user['problem_q']}
💥 Извлекающих: {user['implication_q']}  
✨ Направляющих: {user['need_payoff_q']}

🏅 Ваш результат: {badge}
Общий балл: {total_score}

💡 РЕКОМЕНДАЦИИ:
{recommendations_text}

🚀 ПОЛЕЗНЫЙ КОНТЕНТ ПО ПРОДЖАМ И ИИ:
и новые боты в будущем вы сможете найти на канале @TaktikaKutuzova

🎯 Для новой тренировки напишите "начать" """

    await update.message.reply_text(report)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    if message_text.lower() in ['начать', 'старт']:
        await start_command(update, context)
        return
    
    if message_text.upper() == 'ДА':
        await handle_feedback(update, context)
        return
    
    if message_text.lower() == 'завершить':
        user = get_user_data(user_id)
        await send_final_report(update, user)
        if user_id in user_data:
            del user_data[user_id]
        return
    
    if len(message_text) <= 5:
        await update.message.reply_text('Задайте более развернутый вопрос клиенту или напишите "начать" для новой тренировки.')
        return
    
    user = get_user_data(user_id)
    
    if user['question_count'] >= 10:
        await send_final_report(update, user)
        if user_id in user_data:
            del user_data[user_id]
        return
    
    try:
        # Определяем тип вопроса
        question_type = analyze_question_type(message_text)
        
        # Обновляем счетчики
        user['question_count'] += 1
        user['last_question_type'] = question_type
        
        if question_type == 'Ситуационный':
            user['situational_q'] += 1
            user['clarity_level'] += 10
        elif question_type == 'Проблемный':
            user['problem_q'] += 1
            user['clarity_level'] += 15
        elif question_type == 'Извлекающий':
            user['implication_q'] += 1
            user['clarity_level'] += 25
        elif question_type == 'Направляющий':
            user['need_payoff_q'] += 1
            user['clarity_level'] += 20
        
        user['clarity_level'] = min(user['clarity_level'], 100)
        
        # Генерируем ответ клиента
        client_prompt = f"""Вы клиент из кейса: {user['client_case']}

Отвечайте нейтрально и сдержанно. НЕ раскрывайте проблемы сами - только на конкретные СПИН-вопросы. 

Принципы ответов:
- На ситуационные вопросы: давайте факты
- На проблемные: признавайте проблемы, но не драматизируйте
- На извлекающие: раскрывайте последствия постепенно
- На направляющие: подтверждайте ценность решений

Отвечайте коротко, реалистично, как настоящий занятой руководитель."""

        client_response = await call_openai(client_prompt, f"Вопрос: {message_text}")
        
        # Проверяем условия завершения
        if user['question_count'] >= 10 or user['clarity_level'] >= 80:
            if user['clarity_level'] >= 80 and user['question_count'] >= 5:
                await update.message.reply_text(f"""Был задан {question_type} вопрос

{client_response}

🏁 Достигнута ясность {user['clarity_level']}%. Завершить тренировку? (напишите "завершить" или продолжайте задавать вопросы)""")
            elif user['question_count'] >= 10:
                await send_final_report(update, user)
                if user_id in user_data:
                    del user_data[user_id]
            else:
                await update.message.reply_text(f"""Был задан {question_type} вопрос

{client_response}

Если нужна обратная связь от наставника — напишите ДА. Для завершения напишите "завершить". Если готовы к следующему вопросу — продолжайте.

📊 Прогресс: {user['question_count']}/10 вопросов, ясность {user['clarity_level']}%""")
        else:
            await update.message.reply_text(f"""Был задан {question_type} вопрос

{client_response}

Если нужна обратная связь от наставника — напишите ДА. Для завершения напишите "завершить". Если готовы к следующему вопросу — продолжайте.

📊 Прогресс: {user['question_count']}/10 вопросов, ясность {user['clarity_level']}%""")
    
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text('Произошла ошибка. Попробуйте еще раз.')

def main():
    """Запуск бота"""
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    logger.info("SPIN Training Bot запущен!")
    application.run_polling()
    
    # Запускаем бота в фоне
    import asyncio
    import threading
    
    def run_bot():
        asyncio.run(application.run_polling())
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем простой веб-сервер для health checks
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import socket
    
    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'OK')
            else:
                self.send_response(404)
                self.end_headers()
        
        def log_message(self, format, *args):
            # Отключаем логирование HTTP запросов
            pass
    
    # Находим свободный порт
    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    port = int(os.getenv('PORT', 8080))
    
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server запущен на порту {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Ошибка запуска health check сервера: {e}")
        # Если не удалось запустить веб-сервер, просто запускаем бота
        application.run_polling()

if __name__ == '__main__':
    main()
