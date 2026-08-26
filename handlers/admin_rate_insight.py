"""
handlers/admin_rate_insight.py
---------------------------------
Оценка инсайда админом: кнопка "✅ Оценить инсайд" запускает мини-FSM,
после чего админ присылает число кредитов доверия (0–config.MAX_INSIGHT_CREDITS).

Уведомление анонимное (см. utils.formatting.format_insight_notification) —
кто прислал инсайд, не показывается. Заметки об авторе (user_notes) —
видны только админам, помогают узнавать повторных авторов по user_id.
"""
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from database import insights_repo, notes_repo, users_repo
from keyboards.main_menu import main_menu_kb
from states.rating_states import RateInsightForm
from utils.access_control import is_admin
from utils.formatting import esc, plural_credits
from utils.levels import get_level_info

router = Router(name="admin_rate_insight")


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

    insight_id = int(callback.data.split(":", 1)[1])
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

    await state.set_state(RateInsightForm.waiting_rating)
    await state.update_data(insight_id=insight_id)
    await callback.message.answer(
        f"Введите число кредитов доверия (0–{config.MAX_INSIGHT_CREDITS}) за инсайд #{insight_id}.\n"
        "0 = отклонить инсайд."
    )


@router.message(RateInsightForm.waiting_rating, F.text)
async def apply_rating(message: Message, state: FSMContext, bot: Bot) -> None:
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
    insight = insights_repo.get_insight(insight_id)

    if not insight or insight["status"] != "pending":
        await state.clear()
        await message.answer("Этот инсайд уже оценён кем-то другим.")
        return

    insights_repo.set_insight_rated(insight_id, value, message.from_user.id)

    if value > 0:
        old_balance = users_repo.get_credits(insight["user_id"])
        level_before = get_level_info(old_balance)
        new_balance = users_repo.add_credits(insight["user_id"], value)
        level_after = get_level_info(new_balance)

        user_text = (
            f"✅ Ваш инсайд #{insight_id} одобрен!\n"
            f"Начислено: {value} {plural_credits(value)} доверия.\n"
            f"Текущий баланс: {new_balance} {plural_credits(new_balance)}."
        )
        if level_after.index > level_before.index:
            user_text += (
                f"\n\n🎉 Новый уровень: {level_after.color} <b>{level_after.name}</b>!"
            )
    else:
        user_text = f"❌ Ваш инсайд #{insight_id} отклонён модератором."

    try:
        await bot.send_message(insight["user_id"], user_text)
    except (TelegramForbiddenError, TelegramBadRequest):
        pass

    await message.answer(f"Готово. Инсайду #{insight_id} начислено {value} {plural_credits(value)}.")

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
        await message.answer("Хорошо, без заметки.", reply_markup=main_menu_kb(is_admin=True))
        return

    notes_repo.add_note(user_id, message.from_user.id, raw)
    await message.answer(
        "📝 Заметка сохранена — будет видна админам при оценке следующих "
        "инсайдов этого автора.",
        reply_markup=main_menu_kb(is_admin=True),
    )
