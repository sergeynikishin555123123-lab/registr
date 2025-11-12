import csv
import os
from typing import Dict, List

class ContentManager:
    def __init__(self):
        self.content = {}
        self.load_content()
    
    def load_content(self):
        """Загружает контент из CSV файла"""
        try:
            with open('content.csv', 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    key = row['key']
                    self.content[key] = {
                        'text': row['text'],
                        'buttons': [btn.strip() for btn in row['button'].split(',')] if row['button'] else [],
                        'comment': row.get('comment', '')
                    }
        except FileNotFoundError:
            print("⚠️ Файл content.csv не найден")
    
    def get_text(self, key: str, user_scenario: str = 'default') -> str:
        """Получает текст по ключу с учетом сценария"""
        scenario_key = f"{key}_{user_scenario}"
        return self.content.get(scenario_key, {}).get('text', self.content.get(key, {}).get('text', 'Текст не найден'))
    
    def get_buttons(self, key: str, user_scenario: str = 'default') -> List[str]:
        """Получает кнопки по ключу с учетом сценария"""
        scenario_key = f"{key}_{user_scenario}"
        return self.content.get(scenario_key, {}).get('buttons', self.content.get(key, {}).get('buttons', []))

content_manager = ContentManager()
