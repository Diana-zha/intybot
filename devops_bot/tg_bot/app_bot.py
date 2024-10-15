import re
import logging
import paramiko
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
import psycopg2

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для базы данных
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')

# Флаги для определения типа поиска
CONFIRMATION = 1
SEARCH_EMAIL = 2
SEARCH_PHONE = 3
VERIFY_PASSWORD = 4

# Функция для отправки меню с кнопкой /help
def show_menu(update: Update, context: CallbackContext) -> None:
    keyboard = [['/help']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    update.message.reply_text("Выберите опцию:", reply_markup=reply_markup)

# Команды для поиска email и номера телефона
def find_email(update: Update, context: CallbackContext) -> int:
    context.user_data['searching_email'] = True
    context.user_data['searching_phone'] = False
    update.message.reply_text('Пожалуйста, отправьте текст для поиска email-адресов.')
    return SEARCH_EMAIL

def find_phone_number(update: Update, context: CallbackContext) -> int:
    context.user_data['searching_phone'] = True
    context.user_data['searching_email'] = False
    update.message.reply_text('Пожалуйста, отправьте текст для поиска номеров телефонов.')
    return SEARCH_PHONE

def handle_message(update: Update, context: CallbackContext) -> int:
    text = update.message.text

    if context.user_data.get('searching_email'):
        emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
        if emails:
            update.message.reply_text(f'Найденные email-адреса: {", ".join(emails)}. Сохранить в БД? (да/нет)')
            context.user_data['emails'] = emails
            return CONFIRMATION
        else:
            update.message.reply_text('Email-адреса не найдены.')

    if context.user_data.get('searching_phone'):
        phones = re.findall(r'(\+7|8)[\s-]?(\(?\d{3}\)?)?[\s-]?(\d{3})[\s-]?(\d{2})[\s-]?(\d{2})', text)
        if phones:
            phones_list = [f"{phone[0]} {phone[2]}-{phone[3]}-{phone[4]}" for phone in phones]
            update.message.reply_text(f'Найденные номера телефонов: {", ".join(phones_list)}. Сохранить в БД? (да/нет)')
            context.user_data['phones'] = phones_list
            return CONFIRMATION
        else:
            update.message.reply_text('Номера телефонов не найдены.')

    return ConversationHandler.END

def confirm_save(update: Update, context: CallbackContext) -> int:
    response = update.message.text.lower()
    if response == "да":
        try:
            conn = psycopg2.connect(
                dbname=DB_DATABASE,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT
            )
            update.message.reply_text("Подключение к базе данных успешно.")
            cursor = conn.cursor()

            if 'emails' in context.user_data:
                for email in context.user_data['emails']:
                    cursor.execute("INSERT INTO users (email) VALUES (%s)", (email,))
                conn.commit()
                update.message.reply_text("Email-адреса успешно сохранены.")
                context.user_data.pop('emails')

            if 'phones' in context.user_data:
                for phone in context.user_data['phones']:
                    cursor.execute("INSERT INTO phone_numbers (phone_number) VALUES (%s)", (phone,))
                conn.commit()
                update.message.reply_text("Номера телефонов успешно сохранены.")
                context.user_data.pop('phones')

            cursor.close()
            conn.close()
        except Exception as e:
            update.message.reply_text(f"Ошибка при сохранении данных: {str(e)}")
            logger.error(f"Ошибка при сохранении данных: {str(e)}")
    elif response == "нет":
        update.message.reply_text("Данные не сохранены.")
    else:
        update.message.reply_text("Пожалуйста, ответьте 'да' или 'нет'.")

    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Операция отменена.")
    return ConversationHandler.END


def verify_password(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Пожалуйста, отправьте пароль для проверки.')
    return VERIFY_PASSWORD

# Проверка пароля на сложность
def check_password(update: Update, context: CallbackContext) -> int:
    password = update.message.text
    if (len(password) >= 8 and
        re.search(r'[A-Z]', password) and
        re.search(r'[a-z]', password) and
        re.search(r'\d', password) and
        re.search(r'[!@#$%^&*(),.?":{}|<>]', password)):
        update.message.reply_text('Пароль надежный.')
    else:
        update.message.reply_text('Пароль слабый.')

    return ConversationHandler.END

# Обновите ваш ConversationHandler, чтобы включить новое состояние
conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(Filters.text & ~Filters.command, handle_message),
        CommandHandler('verify_password', verify_password)
    ],
    states={
        CONFIRMATION: [MessageHandler(Filters.regex('^(да|нет)$'), confirm_save)],
        VERIFY_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, check_password)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

def get_apt_list(update: Update, context: CallbackContext) -> None:
    rm_host = os.getenv("RM_HOST")
    rm_user = os.getenv("RM_USER")
    rm_password = os.getenv("RM_PASSWORD")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(rm_host, username=rm_user, password=rm_password)
        command = f"apt-cache show {context.args[0]}" if context.args else "dpkg --get-selections"

        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        ssh.close()

        if error:
            update.message.reply_text(f"Ошибка: {error}")
        else:
            max_message_length = 4096
            for i in range(0, len(output), max_message_length):
                part = output[i:i + max_message_length]
                update.message.reply_text(part)

    except Exception as e:
        update.message.reply_text(f"Ошибка: {e}")
        logger.error(f"Ошибка подключения к {rm_host}: {e}")

def get_system_info(update: Update, context: CallbackContext) -> None:
    rm_host = os.getenv("RM_HOST")
    rm_user = os.getenv("RM_USER")
    rm_password = os.getenv("RM_PASSWORD")

    system_commands = {
        "get_uptime": "uptime",
        "get_release": "cat /etc/os-release",
        "get_uname": "uname -a",
        "get_df": "df -h",
        "get_free": "free -h",
        "get_mpstat": "mpstat",
        "get_w": "w",
        "get_auths": "last -n 10",
        "get_critical": "journalctl -p crit -n 5",
        "get_ps": "ps aux",
        "get_ss": "ss -tuln",
        "get_services": "systemctl list-units --type=service --state=running"
    }

    command = update.message.text[1:]
    if command not in system_commands:
        update.message.reply_text("Неизвестная команда.")
        return

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(rm_host, username=rm_user, password=rm_password)

        stdin, stdout, stderr = ssh.exec_command(system_commands[command])
        output = stdout.read().decode()
        ssh.close()

        max_message_length = 4096
        for i in range(0, len(output), max_message_length):
            part = output[i:i + max_message_length]
            update.message.reply_text(part)

    except Exception as e:
        update.message.reply_text(f"Ошибка: {e}")
        logger.error(f"Ошибка подключения к {rm_host}: {e}")

def get_repl_logs(update: Update, context: CallbackContext) -> None:
    # Путь к файлу логов PostgreSQL
    log_file_path = '/var/log/postgresql/postgresql.log'
    repl_keywords = ["replication", "wal", "apply", "standby", "sync", "primary", "hot standby"]

    try:
        # Чтение логов из файла
        with open(log_file_path, 'r') as log_file:
            logs = log_file.readlines()

        # Фильтрация репликационных логов
        repl_logs = [log for log in logs if any(keyword in log.lower() for keyword in repl_keywords)]

        # Отправка результата пользователю
        if repl_logs:
            latest_repl_logs = ''.join(repl_logs[-10:])
            update.message.reply_text(f"Последние репликационные логи:\n{latest_repl_logs}")
        else:
            update.message.reply_text("Репликационные логи не найдены.")

    except Exception as e:
        update.message.reply_text(f"Ошибка при получении логов: {str(e)}")
        logger.error(f"Ошибка при получении логов: {str(e)}")

def get_db_data(update: Update, context: CallbackContext, query: str) -> None:
    try:
        conn = psycopg2.connect(dbname=DB_DATABASE, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        cur = conn.cursor()

        cur.execute(query)
        rows = cur.fetchall()

        if rows:
            message_text = "\n".join(row[0] for row in rows)
        else:
            message_text = "Данные не найдены."

        update.message.reply_text(message_text)

        cur.close()
        conn.close()

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Ошибка базы данных: {error}")
        update.message.reply_text('Ошибка базы данных.')

def get_emails(update: Update, context: CallbackContext) -> None:
    get_db_data(update, context, "SELECT email FROM users;")

def get_phone_numbers(update: Update, context: CallbackContext) -> None:
    get_db_data(update, context, "SELECT phone_number FROM phone_numbers;")

def show_help(update: Update, context: CallbackContext) -> None:
    help_text = (
        "Вот список доступных команд:\n"
        "/find_email - Поиск email-адресов в тексте.\n"
        "/find_phone_number - Поиск номеров телефонов в тексте.\n"
        "/verify_password - Проверка надежности пароля.\n"
        "/get_uptime - Получить время работы системы.\n"
        "/get_release - Получить информацию о версии системы.\n"
        "/get_uname - Получить информацию о архитектуре системы, имени хоста и версии ядра.\n"
        "/get_df - Получить информацию о файловой системе.\n"
        "/get_free - Получить информацию о использовании памяти.\n"
        "/get_mpstat - Получить информацию о производительности системы.\n"
        "/get_w - Получить информацию о вошедших пользователях.\n"
        "/get_auths - Получить последние 10 событий входа.\n"
        "/get_critical - Получить последние 5 критических событий.\n"
        "/get_ps - Получить информацию о запущенных процессах.\n"
        "/get_ss - Получить информацию о используемых портах.\n"
        "/get_apt_list - Получить информацию об установленных пакетах.\n"
        "/get_services - Получить информацию о запущенных службах.\n"
        "/get_repl_logs - Получить репликационные логи.\n"
        "/get_emails - Получить email-адреса.\n"
        "/get_phone_numbers - Получить номера телефонов."
    )
    update.message.reply_text(help_text)

# Основная функция для запуска бота
def main() -> None:
    updater = Updater(os.getenv("TOKEN"), use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(conv_handler)

    # Команды
    dispatcher.add_handler(CommandHandler("start", show_menu))
    dispatcher.add_handler(CommandHandler("help", show_help))
    dispatcher.add_handler(CommandHandler("find_email", find_email))
    dispatcher.add_handler(CommandHandler("find_phone_number", find_phone_number))
    dispatcher.add_handler(CommandHandler("verify_password", verify_password))
    dispatcher.add_handler(CommandHandler("get_apt_list", get_apt_list))
    dispatcher.add_handler(CommandHandler("get_repl_logs", get_repl_logs))
    dispatcher.add_handler(CommandHandler("get_emails", get_emails))
    dispatcher.add_handler(CommandHandler("get_phone_numbers", get_phone_numbers))

    # Обработчики команд мониторинга системы
    monitoring_command_list = [
        "get_uptime", "get_release", "get_uname", "get_df",
        "get_free", "get_mpstat", "get_w", "get_auths",
        "get_critical", "get_ps", "get_ss", "get_services"
    ]

    for command in monitoring_command_list:
        dispatcher.add_handler(CommandHandler(command, get_system_info))

    # Обработчики сообщений
    dispatcher.add_handler(conv_handler)

    # Запуск бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
