from datetime import datetime, timedelta
import logging
import os
import random
import sys
import time

from dotenv import load_dotenv
import requests
import vk_api

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
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
    except Exception as error:
        logging.error(f'Ошибка при отправке сообщения: {error}')
        raise


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != 200:
            logging.error(
                f'Эндпоинт: {ENDPOINT} вернул статус {response.status_code}.'
            )
            raise Exception(f'HTTPError: {response.status_code}')
        return response.json()
    except requests.RequestException as error:
        logging.error(
            f'Сбой в работе программы: Эндпоинт: {ENDPOINT}. {error}'
        )
        return None
    except Exception as error:
        logging.error(
            f'Сбой в работе программы: Эндпоинт {ENDPOINT}. {error}'
        )
        raise


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        logging.error('Полученный ответ не является словарем.')
        raise TypeError('Полученный ответ не является словарем.')
    if 'homeworks' not in response:
        logging.error('В ответе отсутствует ключ "homeworks".')
        raise KeyError('В ответе отсутствует ключ "homeworks".')
    if not isinstance(response['homeworks'], list):
        logging.error('В ответе по ключу "homeworks" не хранится список.')
        raise TypeError('В ответе по ключу "homeworks" не хранится список.')
    if 'current_date' not in response:
        logging.error('В ответе отсутствует ключ "current_date".')
        raise KeyError('В ответе отсутствует ключ "current_date".')
    if not isinstance(response['current_date'], int):
        logging.error(
            'В ответе по ключу "current_date" не хранится число(int).'
        )
        raise TypeError(
            'В ответе по ключу "current_date" не хранится число(int).'
        )


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


def processing_homeworks(homeworks, vk, last_statuses):
    """Обработка списка домашних работ, отправка сообщений."""
    for homework in homeworks:
        try:
            message = parse_status(homework)
        except (KeyError, ValueError) as error:
            logging.error(f'Ошибка данных в homework: {error}')
            continue
        name = homework['homework_name']
        status = homework['status']
        if last_statuses.get(name) != status:
            try:
                send_message(vk, message)
                last_statuses[name] = status
                logging.debug(
                    f'Для ДЗ:{name} обновлен статус: {status}.'
                )
            except Exception as error:
                logging.error(
                    f'Не удалось отправить сообщение: {error}'
                )


def main():
    """Основная логика работы бота."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    if not check_tokens():
        logging.critical('Программа принудительно остановлена.')
        sys.exit(1)

    # Создаем сессию для бота
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int((datetime.now() - timedelta(days=60)).timestamp())

    last_statuses = {}
    error_sent = False

    while True:
        try:
            response = get_api_answer(timestamp)
            if response is None:
                time.sleep(RETRY_PERIOD)
                continue
            check_response(response)
            homeworks = response['homeworks']
            current_date = response['current_date']

            if not homeworks:
                logging.debug('Обновлений по статусам нет.')
            else:
                processing_homeworks(homeworks, vk, last_statuses)
            timestamp = current_date
            error_sent = False

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if not error_sent:
                try:
                    send_message(vk, message)
                    error_sent = True
                except Exception as error:
                    logging.error(
                        f'Сообщение об ошибке не было отправлено: {error}'
                    )

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
