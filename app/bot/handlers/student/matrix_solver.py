import html
from datetime import datetime, timezone
from typing import Dict, Optional
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.student.test_solver import show_test_result
from app.bot.keyboards.inline_keyboards import get_matrix_finish_confirm_keyboard, get_matrix_solver_keyboard
from app.bot.keyboards.reply_keyboards import get_student_main_keyboard
from app.bot.states.student_states import MatrixSolverState
from app.database.repositories.test_repo import TestRepository
from app.database.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.scoring_service import ScoringService

router = Router(name="student_matrix_solver")


def build_matrix_header_text(test, total_q: int, current_q: int, user_answers: Dict[int, str]) -> str:
    answered_count = len(user_answers)
    pct = (total_q > 0 and (answered_count / total_q * 100)) or 0
    filled_blocks = int(round((pct / 100) * 10))
    bar = "🟩" * filled_blocks + "⬜" * (10 - filled_blocks)
    
    cur_val = user_answers.get(current_q)
    if cur_val:
        cur_status = f"(Kiritilgan: <b>{html.escape(str(cur_val))}</b> ✅)"
    else:
        cur_status = "(Kiritilgan: ⚪ <i>Belgilanmagan</i>)"

    return (
        "╔══════════════════════════════╗\n"
        "║   📝 <b>INTERAKTIV TEST MATRITSA</b>   ║\n"
        "╚══════════════════════════════╝\n\n"
        f"🎯 <b>Test:</b> {html.escape(test.title)}\n"
        f"🔑 <b>Kod:</b> <code>{test.code}</code>  |  ❓ <b>Jami:</b> {total_q} ta savol\n"
        f"📊 <b>Belgilandi:</b> {answered_count}/{total_q} ({pct:.0f}%) [{bar}]\n\n"
        f"👉 <b>Tanlangan:</b> <code>{current_q}-savol</code> {cur_status}\n"
        "<i>Quyidagi tugmalardan birini bosing yoki javobni o'zgartiring:</i>"
    )


async def open_matrix_solver(target: Message | CallbackQuery, test_id: int, state: FSMContext, session: AsyncSession, start_q: int = 1):
    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        if isinstance(target, CallbackQuery):
            await target.answer("Test topilmadi!", show_alert=True)
        else:
            await target.answer("Test topilmadi!")
        return

    total_q = test.total_questions if test.total_questions > 0 else len(test.test_questions)
    if total_q == 0:
        total_q = 1

    data = await state.get_data()
    user_answers = data.get("matrix_answers", {})
    user_answers = {int(k): str(v) for k, v in user_answers.items()}

    page = (start_q - 1) // 20 + 1
    await state.update_data(
        test_id=test.id,
        total_questions=total_q,
        current_q=start_q,
        page=page,
        matrix_answers=user_answers
    )
    await state.set_state(MatrixSolverState.solving)

    header_text = build_matrix_header_text(test, total_q, start_q, user_answers)
    kb = get_matrix_solver_keyboard(
        test_id=test.id,
        total_questions=total_q,
        current_q=start_q,
        user_answers=user_answers,
        page=page,
        page_size=20
    )

    if isinstance(target, CallbackQuery):
        await target.answer()
        try:
            if target.message.photo:
                await target.message.edit_caption(caption=header_text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.message.edit_text(header_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.message.answer(header_text, reply_markup=kb, parse_mode="HTML")
    else:
        if test.file_id:
            try:
                if test.file_type == "photo":
                    await target.answer_photo(photo=test.file_id, caption=header_text, reply_markup=kb, parse_mode="HTML")
                    return
                else:
                    await target.answer_document(document=test.file_id, caption=header_text, reply_markup=kb, parse_mode="HTML")
                    return
            except Exception:
                pass
        await target.answer(header_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("start_matrix:"))
async def start_matrix_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    await open_matrix_solver(callback, test_id, state, session, start_q=1)


@router.callback_query(F.data.startswith("mat_sel:"))
async def matrix_select_q_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    q_num = int(parts[2])
    page = int(parts[3])

    data = await state.get_data()
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}
    total_q = data.get("total_questions", 40)

    await state.update_data(current_q=q_num, page=page)
    await callback.answer(f"🎯 {q_num}-savol")

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        return

    header_text = build_matrix_header_text(test, total_q, q_num, user_answers)
    kb = get_matrix_solver_keyboard(
        test_id=test_id,
        total_questions=total_q,
        current_q=q_num,
        user_answers=user_answers,
        page=page,
        page_size=20
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=header_text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(header_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("mat_ans:"))
async def matrix_select_ans_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    q_num = int(parts[2])
    opt = parts[3]
    page = int(parts[4])

    data = await state.get_data()
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}
    total_q = data.get("total_questions", 40)

    user_answers[q_num] = opt
    await callback.answer(f"{q_num}-savol: {opt} ✅")

    next_q = q_num + 1 if q_num < total_q else q_num
    next_page = (next_q - 1) // 20 + 1

    await state.update_data(current_q=next_q, page=next_page, matrix_answers=user_answers)

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        return

    header_text = build_matrix_header_text(test, total_q, next_q, user_answers)
    kb = get_matrix_solver_keyboard(
        test_id=test_id,
        total_questions=total_q,
        current_q=next_q,
        user_answers=user_answers,
        page=next_page,
        page_size=20
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=header_text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(header_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("mat_clear:"))
async def matrix_clear_ans_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    q_num = int(parts[2])
    page = int(parts[3])

    data = await state.get_data()
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}
    total_q = data.get("total_questions", 40)

    if q_num in user_answers:
        del user_answers[q_num]
    await callback.answer(f"{q_num}-savol javobi o'chirildi ⚪")

    await state.update_data(matrix_answers=user_answers)

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        return

    header_text = build_matrix_header_text(test, total_q, q_num, user_answers)
    kb = get_matrix_solver_keyboard(
        test_id=test_id,
        total_questions=total_q,
        current_q=q_num,
        user_answers=user_answers,
        page=page,
        page_size=20
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=header_text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(header_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("mat_pag:"))
async def matrix_pagination_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    current_q = int(parts[2])
    target_page = int(parts[3])

    await callback.answer()
    data = await state.get_data()
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}
    total_q = data.get("total_questions", 40)

    await state.update_data(page=target_page)

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        return

    header_text = build_matrix_header_text(test, total_q, current_q, user_answers)
    kb = get_matrix_solver_keyboard(
        test_id=test_id,
        total_questions=total_q,
        current_q=current_q,
        user_answers=user_answers,
        page=target_page,
        page_size=20
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=header_text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(header_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("mat_type:"))
async def matrix_type_custom_prompt(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    q_num = int(parts[2])
    page = int(parts[3])

    await state.update_data(type_target_q=q_num, page=page)
    await state.set_state(MatrixSolverState.waiting_for_custom_input)
    await callback.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Matritsaga qaytish", callback_data=f"mat_resume:{test_id}")]]
    )
    await callback.message.answer(
        f"✏️ <b>{q_num}-savol</b> uchun javobingizni yuboring:\n"
        "(Masalan: <code>0.75</code> yoki <code>3/4</code> yoki <code>12</code> yoki <code>-4.5</code>)",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.message(MatrixSolverState.waiting_for_custom_input, F.text)
async def process_custom_matrix_typed_answer(message: Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()
    data = await state.get_data()
    test_id = data.get("test_id")
    target_q = data.get("type_target_q", 1)
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}
    total_q = data.get("total_questions", 40)

    user_answers[target_q] = text
    next_q = target_q + 1 if target_q < total_q else target_q
    next_page = (next_q - 1) // 20 + 1

    await state.update_data(matrix_answers=user_answers, current_q=next_q, page=next_page)
    await state.set_state(MatrixSolverState.solving)

    await message.answer(f"✅ <b>{target_q}-savol javobi saqlandi:</b> <code>{html.escape(text)}</code>", parse_mode="HTML")
    await open_matrix_solver(message, test_id, state, session, start_q=next_q)


@router.callback_query(F.data.startswith("mat_resume:"))
async def matrix_resume_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    cur_q = data.get("current_q", 1)
    await open_matrix_solver(callback, test_id, state, session, start_q=cur_q)


@router.callback_query(F.data.startswith("mat_fin_prompt:"))
async def matrix_finish_prompt_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}
    total_q = data.get("total_questions", 40)

    answered_count = len(user_answers)
    if answered_count < total_q:
        missing = [i for i in range(1, total_q + 1) if i not in user_answers]
        if len(missing) <= 10:
            missing_str = ", ".join(map(str, missing))
        else:
            missing_str = ", ".join(map(str, missing[:10])) + f" ... va yana {len(missing)-10} ta"

        text = (
            "⚠️ <b>Diqqat! Barcha savollar belgilanmadi!</b>\n\n"
            f"📊 <b>Holat:</b> {answered_count} / {total_q} ta savol belgilandi.\n"
            f"⚪ <b>Bo'sh qolgan savollar ({len(missing)} ta):</b> <code>{missing_str}</code>\n\n"
            "<i>Belgilanmagan savollar xato deb hisoblanadi. Testni yakunlashni tasdiqlaysizmi?</i>"
        )
    else:
        text = (
            f"🎉 <b>Barcha {total_q} ta savolga javob berildi!</b>\n\n"
            "Testni yakunlab, natijangiz va xatolar tahlilini ko'rishni tasdiqlaysizmi?"
        )

    await callback.answer()
    await callback.message.answer(text, reply_markup=get_matrix_finish_confirm_keyboard(test_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("mat_fin_confirm:"))
async def matrix_finish_confirm_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    user_answers = {int(k): str(v) for k, v in data.get("matrix_answers", {}).items()}

    await callback.answer("🚀 Natijalar hisoblanmoqda...")

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        await callback.message.answer("Test topilmadi.")
        return

    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(callback.from_user.id)
    if not user:
        user = await user_repo.create(
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "O'quvchi",
            last_name=callback.from_user.last_name or "",
            username=callback.from_user.username
        )

    answers_list = [f"{q}.{user_answers[q]}" for q in sorted(user_answers.keys())]
    raw_answers = " ".join(answers_list) if answers_list else "none"

    scoring_service = ScoringService(session)
    try:
        res, visual_grid = await scoring_service.evaluate_quick_submission(
            test_id=test.id,
            user_id=user.id,
            raw_answers=raw_answers
        )
        await state.clear()
        auth_service = AuthService(session)
        is_admin = await auth_service.is_admin(callback.from_user.id)

        await callback.message.answer(
            f"⚡ <b>\"{html.escape(test.title)}\"</b> — test yakunlandi!",
            reply_markup=get_student_main_keyboard(is_admin=is_admin),
            parse_mode="HTML"
        )
        await show_test_result(callback.message, res, session, visual_breakdown=visual_grid)
    except Exception as e:
        await callback.message.answer(f"⚠️ <b>Xatolik yuz berdi:</b> {html.escape(str(e))}", parse_mode="HTML")
