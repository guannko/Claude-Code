from .ru import RU
from .en import EN

TEXTS = {
    "ru": RU,
    "en": EN,
}


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """
    Получить текст по ключу и языку.
    Поддерживает форматирование: t("welcome", lang, name="Иван")
    """
    text = TEXTS.get(lang, TEXTS["ru"]).get(key, f"[{key}]")
    return text.format(**kwargs) if kwargs else text
