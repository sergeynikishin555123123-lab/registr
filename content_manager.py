import csv
import logging
import pandas as pd
from pathlib import Path
import json
from typing import Dict, List, Optional, Any
from database import AsyncSessionLocal, ContentVersion
from sqlalchemy import select
import io

logger = logging.getLogger(__name__)

class ContentManager:
    def __init__(self, content_file: str = "content.csv"):
        self.content_file = content_file
        self.content: Dict[str, Dict[str, Any]] = {}
        self.load_content()
    
    def load_content(self) -> bool:
        """Загружает контент из CSV файла"""
        try:
            if Path(self.content_file).exists():
                df = pd.read_csv(self.content_file, encoding='utf-8')
                
                for _, row in df.iterrows():
                    key = row['key']
                    self.content[key] = {
                        'text': row['text'],
                        'buttons': self._parse_buttons(row.get('buttons', '[]')),
                        'comment': row.get('comment', ''),
                        'scenario': row.get('scenario', 'default')
                    }
                
                logger.info(f"✅ Контент загружен: {len(self.content)} записей")
                return True
            else:
                logger.warning("⚠️ Файл контента не найден, создаем стандартный")
                return self.create_default_content()
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контента: {e}")
            return self.create_default_content()
    
    def _parse_buttons(self, buttons_str: str) -> List[List[Dict[str, str]]]:
        """Парсит строку кнопок в структуру для Telegram"""
        try:
            if pd.isna(buttons_str) or not buttons_str.strip():
                return []
            
            # Парсим JSON структуру
            buttons_data = json.loads(buttons_str)
            
            # Преобразуем в формат для Telegram
            telegram_buttons = []
            for row in buttons_data:
                telegram_row = []
                for button in row:
                    if isinstance(button, dict):
                        telegram_row.append(button)
                    else:
                        telegram_row.append({"text": str(button)})
                telegram_buttons.append(telegram_row)
            
            return telegram_buttons
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга кнопок '{buttons_str}': {e}")
            return []
    
    def create_default_content(self) -> bool:
        """Создает стандартный контент"""
        try:
            default_content = [
                {
                    'key': 'welcome_default',
                    'text': '🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье. Давайте начнем!',
                    'buttons': '[["🧪 Начать 60-секундный тест"], ["💰 Оплатить анализ", "👤 Профиль"], ["🔗 Моя реф ссылка", "ℹ️ О проекте"]]',
                    'comment': 'Приветствие по умолчанию',
                    'scenario': 'default'
                },
                {
                    'key': 'welcome_blogger1',
                    'text': '👋 Привет! Вы пришли от Блоггера 1!\n\nДавайте узнаем больше о вашем здоровье и начнем путь к улучшению самочувствия!',
                    'buttons': '[["🧪 Начать 60-секундный тест"], ["💰 Спецпредложение", "👤 Профиль"]]',
                    'comment': 'Приветствие для блоггера 1',
                    'scenario': 'blogger1'
                },
                {
                    'key': 'payment_description',
                    'text': '💰 *Оплата анализа*\n\nСтоимость полного анализа: 2 990 руб.\n\n*Включает:*\n• Комплект для сбора анализов\n• Подробный отчет с интерпретацией\n• Персональные рекомендации\n• Поддержку менеджера',
                    'buttons': '[["💳 Оплатить 2 990 руб", "🧪 Сначала пройти тест"], ["🔙 Назад"]]',
                    'comment': 'Описание оплаты',
                    'scenario': 'default'
                },
                {
                    'key': 'quiz_welcome',
                    'text': '🧪 *60-секундный тест*\n\nОтветьте на 3 простых вопроса, чтобы получить персональные рекомендации.',
                    'buttons': '[["✅ Начать тест"], ["🔙 Назад"]]',
                    'comment': 'Приветствие квиза',
                    'scenario': 'default'
                },
                {
                    'key': 'quiz_question1',
                    'text': '❓ *Вопрос 1/3:* Как часто вы чувствуете усталость?',
                    'buttons': '[["😫 Постоянно", "😐 Часто"], ["😊 Иногда", "🎉 Редко"], ["🔙 Назад"]]',
                    'comment': 'Первый вопрос квиза',
                    'scenario': 'default'
                },
                {
                    'key': 'quiz_question2', 
                    'text': '✅ *Ответ сохранен*\n\n❓ *Вопрос 2/3:* Как вы оцениваете качество сна?',
                    'buttons': '[["😴 Отлично", "🛌 Нормально"], ["⏰ Плохо", "💤 Бессонница"], ["🔙 Назад"]]',
                    'comment': 'Второй вопрос квиза',
                    'scenario': 'default'
                },
                {
                    'key': 'quiz_question3',
                    'text': '✅ *Ответ сохранен*\n\n❓ *Вопрос 3/3:* Как часто занимаетесь спортом?',
                    'buttons': '[["💪 Регулярно", "🚶 Иногда"], ["🧘 Редко", "🚫 Никогда"], ["🔙 Назад"]]',
                    'comment': 'Третий вопрос квиза',
                    'scenario': 'default'
                },
                {
                    'key': 'quiz_complete',
                    'text': '🎉 *Тест завершен!*\n\nНа основе ваших ответов мы подготовили специальное предложение.\n\n*Полный анализ со скидкой 20%* - 2 990 руб вместо 3 737 руб!',
                    'buttons': '[["💳 Заказать со скидкой"], ["👤 Профиль", "ℹ️ О проекте"]]',
                    'comment': 'Завершение квиза',
                    'scenario': 'default'
                },
                {
                    'key': 'payment_success',
                    'text': '🎉 *Оплата подтверждена!*\n\nСпасибо за заказ! Теперь нам нужны ваши контактные данные для доставки набора.',
                    'buttons': '[["📞 Оставить контакты"]]',
                    'comment': 'Успешная оплата',
                    'scenario': 'default'
                },
                {
                    'key': 'timezone_selection',
                    'text': '🕐 *Выберите ваш часовой пояс:*',
                    'buttons': '[["Москва (+3)", "Екатеринбург (+5)"], ["Калининград (+2)", "Определить по городу"]]',
                    'comment': 'Выбор часового пояса',
                    'scenario': 'default'
                },
                {
                    'key': 'collection_instructions',
                    'text': '📋 *Инструкция по сбору анализов*\n\nПожалуйста, внимательно прочитайте инструкцию перед сбором.',
                    'buttons': '[["📄 Скачать инструкцию PDF"], ["✅ Понятно"]]',
                    'comment': 'Инструкция по сбору',
                    'scenario': 'default'
                }
            ]
            
            df = pd.DataFrame(default_content)
            df.to_csv(self.content_file, index=False, encoding='utf-8')
            self.load_content()
            
            logger.info("✅ Стандартный контент создан")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания стандартного контента: {e}")
            return False
    
    def get(self, key: str, scenario: str = 'default', **kwargs) -> Optional[Dict[str, Any]]:
        """Получает контент по ключу и сценарию"""
        try:
            # Пытаемся найти контент для конкретного сценария
            scenario_key = f"{key}_{scenario}"
            if scenario_key in self.content:
                content = self.content[scenario_key].copy()
            elif key in self.content:
                content = self.content[key].copy()
            else:
                logger.warning(f"⚠️ Контент не найден: {key} для сценария {scenario}")
                return None
            
            # Заменяем плейсхолдеры
            if 'text' in content and kwargs:
                content['text'] = content['text'].format(**kwargs)
            
            return content
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения контента {key}: {e}")
            return None
    
    async def save_to_database(self):
        """Сохраняет контент в базу данных (для версионирования)"""
        try:
            async with AsyncSessionLocal() as session:
                for key, content in self.content.items():
                    # Проверяем существующую версию
                    result = await session.execute(
                        select(ContentVersion).where(
                            ContentVersion.key == key,
                            ContentVersion.is_active == True
                        )
                    )
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        # Деактивируем старую версию
                        existing.is_active = False
                    
                    # Создаем новую версию
                    new_version = ContentVersion(
                        key=key,
                        text=content['text'],
                        buttons=content['buttons'],
                        comment=content.get('comment', ''),
                        version=(existing.version + 1) if existing else 1,
                        is_active=True
                    )
                    session.add(new_version)
                
                await session.commit()
                logger.info("✅ Контент сохранен в базу данных")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения контента в БД: {e}")
            return False
    
    async def load_from_database(self):
        """Загружает контент из базы данных"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ContentVersion).where(ContentVersion.is_active == True)
                )
                active_content = result.scalars().all()
                
                self.content.clear()
                for item in active_content:
                    self.content[item.key] = {
                        'text': item.text,
                        'buttons': item.buttons,
                        'comment': item.comment
                    }
                
                logger.info(f"✅ Контент загружен из БД: {len(self.content)} записей")
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контента из БД: {e}")
            return False
    
    def export_to_csv(self, filename: str = None) -> bool:
        """Экспортирует контент в CSV файл"""
        try:
            export_data = []
            for key, content in self.content.items():
                export_data.append({
                    'key': key,
                    'text': content['text'],
                    'buttons': json.dumps(content['buttons'], ensure_ascii=False),
                    'comment': content.get('comment', ''),
                    'scenario': content.get('scenario', 'default')
                })
            
            df = pd.DataFrame(export_data)
            export_filename = filename or f"content_export_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv"
            df.to_csv(export_filename, index=False, encoding='utf-8')
            
            logger.info(f"✅ Контент экспортирован в {export_filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта контента: {e}")
            return False
    
    def import_from_csv(self, filename: str) -> bool:
        """Импортирует контент из CSV файла"""
        try:
            # Создаем резервную копию
            backup_filename = f"content_backup_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv"
            self.export_to_csv(backup_filename)
            
            # Загружаем новый контент
            self.content_file = filename
            success = self.load_content()
            
            if success:
                logger.info(f"✅ Контент импортирован из {filename}")
                return True
            else:
                # Восстанавливаем из резервной копии
                self.content_file = backup_filename
                self.load_content()
                logger.error("❌ Ошибка импорта, восстановлен резервный контент")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка импорта контента: {e}")
            return False
    
    def validate_content(self) -> Dict[str, List[str]]:
        """Проверяет валидность контента"""
        errors = []
        warnings = []
        
        try:
            required_keys = ['welcome_default', 'payment_description', 'quiz_welcome']
            
            for key in required_keys:
                if key not in self.content:
                    errors.append(f"Отсутствует обязательный ключ: {key}")
            
            for key, content in self.content.items():
                # Проверяем текст
                if not content.get('text', '').strip():
                    errors.append(f"Пустой текст для ключа: {key}")
                
                # Проверяем кнопки
                buttons = content.get('buttons', [])
                if buttons:
                    for row in buttons:
                        for button in row:
                            if not button.get('text', '').strip():
                                errors.append(f"Пустой текст кнопки в ключе: {key}")
            
            # Проверяем плейсхолдеры
            for key, content in self.content.items():
                text = content.get('text', '')
                if '{' in text and '}' in text:
                    # Это может быть плейсхолдер, добавляем предупреждение
                    warnings.append(f"Возможные плейсхолдеры в ключе: {key}")
            
            return {'errors': errors, 'warnings': warnings}
            
        except Exception as e:
            logger.error(f"❌ Ошибка валидации контента: {e}")
            return {'errors': [f"Ошибка валидации: {e}"], 'warnings': []}
    
    def get_content_stats(self) -> Dict[str, Any]:
        """Возвращает статистику контента"""
        try:
            scenarios = set()
            total_buttons = 0
            total_chars = 0
            
            for key, content in self.content.items():
                scenarios.add(content.get('scenario', 'default'))
                total_chars += len(content.get('text', ''))
                
                buttons = content.get('buttons', [])
                for row in buttons:
                    total_buttons += len(row)
            
            return {
                'total_entries': len(self.content),
                'scenarios': list(scenarios),
                'total_buttons': total_buttons,
                'total_chars': total_chars,
                'scenario_distribution': {scenario: len([c for c in self.content.values() if c.get('scenario') == scenario]) for scenario in scenarios}
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики контента: {e}")
            return {}

# Глобальный экземпляр менеджера контента
content_manager = ContentManager()
