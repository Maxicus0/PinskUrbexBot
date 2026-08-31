"""
handlers/admin_rate_insight.py
---------------------------------
Оценка инсайда админом. Отдельных кнопок "✅ Оценить инсайд" и "⏭ Пропустить
без оценки" нет: как только показана карточка ожидающего инсайда (при входе
в очередь по кнопке «📋 Ожидающие инсайды», см. handlers/admin_panel.py,
list_pending, либо при автопереходе к следующему инсайду, см.
_advance_to_next_insight ниже) — сразу следом идёт запрос числа кредитов
доверия (0–config.MAX_INSIGHT_CREDITS), см. present_insight_for_rating.
Под этим запросом только одна кнопка — "🔙 Назад в меню" (см.
keyboards.insight_kb.rating_back_kb): она прерывает оценку без каких-либо
изменений, сам инсайд остаётся pending и просто ждёт своей очереди дальше
(см. cancel_rating).

0 кредитов = отказ, но не молчаливый: с релиза 0.4 админ обязан следом
указать текстовую причину (waiting_reject_reason) — она уходит автору
инсайда вместе с уведомлением об отказе, чтобы человек понимал, что не так,
а не просто увидел "отклонено". Пропустить этот шаг нельзя (в отличие от
последующей заметки об авторе, где "-" пропускает её осознанно).

Уведомление анонимное (см. utils.formatting.format_insight_notification) —
кто прислал инсайд, не показывается. Заметки об авторе (user_notes) —
видны только админам, помогают узнавать повторных авторов по user_id.

Хранение в БД временное (см. module docstring database/insights_repo.py):
как только обработка инсайда завершена — оценкой (с причиной отказа, если
она была нулевой) и опциональной заметкой об авторе — insights_repo.
delete_insight() стирает его из БД вместе с медиафайлами. Начисленные
кредиты при этом не теряются: они уже записаны в users.credits к этому
моменту. Содержимое самого инсайда остаётся только в переписке админа с
ботом в Telegram — карточка, которую бот прислал при открытии очереди,
никуда не удаляется, просто в БД её после обработки больше нет (см. README,
раздел "Безопасность и анонимность").

После оценки (и заметки) админ не возвращается в пустое меню — сразу
показывается следующий ожидающий инсайд (строго по порядку поступления, от
самого старого к самому новому — у самого старого всегда наибольший номер
очереди, см. insights_repo.get_next_pending_insight и get_queue_position),
чтобы разбирать всю очередь одну за другой, просто отвечая в чат. Инсайды
никогда не показываются все сразу — только по одному.
"""
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, InputMediaVideo, Message

import config
from database import insights_repo, notes_repo, users_repo
from keyboards.admin_menu import admin_menu_kb
from keyboards.insight_kb import rating_back_kb
from keyboards.main_menu import main_menu_kb
from states.rating_states import RateInsightForm
from utils.access_control import is_admin
from utils.bot_delivery import send_message_to_user
from utils.formatting import CAPTION_LIMIT, esc, format_insight_notification, plural_credits
from utils.holidays import format_bonus_line, get_active_holiday
from utils.levels import get_level_info

logger = logging.getLogger(__name__)

router = Router(name="admin_rate_insight")

# Показывается вместо "Инсайд не найден" / "уже оценён" в общем случае —
# инсайд мог тем временем пропасть из очереди, если его успел разобрать
# другой админ (или тот же — из другого места, например после перезапуска
# бота), поэтому формулировка обобщена, а не привязана к одной причине.
_ALREADY_HANDLED_TEXT = "Этот инсайд уже обработан кем-то другим."


async def present_insight_for_rating(
    message: Message, insight, queue_number: int, state: FSMContext
) -> None:
    """Показывает один ожидающий инсайд админу (медиа, если есть, + текст) и
    сразу же, без промежуточных кнопок выбора, запускает его оценку: заметки
    об авторе (если есть) и запрос числа кредитов доверия. Общая точка входа
    и для первого захода в очередь («📋 Ожидающие инсайды», см.
    handlers/admin_panel.py, list_pending), и для автоперехода к следующему
    инсайду сразу после оценки текущего (см. _advance_to_next_insight ниже)
    — так админ может разобрать всю очередь одну за другой, просто отвечая
    в чат числом, не возвращаясь в админ-панель вручную. Инсайды всегда
    показываются по одному, никогда все сразу."""
    await _send_insight_card(message, insight, queue_number)

    notes = notes_repo.get_notes(insight["user_id"])
    if notes:
        await message.answer(_format_notes(notes))

    # Номер в очереди фиксируется здесь и переиспользуется во всех текстах
    # этой оценки (см. apply_rating) — id из БД пользователю/админу не
    # показываем (см. utils.formatting.format_insight_notification).
    await state.set_state(RateInsightForm.waiting_rating)
    await state.update_data(insight_id=insight["id"], queue_number=queue_number)
    await message.answer(
        f"Введите число кредитов доверия (0–{config.MAX_INSIGHT_CREDITS}) за инсайд #{queue_number}.\n"
        "0 = отклонить инсайд.",
        reply_markup=rating_back_kb(),
    )


async def _send_insight_card(message: Message, insight, queue_number: int) -> None:
    """Сама карточка инсайда (медиа + текст), без каких-либо кнопок — выбор
    здесь у админа только один: ввести число кредитов (см.
    present_insight_for_rating выше) или нажать «Назад в меню» под этим
    запросом."""
    text = format_insight_notification(insight, queue_number)
    media = insights_repo.get_insight_media(insight["id"])

    if not media:
        await message.answer(text)
        return

    try:
        if len(media) == 1:
            item = media[0]
            send = (
                message.answer_photo
                if item["media_type"] == "photo"
                else message.answer_video
            )
            if len(text) <= CAPTION_LIMIT:
                await send(item["file_id"], caption=text)
            else:
                await send(item["file_id"])
                await message.answer(text)
        else:
            # Медиагруппа не поддерживает подпись длиннее лимита у каждого
            # элемента по отдельности — текст уходит отдельным сообщением
            # следом.
            items = [
                InputMediaVideo(media=m["file_id"])
                if m["media_type"] == "video"
                else InputMediaPhoto(media=m["file_id"])
                for m in media
            ]
            await message.answer_media_group(items)
            await message.answer(text)
    except TelegramBadRequest as e:
        # file_id мог быть выдан другим ботом на этой же БД (см.
        # config.BETA_BOT_TOKEN) — не теряем инсайд, показываем текстом.
        logger.warning("Не удалось показать медиа инсайда #%s: %s", insight["id"], e)
        await message.answer(text + "\n\n📷 Медиа приложено, но недоступно через этого бота.")


async def _advance_to_next_insight(message: Message, state: FSMContext) -> None:
    """Показывает следующий ожидающий инсайд (строго по порядку поступления,
    от старого к новому), чтобы админ мог разобрать очередь одну за другой,
    не возвращаясь в админ-панель вручную. Если очередь пуста — просто
    главное меню (и FSM-состояние обязательно очищается, иначе бот застрял
    бы в ожидании заметки/оценки, которых больше не будет)."""
    next_insight = insights_repo.get_next_pending_insight()
    if not next_insight:
        await state.clear()
        await message.answer(
            "✅ Ожидающих инсайдов больше нет — всё разобрано.",
            reply_markup=main_menu_kb(is_admin=True),
        )
        return

    queue_number = insights_repo.get_queue_position(next_insight["id"])
    await message.answer(f"➡️ Следующий на очереди — инсайд #{queue_number}:")
    await present_insight_for_rating(message, next_insight, queue_number, state)


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


@router.callback_query(F.data == "rate:cancel")
async def cancel_rating(callback: CallbackQuery, state: FSMContext) -> None:
    """«🔙 Назад в меню» под запросом числа кредитов — прерывает оценку
    текущего инсайда без каких-либо изменений: сам инсайд никуда не
    девается, остаётся pending и просто ждёт своей очереди дальше (его
    снова покажет следующий заход в «📋 Ожидающие инсайды»)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


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
        await message.answer(_ALREADY_HANDLED_TEXT)
        return

    if value == 0:
        # 0 кредитов = отказ, но с 0.4 не молчаливый: причина обязательна и
        # уходит автору инсайда вместе с уведомлением об отказе (см.
        # apply_reject_reason ниже). Инсайд в БД пока не трогаем — он
        # остаётся pending до тех пор, пока причина не будет получена.
        await state.set_state(RateInsightForm.waiting_reject_reason)
        await state.update_data(user_id=insight["user_id"])
        await message.answer(
            f"❗️ Инсайд #{queue_number} отклонён (0 кредитов).\n\n"
            "Обязательно укажите текстовую причину отказа одним сообщением — "
            "она будет отправлена автору вместе с уведомлением (имя автора "
            "ему по-прежнему не раскрывается)."
        )
        return

    # Праздничный бонус (если сегодня праздник, см. utils/holidays.py)
    # начисляется только на одобренные инсайды.
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

    # Автор мог отправить инсайд через другого бота, чем тот, которым админ
    # его сейчас оценивает (см. config.BETA_BOT_TOKEN) — пробуем всех ботов,
    # пока сообщение не дойдёт.
    await send_message_to_user(bots, insight["user_id"], user_text)

    # Кредиты уже начислены (users.credits) — сам инсайд в БД дальше не
    # нужен, удаляем сразу (см. module docstring и database/insights_repo.py).
    # Заметка об авторе ниже пишется в user_notes по user_id, insight_id ей
    # не требуется.
    insights_repo.delete_insight(insight_id)

    admin_confirm = f"Готово. Инсайду #{queue_number} начислено {value} {plural_credits(value)}"
    if bonus:
        admin_confirm += f" + {bonus} праздничных"
    await message.answer(admin_confirm + ".")

    await _prompt_for_note(message, state, insight["user_id"])


@router.message(RateInsightForm.waiting_rating)
async def apply_rating_wrong_type(message: Message) -> None:
    """Ловит всё, что не текст (фото, стикер, голосовое и т.п.) — без этого
    хендлера такое сообщение молча проваливалось бы, ничего не отвечая
    админу."""
    await message.answer("Ожидается число кредитов доверия текстом. Попробуйте ещё раз:")


@router.message(RateInsightForm.waiting_reject_reason, F.text)
async def apply_reject_reason(message: Message, state: FSMContext, bots: list[Bot]) -> None:
    reason = message.text.strip()
    if not reason or reason == "-":
        await message.answer(
            "Причина обязательна — «-» тут не сработает. Опишите коротко, "
            "почему инсайд отклонён:"
        )
        return

    data = await state.get_data()
    insight_id = data["insight_id"]
    queue_number = data.get("queue_number", insight_id)
    user_id = data["user_id"]

    # Инсайд мог тем временем исчезнуть (например, если бот перезапустился и
    # его подобрал другой процесс/админ) — на всякий случай перепроверяем.
    insight = insights_repo.get_insight(insight_id)
    if not insight or insight["status"] != "pending":
        await state.clear()
        await message.answer(_ALREADY_HANDLED_TEXT)
        return

    user_text = (
        "❌ Ваш инсайд отклонён модератором.\n"
        f"Причина: {esc(reason)}"
    )
    await send_message_to_user(bots, user_id, user_text)

    insights_repo.delete_insight(insight_id)

    await message.answer(
        f"Готово. Инсайду #{queue_number} отказано (0 кредитов). Причина отправлена автору."
    )

    await _prompt_for_note(message, state, user_id)


@router.message(RateInsightForm.waiting_reject_reason)
async def apply_reject_reason_wrong_type(message: Message) -> None:
    await message.answer("Причина отказа нужна текстом одним сообщением. Попробуйте ещё раз:")


async def _prompt_for_note(message: Message, state: FSMContext, user_id: int) -> None:
    """Общий шаг после оценки (одобрение или отказ с причиной) — предлагает
    оставить приватную заметку об авторе, затем передаёт очередь дальше в
    apply_note."""
    await state.set_state(RateInsightForm.waiting_note)
    await state.update_data(user_id=user_id)
    await message.answer(
        "📝 Хотите оставить заметку об этом авторе (например, что материал "
        "повторяет уже известную новость, или чтобы в следующий раз сразу "
        "опознать повторную отправку как спам)? Заметку увидят только админы "
        "при оценке следующих инсайдов этого же человека — сам автор её не увидит.\n\n"
        "Напишите текст заметки, или «-», чтобы пропустить."
    )


@router.message(RateInsightForm.waiting_note, F.text)
async def apply_note(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = data["user_id"]
    raw = message.text.strip()

    if raw == "-":
        await message.answer("Хорошо, без заметки.")
    else:
        notes_repo.add_note(user_id, message.from_user.id, raw)
        await message.answer(
            "📝 Заметка сохранена — будет видна админам при оценке следующих "
            "инсайдов этого автора."
        )

    await _advance_to_next_insight(message, state)


@router.message(RateInsightForm.waiting_note)
async def apply_note_wrong_type(message: Message) -> None:
    await message.answer("Заметка нужна текстом (или «-», чтобы пропустить). Попробуйте ещё раз:")
