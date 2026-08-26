"""
utils/levels.py
------------------
Система уровней доверия — косметическая надстройка над users.credits.
Пороги/названия/цвета настраиваются в config.LEVELS, здесь только логика:
по числу кредитов определить текущий уровень, прогресс до следующего и
собрать полоску заполнения для отображения во вкладке "🎖 Мой уровень".
"""
from dataclasses import dataclass

import config

BAR_LENGTH = 10
BAR_FILLED = "▰"
BAR_EMPTY = "▱"


@dataclass(frozen=True)
class LevelInfo:
    index: int                  # номер уровня (0, 1, 2, ...)
    name: str                   # название уровня ("Сталкер" и т.п.)
    color: str                  # эмодзи-цвет уровня
    credits: int                # текущий баланс кредитов пользователя
    threshold: int              # порог кредитов, с которого начинается этот уровень
    next_threshold: int | None  # порог следующего уровня (None, если уровень максимальный)
    next_name: str | None       # название следующего уровня (None, если уровень максимальный)

    @property
    def is_max(self) -> bool:
        return self.next_threshold is None

    @property
    def credits_to_next(self) -> int:
        if self.is_max:
            return 0
        return max(0, self.next_threshold - self.credits)

    @property
    def progress_fraction(self) -> float:
        """Доля заполнения полоски (0.0–1.0) между текущим и следующим уровнем."""
        if self.is_max:
            return 1.0
        span = self.next_threshold - self.threshold
        if span <= 0:
            return 1.0
        return max(0.0, min(1.0, (self.credits - self.threshold) / span))


def get_level_info(credits: int) -> LevelInfo:
    levels = config.LEVELS
    idx = 0
    for i, (threshold, _name, _color) in enumerate(levels):
        if credits >= threshold:
            idx = i
        else:
            break

    threshold, name, color = levels[idx]
    if idx + 1 < len(levels):
        next_threshold, next_name, _ = levels[idx + 1]
    else:
        next_threshold, next_name = None, None

    return LevelInfo(
        index=idx,
        name=name,
        color=color,
        credits=credits,
        threshold=threshold,
        next_threshold=next_threshold,
        next_name=next_name,
    )


def progress_bar(fraction: float, length: int = BAR_LENGTH) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * length)
    return BAR_FILLED * filled + BAR_EMPTY * (length - filled)
