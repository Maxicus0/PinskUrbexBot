"""utils/access_control.py — простые проверки прав доступа."""
import config


def is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


def has_object_access(user_credits: int, object_min_credits: int) -> bool:
    """Хватает ли кредитов доверия на конкретный объект (у объекта свой порог)."""
    return user_credits >= object_min_credits
