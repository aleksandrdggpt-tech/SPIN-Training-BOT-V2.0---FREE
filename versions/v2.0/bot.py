import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import time
import openai
import httpx

from engine.scenario_loader import ScenarioLoader, ScenarioValidationError
from engine.question_analyzer import QuestionAnalyzer
from engine.report_generator import ReportGenerator
from engine.case_generator import CaseGenerator

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SCENARIO_PATH = os.getenv('SCENARIO_PATH', 'scenarios/spin_sales/config.json')

# LLM config
PRIMARY_MODEL = os.getenv('PRIMARY_MODEL', 'gpt-4o-mini')
FALLBACK_MODEL = os.getenv('FALLBACK_MODEL', 'gpt-5-mini')
LLM_TIMEOUT_SEC = float(os.getenv('LLM_TIMEOUT_SEC', '30'))
LLM_MAX_RETRIES = int(os.getenv('LLM_MAX_RETRIES', '1'))

# Dual-pipeline configs (response/feedback)
RESPONSE_PRIMARY_PROVIDER = os.getenv('RESPONSE_PRIMARY_PROVIDER', 'openai')
RESPONSE_PRIMARY_MODEL = os.getenv('RESPONSE_PRIMARY_MODEL', PRIMARY_MODEL)
RESPONSE_FALLBACK_PROVIDER = os.getenv('RESPONSE_FALLBACK_PROVIDER', 'openai')
RESPONSE_FALLBACK_MODEL = os.getenv('RESPONSE_FALLBACK_MODEL', FALLBACK_MODEL)

FEEDBACK_PRIMARY_PROVIDER = os.getenv('FEEDBACK_PRIMARY_PROVIDER', 'openai')
FEEDBACK_PRIMARY_MODEL = os.getenv('FEEDBACK_PRIMARY_MODEL', PRIMARY_MODEL)
FEEDBACK_FALLBACK_PROVIDER = os.getenv('FEEDBACK_FALLBACK_PROVIDER', 'openai')
FEEDBACK_FALLBACK_MODEL = os.getenv('FEEDBACK_FALLBACK_MODEL', FALLBACK_MODEL)

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Classification pipeline
CLASSIFICATION_PRIMARY_PROVIDER = os.getenv('CLASSIFICATION_PRIMARY_PROVIDER', 'openai')
CLASSIFICATION_PRIMARY_MODEL = os.getenv('CLASSIFICATION_PRIMARY_MODEL', PRIMARY_MODEL)
CLASSIFICATION_FALLBACK_PROVIDER = os.getenv('CLASSIFICATION_FALLBACK_PROVIDER', 'openai')
CLASSIFICATION_FALLBACK_MODEL = os.getenv('CLASSIFICATION_FALLBACK_MODEL', FALLBACK_MODEL)

# Отладочная информация
print(f"BOT_TOKEN: {BOT_TOKEN}")
print(f"OPENAI_API_KEY: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else 'None'}...")
print(f"SCENARIO_PATH: {SCENARIO_PATH}")
print(f"PRIMARY_MODEL: {PRIMARY_MODEL}")
print(f"FALLBACK_MODEL: {FALLBACK_MODEL}")
print(f"RESP PIPE: {RESPONSE_PRIMARY_PROVIDER}:{RESPONSE_PRIMARY_MODEL} -> {RESPONSE_FALLBACK_PROVIDER}:{RESPONSE_FALLBACK_MODEL}")
print(f"FDBK PIPE: {FEEDBACK_PRIMARY_PROVIDER}:{FEEDBACK_PRIMARY_MODEL} -> {FEEDBACK_FALLBACK_PROVIDER}:{FEEDBACK_FALLBACK_MODEL}")
print(f"CLSF PIPE: {CLASSIFICATION_PRIMARY_PROVIDER}:{CLASSIFICATION_PRIMARY_MODEL} -> {CLASSIFICATION_FALLBACK_PROVIDER}:{CLASSIFICATION_FALLBACK_MODEL}")

# Хранилище данных пользователей
user_data: Dict[int, Dict[str, Any]] = {}

# Глобальные объекты сценария и движка
scenario_loader = ScenarioLoader()
question_analyzer = QuestionAnalyzer()
report_generator = ReportGenerator()
case_generator: Optional[CaseGenerator] = None
scenario_config: Optional[Dict[str, Any]] = None

def get_user_data(user_id: int) -> Dict[str, Any]:
    """Получение данных пользователя c инициализацией session/stats."""
    if user_id not in user_data:
        user_data[user_id] = {
            'session': {
                'question_count': 0,
                'clarity_level': 0,
                'per_type_counts': {},
                'client_case': '',
                'case_data': None,  # Сохраним данные кейса
                'last_question_type': '',
                'chat_state': 'new',
                'contextual_questions': 0,
                'last_client_response': '',
                'context_streak': 0
            },
            'stats': {
                'total_trainings': 0,
                'total_questions': 0,
                'best_score': 0,
                'total_xp': 0,
                'current_level': 1,
                'badges_earned': [],
                'achievements_unlocked': [],
                'master_streak': 0,
                'total_contextual_questions': 0,
                'last_contextual_questions': 0,
                'last_training_date': None,
                'recent_cases': []  # Хеши последних 5 кейсов
            }
        }
    return user_data[user_id]

def reset_session(user_id: int) -> None:
    """Очистка данных текущей сессии и возврат в ожидание старта."""
    u = get_user_data(user_id)
    cfg = _ensure_scenario_loaded()
    u['session'] = {
        'question_count': 0,
        'clarity_level': 0,
        'per_type_counts': {t['id']: 0 for t in cfg['question_types']},
        'client_case': '',
        'case_data': None,  # Очищаем данные кейса
        'last_question_type': '',
        'chat_state': 'waiting_start'
    }

def update_stats(user_id: int, session_score: int) -> None:
    """Обновление общей статистики пользователя на основе завершенной сессии."""
    u = get_user_data(user_id)
    s = u['session']
    st = u['stats']
    
    # Базовая статистика
    st['total_trainings'] += 1
    st['total_questions'] += int(s.get('question_count', 0))
    st['best_score'] = max(int(st.get('best_score', 0)), int(session_score))
    st['last_training_date'] = datetime.now().isoformat()
    
    # XP и уровень
    st['total_xp'] = int(st.get('total_xp', 0)) + int(session_score)
    cfg = _ensure_scenario_loaded()
    old_level = int(st.get('current_level', 1))
    new_level = _calculate_level(int(st['total_xp']), cfg.get('ranking', {}).get('levels', []))
    st['current_level'] = new_level
    
    # Серия Маэстро
    if int(session_score) >= 221:
        st['master_streak'] = int(st.get('master_streak', 0)) + 1
    else:
        st['master_streak'] = 0
    
    # Контекстуальные вопросы: обновляем общие показатели
    last_contextual = int(s.get('contextual_questions', 0))
    st['last_contextual_questions'] = last_contextual
    st['total_contextual_questions'] = int(st.get('total_contextual_questions', 0)) + last_contextual

    # Достижения (включая Active Listening)
    _check_achievements(user_id)
    
    # Лог об уровне
    if new_level > old_level:
        logger.info(f"🎉 Пользователь {user_id} повысил уровень: {old_level} → {new_level}")
        # Сохраняем информацию для показа пользователю
        st['level_up_notification'] = {
            'old_level': old_level,
            'new_level': new_level,
            'should_show': True
        }

def _calculate_level(xp: int, levels: List[Dict]) -> int:
    """Определение уровня по опыту"""
    try:
        for lvl in sorted(levels, key=lambda l: int(l.get('min_xp', 0))):
            if xp < int(lvl.get('min_xp', 0)):
                break
        # Найти максимальный уровень, чей min_xp <= xp
        eligible = [int(l.get('level', 1)) for l in levels if xp >= int(l.get('min_xp', 0))]
        return max(eligible) if eligible else 1
    except Exception:
        return 1

def _check_achievements(user_id: int):
    """Проверка и разблокировка достижений"""
    u = get_user_data(user_id)
    st = u['stats']
    cfg = _ensure_scenario_loaded()
    achievements = cfg.get('achievements', {}).get('list', [])
    
    newly_unlocked = []
    for ach in achievements:
        if ach.get('id') in st.get('achievements_unlocked', []):
            continue
        condition = ach.get('condition', '')
        try:
            if eval(condition, {"__builtins__": {}}, st):
                st['achievements_unlocked'].append(ach['id'])
                newly_unlocked.append(ach)
                logger.info(f"🎖️ Достижение разблокировано: {ach.get('name')}")
        except Exception as e:
            logger.error(f"Ошибка проверки достижения {ach.get('id')}: {e}")
    return newly_unlocked

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам бота"""
    help_text = """📖 ДОСТУПНЫЕ КОМАНДЫ:

🎯 Основные:
/start - Начать новую тренировку
/stats - Ваша общая статистика
/rank - Детальная информация о ранге и достижениях
/case - Информация о текущем кейсе

🔧 Дополнительные:
/scenario - Информация о сценарии
/validate - Проверка конфигурации (для разработчиков)
/help - Показать эту справку

💬 Команды в чате:
• "начать" или "старт" - начать тренировку
• "ДА" - получить обратную связь от наставника
• "завершить" - завершить текущую тренировку

❓ Есть вопросы? Просто начните тренировку командой /start!"""
    
    await update.message.reply_text(help_text)

def log_case_statistics(user_id: int):
    """Логирование статистики сгенерированных кейсов"""
    user = user_data.get(user_id)
    if not user or not user['session'].get('case_data'):
        return
    
    case_data = user['session']['case_data']
    logger.info(f"""
    === СТАТИСТИКА КЕЙСА ===
    User ID: {user_id}
    Должность: {case_data['position']}
    Компания: {case_data['company']['type']}
    Размер: {case_data['company_size']}
    Продукт: {case_data['product']['name']}
    Объём: {case_data['volume']}
    Тип ситуации: {case_data['situation']['type']}
    ========================
    """)

async def call_llm(kind: str, system_prompt: str, user_message: str) -> str:
    """Вызов LLM по конвейеру kind ('response'|'feedback') с фолбэком и провайдерами."""
    assert kind in ('response', 'feedback', 'classification', 'context')

    if kind == 'response':
        primary_provider = RESPONSE_PRIMARY_PROVIDER
        primary_model = RESPONSE_PRIMARY_MODEL
        fallback_provider = RESPONSE_FALLBACK_PROVIDER
        fallback_model = RESPONSE_FALLBACK_MODEL
    elif kind == 'feedback':
        primary_provider = FEEDBACK_PRIMARY_PROVIDER
        primary_model = FEEDBACK_PRIMARY_MODEL
        fallback_provider = FEEDBACK_FALLBACK_PROVIDER
        fallback_model = FEEDBACK_FALLBACK_MODEL
    else:
        primary_provider = CLASSIFICATION_PRIMARY_PROVIDER
        primary_model = CLASSIFICATION_PRIMARY_MODEL
        fallback_provider = CLASSIFICATION_FALLBACK_PROVIDER
        fallback_model = CLASSIFICATION_FALLBACK_MODEL

    async def _invoke_openai(model_name: str) -> str:
        client = openai.AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(LLM_TIMEOUT_SEC),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1)
            )
        )
        # Для части моделей (напр. gpt-5-*) параметр max_tokens не поддерживается
        openai_payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.0 if kind == 'classification' else 0.7,
        }
        if str(model_name).startswith("gpt-5"):
            openai_payload["max_completion_tokens"] = 20 if kind == 'classification' else 400
            logger.info(f"OpenAI payload (gpt-5*): keys={list(openai_payload.keys())}")
        else:
            openai_payload["max_tokens"] = 20 if kind == 'classification' else 400
            logger.info(f"OpenAI payload: keys={list(openai_payload.keys())}")
        try:
            resp = await client.chat.completions.create(**openai_payload)
        except Exception as e:
            logger.error(f"OpenAI request failed model={model_name} keys={list(openai_payload.keys())} error={e}")
            raise
        return resp.choices[0].message.content.strip()

    async def _invoke_anthropic(model_name: str) -> str:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("Anthropic API key not set")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model_name,
            "max_tokens": 10 if kind == 'context' else (20 if kind == 'classification' else 400),
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "temperature": 0.0 if kind in ('classification','context') else 0.7
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(LLM_TIMEOUT_SEC)) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            # content: [{"type":"text","text":"..."}, ...]
            content = data.get('content', [])
            if content and isinstance(content, list) and 'text' in content[0]:
                return content[0]['text'].strip()
            raise RuntimeError("Anthropic response format unexpected")

    async def _invoke(provider: str, model: str) -> str:
        if provider == 'openai':
            return await _invoke_openai(model)
        elif provider == 'anthropic':
            return await _invoke_anthropic(model)
        else:
            raise RuntimeError(f"Unknown provider: {provider}")

    # Primary with retries
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            logger.info(f"LLM primary: {kind} provider={primary_provider} model={primary_model} attempt={attempt+1}")
            return await _invoke(primary_provider, primary_model)
        except Exception as e:
            logger.warning(f"Primary failed ({kind}): {type(e).__name__}: {e}")
            if attempt < LLM_MAX_RETRIES:
                continue
    # Fallback
    try:
        logger.info(f"LLM fallback: {kind} provider={fallback_provider} model={fallback_model}")
        return await _invoke(fallback_provider, fallback_model)
    except Exception as e:
        logger.error(f"Fallback failed ({kind}): {type(e).__name__}: {e}")
        return "Произошла ошибка при генерации ответа. Попробуйте ещё раз позже."
    
def _ensure_scenario_loaded() -> Dict[str, Any]:
    global scenario_config, case_generator
    if scenario_config is None:
        try:
            loaded = scenario_loader.load_scenario(SCENARIO_PATH)
            scenario_config = loaded.config
            
            # Инициализируем CaseGenerator если есть case_variants
            if 'case_variants' in scenario_config and case_generator is None:
                case_generator = CaseGenerator(scenario_config['case_variants'])
                logger.info("CaseGenerator инициализирован")
                
        except (FileNotFoundError, ScenarioValidationError) as e:
            logger.error(f"Ошибка загрузки сценария: {e}")
            raise
    return scenario_config

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    print(f"🚀 Команда /start вызвана пользователем {update.effective_user.id}")
    user_id = update.effective_user.id
    
    # Инициализируем и переводим в ожидание старта
    cfg = _ensure_scenario_loaded()
    reset_session(user_id)
    
    # Отправляем ТОЛЬКО приветствие
    welcome_message = scenario_loader.get_message('welcome')
    await update.message.reply_text(welcome_message)

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
    
    session = user['session']
    if not session['last_question_type']:
        await update.message.reply_text('Сначала задайте вопрос клиенту.')
        return
    
    cfg = _ensure_scenario_loaded()
    # Counters by type from current session
    per_type = session.get('per_type_counts', {})
    situational_q = int(per_type.get('situational', 0))
    problem_q = int(per_type.get('problem', 0))
    implication_q = int(per_type.get('implication', 0))
    need_payoff_q = int(per_type.get('need_payoff', 0))
    feedback_prompt = scenario_loader.get_prompt(
        'feedback',
        last_question_type=session['last_question_type'],
        question_count=session['question_count'],
        clarity_level=session['clarity_level'],
        situational_q=situational_q,
        problem_q=problem_q,
        implication_q=implication_q,
        need_payoff_q=need_payoff_q,
    )

    try:
        feedback = await call_llm('feedback', feedback_prompt, 'Проанализируй ситуацию')
        await update.message.reply_text(
            f"📊 ОБРАТНАЯ СВЯЗЬ ОТ НАСТАВНИКА:\n\n{feedback}\n\nТеперь попробуйте задать улучшенный вопрос."
        )
    except Exception as e:
        logger.error(f"Ошибка получения обратной связи: {e}")
        await update.message.reply_text(scenario_loader.get_message('error_generic'))

async def send_final_report(update: Update, user: Dict[str, Any]):
    """Отправка финального отчета (универсально)."""
    cfg = _ensure_scenario_loaded()
    session = user['session']
    case_data = session.get('case_data')

    # Подсчет очков через анализатор, используя конфиг
    temp_user = {
        'question_count': session['question_count'],
        'clarity_level': session['clarity_level'],
        'per_type_counts': session['per_type_counts'],
    }
    temp_user['total_score'] = QuestionAnalyzer().calculate_score(session, cfg['question_types'])

    # Генерируем базовый отчёт
    report = ReportGenerator().generate_final_report(temp_user, cfg)

    # Добавляем информацию о кейсе
    case_info = ""
    if case_data:
        case_info = f"""
📋 ИНФОРМАЦИЯ О КЕЙСЕ:
Должность: {case_data['position']}
Компания: {case_data['company']['type']}
Продукт: {case_data['product']['name']}
Объём: {case_data['volume']}
"""

    # Общая статистика пользователя
    stats = user['stats']
    stats_info = f"""
📈 ВАША ОБЩАЯ СТАТИСТИКА:
Пройдено тренировок: {stats['total_trainings']}
Всего вопросов задано: {stats['total_questions']}
Лучший результат: {stats['best_score']} баллов
"""

    # НОВОЕ: Ранг и достижения
    levels = cfg.get('ranking', {}).get('levels', [])
    stats = user['stats']
    current_level_data = next((l for l in levels if l.get('level') == stats.get('current_level', 1)), (levels[0] if levels else {'level': 1, 'name': 'Новичок', 'emoji': '🌱', 'min_xp': 0, 'description': ''}))
    next_level_data = next((l for l in levels if l.get('level') == stats.get('current_level', 1) + 1), None)
    xp_progress = ""
    if next_level_data:
        current_xp = int(stats.get('total_xp', 0))
        xp_to_next = int(next_level_data.get('min_xp', 0)) - current_xp
        if xp_to_next > 0:
            xp_progress = f"\nДо следующего уровня: {xp_to_next} XP"
    rank_info = f"""
⭐ ВАШ РАНГ:
{current_level_data.get('emoji', '')} Уровень {current_level_data.get('level', 1)}: {current_level_data.get('name', '')}
Опыт (XP): {stats.get('total_xp', 0)}{xp_progress}
{current_level_data.get('description', '')}

💡 Используйте /rank для детального просмотра прогресса и достижений
"""

    # Проверка повышения уровня
    level_up_msg = ""
    if stats.get('level_up_notification', {}).get('should_show'):
        notif = stats['level_up_notification']
        level_data = next((l for l in levels if l.get('level') == notif['new_level']), None)
        level_emoji = level_data.get('emoji', '🎉') if level_data else '🎉'
        level_name = level_data.get('name', '') if level_data else ''
        level_up_msg = f"\n\n🎊 ПОЗДРАВЛЯЕМ! ВЫ ПОВЫСИЛИ УРОВЕНЬ!\n{level_emoji} Уровень {notif['old_level']} → Уровень {notif['new_level']}: {level_name}\n\nИспользуйте /rank для подробностей\n"
        stats['level_up_notification']['should_show'] = False

    newly_unlocked = _check_achievements(update.effective_user.id)
    achievements_info = ""
    if newly_unlocked:
        achievements_info = "\n\n🎖️ НОВЫЕ ДОСТИЖЕНИЯ:\n" + "\n".join(
            f"{ach.get('emoji', '')} {ach.get('name', '')} - {ach.get('description', '')}"
            for ach in newly_unlocked
        )

    # Активное слушание — статистика
    contextual_q = int(user['session'].get('contextual_questions', 0))
    qcount = int(user['session'].get('question_count', 0))
    contextual_pct = int((contextual_q / qcount) * 100) if qcount > 0 else 0
    listening_section = f"""
👂 АКТИВНОЕ СЛУШАНИЕ:
Контекстуальных вопросов: {contextual_q}/{qcount} ({contextual_pct}%)
"""
    if contextual_pct >= 70:
        listening_section += "🏆 Отлично! Вы внимательно слушаете клиента!\n"
    elif contextual_pct >= 40:
        listening_section += "💡 Хорошо, но можно чаще использовать факты из ответов\n"
    else:
        listening_section += "⚠️ Совет: стройте вопросы на основе ответов клиента\n"

    # Объединяем отчёт с дополнительной информацией
    full_report = f"{report}{case_info}{stats_info}{listening_section}{rank_info}{level_up_msg}{achievements_info}\n\n🎯 Для новой тренировки напишите \"начать\" или используйте /help для справки"
    await update.message.reply_text(full_report)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text
    cfg = _ensure_scenario_loaded()
    rules = cfg['game_rules']
    
    # Обработка запуска тренировки из состояния ожидания
    u = get_user_data(user_id)
    sess = u['session']
    if sess.get('chat_state') == 'waiting_start':
        if message_text.lower() in ['начать', 'старт']:
            # ГЕНЕРИРУЕМ КЕЙС ЗДЕСЬ
            try:
                # Получаем список недавних кейсов для исключения повторов
                recent_cases = u['stats'].get('recent_cases', [])
                
                # Генерируем случайный уникальный кейс
                case_data = case_generator.generate_random_case(exclude_recent=recent_cases)
                
                # Сохраняем данные кейса
                sess['case_data'] = case_data
                
                # Генерируем кейс напрямую без GPT (мгновенно)
                client_case = case_generator.build_case_direct(case_data)
                
                # Сохраняем сгенерированный кейс
                sess['client_case'] = client_case
                sess['chat_state'] = 'training_active'
                
                # Добавляем хеш кейса в историю
                case_hash = case_generator._get_case_hash(case_data)
                recent_cases.append(case_hash)
                if len(recent_cases) > 5:
                    recent_cases.pop(0)
                u['stats']['recent_cases'] = recent_cases
                
                # Логируем статистику кейса сразу после генерации
                log_case_statistics(user_id)
                logger.info(f"""
                === КЕЙС СГЕНЕРИРОВАН МГНОВЕННО ===
                Метод: Прямая подстановка (без GPT)
                User ID: {user_id}
                Должность: {case_data['position']}
                Компания: {case_data['company']['type']}
                Продукт: {case_data['product']['name']}
                Время генерации: < 0.001 сек
                ====================================
                """)

                # Отправляем кейс пользователю
                await update.message.reply_text(client_case)
                
            except Exception as e:
                logger.error(f"Ошибка генерации кейса: {e}")
                await update.message.reply_text('Произошла ошибка при генерации кейса. Попробуйте ещё раз написать "начать".')
            return
        else:
            await update.message.reply_text('Напишите "начать" для старта тренировки')
            return
    
    if message_text.upper() == 'ДА':
        await handle_feedback(update, context)
        return
    
    if message_text.lower() == 'завершить':
        user = get_user_data(user_id)
        cfg = _ensure_scenario_loaded()
        
        # 1️⃣ Сначала обновляем статистику
        total_score = QuestionAnalyzer().calculate_score(user['session'], cfg['question_types'])
        update_stats(user_id, total_score)
        
        # 2️⃣ Потом показываем отчёт
        await send_final_report(update, user)
        
        # 3️⃣ Логируем статистику кейса
        log_case_statistics(user_id)
        
        # 4️⃣ Очищаем сессию
        reset_session(user_id)
        return
    
    if len(message_text) <= rules.get('short_question_threshold', 5):
        await update.message.reply_text('Задайте более развернутый вопрос клиенту или напишите "начать" для новой тренировки.')
        return
    
    user = get_user_data(user_id)
    session = user['session']
    
    if session['question_count'] >= rules['max_questions']:
        cfg = _ensure_scenario_loaded()
        # 1️⃣ Сначала обновляем статистику
        total_score = QuestionAnalyzer().calculate_score(session, cfg['question_types'])
        update_stats(user_id, total_score)
        # 2️⃣ Потом показываем отчёт
        await send_final_report(update, user)
        # 3️⃣ Логируем статистику кейса
        log_case_statistics(user_id)
        # 4️⃣ Очищаем сессию
        reset_session(user_id)
        return
    
    try:
        # Определяем тип вопроса из конфига
        # Классификация через LLM с fallback
        qtype = await question_analyzer.classify_question(
            message_text,
            cfg['question_types'],
            session.get('client_case', ''),
            lambda kind, sys, usr: call_llm(kind, sys, usr),
            cfg.get('prompts', {})
        )
        question_type_name = qtype.get('name', qtype.get('id'))
        
        # Обновляем счетчики
        session['question_count'] += 1
        session['last_question_type'] = question_type_name

        qid = qtype.get('id')
        session['per_type_counts'][qid] = int(session['per_type_counts'].get(qid, 0)) + 1
        session['clarity_level'] += question_analyzer.calculate_clarity_increase(qtype)
        
        session['clarity_level'] = min(session['clarity_level'], 100)
        
        # Генерируем ответ клиента с учетом данных кейса
        case_data = session.get('case_data') or {}
        enriched_prompt = (
            f"Вы клиент из кейса со следующими параметрами:\n\n"
            f"РОЛЬ: {case_data.get('position', '')} в компании \"{(case_data.get('company') or {}).get('type', '')}\"\n"
            f"КОНТЕКСТ: {session.get('client_case', '')}\n\n"
            f"ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ:\n"
            f"- Объём закупок: {case_data.get('volume', '')}\n"
            f"- Частота: {case_data.get('frequency', '')}\n"
            f"- Количество поставщиков: {case_data.get('suppliers_count', '')}\n"
            f"- Тип ситуации: {(case_data.get('situation') or {}).get('type', '')}\n"
            f"- Характер закупки: {case_data.get('urgency', '')}\n\n"
            f"ПРИНЦИПЫ ОТВЕТОВ:\n"
            f"- Отвечайте нейтрально и сдержанно, как реальный занятой руководитель\n"
            f"- НЕ раскрывайте проблемы сами - только на конкретные SPIN-вопросы\n"
            f"- На ситуационные вопросы: давайте факты и цифры\n"
            f"- На проблемные: признавайте проблемы, но не драматизируйте\n"
            f"- На извлекающие: раскрывайте последствия постепенно, намёками\n"
            f"- На направляющие: подтверждайте ценность предложенных решений\n\n"
            f"СТИЛЬ: Короткие реалистичные ответы (2-4 предложения), профессиональный тон.\n\n"
            f"Вопрос продавца: {message_text}"
        )
        client_response = await call_llm('response', enriched_prompt, "Ответь на вопрос как клиент")

        # === Активное слушание: проверяем, использовал ли вопрос контекст прошлого ответа ===
        is_contextual = False
        last_resp = session.get('last_client_response', '')
        if last_resp:
            is_contextual = await question_analyzer.check_context_usage(
                message_text,
                last_resp,
                lambda kind, sys, usr: call_llm('context', sys, usr),
                cfg.get('prompts', {})
            )
        context_badge = ""
        if is_contextual:
            session['contextual_questions'] = int(session.get('contextual_questions', 0)) + 1
            contextual_bonus = int(cfg.get('scoring', {}).get('question_weights', {}).get('contextual_bonus', 0))
            session['clarity_level'] = min(100, session['clarity_level'] + contextual_bonus)
            context_badge = " 👂"
        # Сохраняем последний ответ клиента для следующей итерации
        session['last_client_response'] = client_response
        
        # Проверяем условия завершения
        if session['question_count'] >= rules['max_questions'] or session['clarity_level'] >= rules['target_clarity']:
            if session['clarity_level'] >= rules['target_clarity'] and session['question_count'] >= rules['min_questions_for_completion']:
                await update.message.reply_text(
                    scenario_loader.get_message(
                        'question_feedback',
                        question_type=question_type_name + context_badge,
                        client_response=client_response,
                        progress_line=scenario_loader.get_message(
                            'progress', count=session['question_count'], max=rules['max_questions'], clarity=session['clarity_level']
                        )
                    )
                )
                await update.message.reply_text(
                    scenario_loader.get_message('clarity_reached', clarity=session['clarity_level'])
                )
            elif session['question_count'] >= rules['max_questions']:
                cfg = _ensure_scenario_loaded()
                # 1️⃣ Сначала обновляем статистику
                total_score = QuestionAnalyzer().calculate_score(session, cfg['question_types'])
                update_stats(user_id, total_score)
                # 2️⃣ Потом показываем отчёт
                await send_final_report(update, user)
                # 3️⃣ Логируем статистику кейса
                log_case_statistics(user_id)
                # 4️⃣ Очищаем сессию
                reset_session(user_id)
            else:
                await update.message.reply_text(
                    scenario_loader.get_message(
                        'question_feedback',
                        question_type=question_type_name + context_badge,
                        client_response=client_response,
                        progress_line=scenario_loader.get_message(
                            'progress', count=session['question_count'], max=rules['max_questions'], clarity=session['clarity_level']
                        )
                    )
                )
        else:
            await update.message.reply_text(
                scenario_loader.get_message(
                    'question_feedback',
                    question_type=question_type_name + context_badge,
                    client_response=client_response,
                    progress_line=scenario_loader.get_message(
                        'progress', count=session['question_count'], max=rules['max_questions'], clarity=session['clarity_level']
                    )
                )
            )
    
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text(scenario_loader.get_message('error_generic'))

async def validate_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка конфигурации на логические ошибки"""
    await update.message.reply_text("🔍 Проверяю конфигурацию...")
    _ensure_scenario_loaded()
    errors = []
    warnings = []

    # Проверка 1: У каждого типа компании есть совместимые продукты
    for company in case_generator.variants['companies']:
        compatible_products = [
            p for p in case_generator.variants['products']
            if company['type'] in p.get('compatible_companies', [])
        ]
        if not compatible_products:
            errors.append(f"❌ {company['type']}: нет совместимых продуктов!")

    # Проверка 2: У каждого размера есть должности (если задан positions_by_size)
    positions_by_size = case_generator.variants.get('positions_by_size', {})
    for size in case_generator.variants['company_sizes']:
        if positions_by_size and not positions_by_size.get(size):
            errors.append(f"❌ {size}: нет должностей!")

    # Проверка 3: У всех продуктов есть обязательные поля (рекомендательные)
    for product in case_generator.variants['products']:
        if 'compatible_companies' not in product:
            warnings.append(f"⚠️ {product['name']}: нет поля compatible_companies")
        if 'frequency_options' not in product:
            warnings.append(f"⚠️ {product['name']}: нет поля frequency_options")
        if 'volume_range' not in product:
            warnings.append(f"⚠️ {product['name']}: нет поля volume_range")

    result = "📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ:\n\n"
    if errors:
        result += "🚨 ОШИБКИ:\n" + "\n".join(errors) + "\n\n"
    if warnings:
        result += "⚠️ ПРЕДУПРЕЖДЕНИЯ:\n" + "\n".join(warnings) + "\n\n"
    if not errors and not warnings:
        result += "✅ Конфигурация корректна! Логических ошибок не найдено."
    await update.message.reply_text(result)
async def test_speed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тест скорости генерации кейсов"""
    await update.message.reply_text("🧪 Тестирую скорость генерации...")
    
    # Тест прямой генерации
    start = time.time()
    case_data = case_generator.generate_random_case()
    case_direct = case_generator.build_case_direct(case_data)
    time_direct = time.time() - start
    
    # Тест с GPT (если метод существует)
    start = time.time()
    try:
        case_prompt = case_generator.build_case_prompt(case_data)
        case_gpt = await call_llm('response', case_prompt, 'Создай кейс')
        time_gpt = time.time() - start
    except Exception:
        time_gpt = 0.0
    
    result = f"""📊 РЕЗУЛЬТАТЫ ТЕСТА:

⚡ Прямая генерация: {time_direct:.4f} сек
🤖 Генерация с GPT: {time_gpt:.4f} сек

Ускорение: {time_gpt/time_direct if time_direct > 0 and time_gpt > 0 else 0:.1f}x

✅ Прямая генерация экономит {max(time_gpt - time_direct, 0):.2f} секунд на каждый кейс!"""
    
    await update.message.reply_text(result)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику пользователя"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        await update.message.reply_text('У вас пока нет статистики. Начните тренировку командой /start')
        return
    
    stats = user_data[user_id]['stats']
    session = user_data[user_id]['session']
    
    session_status = "❌ Нет активной тренировки"
    if session['chat_state'] == 'waiting_start':
        session_status = "⏳ Ожидается начало тренировки"
    elif session['chat_state'] == 'training_active':
        session_status = f"✅ Активная тренировка ({session['question_count']}/10 вопросов)"
    
    stats_message = f"""📊 ВАША СТАТИСТИКА:

🎯 Общие показатели:
- Пройдено тренировок: {stats['total_trainings']}
- Всего задано вопросов: {stats['total_questions']}
- Лучший результат: {stats['best_score']} баллов

🏆 Заработанные награды:
{chr(10).join(stats['badges_earned'][-5:]) if stats['badges_earned'] else '• Пока нет наград'}

⏱ Последняя тренировка:
{stats['last_training_date'] if stats['last_training_date'] else 'Ещё не проводилась'}

📍 Текущий статус:
{session_status}

💡 Для новой тренировки напишите "начать" или /start"""

    await update.message.reply_text(stats_message)

async def case_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о текущем кейсе"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        await update.message.reply_text('Начните тренировку командой /start')
        return
    
    session = user_data[user_id]['session']
    
    if session['chat_state'] != 'training_active':
        await update.message.reply_text('Нет активного кейса. Начните тренировку написав "начать"')
        return
    
    case_data = session.get('case_data')
    if not case_data:
        await update.message.reply_text('Данные кейса недоступны')
        return
    
    case_info = f"""📋 ТЕКУЩИЙ КЕЙС:

👤 Клиент:
- Должность: {case_data['position']}
- Компания: {case_data['company']['type']}
- Размер: {case_data['company_size']}
- Регион: {case_data['region']}

📦 Продукт: {case_data['product']['name']}
- Описание: {case_data['product'].get('description', 'Не указано')}
- Объём закупок: {case_data['volume']}
- Частота: {case_data['frequency']}

🎯 Ситуация: {case_data['situation']['type']}

📊 Ваш прогресс:
- Вопросов задано: {session['question_count']}/10
- Уровень ясности: {session['clarity_level']}%

💬 Продолжайте задавать вопросы клиенту!"""

    await update.message.reply_text(case_info)

async def test_cases_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда: генерация 5 случайных кейсов (только для разработки)"""
    user_id = update.effective_user.id
    
    test_results = "🧪 ТЕСТ ГЕНЕРАТОРА КЕЙСОВ\n\n"
    
    for i in range(5):
        case_data = case_generator.generate_random_case()
        test_results += f"""Кейс #{i+1}:
👤 {case_data['position']}
🏢 {case_data['company']['type']} ({case_data['company_size']})
📦 {case_data['product']['name']}
📊 {case_data['volume']} {case_data['frequency']}
🎯 Тип: {case_data['situation']['type']}
{'='*40}
"""
    
    await update.message.reply_text(test_results)

async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текущий ранг и прогресс"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        await update.message.reply_text('У вас пока нет статистики. Начните тренировку командой /start')
        return
    
    cfg = _ensure_scenario_loaded()
    stats = user_data[user_id]['stats']
    levels = cfg.get('ranking', {}).get('levels', [])
    current_level = stats.get('current_level', 1)
    current_level_data = next((l for l in levels if l.get('level') == current_level), (levels[0] if levels else {'level': 1, 'name': 'Новичок', 'emoji': '🌱', 'min_xp': 0, 'description': ''}))
    next_level_data = next((l for l in levels if l.get('level') == current_level + 1), None)
    current_xp = int(stats.get('total_xp', 0))
    
    if next_level_data:
        xp_needed = int(next_level_data.get('min_xp', 0)) - int(current_level_data.get('min_xp', 0))
        xp_current = current_xp - int(current_level_data.get('min_xp', 0))
        percent = max(0, min(100, int((xp_current / xp_needed) * 100))) if xp_needed > 0 else 100
        filled = "█" * (percent // 10)
        empty = "░" * (10 - percent // 10)
        progress_bar = f"\n[{filled}{empty}] {percent}%"
        xp_to_next = int(next_level_data.get('min_xp', 0)) - current_xp
        next_level_info = f"\n\n📊 До уровня {next_level_data.get('level')} \"{next_level_data.get('name', '')}\":\nНужно: {max(xp_to_next, 0)} XP{progress_bar}"
    else:
        next_level_info = "\n\n🏆 Вы достигли максимального уровня!"
    
    achievements = cfg.get('achievements', {}).get('list', [])
    unlocked = stats.get('achievements_unlocked', [])
    achievements_text = f"\n\n🎖️ ДОСТИЖЕНИЯ ({len(unlocked)}/{len(achievements)}):\n"
    for ach in achievements:
        status = "✅" if ach.get('id') in unlocked else "⬜"
        achievements_text += f"{status} {ach.get('emoji', '')} {ach.get('name', '')}\n"
    
    rank_message = f"""⭐ ВАШ РАНГ

{current_level_data.get('emoji', '')} Уровень {current_level_data.get('level', 1)}: {current_level_data.get('name', '')}
{current_level_data.get('description', '')}

💎 Опыт: {current_xp} XP{next_level_info}{achievements_text}
🎯 Продолжайте тренировки для повышения уровня!"""

    await update.message.reply_text(rank_message)
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
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scenario", scenario_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("case", case_command))
    # application.add_handler(CommandHandler("test_cases", test_cases_command))  # dev only
    # application.add_handler(CommandHandler("test_speed", test_speed_command))  # dev only
    application.add_handler(CommandHandler("validate", validate_config_command))
    application.add_handler(CommandHandler("rank", rank_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    logger.info("SPIN Training Bot запущен!")
    
    # Запускаем простой веб-сервер для health checks
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import socket
    import threading
    
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
    
    # Запускаем health-check сервер в отдельном потоке
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server запущен на порту {port}")
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
    except Exception as e:
        logger.error(f"Ошибка запуска health check сервера: {e}")

    # Запускаем бота (основной поток)
    try:
        application.run_polling()
    except Exception:
        logger.exception("Критическая ошибка запуска бота")

if __name__ == '__main__':
    main()
