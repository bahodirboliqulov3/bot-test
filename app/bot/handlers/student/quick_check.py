import html
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.bot.handlers.student.test_solver import show_test_result
from app.bot.keyboards.reply_keyboards import get_cancel_keyboard, get_student_main_keyboard
from app.bot.states.student_states import QuickCheckState
from app.database.repositories.test_repo import TestRepository
from app.database.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.scoring_service import ScoringService

router = Router(name="student_quick_check")


# 1. Direct one-line test answer checker: "101 ABCD...", "101*ABCD", "101#ABCD", "101-ABCD", "101:ABCD", "101 1-A 2-B 3-C", etc.
@router.message(StateFilter("*"), F.text.func(lambda text: bool(text and ScoringService.parse_direct_code_and_answers(text))))
async def direct_code_and_answers_handler(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()
    parsed_pair = ScoringService.parse_direct_code_and_answers(text)
    if not parsed_pair:
        return

    await state.clear()
    test_code, raw_answers = parsed_pair
    test_repo = TestRepository(session)
    test = await test_repo.get_by_code(test_code)

    if not test:
        await message.answer(
            f"🙈 <b>{html.escape(test_code)}</b> kodli test topilmadi!\n\n"
            "💡 <i>Test kodini to‘g‘ri kiritganingizga ishonch hosil qiling. Masalan:</i>\n"
            f"<code>{html.escape(test_code)} ABCDABCD...</code>",
            parse_mode="HTML"
        )
        return

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        user = await user_repo.create(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "O'quvchi",
            last_name=message.from_user.last_name or "",
            username=message.from_user.username
        )

    scoring_service = ScoringService(session)
    try:
        res, visual_grid = await scoring_service.evaluate_quick_submission(
            test_id=test.id,
            user_id=user.id,
            raw_answers=raw_answers
        )
        auth_service = AuthService(session)
        is_admin = await auth_service.is_admin(message.from_user.id)

        await message.answer(
            f"⚡ <b>\"{html.escape(test.title)}\"</b> — javoblar tekshirildi!",
            reply_markup=get_student_main_keyboard(is_admin=is_admin),
            parse_mode="HTML"
        )
        await show_test_result(message, res, session, visual_breakdown=visual_grid)
    except ValueError as e:
        err_msg = html.escape(str(e))
        await message.answer(
            f"⚠️ <b>Xatolik:</b>\n{err_msg}\n\n"
            f"📝 <i>To‘g‘ri format:</i> <code>{test.code} ABCDABCD...</code>",
            parse_mode="HTML"
        )


# Direct single test code sent without state: e.g. "101" or "TEST-105" or "101" or "TEST-AB12C"
@router.message(StateFilter(None), F.text.regexp(r"(?i)^[#/#]?(TEST-[A-Z0-9_\-]+|[A-Z0-9_\-]{2,24})$"))
async def direct_single_test_code_handler(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip().upper().lstrip("#/")
    if text.startswith("/") or text in ["❌ BEKOR QILISH", "🏠 BOSH MENYU"]:
        return

    test_repo = TestRepository(session)
    test = await test_repo.get_by_code(text)
    if not test:
        return

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    if not user:
        await user_repo.create(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "O'quvchi",
            last_name=message.from_user.last_name or "",
            username=message.from_user.username
        )

    await state.update_data(test_id=test.id)
    await state.set_state(QuickCheckState.waiting_for_answers)

    q_count = test.total_questions if test.total_questions > 0 else len(test.test_questions)
    info_msg = (
        f"📝 <b>Test topildi:</b> {html.escape(test.title)}\n"
        f"🔑 <b>Kod:</b> <code>{test.code}</code>\n"
        f"❓ <b>Savollar soni:</b> {q_count} ta\n\n"
        f"2️⃣ <b>Endi javoblaringizni yuboring:</b>\n\n"
        f"📌 <b>Qabul qilinadigan formatlar:</b>\n"
        f"• <code>a,b,c,0.75</code> <i>(nomersiz, vergul bilan)</i>\n"
        f"• <code>ABCDABCD...</code> <i>(barcha variantlar ketma-ket)</i>\n"
        f"• <code>A, B, C, 3/4, 0.75, 12</code> <i>(kasrli / raqamli)</i>\n"
        f"• <code>1.A 2.B 3.C 4.0.75</code> <i>(raqamlangan tartibda)</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Interaktiv Matritsada ishlash (Tugmali)", callback_data=f"start_matrix:{test.id}")],
        ]
    )

    if test.file_id:
        if test.file_type == "photo":
            try:
                await message.answer_photo(photo=test.file_id, caption=info_msg, reply_markup=kb, parse_mode="HTML")
                return
            except Exception:
                pass
        else:
            try:
                await message.answer_document(document=test.file_id, caption=info_msg, reply_markup=kb, parse_mode="HTML")
                return
            except Exception:
                pass

    await message.answer(info_msg, reply_markup=kb, parse_mode="HTML")



@router.message(StateFilter("*"), F.text.in_(["✅ Javobni tekshirish", "/tekshir", "/check"]))
async def start_quick_check_menu(message: Message, state: FSMContext):
    await state.set_state(QuickCheckState.waiting_for_test_code)
    await message.answer(
        "✅ <b>Javoblarni tekshirish</b>\n\n"
        "1️⃣ <b>Test kodini kiriting:</b>\n"
        "<i>(Masalan: <code>101</code> yoki <code>TEST-101</code>)</i>\n\n"
        "💡 <i>Yoki kod va javoblarni bitta xabarda yuborishingiz ham mumkin:</i>\n"
        "<code>101 ABCDABCD...</code>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(StateFilter("*"), F.text.in_(["🔢 Raqamli javoblarni tekshirish"]))
async def start_sat_check_menu(message: Message, state: FSMContext):
    await state.set_state(QuickCheckState.waiting_for_test_code)
    await message.answer(
        "🔢 <b>Raqamli & Kasrli javoblarni tekshirish</b>\n\n"
        "1️⃣ <b>Test kodini kiriting:</b>\n"
        "<i>(Masalan: <code>101</code> yoki <code>101</code>)</i>\n\n"
        "💡 <b>Eslatma:</b> Keyingi qadamda kasrli (<code>3/4</code>), o‘nli (<code>0.75</code>), butun (<code>12</code>) va manfiy (<code>-4.5</code>) javoblaringizni yuborasiz.\n\n"
        "<i>Yoki bitta xabarda yuboring:</i>\n"
        "<code>101 1.A 2.B 3.12 4.3/4 5.-4.5</code>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(QuickCheckState.waiting_for_test_code, F.text)
async def process_quick_check_test_code(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()
    if text in ["❌ Bekor qilish", "🏠 Bosh menyu"]:
        await state.clear()
        auth_service = AuthService(session)
        is_admin = await auth_service.is_admin(message.from_user.id)
        await message.answer("❌ Bekor qilindi.", reply_markup=get_student_main_keyboard(is_admin=is_admin))
        return

    # Check if user sent direct code + answers in this step as well
    parsed_pair = ScoringService.parse_direct_code_and_answers(text)
    if parsed_pair:
        await state.clear()
        await direct_code_and_answers_handler(message, session)
        return

    code = text.upper()
    test_repo = TestRepository(session)
    test = await test_repo.get_by_code(code)

    if not test:
        await message.answer(
            "⛔ <b>Ushbu kodli test topilmadi!</b>\n\n"
            "Iltimos, test kodini to‘g‘ri kiriting (masalan: <code>101</code>):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(test_id=test.id)
    await state.set_state(QuickCheckState.waiting_for_answers)

    q_count = test.total_questions if test.total_questions > 0 else len(test.test_questions)
    info_msg = (
        f"📝 <b>Test topildi:</b> {html.escape(test.title)}\n"
        f"🔑 <b>Kod:</b> <code>{test.code}</code>\n"
        f"❓ <b>Savollar soni:</b> {q_count} ta\n\n"
        f"2️⃣ <b>Endi javoblaringizni yuboring:</b>\n\n"
        f"📌 <b>Qabul qilinadigan formatlar:</b>\n"
        f"• <code>a,b,c,0.75</code> <i>(nomersiz, vergul bilan)</i>\n"
        f"• <code>ABCDABCD...</code> <i>(ketma-ket harflar)</i>\n"
        f"• <code>A, B, C, 3/4, 0.75, 12</code> <i>(kasr / raqam)</i>\n"
        f"• <code>1.A 2.B 3.C 4.0.75</code> <i>(raqamlangan)</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Interaktiv Matritsada ishlash (Tugmali)", callback_data=f"start_matrix:{test.id}")],
        ]
    )

    if test.file_id:
        if test.file_type == "photo":
            try:
                await message.answer_photo(photo=test.file_id, caption=info_msg, reply_markup=kb, parse_mode="HTML")
                return
            except Exception:
                pass
        else:
            try:
                await message.answer_document(document=test.file_id, caption=info_msg, reply_markup=kb, parse_mode="HTML")
                return
            except Exception:
                pass

    await message.answer(info_msg, reply_markup=kb, parse_mode="HTML")


@router.message(QuickCheckState.waiting_for_answers, F.text)
async def process_quick_check_text_answers(message: Message, state: FSMContext, session: AsyncSession):
    raw_text = message.text.strip()
    if raw_text in ["❌ Bekor qilish", "🏠 Bosh menyu"]:
        await state.clear()
        auth_service = AuthService(session)
        is_admin = await auth_service.is_admin(message.from_user.id)
        await message.answer("❌ Bekor qilindi.", reply_markup=get_student_main_keyboard(is_admin=is_admin))
        return

    data = await state.get_data()
    test_id = data.get("test_id")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(message.from_user.id)
    scoring_service = ScoringService(session)

    try:
        res, visual_grid = await scoring_service.evaluate_quick_submission(
            test_id=test_id,
            user_id=user.id,
            raw_answers=raw_text
        )
        await state.clear()
        auth_service = AuthService(session)
        is_admin = await auth_service.is_admin(message.from_user.id)

        await message.answer("✅ Javoblaringiz muvaffaqiyatli tekshirildi!", reply_markup=get_student_main_keyboard(is_admin=is_admin))
        await show_test_result(message, res, session, visual_breakdown=visual_grid)
    except ValueError as e:
        err_msg = html.escape(str(e))
        await message.answer(
            f"⚠️ <b>Xatolik:</b>\n{err_msg}",
            reply_markup=get_cancel_keyboard(),
            parse_mode="HTML"
        )

