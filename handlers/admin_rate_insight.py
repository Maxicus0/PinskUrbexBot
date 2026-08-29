"""
handlers/admin_rate_insight.py
---------------------------------
Оценка инсайда админом: кнопка "✅ Оценить инсайд" запускает мини-FSM,
после чего админ присылает число кредитов доверия (0–config.MAX_INSIGHT_CREDITS).

Уведомление анонимное (см. utils.formatting.format_insight_notification) —
кто прислал инсайд, не показывается. Заметки об авторе (user_notes) —
видны только админам, помогают узнавать повторных авторов по user_id.

После оценки и (опциональной) заметки об авторе админ не возвращается в
пустое меню — сразу показывается следующий ожидающий инсайд (строго по
порядку поступления, от самого старого к самому новому — у самого старого
всегда наибольший номер очереди, см. insights_repo.get_next_pending_insight
и get_queue_position), чтобы разбирать всю очередь одну за другой, просто
отвечая в чат. Инсайды никогда не показываются все сразу — только по
одному (см. handlers/admin_panel.py, list_pending).
"""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import insights_repo, notes_repo, users_repo
from handlers.admin_panel import send_pending_insight
from keyboards.main_menu import main_menu_kb
from states.rating_states import RateInsightForm
from utils.access_control import is_admin
from utils.bot_delivery import send_message_to_user
from utils.formatting import esc, plural_credits
from utils.holidays import format_bonus_line, get_active_holiday
from utils.levels import get_level_info

router = Router(name="admin_rate_insight")


async def _advance_to_next_insight(message: Message) -> None:
    """Показывает следующий ожидающий инсайд (строго по порядку поступления,
    от старого к новому), чтобы админ мог разобрать очередь одну за другой,
    не возвращаясь в админ-панель вручную. Если очередь пуста — просто
    главное меню."""
    next_insight = insights_repo.get_next_pending_insight()
    if not next_insight:
        await message.answer(
            "✅ Ожидающих инсайдов больше нет — всё разобрано.",
            reply_markup=main_menu_kb(is_admin=True),
        )
        return

    queue_number = insights_repo.get_queue_position(next_insight["id"])
    await message.answer(f"➡️ Следующий на очереди — инсайд #{queue_number}:")
    await send_pending_insight(message, next_insight, queue_number)


def _admin_display_name(admin_id: int) -> str:
    """username/имя админа из users, иначе просто telegram_id."""
    admin_user = users_repo.get_user(admin_id)
    if admin_user and admin_user["username"]:
        return f"@{admin_user['username']}"
    if admin_user and admin_user["full_name"]:
        return admin_user["full_name"]
    return f"админ {admin_id}"


def _format_notes(notes) -> str:
    lines = [f"📝 <b>Заметки об этом авторе</b> ({len(notes)}) — видны только админам:"]
    for note in notes:
        author = _admin_display_name(note["admin_id"])
        date = str(note["created_at"])[:16]
        lines.append(f"\n🕓 {date} · {esc(author)}\n{esc(note['text'])}")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("rate:"))
async def start_rating(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    try:
        insight_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректные данные кнопки.", show_alert=True)
        return

    insight = insights_repo.get_insight(insight_id)
    if not insight:
        await callback.answer("Инсайд не найден.", show_alert=True)
        return
    if insight["status"] != "pending":
        await callback.answer("Этот инсайд уже оценён.", show_alert=True)
        return

    await callback.answer()

    notes = notes_repo.get_notes(insight["user_id"])
    if notes:
        await callback.message.answer(_format_notes(notes))

    # Номер в очереди фиксируется здесь и переиспользуется во всех текстах
    # этой оценки (см. apply_rating) — id из БД пользователю/админу не
    # показываем (см. utils.formatting.format_insight_notification).
    queue_number = insights_repo.get_queue_position(insight_id)

    await state.set_state(RateInsightForm.waiting_rating)
    await state.update_data(insight_id=insight_id, queue_number=queue_number)
    await callback.message.answer(
        f"Введите число кредитов доверия (0–{config.MAX_INSIGHT_CREDITS}) за инсайд #{queue_number}.\n"
        "0 = отклонить инсайд."
    )


@router.message(RateInsightForm.waiting_rating, F.text)
async def apply_rating(message: Message, state: FSMContext, bots: list[Bot]) -> None:
    raw = message.text.strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("Нужно просто число. Попробуйте ещё раз:")
        return

    value = int(raw)
    if not (config.MIN_INSIGHT_CREDITS <= value <= config.MAX_INSIGHT_CREDITS):
        await message.answer(
            f"Число должно быть от {config.MIN_INSIGHT_CREDITS} до {config.MAX_INSIGHT_CREDITS}. "
            "Попробуйте ещё раз:"
        )
        return

    data = await state.get_data()
    insight_id = data["insight_id"]
    queue_number = data.get("queue_number", insight_id)
    insight = insights_repo.get_insight(insight_id)

    if not insight or insight["status"] != "pending":
        await state.clear()
        await message.answer("Этот инсайд уже оценён кем-то другим.")
        return

    insights_repo.set_insight_rated(insight_id, value, message.from_user.id)

    if value > 0:
        # Праздничный бонус (если сегодня праздник, см. utils/holidays.py)
        # начисляется только на одобренные инсайды — отклонённые (0) его не
        # получают.
        holiday = get_active_holiday()
        bonus = holiday["bonus_credits"] if holiday else 0

        old_balance = users_repo.get_credits(insight["user_id"])
        level_before = get_level_info(old_balance)
        new_balance = users_repo.add_credits(insight["user_id"], value + bonus)
        level_after = get_level_info(new_balance)

        user_text = (
            "✅ Ваш инсайд одобрен!\n"
            f"Начислено: {value} {plural_credits(value)} доверия.\n"
        )
        if bonus:
            user_text += f"{format_bonus_line(holiday)}\n"
        user_text += f"Текущий баланс: {new_balance} {plural_credits(new_balance)}."
        if level_after.index > level_before.index:
            user_text += (
                f"\n\n🎉 Новый уровень: {level_after.color} <b>{level_after.name}</b>!"
            )
    else:
        bonus = 0
        user_text = "❌ Ваш инсайд отклонён модератором."

    # Автор мог отправить инсайд через другого бота, чем тот, которым админ
    # его сейчас оценивает (см. config.BETA_BOT_TOKEN) — пробуем всех ботов,
    # пока сообщение не дойдёт.
    await send_message_to_user(bots, insight["user_id"], user_text)

    admin_confirm = f"Готово. Инсайду #{queue_number} начислено {value} {plural_credits(value)}"
    if bonus:
        admin_confirm += f" + {bonus} праздничных"
    await message.answer(admin_confirm + ".")

    await state.set_state(RateInsightForm.waiting_note)
    await state.update_data(user_id=insight["user_id"])
    await message.answer(
        "📝 Хотите оставить заметку об этом авторе (например, что материал "
        "повторяет уже известную новость)? Заметку увидят только админы при "
        "оценке следующих инсайдов этого же человека — сам автор её не увидит.\n\n"
        "Напишите текст заметки, или «-», чтобы пропустить."
    )


@router.message(RateInsightForm.waiting_note, F.text)
async def apply_note(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = data["user_id"]
    raw = message.text.strip()
    await state.clear()

    if raw == "-":
        await message.answer("Хорошо, без заметки.")
    else:
        notes_repo.add_note(user_id, message.from_user.id, raw)
        await message.answer(
            "📝 Заметка сохранена — будет видна админам при оценке следующих "
            "инсайдов этого автора."
        )

    await _advance_to_next_insight(message)
