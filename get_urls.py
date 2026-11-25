import json
import os
import re
import time
from random import uniform

import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

URLS_FILE = 'to_process.json'
POPULAR_FILMS = 'https://www.kinopoisk.ru/lists/movies/popular-films/?b=foreign'


def convert(urls) -> list:
    """Convert URL values to strings and discard empty values."""
    return [str(url) for url in urls if url]


def load_state(file):
    """Load film URLs from JSON and restore the set used during collection."""
    if os.path.exists(file):
        with open(file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        state['saved_urls'] = set(state.get('saved_urls', []))
        return state
    return {'saved_urls': set()}


def save_urls(file, state):
    """Save the complete URL set in a deterministic JSON representation."""
    state_copy = state.copy()
    state_copy['saved_urls'] = sorted(state_copy['saved_urls'])
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(state_copy, f, ensure_ascii=False, indent=2)


def load_url(url) -> list:
    """Get film URLs from one popular-films page."""
    driver = webdriver.Chrome()
    try:
        driver.get(url)
        time.sleep(uniform(2, 5))

        wait = WebDriverWait(driver, 10)
        link_elements = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, 'a[href*="/film/"]')
            )
        )
        urls = convert(el.get_attribute('href') for el in link_elements)
        film_urls = [
            url for url in urls
            if re.fullmatch(r'https://www\.kinopoisk\.ru/film/\d+/', url)
        ]
        return list(dict.fromkeys(film_urls))
    finally:
        driver.quit()


def get_urls(url: str, state: dict, max_pages: int = 5) -> list:
    """Collect new film URLs and add them to the existing state."""
    film_pages = []
    delays = [10, 12, 11.1, 12.2, 13.4, 18, 15, 9.1, 10.5, 20, 13.1, 16.9]
    time.sleep(np.random.choice(delays))

    for page in range(1, max_pages + 1):
        loaded_data = load_url(url + f'&page={page}')
        if not loaded_data:
            break

        for film_url in loaded_data:
            if film_url not in state['saved_urls']:
                film_pages.append(film_url)
                state['saved_urls'].add(film_url)
        time.sleep(np.random.choice(delays))

    return film_pages


def main():
    urls_status = load_state(URLS_FILE)
    urls = get_urls(POPULAR_FILMS, urls_status)
    save_urls(URLS_FILE, urls_status)
    print(f'Added {len(urls)} new URLs; {len(urls_status["saved_urls"])} saved in total.')


if __name__ == '__main__':
    main()
