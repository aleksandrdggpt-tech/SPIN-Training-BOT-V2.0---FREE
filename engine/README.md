# Engine Modules

Модули движка для SPIN Training Bot v2.0

## Структура

### case_generator.py
Генератор случайных уникальных кейсов для тренировок.

Основные возможности:
- Генерация случайных параметров кейса (должность, компания, продукт)
- Защита от повторов (история последних кейсов через хеш)
- Совместимость продуктов и типов компаний
- Построение промптов для GPT с конкретными параметрами

Использование:
```python
from engine.case_generator import CaseGenerator

generator = CaseGenerator(config['case_variants'])
case_data = generator.generate_random_case(exclude_recent=[...])
prompt = generator.build_case_prompt(case_data)
```

### scenario_loader.py
Загрузчик и валидатор конфигурационных файлов сценариев. Валидация включает базовые секции и опциональную секцию `case_variants`.

### question_analyzer.py
Анализатор типов вопросов по методике SPIN.

### report_generator.py
Генератор финальных отчётов и статистики.

