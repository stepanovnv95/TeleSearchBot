# -*- coding: utf-8 -*-

# TODO: подсказки при вводе команд

# TODO: жирынй шрифт не жирный, ** не работает

import config
import telebot
from enum import Enum
import sqlite3
import schedule
import time
import threading
from google import google

bot = telebot.TeleBot(config.token)


# состояния диалога
class States(Enum):
    START = 0  # начальное состояние
    ADD_REQUESTS = 1  # добавление поисковых запросов
    REMOVE_REQUESTS = 2  # удаление поисковых запросов
    SET_TIME = 3  # установка времени рассылки


users_states = {}


def set_user_state(id, state):
    users_states[id] = state


def get_user_state(id):
    if id not in users_states.keys():
        users_states[id] = States.START.value
    return users_states[id]


# декоратор, автоматически открывающий и закрывающий БД
def sqlite_decorator(decorate_function):
    def wrapper(message):
        connection = sqlite3.connect(config.database)
        cursor = connection.cursor()
        r = decorate_function(message, connection, cursor)  # вызов декорируемой функции
        connection.close()
        return r

    return wrapper


# /start - регистрация пользователя
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) <= States.START.value,
    commands=['start']
)
@sqlite_decorator
def cmd_start(message, connection, cursor):
    # проверка наличия пользовател в БД
    sql_query = "SELECT * FROM Users WHERE chat_id == ?"
    sql_data = (message.chat.id,)
    cursor.execute(sql_query, sql_data)
    if cursor.fetchone() is not None:
        return
    # если пользователя нет, то добавляем
    sql_query = "INSERT INTO Users (chat_id, state) VALUES (?, ?)"
    sql_data = (message.chat.id, 0)
    cursor.execute(sql_query, sql_data)
    # устанавливаем никакое расписание поиска
    sql_query = "INSERT INTO Time (chat_id, time) VALUES (?, ?)"
    sql_data = (message.chat.id, '-')
    cursor.execute(sql_query, sql_data)
    connection.commit()
    # вывод хелпа
    cmd_help(message)


# /help - помощь по командам
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.START.value,
    commands=['help']
)
def cmd_help(message):
    msg = '''
/start - завести учетную запись
/help - список команд
/requests - список ваших запросов
/add - добавить поисковой запрос
/remove - удалить поисковой запрос
/time - настройка расписания поиска
/stop - отключение рассылки сообщений'''
    bot.send_message(message.chat.id, msg)


# /requests - вывод списка поисковых запросов
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.START.value,
    commands=['requests']
)
@sqlite_decorator
def cmd_requests(message, connection, cursor):
    sql_query = "SELECT request FROM Requests WHERE chat_id = ?"
    sql_data = (message.chat.id,)
    requests = cursor.execute(sql_query, sql_data).fetchall()
    msg = 'Ваши поисковые запросы:\n'
    for r in requests:
        msg += r[0] + '\n'
    bot.send_message(message.chat.id, msg)


# /add - переход в состояние добавления поисковых запросов
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.START.value,
    commands=['add']
)
def cmd_add(message):
    # меняет состояние пользователя на ввод поисковых запросов
    set_user_state(message.chat.id, States.ADD_REQUESTS.value)
    msg = '''
Введите поисковой запрос.
Можно ввести несколько запросов, каждый на новой строке.
"-" чтобы отменить.'''
    bot.send_message(message.chat.id, msg)


# получение поисковых запросов после команды /add
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.ADD_REQUESTS.value
)
@sqlite_decorator
def cmd_add_add(message, connection, cursor):
    msg = '''
Добавлены следующие запросы:\n'''
    if message.text != '-':
        requests = message.text.split('\n')
        for r in requests:
            if r == '':
                continue
            msg += r + '\n'
            sql_query = "INSERT INTO Requests (chat_id, request) VALUES (?, ?)"
            sql_data = (message.chat.id, r)
            cursor.execute(sql_query, sql_data)
            connection.commit()
    # возвращаем состояние пользователя
    set_user_state(message.chat.id, States.START.value)
    bot.send_message(message.chat.id, msg)


# /remove - переход в состояние удаления поисковых запросов
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.START.value,
    commands=['remove']
)
@sqlite_decorator
def cmd_remove(message, connection, cursor):
    # меняет состояние пользователя на удаление поисковых запросов
    set_user_state(message.chat.id, States.REMOVE_REQUESTS.value)
    # вывод сохраненных запросов
    msg = '''
Введите число, чтобы удалить запрос или "-" чтобы выйти из меню удаления.
Чтобы удалить несколько запросов, надо вводить числа на новой строке.
0. Удалить все запросы\n'''
    sql_query = "SELECT request FROM Requests WHERE chat_id = ?"
    sql_data = (message.chat.id,)
    r = cursor.execute(sql_query, sql_data).fetchall()
    # каждый запрос пронумерован чтобы не вводить сам запрос
    for i in range(len(r)):
        msg += '{0}. {1}\n'.format(i + 1, r[i][0])
    bot.send_message(message.chat.id, msg)


# удаление поисковых запросов после команды /remove
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.REMOVE_REQUESTS.value
)
@sqlite_decorator
def cmd_remove_remove(message, connection, cursor):
    sql_query = "SELECT request FROM Requests WHERE chat_id = ?"
    sql_data = (message.chat.id,)
    requests = cursor.execute(sql_query, sql_data).fetchall()
    nums = message.text.split('\n')
    msg = 'Удалены запросы:\n'
    for n in nums:
        # пытаемся получить число из сообщения
        try:
            n = int(n)
        except ValueError:
            n = None
        if (n is None) or (n > len(requests)):
            continue
        if n == 0:
            # удалить все
            sql_query = "DELETE FROM Requests WHERE chat_id = ?"
            sql_data = (message.chat.id,)
            cursor.execute(sql_query, sql_data)
            connection.commit()
            msg = 'Список запросов очищен'
            break
        # n точно число от 1 до количества запросов
        sql_query = "DELETE FROM Requests WHERE chat_id = ? AND request = ? "
        sql_data = (message.chat.id, requests[n - 1][0])
        msg += sql_data[1] + '\n'
        cursor.execute(sql_query, sql_data)
        connection.commit()
    # возвращаем состояние пользователя
    set_user_state(message.chat.id, States.START.value)
    bot.send_message(message.chat.id, msg)


# /time - переход в состояние установки времени поиска
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.START.value,
    commands=['time']
)
@sqlite_decorator
def cmd_time(message, connection, cursor):
    # меняет состояние пользователя на выбор времени поиска
    set_user_state(message.chat.id, States.SET_TIME.value)
    # поиск текущего время поиска
    sql_query = "SELECT time FROM Time WHERE chat_id = ?"
    sql_data = (message.chat.id,)
    time = cursor.execute(sql_query, sql_data).fetchone()
    msg = 'Ваше расписание поиска: '
    if time[0] == '-':
        msg += 'никогда'
    else:
        msg += time[0]
    msg += '''
Укажите новое время поиска.
На первой строке дни: все, пн, вт, ср, чт, пт, сб, вск
На второй время, например: 15:40
Одним сообщением!
"-" для отмены.'''
    bot.send_message(message.chat.id, msg)


# установка времени поиска после команды /time
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.SET_TIME.value
)
@sqlite_decorator
def cmd_time_time(message, connection, cursor):
    day = message.text.split('\n')[0]  # в первой строке день
    time = message.text.split('\n')[-1]  # во второй - время
    time_str = ''  # в результате парсинга, время поиска будет указано в этой строке
    # попытка распознать дни недели
    days_list = ['все', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вск']
    for d in day.split(','):
        for a in days_list:
            if a in d:
                if time_str == '':
                    time_str += a
                else:
                    time_str += ',' + a
                break
    if time_str == '':  # день не указан
        time_str = 'cancel'
    else:
        # попытка распознать время
        time_str += ' '
        try:
            hour = int(time.split(':')[0])
            if hour < 0 or hour > 23:
                hour = 0
            minutes = int(time.split(':')[-1])
            if minutes < 0 or minutes > 59:
                minutes = 0
        except ValueError:
            hour, minutes = 0, 0

        time_str += str(hour) + ':'
        if minutes < 10:
            time_str += '0' + str(minutes)
        else:
            time_str += str(minutes)
    # запоминаем время
    if (time_str != 'cancel'):
        sql_query = "UPDATE Time SET time = ? WHERE chat_id = ?"
        sql_data = (time_str, message.chat.id)
        cursor.execute(sql_query, sql_data)
        # перезапуск задачи
        schedule.clear(str(message.chat.id))
        create_task_from_string(time_str, message.chat.id)
    # возвращаем состояние пользователя
    set_user_state(message.chat.id, States.START.value)
    if time_str == 'cancel':
        msg = "Расписание поиска не изменено"
    else:
        msg = "Расписание поиска: "
        msg += time_str
    bot.send_message(message.chat.id, msg)


# /stop - отмена поиска по расписанию (время поиска = никогда)
@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id) == States.START.value,
    commands=['stop']
)
@sqlite_decorator
def cmd_stop(message, connection, cursor):
    sql_query = "UPDATE Time SET time = ? WHERE chat_id = ?"
    sql_data = ('-', message.chat.id)
    cursor.execute(sql_query, sql_data)
    connection.commit()
    schedule.clear(str(message.chat.id))
    msg = '''
Вы отключили рассылку сообщений'''
    bot.send_message(message.chat.id, msg)


# запуск поиска для конкретного пользователя
@sqlite_decorator
def start_search(id, connection, cursor):
    sql_query = "SELECT Request FROM Requests WHERE chat_id = ?"
    sql_data = (id,)
    requests = cursor.execute(sql_query, sql_data).fetchall()
    for req in requests:
        result = google.search(query=req[0], time_interval='w', pages=config.google_pages, timeout=20)
        msg_array = ['Результаты по запросу:\n' + req[0] + '\n']
        need_send = False
        for res in result:
            # проверка на выдачу этой ссылки
            sql_query = "SELECT chat_id FROM Found WHERE chat_id = ? AND link = ?"
            sql_data = (id, res.link)
            sql_result = cursor.execute(sql_query, sql_data).fetchall()
            if len(sql_result) == 0:  # эта ссылка найдена в первый раз
                need_send = True
                # сохранение в БД
                sql_query = "INSERT INTO Found (chat_id, link) VALUES (?, ?)"
                sql_data = (id, res.link)
                cursor.execute(sql_query, sql_data)
                connection.commit()
                # формирование сообщения
                msg_array.append('**' + res.name + '**\n')
                msg_array[-1] += res.description + '\n'
                msg_array[-1] += res.link + '\n'

        # отправка результатов
        if need_send:
            # сообщения нужно нарезать блоками не более 4096 смволов
            limit = 4096
            msg = ''
            for block in msg_array:
                if len(msg) + len(block) <= 4096 - 4:  # минус '\n\n' x2
                    msg += block + '\n\n'
                else:
                    bot.send_message(id, msg)
                    msg = block + '\n\n'
                    time.sleep(5)
            if msg != '':
                bot.send_message(id, msg)
        time.sleep(60)  # чтобы в гугле не забанили


# создает задачи из строки времени
def create_task_from_string(string, id):
    string = string.split(' ')
    days = string[0].split(',')
    time = string[1]
    for d in days:
        if d == 'все':
            schedule.every().day.at(time).do(start_search, id).tag(str(id))
        elif d == 'пн':
            schedule.every().monday.at(time).do(start_search, id).tag(str(id))
        elif d == 'вт':
            schedule.every().thursday.at(time).do(start_search, id).tag(str(id))
        elif d == 'ср':
            schedule.every().wednesday.at(time).do(start_search, id).tag(str(id))
        elif d == 'чт':
            schedule.every().thursday.at(time).do(start_search, id).tag(str(id))
        elif d == 'пт':
            schedule.every().friday.at(time).do(start_search, id).tag(str(id))
        elif d == 'сб':
            schedule.every().saturday.at(time).do(start_search, id).tag(str(id))
        elif d == 'вск':
            schedule.every().sunday.at(time).do(start_search, id).tag(str(id))


def create_tasks():
    connection = sqlite3.connect(config.database)
    cursor = connection.cursor()
    sql_query = "SELECT chat_id, time FROM Time"
    result = cursor.execute(sql_query).fetchall()
    connection.close()
    for r in result:
        chat_id = r[0]
        time = r[1]
        if time == '-':
            continue
        create_task_from_string(time, chat_id)


def sheldure_pending():
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    print('Это бот для телеграма, не выключать!')
    create_tasks()
    thread = threading.Thread(target=sheldure_pending)
    thread.start()
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            time.sleep(15)
