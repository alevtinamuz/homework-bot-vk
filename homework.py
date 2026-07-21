from datetime import datetime, timedelta
import logging
import os
import random
import sys
import time

from dotenv import load_dotenv
from http import HTTPStatus
import requests
import vk_api
from vk_api.exceptions import ApiError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 6
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID,
    }
    missing = [name for name, value in tokens.items() if not value]
    if missing:
        logging.critical(
            f'Отсутствуют обязательные переменные окружения: '
            f'{', '.join(missing)}'
        )
        return False
    return True


def send_message(vk, message):
    """Отправляет сообщение в VK-чат."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=random.randint(0, 100000)
        )
        logging.debug(f'Сообщение отправлено: {message}')
        return True
    except ApiError as error:
        logging.error(f'Ошибка VK API: {error}')
        return False
    except requests.RequestException as error:
        logging.error(f'Сетевая ошибка: {error}')
        return False
    except Exception as error:
        logging.error(f'Ошибка при отправке сообщения: {error}')
        return False


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise ConnectionError(
            f'Сетевая ошибка. Эндпоинт: {ENDPOINT}. {error}. '
            f'Параметры запроса: {payload}'
        )
    if response.status_code != HTTPStatus.OK:
        raise RuntimeError(
            f'HTTPError: {response.status_code}. Параметры запроса: {payload}'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        message = (
            f'Полученный ответ не является словарем. '
            f'Ответ является: {type(response).__name__}'
        )
        logging.error(message)
        raise TypeError(message)
    if 'homeworks' not in response:
        message = 'В ответе отсутствует ключ "homeworks".'
        logging.error(message)
        raise KeyError(message)
    if not isinstance(response['homeworks'], list):
        message = (
            f'В ответе по ключу "homeworks" не хранится список. '
            f'Ответ хранит: {type(response['homeworks']).__name__}'
        )
        logging.error(message)
        raise TypeError(message)
    if 'current_date' not in response:
        message = 'В ответе отсутствует ключ "current_date".'
        logging.error(message)
        raise KeyError(message)
    if not isinstance(response['current_date'], int):
        message = (
            f'В ответе по ключу "current_date" не хранится число(int). '
            f'Ответ хранит: {type(response['current_date']).__name__}'
        )
        logging.error(message)
        raise TypeError(message)


def parse_status(homework):
    """Извлекает из информации о конкретной домашней работе статус."""
    if 'homework_name' not in homework:
        logging.error('В homework отсутствует ключ "homework_name".')
        raise KeyError('В homework отсутствует ключ "homework_name".')

    if 'status' not in homework:
        logging.error('В homework отсутствует ключ "status".')
        raise KeyError('В homework отсутствует ключ "status".')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        logging.error(
            f'Неожиданный статус домашней работы, обнаруженный в ответе API: '
            f'{status}.'
        )
        raise ValueError(
            f'Неожиданный статус домашней работы, обнаруженный в ответе API: '
            f'{status}.'
        )

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Программа принудительно остановлена.')
        sys.exit(1)

    # Создаем сессию для бота
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int((datetime.now() - timedelta(days=60)).timestamp())

    last_status = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            homeworks = response['homeworks']
            current_date = response['current_date']

            if not homeworks:
                logging.debug('Обновлений по статусам нет.')
            else:
                status = homeworks[-1].get('status')
                if status != last_status:
                    message = parse_status(homeworks[-1])
                    if send_message(vk, message):
                        last_status = status
                        logging.debug(f'Статус обновлен: {status}')
            timestamp = current_date

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if last_status != message:
                if send_message(vk, message):
                    last_status = message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    main()
