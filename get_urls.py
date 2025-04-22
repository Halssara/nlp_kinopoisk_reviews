import json
import os
import time
from random import uniform

import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.microsoft import EdgeChromiumDriverManager

URLS_FILE = 'to_process.json'


def convert(soup) -> list:
    """
        Convert urls dtype to string
        :param reviews: list of urls
        :return: list of strings
    """
    soup_converted = []
    for el in soup:
        for i in el:
            map(str, i)
        el = ''.join(el)
        soup_converted.append(el)
    return soup_converted


def load_state(file):
    """
    load urls from json
    :return: dict of urls
    """
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return {'saved_urls': set()}


def save_urls(file, state):
    """
    Write url list to json
    :param file: f-name
    :param state: dict to json
    :return: None
    """
    state_copy = state.copy()
    state_copy['saved_urls'] = list(state_copy['saved_urls'])
    with open(file, 'w') as f:
        json.dump(state, f)


def load_url(url) -> list:
    '''
    Get urls of populars films
    :param url: url top films
    :return: film urls on kinopoisk
    '''
    driver = webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()))
    driver.get(url)
    time.sleep(uniform(2, 5))

    wait = WebDriverWait(driver, 10)
    link_elements = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'base-movie-main-info_link__YwtP1')))

    loaded_urls = [el.get_attribute('href') for el in link_elements]
    driver.quit()
    return convert(loaded_urls)


def get_urls(url: str, state: dict) -> list:
    """
    Function to write result top urls from kinopoisk
    :param url: url page
    :param state: current urls in json
    :return: film pages
    """
    page = 1
    delays = [10, 12, 11.1, 12.2, 13.4, 18, 15, 9.1, 10.5, 20, 13.1, 16.9]
    film_pages = []
    time.sleep(np.random.choice(delays))
    while page <= 5:
        loaded_data = load_url(url + f'&page={page}')
        if not loaded_data:
            break
        else:
            for el in loaded_data:
                if el not in state['saved_urls']:
                    film_pages.append(el)
                    state['saved_urls'].add(el)
            page += 1
            time.sleep(np.random.choice(delays))
    return film_pages


POPULAR_FILMS = "https://www.kinopoisk.ru/lists/movies/popular-films/?b=foreign"

urls_status = load_state(URLS_FILE)
urls = get_urls(POPULAR_FILMS, urls_status)

save_urls(URLS_FILE, {'saved_urls': urls})
