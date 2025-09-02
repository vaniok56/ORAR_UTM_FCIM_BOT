EN_TEXTS = {
    "welcome": "Welcome!",
    "help": "Here is the list of available commands:",
    "unknown_command": "Unknown command. Please try again.",
    "choose_group": "Choose your group:",
    "next_course": "Next course:",
    "next_day": "Schedule for the next day:",
    "select_language": "Select language:",
    "lang_russian": "Russian",
    "lang_romanian": "Romanian",
    "lang_english": "English",
    # Add other strings as needed
}
RU_TEXTS = {
    "welcome": "Добро пожаловать!",
    "help": "Вот список доступных команд:",
    "unknown_command": "Неизвестная команда. Пожалуйста, попробуйте еще раз.",
    "choose_group": "Выберите вашу группу:",
    "next_course": "Следующая пара:",
    "next_day": "Расписание на следующий день:",
    "select_language": "Выберите язык:",
    "lang_russian": "Русский",
    "lang_english": "Английский",
    # Добавьте другие строки по мере необходимости
}

RO_TEXTS = {
    "welcome": "Bine ați venit!",
    "help": "Lista comenzilor disponibile:",
    "unknown_command": "Comandă necunoscută. Vă rugăm să încercați din nou.",
    "choose_group": "Alegeți grupa dvs.:",
    "next_course": "Următoarea pereche:",
    "next_day": "Orarul pentru ziua următoare:",
    "select_language": "Alegeți limba:",
    "lang_russian": "Русский",
    "lang_romanian": "Română",
    # Adăugați alte texte după necesitate
}

def get_texts(lang):
    if lang == 'ru':
        return RU_TEXTS
    elif lang == 'ro':
        return RO_TEXTS
    else:
        return EN_TEXTS
