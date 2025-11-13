import csv
import logging
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

class ContentManager:
    def __init__(self, content_file="content.csv"):
        self.content_file = content_file
        self.content = {}
        self.load_content()
    
    def load_content(self):
        """Загружает контент из CSV файла"""
        try:
            if Path(self.content_file).exists():
                df = pd.read_csv(self.content_file)
                for _, row in df.iterrows():
                    key = row['key']
                    self.content[key] = {
                        'text': row['text'],
                        'buttons': eval(row['buttons']) if pd.notna(row['buttons']) else [],
                        'comment': row.get('comment', '')
                    }
                logger.info(f"✅ Контент загружен из {self.content_file}: {len(self.content)} записей")
            else:
                self.create_default_content()
                logger.info("✅ Создан файл с контентом по умолчанию")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контента: {e}")
            self.create_default_content()
    
    def create_default_content(self):
        """Создает контент по умолчанию"""
        default_content = [
            {
                'key': 'welcome_default',
                'text': '🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье.',
                'buttons': "['🧪 Начать тест', '💰 Оплатить анализ', '👤 Профиль', '🔗 Моя реф ссылка', 'ℹ️ О проекте']",
                'comment': 'Приветствие для сценария по умолчанию'
            },
            {
                'key': 'welcome_blogger1', 
                'text': '👋 Привет! Вы пришли от Блоггера 1!\n\nДавайте узнаем больше о вашем здоровье...',
                'buttons': "['🧪 Начать тест', '💰 Оплатить анализ', '👤 Профиль', '🔗 Моя реф ссылка', 'ℹ️ О проекте']",
                'comment': 'Приветствие для блоггера 1'
            },
            {
                'key': 'payment_description',
                'text': '💰 Оплата анализа\n\nСтоимость полного анализа: 2 990 руб.\n\nВключает:\n• Комплект для сбора анализов\n• Подробный отчет\n• Персональные рекомендации',
                'buttons': "[]",
                'comment': 'Описание оплаты'
            },
            {
                'key': 'payment_success',
                'text': '🎉 Оплата подтверждена! Спасибо за заказ!\n\nТеперь нам нужны ваши контактные данные для доставки набора.',
                'buttons': "[]",
                'comment': 'Сообщение после успешной оплаты'
            }
        ]
        
        df = pd.DataFrame(default_content)
        df.to_csv(self.content_file, index=False, encoding='utf-8')
        self.load_content()
    
    def get(self, key, default=None):
        """Получает контент по ключу"""
        return self.content.get(key, default)
    
    def update_content(self, key, text, buttons=None, comment=""):
        """Обновляет контент"""
        self.content[key] = {
            'text': text,
            'buttons': buttons or [],
            'comment': comment
        }
        self.save_content()
    
    def save_content(self):
        """Сохраняет контент в CSV"""
        try:
            data = []
            for key, value in self.content.items():
                data.append({
                    'key': key,
                    'text': value['text'],
                    'buttons': str(value['buttons']),
                    'comment': value.get('comment', '')
                })
            
            df = pd.DataFrame(data)
            # Создаем backup
            if Path(self.content_file).exists():
                backup_file = f"{self.content_file}.backup"
                Path(self.content_file).rename(backup_file)
            
            df.to_csv(self.content_file, index=False, encoding='utf-8')
            logger.info("✅ Контент сохранен")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения контента: {e}")
            return False

content_manager = ContentManager()
