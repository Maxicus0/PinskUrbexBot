"""handlers/admin_panel.py — вход в админ-панель, список ожидающих инсайдов
и служебная функция 'изменить свои кредиты' (для тестов, только админам).

Показ карточки ожидающего инсайда и запуск его оценки живут в
handlers/admin_rate_insight.py (present_insight_for_rating) — этот модуль
только находит, с какого инсайда начать, и передаёт туда управление."""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import insights_repo, users_repo
from handlers.admin_rate_insight import present_insight_for_rating
from keyboards.admin_menu import admin_menu_kb
from keyboards.main_menu import BTN_ADMIN_PANEL
from states.admin_states import AdminSelfCreditsForm
from utils.access_control import is_admin
from utils.formatting import plural_credits

router = Router(name="admin_panel")


@router.message(F.text == BTN_ADMIN_PANEL, StateFilter(None))
async def open_admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:menu")
async def back_to_admin_menu(callback: CallbackQuery) -> None:
    """Кнопка «🔙 В админ-панель» из списка объектов (admin_objects_list_kb)."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin:pending")
async def list_pending(callback: CallbackQuery, state: FSMContext) -> None:
    """Не показывает список всех ожидающих инсайдов сразу — сразу же ведёт
    к оценке одного, самого старого (наибольший номер очереди, см.
    insights_repo.get_next_pending_insight и get_queue_position): карточка
    инсайда и следом сразу запрос числа кредитов доверия (см.
    handlers/admin_rate_insight.py, present_insight_for_rating) — отдельной
    кнопки «Оценить инсайд» больше нет. После оценки этого инсайда админ
    автоматически переходит к следующему по порядку (см. _advance_to_next_insight)
    — так вся очередь разбирается по одному инсайду за раз."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    await callback.answer()
    total = insights_repo.count_pending_insights()
    if not total:
        await callback.message.answer("✅ Ожидающих инсайдов нет — всё разобрано.")
        return

    insight = insights_repo.get_next_pending_insight()
    queue_number = insights_repo.get_queue_position(insight["id"])
    await callback.message.answer(
        f"📋 Ожидающих инсайдов: {total}. Начинаем с самого старого "
        "(автор скрыт — оценка анонимная)."
    )
    await present_insight_for_rating(callback.message, insight, queue_number, state)


@router.callback_query(F.data == "admin:set_own_credits")
async def start_set_own_credits(callback: CallbackQuery, state: FSMContext) -> None:
    """Служебная функция только для тестов: админ выставляет себе любое
    значение кредитов доверия, чтобы быстро проверить карточку уровня и
    пороги доступа объектов, не дожидаясь реальных инсайдов."""
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для модераторов.", show_alert=True)
        return

    current = users_repo.get_credits(callback.from_user.id)
    await state.set_state(AdminSelfCreditsForm.waiting_value)
    await callback.answer()
    await callback.message.answer(
        "🧪 <b>Тестовый режим — только для админов</b>\n\n"
        f"Текущий баланс: {current} {plural_credits(current)} доверия.\n"
        "Пришлите любое целое число — баланс будет выставлен ровно в это "
        "значение (не прибавится, а заменится)."
    )


@router.message(AdminSelfCreditsForm.waiting_value, F.text)
async def apply_set_own_credits(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        # Не должно случаться (в это состояние попадают только через
        # проверенную выше кнопку), но на всякий случай не выполняем.
        await state.clear()
        return

    raw = message.text.strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("Нужно целое число. Попробуйте ещё раз:")
        return

    value = int(raw)
    new_balance = users_repo.set_credits(message.from_user.id, value)
    await state.clear()
    await message.answer(
        f"✅ Баланс выставлен: {new_balance} {plural_credits(new_balance)} доверия.",
        reply_markup=admin_menu_kb(),
    )
