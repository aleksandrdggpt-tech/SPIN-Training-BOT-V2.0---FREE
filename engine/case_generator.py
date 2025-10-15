import random
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class CaseGenerator:
    """Генератор случайных кейсов для тренировки"""
    
    def __init__(self, case_variants: Dict[str, Any]):
        """
        Инициализация генератора
        
        Args:
            case_variants: Словарь с вариантами из config.json
        """
        self.variants = case_variants
        self._preprocess_data()
        logger.info(f"CaseGenerator инициализирован: {len(case_variants.get('positions', []))} должностей, "
                   f"{len(case_variants.get('companies', []))} компаний, {len(case_variants.get('products', []))} продуктов")
    
    def _preprocess_data(self):
        """Предварительная обработка данных для оптимизации"""
        # Создаём индекс совместимости продуктов и компаний
        self.product_company_index = {}
        for product in self.variants.get('products', []):
            compatible = product.get('compatible_companies', [])
            self.product_company_index[product['name']] = compatible
        
        # Группируем продукты по единицам измерения для оптимизации генерации объёмов
        self.products_by_unit = {}
        for product in self.variants.get('products', []):
            unit = product.get('unit', 'тонн')
            if unit not in self.products_by_unit:
                self.products_by_unit[unit] = []
            self.products_by_unit[unit].append(product)
    
    def generate_random_case(self, exclude_recent: List[str] = None) -> Dict[str, Any]:
        """
        Генерация случайного ЛОГИЧНОГО кейса с валидацией
        """
        max_attempts = 30
        attempts = 0
        last_case = None
        
        while attempts < max_attempts:
            # ШАГ 1: Компания
            company = random.choice(self.variants['companies'])
            # ШАГ 2: Размер
            size = self._select_compatible_size(company)
            # ШАГ 3: Должность
            position = self._select_position_for_size(size)
            # ШАГ 4: Продукт
            product = self._select_compatible_product(company)
            # ШАГ 5: Объём
            volume = self._generate_volume(product, size)
            # ШАГ 6: Частота
            frequency = self._select_frequency(product)
            # ШАГ 7: Характер закупки
            urgency = random.choice(['плановая закупка', 'замена поставщика', 'новый проект', 'срочная потребность'])
            # ШАГ 8: Остальное
            region = random.choice(self.variants['regions'])
            situation = random.choice(self.variants['base_situations'])
            suppliers_count = random.randint(1, 5)

            case_data = {
                'position': position,
                'company': company,
                'company_size': size,
                'region': region,
                'product': product,
                'situation': situation,
                'volume': volume,
                'suppliers_count': suppliers_count,
                'frequency': frequency,
                'urgency': urgency
            }

            validated = self._validate_case_logic(case_data)
            logger.info(f"\n╔════════ ГЕНЕРАЦИЯ КЕЙСА ════════╗\n"
                        f"║ Компания: {company['type']}\n"
                        f"║ Размер: {size}\n"
                        f"║ Должность: {position}\n"
                        f"║ Продукт: {product['name']}\n"
                        f"║ Объём: {volume}\n"
                        f"║ Частота: {frequency}\n"
                        f"║ Регион: {region}\n"
                        f"║ Валидация: {'PASSED' if validated else 'FAILED'}\n"
                        f"╚══════════════════════════════════╝")

            if not validated:
                attempts += 1
                last_case = case_data
                continue

            # Проверка уникальности
            case_hash = self._get_case_hash(case_data)
            if exclude_recent is None or case_hash not in exclude_recent:
                logger.info(f"✅ Сгенерирован логичный кейс: {position} | {company['type']} ({size}) | {product['name']} | {volume}")
                return case_data
            attempts += 1
            last_case = case_data

        logger.warning("Не удалось найти полностью уникальный кейс после валидации")
        return last_case or {}
    
    def _select_compatible_size(self, company: Dict[str, Any]) -> str:
        typical_sizes = company.get('typical_sizes', self.variants['company_sizes'])
        return random.choice(typical_sizes)

    def _select_position_for_size(self, company_size: str) -> str:
        positions = self.variants.get('positions_by_size', {}).get(company_size, [])
        if not positions:
            logger.error(f"Нет должностей для размера {company_size} — fallback к универсальным")
            positions = ["Владелец бизнеса", "Управляющий", "Коммерческий директор"]
        return random.choice(positions)

    def _select_compatible_product(self, company: Dict[str, Any]) -> Dict[str, Any]:
        compatible_products = [
            p for p in self.variants['products']
            if company['type'] in p.get('compatible_companies', [])
        ]
        if not compatible_products:
            logger.error(f"❌ НЕТ совместимых продуктов для {company['type']}! Проверьте config.json")
            compatible_products = [p for p in self.variants['products'] if 'услуг' in p.get('name', '').lower()]
            if not compatible_products:
                logger.critical("Критическая ошибка: нет даже универсальных продуктов! Берём первые 3")
                compatible_products = self.variants['products'][:3]
        product = random.choice(compatible_products)
        logger.info(f"Выбран продукт: {product['name']} для {company['type']}")
        return product
    
    def _generate_volume(self, product: Dict[str, Any], company_size: str) -> str:
        """Генерация АДЕКВАТНОГО объёма с учётом размера компании и продукта"""
        size_multipliers = {
            'микро-бизнес (до 15 человек)': 0.2,
            'малая компания (15-100 человек)': 0.6,
            'средняя компания (100-250 человек)': 1.0,
            'крупная компания (250+ человек)': 1.8
        }
        multiplier = size_multipliers.get(company_size, 1.0)
        volume_range = product.get('volume_range', {'min': 10, 'max': 100})
        base_min = int(volume_range.get('min', 1))
        base_max = int(volume_range.get('max', base_min))
        scaled_min = max(1, int(base_min * multiplier))
        scaled_max = max(scaled_min, int(base_max * multiplier))
        volume = random.randint(scaled_min, scaled_max)
        unit = product.get('unit', 'единиц')
        logger.info(f"Объём для {company_size}: {volume} {unit} (диапазон: {scaled_min}-{scaled_max})")
        return f"{volume} {unit}"

    def _select_frequency(self, product: Dict[str, Any]) -> str:
        """Выбор логичной частоты закупок для продукта с безопасным fallback."""
        options = product.get('frequency_options')
        if isinstance(options, list) and options:
            return random.choice(options)
        # Fallback по типу: расходники чаще, капекс — реже
        if product.get('is_capital_equipment'):
            return random.choice(['по проекту', 'при модернизации'])
        return 'ежемесячно'

    def _validate_case_logic(self, case_data: Dict[str, Any]) -> bool:
        """Валидация логичности сгенерированного кейса."""
        errors = []

        product = case_data['product']
        company_type = case_data['company']['type']
        size = case_data['company_size']
        position = case_data['position']
        frequency = case_data['frequency']

        # 1) Совместимость продукт-компания
        if company_type not in product.get('compatible_companies', []):
            errors.append(f"Продукт {product.get('name')} несовместим с {company_type}")

        # 2) Должность соответствует размеру
        valid_positions = self.variants.get('positions_by_size', {}).get(size, [])
        if valid_positions and position not in valid_positions:
            errors.append(f"Должность {position} не подходит для {size}")

        # 3) Объём адекватен: извлечь число
        try:
            volume_num = int(str(case_data['volume']).split()[0])
        except Exception:
            volume_num = None
        if volume_num is not None and product.get('is_capital_equipment'):
            if volume_num > max(50, product.get('volume_range', {}).get('max', 50)):
                errors.append(f"Слишком большой объём ({volume_num}) для капввода {product.get('name')}")

        # 4) Частота соответствует продукту (если варианты заданы)
        valid_freqs = product.get('frequency_options')
        if isinstance(valid_freqs, list) and valid_freqs and frequency not in valid_freqs:
            errors.append(f"Частота '{frequency}' не подходит для {product.get('name')}")

        # 5) Размер компании типичен для типа компании (если указаны типичные)
        typical_sizes = case_data['company'].get('typical_sizes')
        if isinstance(typical_sizes, list) and typical_sizes and size not in typical_sizes:
            errors.append(f"Размер {size} нетипичен для {company_type}")

        if errors:
            logger.warning("❌ Кейс не прошёл валидацию:\n" + "\n".join(f"  - {e}" for e in errors))
            return False
        logger.info("✅ Кейс прошёл все проверки валидации")
        return True
    
    def _get_case_hash(self, case_data: Dict[str, Any]) -> str:
        """
        Создание уникального хеша кейса для проверки повторов
        
        Args:
            case_data: Данные кейса
            
        Returns:
            Строка-хеш
        """
        return f"{case_data['position']}-{case_data['company']['type']}-{case_data['product']['name']}"
    
    def build_case_prompt(self, case_data: Dict[str, Any]) -> str:
        """
        Построение промпта для GPT с конкретными параметрами кейса
        
        DEPRECATED: Используется только для тестирования. Для продакшена
        используйте build_case_direct().
        
        Args:
            case_data: Данные сгенерированного кейса
            
        Returns:
            Готовый промпт для отправки в GPT
        """
        logger.warning("Используется deprecated метод build_case_prompt. Используйте build_case_direct()")
        # Формируем детали ситуации
        situation_details = case_data['situation']['template'].format(
            volume=case_data['volume'],
            suppliers_count=case_data['suppliers_count'],
            frequency=case_data['frequency'],
            product=case_data['product']['name']
        )
        
        prompt = f"""Создай клиентский кейс для тренировки SPIN-продаж со следующими параметрами:

🎯 ПАРАМЕТРЫ КЕЙСА:
Должность клиента: {case_data['position']}
Компания: {case_data['company']['type']}, размер: {case_data['company_size']}
Регион: {case_data['region']}
Характер закупки: {case_data['urgency']}

📦 ПРОДУКТ: {case_data['product']['name']}
Описание: {case_data['product'].get('description', '')}

ℹ️ БАЗОВАЯ СИТУАЦИЯ: 
{situation_details}

ФОРМАТ ОТВЕТА:
🎯 КЛИЕНТСКИЙ КЕЙС:

Должность клиента: {case_data['position']}
Компания: {case_data['company']['type']}, {case_data['company_size']}

📦 ВЫ ПРОДАЕТЕ: {case_data['product']['name']}

ℹ️ БАЗОВАЯ СИТУАЦИЯ: 
[Перепиши базовую ситуацию своими словами, добавь 2-3 конкретных факта с цифрами. НЕ упоминай проблемы напрямую - они должны выявляться через SPIN-вопросы!]

ТРЕБОВАНИЯ:
- Используй конкретные цифры и факты
- Пиши нейтрально, без упоминания проблем
- Добавь реалистичные детали про процессы компании
- Объём ответа: 3-5 предложений"""

        return prompt

    def _get_varied_description(self, situation_type: str, case_data: Dict[str, Any]) -> str:
        """
        Генерация вариативного описания ситуации из предустановленных вариантов
        """
        descriptions = {
            'seasonal_demand': [
                'пиковые нагрузки весной и осенью',
                'сезонные колебания спроса',
                'требуется гибкость при сезонности'
            ],
            'quality_issues': [
                'участились рекламации от клиентов',
                'вопросы качества требуют внимания',
                'клиенты отмечают проблемы с качеством'
            ],
            'delivery_problems': [
                'требуется чёткий график поставок',
                'сроки поставок критичны',
                'нужна стабильность в логистике'
            ],
            'price_pressure': [
                'бюджет закупок под давлением',
                'сильное давление на закупочные цены'
            ],
            'logistics_issues': [
                'производство в 2 смены, логистика критична',
                'логистика ключевой фактор исполнения'
            ],
            'technical_requirements': [
                'новые требования к сертификации',
                'усилены требования к качеству'
            ],
            'storage_problems': [
                'ограниченные складские площади',
                'нужна оптимизация складской оборачиваемости'
            ],
            'cash_flow': [
                'требуется оптимизация отсрочки платежей',
                'важны условия оплаты и отсрочка'
            ],
            'competition': [
                'усилилось конкурентное давление',
                'агрессивное ценообразование конкурентов'
            ],
            'client_requirements': [
                'клиенты ужесточают требования к срокам',
                'ужесточаются SLA по срокам'
            ],
            'expansion': [
                'планируется расширение производства',
                'запуск нового участка в ближайшие месяцы'
            ],
            'supplier_change': [
                'нужна замена одного из поставщиков',
                'источник поставок меняется'
            ],
        }
        variants = descriptions.get(situation_type, [case_data['situation'].get('description_short', '')])
        if not variants:
            return 'требуется оптимизация процессов'
        return random.choice(variants)

    def build_case_direct(self, case_data: Dict[str, Any]) -> str:
        """
        Прямая генерация кейса без использования GPT (мгновенно)
        """
        region = case_data['region']
        region_text = f", {region}" if region not in case_data['company']['type'] else ""
        specifics = self._get_varied_description(case_data['situation']['type'], case_data)
        product_desc = case_data['product'].get('description', '')
        product_line = f"📦 ВЫ ПРОДАЕТЕ: {case_data['product']['name']}"
        if product_desc:
            product_line += f"\n({product_desc})"

        case_text = f"""🎯 КЛИЕНТСКИЙ КЕЙС:

Должность клиента: {case_data['position']}
Компания: {case_data['company']['type']}, {case_data['company_size']}{region_text}

{product_line}

ℹ️ БАЗОВАЯ СИТУАЦИЯ:

🏭 Компания: {case_data['company']['type']}, {case_data['company_size']}
📦 Объём: {case_data['volume']} {case_data['frequency']}
🤝 Поставщиков: {case_data['suppliers_count']}
📈 Характер закупки: {case_data['urgency']}
💼 Специфика: {specifics}

Теперь можете задать первый вопрос клиенту.

---
Если нужна обратная связь от наставника — напишите ДА.
Для завершения напишите "завершить"."""

        return case_text
