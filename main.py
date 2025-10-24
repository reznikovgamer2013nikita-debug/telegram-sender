"""
Telegram массовая рассылка
Отправляет последнее сообщение из избранного во все группы
"""

import sys
import os
import subprocess


def check_and_install_requirements():
    """Проверка и автоустановка библиотек"""
    print("\n  Проверка библиотек...")
    
    required = ['telethon']
    missing = []
    
    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"  Установка {', '.join(missing)}...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("  OK\n")
        except Exception as e:
            print(f"  Ошибка: {e}\n")
            print("  Установите вручную: pip install telethon")
            sys.exit(1)
    else:
        print("  OK\n")


# Проверяем библиотеки перед импортом
check_and_install_requirements()

import asyncio
import random
import os
import sys
import logging
import gc  # Для очистки памяти (Termux оптимизация)
from datetime import datetime
from typing import Optional, List

from telethon import TelegramClient, events, errors
from telethon.tl.types import (
    Channel, Chat, User, Message,
    MessageMediaPhoto, MessageMediaDocument,
    MessageMediaWebPage, MessageMediaPoll
)
from telethon.tl.functions.channels import GetFullChannelRequest

from config import Config


def setup_interactive():
    """Интерактивная настройка"""
    Config.ensure_data_dir()
    
    print("\n  TELEGRAM РАССЫЛКА\n")
    
    # Проверяем сессию
    session_path = f"{Config.SESSION_NAME}.session"
    session_exists = os.path.exists(session_path)
    
    # Загружаем сохраненные настройки
    settings_loaded = Config.load_settings()
    
    # Если настройки загружены - показываем их
    if settings_loaded:
        print(f"  API: OK")
        if session_exists:
            print(f"  Сессия: OK\n")
        else:
            print(f"  Сессия: нужен код\n")
    else:
        # Первый раз - запрашиваем всё
        print("  my.telegram.org\n")
        Config.API_ID = int(input("  API ID: ").strip())
        Config.API_HASH = input("  API Hash: ").strip()
        if not session_exists:
            Config.PHONE_NUMBER = input("  Телефон: ").strip()
        Config.save_settings()
        print()
    
    # Задержки
    print("  Между чатами (сек):")
    delay_chat = input("  ").strip()
    
    if "-" in delay_chat:
        min_chat, max_chat = delay_chat.split("-")
        Config.DELAY_BETWEEN_CHATS_MIN = int(min_chat.strip())
        Config.DELAY_BETWEEN_CHATS_MAX = int(max_chat.strip())
    else:
        delay_val = int(delay_chat)
        Config.DELAY_BETWEEN_CHATS_MIN = delay_val
        Config.DELAY_BETWEEN_CHATS_MAX = delay_val
    
    print("  Между кругами (сек):")
    delay_round = input("  ").strip()
    
    if "-" in delay_round:
        min_round, max_round = delay_round.split("-")
        Config.DELAY_BETWEEN_ROUNDS_MIN = int(min_round.strip())
        Config.DELAY_BETWEEN_ROUNDS_MAX = int(max_round.strip())
    else:
        delay_val = int(delay_round)
        Config.DELAY_BETWEEN_ROUNDS_MIN = delay_val
        Config.DELAY_BETWEEN_ROUNDS_MAX = delay_val
    
    # Платные группы
    print("  Платные группы (y/n):")
    paid_choice = input("  ").strip().lower()
    Config.SEND_TO_PAID_GROUPS = (paid_choice == 'y' or paid_choice == 'yes' or paid_choice == 'д' or paid_choice == 'да')
    print()


# Отключаем логи Telethon
logging.getLogger('telethon').setLevel(logging.CRITICAL)


class TelegramSender:
    """Класс для безопасной массовой рассылки в Telegram"""
    
    def __init__(self):
        # Убедимся что папка data существует
        Config.ensure_data_dir()
        
        # Создаем клиент с полным путем к сессии
        self.client = TelegramClient(
            Config.SESSION_NAME,
            Config.API_ID,
            Config.API_HASH,
            system_version="4.16.30-vxCUSTOM"
        )
        
    async def start(self):
        """Запуск клиента и авторизация"""
        print("  Авторизация...")
        
        await self.client.connect()
        
        if not await self.client.is_user_authorized():
            phone = Config.PHONE_NUMBER or input('  Телефон: ')
            await self.client.send_code_request(phone)
            code = input('  Код: ')
            try:
                await self.client.sign_in(phone, code)
            except Exception:
                password = input('  2FA: ')
                await self.client.sign_in(password=password)
            self.client.session.save()
        
        me = await self.client.get_me()
        print(f"  {me.first_name}\n")
    
    async def stop(self):
        """Корректное закрытие и сохранение сессии"""
        try:
            if self.client and self.client.session:
                self.client.session.save()
            await self.client.disconnect()
        except Exception as e:
            pass
        
    async def get_last_saved_message(self) -> Optional[Message]:
        """Получить последнее сообщение из избранного"""
        try:
            messages = await self.client.get_messages(Config.SAVED_MESSAGES_ID, limit=1)
            if messages:
                return messages[0]
            else:
                return None
        except Exception as e:
            return None
    
    async def get_all_groups(self) -> List:
        """Получить все группы и каналы, где можно отправлять сообщения"""
        groups = []
        
        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            
            # Проверяем, что это группа или канал (не личный чат)
            if isinstance(entity, (Channel, Chat)):
                # Проверяем права на отправку сообщений
                try:
                    if isinstance(entity, Channel):
                        # Для каналов проверяем, можем ли отправлять
                        if entity.broadcast and not entity.creator and not entity.admin_rights:
                            continue  # Пропускаем каналы, где мы не админы
                        
                        # Пропускаем каналы, где мы забанены или нет прав
                        if entity.banned_rights and entity.banned_rights.send_messages:
                            continue
                    
                    groups.append({
                        'entity': entity,
                        'id': entity.id,
                        'title': entity.title,
                        'dialog': dialog
                    })
                    
                except Exception as e:
                    continue
        
        return groups
    
    async def check_slowmode(self, entity) -> int:
        """Проверить наличие slowmode в чате"""
        try:
            if isinstance(entity, Channel):
                full_channel = await self.client(GetFullChannelRequest(entity))
                slowmode = full_channel.full_chat.slowmode_seconds
                return slowmode or 0
        except Exception as e:
            return 0
        return 0
    
    async def send_message_to_chat(self, chat, message: Message) -> tuple:
        """Отправить сообщение в чат. Возвращает (успех, причина)"""
        try:
            entity = chat['entity']
            
            # Микропауза перед проверками (имитация человека)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Быстрая проверка платных групп (оптимизировано для Termux)
            if isinstance(entity, Channel) and not Config.SEND_TO_PAID_GROUPS:
                try:
                    full_channel = await asyncio.wait_for(
                        self.client(GetFullChannelRequest(entity)),
                        timeout=8.0  # Уменьшен с 10
                    )
                    if hasattr(full_channel.full_chat, 'paid_media_allowed') and full_channel.full_chat.paid_media_allowed:
                        return (False, "платная")
                except:
                    pass
            
            # Быстрая проверка slowmode (оптимизировано для Termux)
            try:
                slowmode = await asyncio.wait_for(
                    self.check_slowmode(chat['entity']),
                    timeout=8.0  # Уменьшен с 10
                )
                if slowmode > 0:
                    return (False, "slowmode")
            except:
                pass
            
            # Микропауза перед отправкой
            await asyncio.sleep(random.uniform(0.2, 0.5))
            
            # Отправляем сообщение (оптимизировано для Termux)
            await asyncio.wait_for(
                self.client.send_message(
                    chat['entity'],
                    message.text or "",
                    file=message.media if message.media else None
                ),
                timeout=20.0  # Уменьшен с 25 для экономии памяти
            )
            
            return (True, None)
        
        except asyncio.TimeoutError:
            return (False, "таймаут")
            
        except errors.FloodWaitError as e:
            wait_seconds = e.seconds
            mins = wait_seconds // 60
            secs = wait_seconds % 60
            
            print(f"\n  FloodWait: {mins}м {secs}с ({datetime.now().strftime('%H:%M')})")
            await asyncio.sleep(wait_seconds)
            print(f"  OK ({datetime.now().strftime('%H:%M')})\n")
            
            return (False, "floodwait")
            
        except errors.ChatWriteForbiddenError:
            return (False, "нет прав")
            
        except errors.UserBannedInChannelError:
            return (False, "бан")
            
        except errors.SlowModeWaitError as e:
            return (False, "slowmode")
            
        except Exception as e:
            return (False, "ошибка")
    
    async def send_round(self):
        """Один круг рассылки"""
        message = await self.get_last_saved_message()
        if not message:
            print("  Нет сообщений")
            return
        
        groups = await self.get_all_groups()
        if not groups:
            print("  Нет групп")
            return
        
        total = len(groups)
        print(f"\n  Групп: {total}\n")
        
        # Перемешиваем группы для естественности
        random.shuffle(groups)
        
        success_count = 0
        skip_count = 0
        
        for i, chat in enumerate(groups, 1):
            try:
                # Показываем что обрабатываем
                print(f"  [{i}/{total}] → {chat['title']}", end='', flush=True)
                
                # Отправляем сообщение с таймаутом (меньше для Termux)
                try:
                    success, reason = await asyncio.wait_for(
                        self.send_message_to_chat(chat, message),
                        timeout=45.0  # Уменьшен с 60 для экономии памяти
                    )
                except asyncio.TimeoutError:
                    success, reason = False, "зависание"
                
                if success:
                    success_count += 1
                    print(f"\r  [{i}/{total}] ✓ {chat['title']}")
                else:
                    skip_count += 1
                    print(f"\r  [{i}/{total}] ⊗ {chat['title']} ({reason})")
                
                # АНТИ-ФЛУДВЕЙТ: умные задержки (БЕЗ адаптации после FloodWait)
                if i < len(groups):
                    base_delay = random.randint(
                        Config.DELAY_BETWEEN_CHATS_MIN,
                        Config.DELAY_BETWEEN_CHATS_MAX
                    )
                    
                    # Каждые 10 успешных отправок - увеличенная пауза
                    if success_count > 0 and success_count % 10 == 0:
                        extra = random.randint(3, 7)
                        print(f"  💤 Передышка +{extra}с")
                        await asyncio.sleep(base_delay + extra)
                    else:
                        # Варьируем задержку (±50%)
                        varied_delay = base_delay + random.uniform(-base_delay*0.3, base_delay*0.5)
                        await asyncio.sleep(max(1, varied_delay))
                    
            except Exception as e:
                # Если критическая ошибка - пропускаем
                skip_count += 1
                print(f"\r  [{i}/{total}] ⊗ {chat['title']} (критическая ошибка)")
                continue
        
        print(f"\n  Готово: {success_count}/{total}\n")
        
        # Сохраняем сессию после каждого круга
        try:
            if self.client and self.client.session:
                self.client.session.save()
        except Exception as e:
            pass
        
        # Очистка памяти (важно для Termux)
        gc.collect()
    
    async def run(self):
        """Основной цикл работы с автовосстановлением"""
        await self.start()
        
        print("  АВТО РЕЖИМ")
        print("  Оптимизация: Termux (экономия памяти)")
        print("  Анти-FloodWait: микропаузы + передышки")
        print("  Выход из групп с баном: ON")
        print("  Автовосстановление: ON\n")
        
        round_num = 0
        errors_count = 0
        max_errors = 5  # Максимум ошибок подряд
        
        while True:
            try:
                round_num += 1
                print(f"  --- Круг #{round_num} ---")
                
                await self.send_round()
                
                # Сбрасываем счетчик ошибок после успешного круга
                errors_count = 0
                
                delay = random.randint(
                    Config.DELAY_BETWEEN_ROUNDS_MIN,
                    Config.DELAY_BETWEEN_ROUNDS_MAX
                )
                
                if delay >= 60:
                    delay_text = f"{delay/60:.0f}м" if delay < 3600 else f"{delay/3600:.1f}ч"
                else:
                    delay_text = f"{delay}с"
                
                print(f"  Пауза: {delay_text}...")
                await asyncio.sleep(delay)
                
            except KeyboardInterrupt:
                print("\n  Стоп\n")
                break
                
            except Exception as e:
                errors_count += 1
                print(f"\n  Ошибка #{errors_count}: {e}")
                
                # Если слишком много ошибок подряд - останавливаемся
                if errors_count >= max_errors:
                    print(f"  Критично: {max_errors} ошибок подряд. Остановка.\n")
                    break
                
                # Иначе ждем и пробуем снова
                wait_time = min(60 * errors_count, 300)  # От 60 до 300 секунд
                print(f"  Переподключение через {wait_time}с...\n")
                await asyncio.sleep(wait_time)
                
                # Пытаемся переподключиться
                try:
                    await self.client.disconnect()
                    await asyncio.sleep(5)
                    await self.client.connect()
                    print("  Переподключено\n")
                except:
                    pass
        
        # Безопасное завершение
        await self.stop()


async def test_mode():
    """Тестовый режим - просмотр без отправки"""
    print("\n  ТЕСТ\n")
    
    sender = TelegramSender()
    await sender.start()
    
    message = await sender.get_last_saved_message()
    
    if not message:
        print("  Нет сообщений\n")
        await sender.stop()
        return
    
    print("  Сообщение: OK")
    if message.text:
        print(f"  {message.text[:60]}{'...' if len(message.text) > 60 else ''}")
    
    groups = await sender.get_all_groups()
    
    can_send = 0
    has_slowmode = 0
    
    for chat in groups:
        slowmode = await sender.check_slowmode(chat['entity'])
        if slowmode > 0:
            has_slowmode += 1
        else:
            can_send += 1
    
    print(f"\n  Групп: {len(groups)}")
    print(f"  Отправить: {can_send}")
    print(f"  Slowmode: {has_slowmode}\n")
    
    await sender.stop()


async def manual_mode():
    """Ручной режим - один круг"""
    print("\n  ОДИН КРУГ\n")
    
    sender = TelegramSender()
    await sender.start()
    await sender.send_round()
    await sender.stop()


async def interactive_menu():
    """Интерактивное меню"""
    sender = TelegramSender()
    await sender.start()
    
    while True:
        print("\n  МЕНЮ")
        print("  1 - Тест")
        print("  2 - Один круг")
        print("  3 - Авто режим")
        print("  4 - Группы")
        print("  5 - Избранное")
        print("  0 - Выход\n")
        
        choice = input("  ").strip()
        
        if choice == "1":
            await test_mode()
            input("\n  Enter...")
            
        elif choice == "2":
            await sender.send_round()
            input("\n  Enter...")
            
        elif choice == "3":
            await sender.run()
            break
            
        elif choice == "4":
            groups = await sender.get_all_groups()
            print(f"\n  Групп: {len(groups)}\n")
            for i, chat in enumerate(groups[:10], 1):
                print(f"  {i}. {chat['title']}")
            if len(groups) > 10:
                print(f"  ... +{len(groups)-10}")
            input("\n  Enter...")
            
        elif choice == "5":
            message = await sender.get_last_saved_message()
            if message:
                if message.text:
                    print(f"\n  {message.text[:80]}\n")
            else:
                print("\n  Пусто")
            input("\n  Enter...")
            
        elif choice == "0":
            break
    
    await sender.stop()


def check_session():
    """Проверка сохраненных настроек и сессии"""
    import json
    
    print("\n  ========================================")
    print("  ПРОВЕРКА АВТОВХОДА")
    print("  ========================================\n")
    
    if not os.path.exists("data"):
        print("  [X] Папка data не существует\n")
        return
    
    print("  [OK] Папка data существует\n")
    
    # Проверка настроек
    settings_path = "data/settings.json"
    if os.path.exists(settings_path):
        size = os.path.getsize(settings_path)
        print(f"  [OK] Настройки API")
        print(f"       {settings_path} ({size} байт)")
        try:
            with open(settings_path, 'r') as f:
                data = json.load(f)
                if 'api_id' in data and 'api_hash' in data:
                    print(f"       API ID: {data['api_id']}")
                    print(f"       API Hash: {data['api_hash'][:10]}...")
        except:
            print("       [!] Ошибка чтения")
    else:
        print(f"  [X] Настройки API отсутствуют")
    
    print()
    
    # Проверка сессии
    session_path = "data/session.session"
    if os.path.exists(session_path):
        size = os.path.getsize(session_path)
        print(f"  [OK] Сессия Telegram")
        print(f"       {session_path} ({size} байт)")
        if size > 0:
            print(f"       Активна")
    else:
        print(f"  [X] Сессия отсутствует")
    
    print("\n  " + "-" * 40 + "\n")
    
    # Итог
    settings_ok = os.path.exists(settings_path) and os.path.getsize(settings_path) > 0
    session_ok = os.path.exists(session_path) and os.path.getsize(session_path) > 0
    
    if settings_ok and session_ok:
        print("  >>> АВТОВХОД РАБОТАЕТ!")
        print("      Ничего вводить не нужно\n")
    elif settings_ok:
        print("  [!] Нужен будет код\n")
    elif session_ok:
        print("  [!] Нужен API ID и Hash\n")
    else:
        print("  ПЕРВЫЙ ЗАПУСК\n")


async def main():
    """Точка входа"""
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
        if mode == "check":
            check_session()
            return
        elif mode == "test":
            setup_interactive()
            sender = TelegramSender()
            await test_mode()
        elif mode == "manual":
            setup_interactive()
            await manual_mode()
        elif mode == "menu":
            setup_interactive()
            await interactive_menu()
        else:
            print("\n  Команды:")
            print("  python main.py         - авто режим")
            print("  python main.py menu    - меню")
            print("  python main.py test    - тест")
            print("  python main.py check   - проверка\n")
            return
    else:
        # Автоматический режим по умолчанию
        setup_interactive()
        sender = TelegramSender()
        await sender.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Выход\n")
    except Exception as e:
        print(f"\n  Ошибка: {e}\n")
