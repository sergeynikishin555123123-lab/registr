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
                logger.info(f"✅ Контент загружен: {len(self.content)} записей")
            else:
                self.create_default_content()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контента: {e}")
            self.create_default_content()
    
    def create_default_content(self):
        default_content = [
            {
                'key': 'welcome_default',
                'text': '🎉 Добро пожаловать в GenoLife!\n\nЯ помогу вам пройти анализ и улучшить здоровье.',
                'buttons': "['🧪 Начать 60-секундный тест', '💰 Оплатить анализ', '👤 Профиль', '🔗 Моя реф ссылка', 'ℹ️ О проекте']",
                'comment': 'Приветствие по умолчанию'
            },
            {
                'key': 'payment_description',
                'text': '💰 *Оплата анализа*\n\nСтоимость полного анализа: 2 990 руб.\n\nВключает:\n• Комплект для сбора анализов\n• Подробный отчет\n• Персональные рекомендации',
                'buttons': "[]",
                'comment': 'Описание оплаты'
            }
        ]
        
        df = pd.DataFrame(default_content)
        df.to_csv(self.content_file, index=False, encoding='utf-8')
        self.load_content()
    
    def get(self, key, default=None):
        return self.content.get(key, default)

content_manager = ContentManager()
