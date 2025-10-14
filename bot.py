import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import httpx

from engine.scenario_loader import ScenarioLoader, ScenarioValidationError
from engine.question_analyzer import QuestionAnalyzer
from engine.report_generator import ReportGenerator

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SCENARIO_PATH = os.getenv('SCENARIO_PATH', 'scenarios/spin_sales/config.json')

# Отладочная информация
print(f"BOT_TOKEN: {BOT_TOKEN}")
print(f"OPENAI_API_KEY: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else 'None'}...")
print(f"SCENARIO_PATH: {SCENARIO_PATH}")

# Хранилище данных пользователей
user_data: Dict[int, Dict[str, Any]] = {}

# Глобальные объекты сценария и движка
scenario_loader = ScenarioLoader()
question_analyzer = QuestionAnalyzer()
report_generator = ReportGenerator()
scenario_config: Optional[Dict[str, Any]] = None

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
    
def _ensure_scenario_loaded() -> Dict[str, Any]:
    global scenario_config
    if scenario_config is None:
        try:
            loaded = scenario_loader.load_scenario(SCENARIO_PATH)
            scenario_config = loaded.config
        except (FileNotFoundError, ScenarioValidationError) as e:
            logger.error(f"Ошибка загрузки сценария: {e}")
            raise
    return scenario_config

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    print(f"🚀 Команда /start вызвана пользователем {update.effective_user.id}")
    user_id = update.effective_user.id
    
    # Инициализация данных пользователя
    cfg = _ensure_scenario_loaded()
    rules = cfg["game_rules"]
    user_data[user_id] = {
        'question_count': 0,
        'clarity_level': 0,
        'per_type_counts': {t['id']: 0 for t in cfg['question_types']},
        'client_case': '',
        'last_question_type': '',
        'chat_state': 'started'
    }
    
    await update.message.reply_text(scenario_loader.get_message('welcome'))
    
    # Генерируем кейс
    try:
        system_prompt = scenario_loader.get_prompt('case_generation')
        client_case = await call_openai(system_prompt, 'Создай новый кейс')
        user_data[user_id]['client_case'] = client_case
        user_data[user_id]['chat_state'] = 'waiting_question'
        await update.message.reply_text(
            scenario_loader.get_message('case_generated', client_case=client_case)
        )
    except Exception as e:
        logger.error(f"Ошибка генерации кейса: {e}")
        await update.message.reply_text(scenario_loader.get_message('error_generic'))

async def scenario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о текущем сценарии."""
    try:
        cfg = _ensure_scenario_loaded()
        info = cfg.get('scenario_info', {})
        await update.message.reply_text(
            f"Сценарий: {info.get('name')} v{info.get('version')}\nОписание: {info.get('description')}\nПуть: {SCENARIO_PATH}"
        )
    except Exception as e:
        logger.error(f"Ошибка отображения сценария: {e}")
        await update.message.reply_text("Ошибка получения информации о сценарии.")

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка запроса обратной связи"""
    user_id = update.effective_user.id
    user = get_user_data(user_id)
    
    if not user['last_question_type']:
        await update.message.reply_text('Сначала задайте вопрос клиенту.')
        return
    
    cfg = _ensure_scenario_loaded()
    # Map legacy counters for prompt
    situational_q = user['per_type_counts'].get('situational', 0)
    problem_q = user['per_type_counts'].get('problem', 0)
    implication_q = user['per_type_counts'].get('implication', 0)
    need_payoff_q = user['per_type_counts'].get('need_payoff', 0)
    feedback_prompt = scenario_loader.get_prompt(
        'feedback',
        last_question_type=user['last_question_type'],
        question_count=user['question_count'],
        clarity_level=user['clarity_level'],
        situational_q=situational_q,
        problem_q=problem_q,
        implication_q=implication_q,
        need_payoff_q=need_payoff_q,
    )

    try:
        feedback = await call_openai(feedback_prompt, 'Проанализируй ситуацию')
        await update.message.reply_text(
            f"📊 ОБРАТНАЯ СВЯЗЬ ОТ НАСТАВНИКА:\n\n{feedback}\n\nТеперь попробуйте задать улучшенный вопрос."
        )
    except Exception as e:
        logger.error(f"Ошибка получения обратной связи: {e}")
        await update.message.reply_text(scenario_loader.get_message('error_generic'))

async def send_final_report(update: Update, user: Dict[str, Any]):
<<<<<<< HEAD
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
вы сможете найти на канале [Тактика Кутузова](https://t.me/TaktikaKutuzova)

🎯 Для новой тренировки напишите "начать" """

=======
    """Отправка финального отчета (универсально)."""
    cfg = _ensure_scenario_loaded()
    # Подсчет очков через анализатор, используя конфиг
    user['total_score'] = QuestionAnalyzer().calculate_score(user, cfg['question_types'])
    report = ReportGenerator().generate_final_report(user, cfg)
>>>>>>> c0edbca (Refactor: convert to universal training-bot constructor (engine, scenarios, docs))
    await update.message.reply_text(report)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text
    cfg = _ensure_scenario_loaded()
    rules = cfg['game_rules']
    
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
    
    if len(message_text) <= rules.get('short_question_threshold', 5):
        await update.message.reply_text('Задайте более развернутый вопрос клиенту или напишите "начать" для новой тренировки.')
        return
    
    user = get_user_data(user_id)
    
    if user['question_count'] >= rules['max_questions']:
        await send_final_report(update, user)
        if user_id in user_data:
            del user_data[user_id]
        return
    
    try:
        # Определяем тип вопроса из конфига
        qtype = question_analyzer.analyze_type(message_text, cfg['question_types'])
        question_type_name = qtype.get('name', qtype.get('id'))
        
        # Обновляем счетчики
        user['question_count'] += 1
        user['last_question_type'] = question_type_name

        qid = qtype.get('id')
        user['per_type_counts'][qid] = int(user['per_type_counts'].get(qid, 0)) + 1
        user['clarity_level'] += question_analyzer.calculate_clarity_increase(qtype)
        
        user['clarity_level'] = min(user['clarity_level'], 100)
        
        # Генерируем ответ клиента
        client_prompt = scenario_loader.get_prompt('client_response', client_case=user['client_case'])
        client_response = await call_openai(client_prompt, f"Вопрос: {message_text}")
        
        # Проверяем условия завершения
        if user['question_count'] >= rules['max_questions'] or user['clarity_level'] >= rules['target_clarity']:
            if user['clarity_level'] >= rules['target_clarity'] and user['question_count'] >= rules['min_questions_for_completion']:
                await update.message.reply_text(
                    scenario_loader.get_message(
                        'question_feedback',
                        question_type=question_type_name,
                        client_response=client_response,
                        progress_line=scenario_loader.get_message(
                            'progress', count=user['question_count'], max=rules['max_questions'], clarity=user['clarity_level']
                        )
                    )
                )
                await update.message.reply_text(
                    scenario_loader.get_message('clarity_reached', clarity=user['clarity_level'])
                )
            elif user['question_count'] >= rules['max_questions']:
                await send_final_report(update, user)
                if user_id in user_data:
                    del user_data[user_id]
            else:
                await update.message.reply_text(
                    scenario_loader.get_message(
                        'question_feedback',
                        question_type=question_type_name,
                        client_response=client_response,
                        progress_line=scenario_loader.get_message(
                            'progress', count=user['question_count'], max=rules['max_questions'], clarity=user['clarity_level']
                        )
                    )
                )
        else:
            await update.message.reply_text(
                scenario_loader.get_message(
                    'question_feedback',
                    question_type=question_type_name,
                    client_response=client_response,
                    progress_line=scenario_loader.get_message(
                        'progress', count=user['question_count'], max=rules['max_questions'], clarity=user['clarity_level']
                    )
                )
            )
    
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text(scenario_loader.get_message('error_generic'))

def main():
    """Запуск бота"""
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Предварительная загрузка сценария с обработкой ошибок
    try:
        _ensure_scenario_loaded()
    except Exception:
        logger.exception("Критическая ошибка загрузки сценария. Проверьте SCENARIO_PATH и формат config.json")
        # Продолжаем запускать бота, но команды будут возвращать ошибки при обращении к сценарию
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("scenario", scenario_command))
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
