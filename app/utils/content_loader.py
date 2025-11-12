import csv
import os
from typing import Dict

class ContentLoader:
    def __init__(self):
        self.content = {}
    
    def load_from_csv(self, file_path: str):
        """Загружает контент из CSV файла"""
        if not os.path.exists(file_path):
            return {}
        
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                key = row['key']
                self.content[key] = {
                    'text': row['text'],
                    'button': row.get('button', ''),
                    'comment': row.get('comment', '')
                }
        return self.content

content_loader = ContentLoader()
