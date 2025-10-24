# Конфигурация для Telegram рассылки
import os
import json

class Config:
    """Настройки для Telegram бота"""
    
    # Папка для данных (сессия и настройки)
    DATA_DIR = "data"
    
    # Путь к файлу сессии
    SESSION_NAME = os.path.join(DATA_DIR, "session")
    
    # Файл с сохраненными настройками
    SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
    
    # ID избранного чата (Saved Messages)
    SAVED_MESSAGES_ID = "me"
    
    # Настройки задаются при запуске
    API_ID = None
    API_HASH = None
    PHONE_NUMBER = None
    DELAY_BETWEEN_CHATS_MIN = None
    DELAY_BETWEEN_CHATS_MAX = None
    DELAY_BETWEEN_ROUNDS_MIN = None
    DELAY_BETWEEN_ROUNDS_MAX = None
    SEND_TO_PAID_GROUPS = False  # Отправлять в группы со звездами
    
    @staticmethod
    def ensure_data_dir():
        """Создать папку для данных если её нет"""
        if not os.path.exists(Config.DATA_DIR):
            os.makedirs(Config.DATA_DIR)
            print(f"  📁 Создана папка: {Config.DATA_DIR}/")
    
    @staticmethod
    def save_settings():
        """Сохранить настройки API"""
        Config.ensure_data_dir()
        settings = {
            'api_id': Config.API_ID,
            'api_hash': Config.API_HASH
        }
        with open(Config.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
    
    @staticmethod
    def load_settings():
        """Загрузить сохраненные настройки API"""
        if os.path.exists(Config.SETTINGS_FILE):
            try:
                with open(Config.SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    Config.API_ID = settings.get('api_id')
                    Config.API_HASH = settings.get('api_hash')
                    return True
            except:
                return False
        return False

