import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import polars as pl
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.common.exceptions import (TimeoutException)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('parser.log'),
        logging.StreamHandler()
    ]
)

STATE_FILE = 'to_process.json'
PROCESSED_URLS_FILE = 'processed_urls.json'
DATA_FILE = 'data.csv'
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30
DELAY_RANGE = (5, 15)
CAPTCHA_TIMEOUT = 30


class SeleniumParser:
    def __init__(self):
        self.ua = UserAgent()
        self.driver = self._init_driver()

    def _init_driver(self):
        """Инициализация Edge WebDriver с настройками"""
        chrome_options = Options()

        # Настройки для имитации человека
        chrome_options.add_argument(f"user-agent={self.ua.random}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # Дополнительные опции для избежания детектирования
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-browser-side-navigation')

        try:
            # Автоматическая загрузка и настройка ChromeDriver
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # Изменяем свойства браузера, чтобы выглядеть более "человечно"
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            return driver
        except Exception as e:
            logging.error(f"Failed to initialize Chrome driver: {str(e)}")
            raise

    def _get_random_delay(self) -> float:
        """Случайная задержка между действиями"""
        return random.uniform(*DELAY_RANGE)

    def _solve_captcha(self) -> bool:
        """Попытка решения капчи"""
        try:
            # Проверяем наличие капчи
            captcha_frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe[title*='reCAPTCHA']")
            if not captcha_frames:
                return True  # Капчи нет, считаем что успешно

            # Переключаемся на фрейм капчи
            WebDriverWait(self.driver, CAPTCHA_TIMEOUT).until(
                EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe[title*='reCAPTCHA']"))
            )

            # Кликаем на чекбокс капчи
            captcha_checkbox = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".recaptcha-checkbox"))
            )
            captcha_checkbox.click()
            time.sleep(2)  # Ждем реакции на клик

            # Проверяем, не появилась ли аудио-капча
            audio_button = self.driver.find_elements(By.CSS_SELECTOR, "#recaptcha-audio-button")
            if audio_button:
                logging.warning("Audio captcha detected, skipping...")
                self.driver.switch_to.default_content()
                return False

            # Возвращаемся к основному контенту
            self.driver.switch_to.default_content()
            time.sleep(5)  # Даем время на проверку капчи
            return True

        except TimeoutException:
            logging.warning("Timeout while solving CAPTCHA")
            self.driver.switch_to.default_content()
            return False
        except Exception as e:
            logging.warning(f"Error solving CAPTCHA: {str(e)}")
            self.driver.switch_to.default_content()
            return False

    def _scroll_page(self):
        """Плавная прокрутка страницы для имитации человека"""
        try:
            scroll_pause_time = 0.5
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(scroll_pause_time)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
        except Exception as e:
            logging.debug(f"Error while scrolling: {str(e)}")

    def load_page(self, url: str) -> bool:
        """Загрузка страницы с обработкой капчи"""
        for attempt in range(MAX_RETRIES + 1):
            try:
                self.driver.get(url)
                time.sleep(self._get_random_delay())

                # Прокручиваем страницу
                self._scroll_page()

                # Проверяем наличие капчи перед попыткой решения
                captcha_frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe[title*='reCAPTCHA']")
                if captcha_frames:
                    logging.info("CAPTCHA detected, attempting to solve...")
                    if not self._solve_captcha():
                        logging.warning("Failed to solve CAPTCHA")
                        if attempt < MAX_RETRIES:
                            time.sleep(self._get_random_delay() * (attempt + 1))
                            continue
                        return False

                # Проверяем что страница загрузилась
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                return True

            except Exception as e:
                logging.warning(f"Attempt {attempt + 1}: Error loading {url} - {str(e)}")
                if attempt < MAX_RETRIES:
                    time.sleep(self._get_random_delay() * (attempt + 1))

        logging.error(f"Failed to load {url} after {MAX_RETRIES} attempts")
        return False

    def get_page_html(self) -> Optional[str]:
        """Получение HTML содержимого страницы"""
        try:
            return self.driver.page_source
        except Exception as e:
            logging.error(f"Error getting page HTML: {str(e)}")
            return None

    def close(self):
        """Закрытие драйвера"""
        try:
            self.driver.quit()
        except Exception as e:
            logging.error(f"Error closing driver: {str(e)}")


def load_state(filename: str) -> Optional[dict]:
    """
    Загружаем состояние из JSON файла
    :return: dict of urls
    """
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Error loading state from {filename}: {str(e)}")
    return None


def save_state(data: Dict,
               filename: str
               ) -> None:
    """Сохраняем состояние в JSON файл"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error saving state to {filename}: {str(e)}")


def load_or_create_df(path: str) -> pl.DataFrame:
    """Загружаем существующий DataFrame или создаем новый"""
    try:
        if Path(path).exists():
            df = pl.read_csv(path)
            # Приводим типы столбцов к нужным
            return df.with_columns([
                pl.col('film_name').cast(pl.Utf8),
                # pl.col('year').cast(pl.Utf8),
                pl.col('user_review').cast(pl.Utf8),
                pl.col('review_type').cast(pl.Utf8)
            ])
    except Exception as e:
        logging.error(f"Error loading DataFrame from {path}: {str(e)}")

    return pl.DataFrame(schema={
        'film_name': pl.Utf8,
        # 'year': pl.Utf8,
        'user_review': pl.Utf8,
        'review_type': pl.Utf8
    })


def save_df(df: pl.DataFrame,
            path: str
            ) -> None:
    """Сохраняем DataFrame в CSV"""
    try:
        df = df.with_columns([
            pl.col('film_name').cast(pl.Utf8),
            # pl.col('year').cast(pl.Utf8),
            pl.col('user_review').cast(pl.Utf8),
            pl.col('review_type').cast(pl.Utf8)
        ])
        df.write_csv(path)
    except Exception as e:
        logging.error(f"Error saving DataFrame to {path}: {str(e)}")


def parse_reviews(html: str) -> List[str]:
    """Парсим отзывы из HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    reviews = []
    review_spans = soup.find_all('span', class_='_reachbanner_', itemprop='reviewBody')
    for span in review_spans:
        # Получаем текст и очищаем его от лишних пробелов
        review_text = span.get_text(strip=True)
        if review_text:
            reviews.append(review_text)
    return reviews


def parse_film_info(html: str) -> str:
    """Парсим информацию о фильме"""
    soup = BeautifulSoup(html, 'html.parser')
    name_elements = soup.find_all(class_='styles_originalTitle__JaNKM')
    if not name_elements:
        return "Unknown"
    # Берем первый найденный элемент и извлекаем текст
    name = name_elements[0].get_text(strip=True)
    return name if name else "Unknown"


# def load_data(url: str) -> List[str]:
#     """Load reviews data from URL."""
#     r = requests.get(url, headers=HEADERS)
#     soup = BeautifulSoup(r.text, 'html.parser')
#     reviews = soup.find_all(class_='_reachbanner_')
#     return [''.join(review.find_all(text=True)) for review in reviews]
#
# def get_name(url: str) -> tuple:
#     """Get film name and year from URL."""
#     r = requests.get(url, headers=HEADERS)
#     soup = BeautifulSoup(r.text, 'html.parser')
#     name = soup.find_all(class_='alternativeHeadline')
#     name_clean = name[0].find_all(text=True) if name else []
#     return (str(name_clean[0]), str(name_clean[1])) if len(name_clean) >= 2 else ('Unknown', '0')


def process_url(
        parser: SeleniumParser,
        url: str,
        status: str,
        df: pl.DataFrame,
        max_pages: int = 5
) -> Tuple[pl.DataFrame, bool]:
    """Обрабатываем URL и возвращаем обновленный DataFrame и статус успеха"""
    success = True
    name = "Unknown"

    # Сначала получаем информацию о фильме
    if parser.load_page(url):
        html = parser.get_page_html()
        if html:
            name = parse_film_info(html)
        else:
            logging.warning(f"Failed to get film info from {url}")
            success = False
    else:
        logging.warning(f"Failed to load film page {url}")
        success = False

    # Обрабатываем страницы с отзывами
    for page in range(1, max_pages + 1):
        review_url = f"{url}reviews/ord/date/status/{status}/perpage/200/page/{page}/"
        if parser.load_page(review_url):
            html = parser.get_page_html()
            if html:
                reviews = parse_reviews(html)
                new_data = pl.DataFrame({
                    'film_name': [name] * len(reviews),
                    # 'year': [year] * len(reviews),
                    'user_review': reviews,
                    'review_type': [status] * len(reviews)
                })
                df = pl.concat([df, new_data])
                time.sleep(parser._get_random_delay())
            else:
                success = False
                break
        else:
            success = False
            break
        return df, success


def main():
    # Инициализация парсера с защитой от блокировки
    parser = SeleniumParser()
    try:
        # Загрузка состояния
        url_status = load_state(STATE_FILE) or {'saved_urls': []}
        processed_urls = load_state(PROCESSED_URLS_FILE) or {'processed': []}

        # Преобразуем в множества для быстрого поиска
        processed_urls_set = set(processed_urls.get('processed', []))
        urls_to_process = set(url_status.get('saved_urls', [])) - processed_urls_set

        # Загружаем или создаем DataFrame
        df = load_or_create_df(DATA_FILE)

        statuses = ['good', 'bad', 'neutral']

        for url in urls_to_process:
            try:
                logging.info(f"Starting processing URL: {url}")
                all_status_success = True

                for status in statuses:
                    logging.info(f"Processing status: {status}")
                    df, success = process_url(parser, url, status, df)
                    if not success:
                        all_status_success = False
                        logging.warning(f"Failed to process status {status} for {url}")
                        break
                    time.sleep(parser._get_random_delay())

                if all_status_success:
                    # Добавляем URL в обработанные только если все статусы успешно обработаны
                    processed_urls['processed'].append(url)
                    save_state(processed_urls, PROCESSED_URLS_FILE)

                    # Сохраняем DataFrame
                    save_df(df, DATA_FILE)
                    logging.info(f"Successfully processed URL: {url}")
                else:
                    logging.warning(f"Not all statuses processed for {url}, will retry later")
                    break
            except Exception as e:
                print(f"Failed to process {url}: {str(e)}")
                break
    finally:
        parser.close()


if __name__ == "__main__":
    main()
