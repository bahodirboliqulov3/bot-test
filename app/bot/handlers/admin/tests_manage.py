import html
from datetime import datetime, timedelta, timezone
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.bot.filters.admin_filter import IsAdminFilter
from app.bot.keyboards.reply_keyboards import get_admin_main_keyboard, get_cancel_keyboard
from app.bot.states.admin_states import (
    AdminEditFileState,
    AdminEditKeyState,
    AdminEditTitleState,
    AdminScheduleState,
    AdminSetPasswordState,
)
from app.database.models.test import Test, TestStatus
from app.database.repositories.channel_repo import ChannelRepository
from app.database.repositories.result_repo import ResultRepository
from app.database.repositories.test_repo import TestRepository
from app.services.excel_service import ExcelService
from app.services.scoring_service import ScoringService
from app.services.test_service import TestService

router = Router(name="admin_tests_manage")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


UZB_TZ = timezone(timedelta(hours=5))


def to_uzb_dt(dt: datetime | None) -> datetime | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(UZB_TZ)


def format_admin_test_card(t: Test) -> str:
    status_icon = "🟢 Faol" if t.status == TestStatus.ACTIVE else "🟡 Qoralama" if t.status == TestStatus.DRAFT else "🕒 Jadval" if t.status == TestStatus.SCHEDULED else "🔴 Yopilgan"
    st_uzb = to_uzb_dt(t.start_time)
    et_uzb = to_uzb_dt(t.end_time)
    start_str = st_uzb.strftime("%d.%m.%Y %H:%M") if st_uzb else "-"
    end_str = et_uzb.strftime("%d.%m.%Y %H:%M") if et_uzb else "-"
    pass_str = t.password or "Yo'q"
    attempts_str = "Faqat 1 marta 🔒" if (t.max_attempts and t.max_attempts == 1) else "Cheksiz 🔓"
    q_count = t.total_questions if t.total_questions > 0 else (len(t.test_questions) if t.test_questions else 0)
    safe_title = html.escape(t.title or "Test")
    safe_code = html.escape(t.code or "")
    key_preview = html.escape(t.answer_key[:30] + "..." if t.answer_key and len(t.answer_key) > 30 else (t.answer_key or "Yo'q"))

    file_info = "📄 Biriktirilgan fayl mavjud" if t.file_id else "❌ Fayl biriktirilmagan"

    return (
        f"📝 <b>{safe_title}</b> (ID: <code>{t.id}</code>)\n\n"
        f"🔑 <b>Test kodi:</b> <code>{safe_code}</code>\n"
        f"🔑 <b>Kalitlar:</b> <code>{key_preview}</code>\n"
        f"❓ <b>Savollar soni:</b> {q_count} ta\n"
        f"📎 <b>Savollar fayli:</b> {file_info}\n"
        f"📊 <b>Holati:</b> {status_icon}\n"
        f"🔒 <b>Qayta topshirish:</b> {attempts_str}\n"
        f"🔐 <b>Parol:</b> {html.escape(pass_str)}\n"
        f"📅 <b>Boshlanish:</b> {start_str} | <b>Tugash:</b> {end_str}\n"
        f"⏱ <b>Vaqt:</b> {t.time_limit_minutes} daqiqa"
    )


def get_admin_test_keyboard(test: Test, page: int = 1) -> InlineKeyboardMarkup:
    attempts_btn_text = "🔓 Qayta topshirish: Cheksiz qilish" if (test.max_attempts and test.max_attempts == 1) else "🔒 Qayta topshirish: 1 marta qilish"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Natijalarni e'lon qilish", callback_data=f"adm_pub_res:{test.id}"),
                InlineKeyboardButton(text="📥 Excel yuklash", callback_data=f"adm_import_xl:{test.id}")
            ],
            [
                InlineKeyboardButton(text="📊 Xatolar tahlili", callback_data=f"adm_analytics:{test.id}:{page}"),
                InlineKeyboardButton(text="📢 E'lon matni", callback_data=f"adm_get_post:{test.id}")
            ],
            [
                InlineKeyboardButton(text="✏️ Kalitni tahrirlash", callback_data=f"adm_edit_key:{test.id}"),
                InlineKeyboardButton(text="✏️ Nomni o‘zgartirish", callback_data=f"adm_edit_title:{test.id}:{page}"),
                InlineKeyboardButton(text="📎 Faylni yangilash", callback_data=f"adm_edit_file:{test.id}:{page}")
            ],
            [
                InlineKeyboardButton(text=attempts_btn_text, callback_data=f"adm_toggle_att:{test.id}:{page}")
            ],
            [
                InlineKeyboardButton(text="🔄 Nusxalash", callback_data=f"adm_clone:{test.id}"),
                InlineKeyboardButton(text="⏰ Jadval", callback_data=f"adm_sched:{test.id}"),
                InlineKeyboardButton(text="🔐 Parol", callback_data=f"adm_pass:{test.id}")
            ],
            [
                InlineKeyboardButton(text="🟢 Faol qilish", callback_data=f"adm_set_status:{test.id}:active"),
                InlineKeyboardButton(text="⛔ Yopish", callback_data=f"adm_set_status:{test.id}:finished"),
                InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"adm_del:{test.id}")
            ],
            [
                InlineKeyboardButton(text="◀️ Barcha testlar ro‘yxatiga qaytish", callback_data=f"adm_tests_page:{page}")
            ]
        ]
    )


def build_admin_tests_page(tests: list[Test], page: int = 1, page_size: int = 5) -> tuple[str, InlineKeyboardMarkup]:
    total_tests = len(tests)
    total_pages = max(1, (total_tests + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    current_page_tests = tests[start_idx:start_idx + page_size]

    text = f"📝 <b>Testlar Boshqaruvi</b> (Jami: {total_tests} ta):\n\n"
    buttons = []

    for idx, t in enumerate(current_page_tests, start=start_idx + 1):
        status_icon = "🟢" if t.status == TestStatus.ACTIVE else "🟡" if t.status == TestStatus.DRAFT else "🕒" if t.status == TestStatus.SCHEDULED else "🔴"
        safe_title = html.escape(t.title or "Test")
        safe_code = html.escape(t.code or "")
        q_count = t.total_questions if t.total_questions > 0 else (len(t.test_questions) if t.test_questions else 0)

        text += (
            f"{idx}. {status_icon} <b>{safe_title}</b> (<code>{safe_code}</code>)\n"
            f"   ❓ {q_count} ta savol | ⏱ {t.time_limit_minutes} daq | ID: {t.id}\n\n"
        )
        short_name = (t.title[:18] + "..") if len(t.title or "") > 18 else (t.title or "Test")
        buttons.append([InlineKeyboardButton(text=f"⚙️ {idx}. {short_name} ({t.code})", callback_data=f"adm_open_test:{t.id}:{page}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"adm_tests_page:{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"adm_tests_page:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(StateFilter("*"), F.text.in_(["📝 Testlar boshqaruvi", "Testlar boshqaruvi"]))
async def list_admin_tests_handler(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    test_repo = TestRepository(session)
    tests = await test_repo.get_recent_tests(limit=50)

    if not tests:
        await message.answer("Bazada hozircha testlar mavjud emas. '➕ Yangi test' tugmasi orqali test yarating.")
        return

    text, kb = build_admin_tests_page(tests, page=1)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_tests_page:"))
async def admin_tests_page_callback(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1])
    test_repo = TestRepository(session)
    tests = await test_repo.get_recent_tests(limit=50)

    if not tests:
        await callback.answer("Bazada testlar mavjud emas.", show_alert=True)
        return

    text, kb = build_admin_tests_page(tests, page=page)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_open_test:"))
async def admin_open_test_callback(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)

    if not test:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    card = format_admin_test_card(test)
    kb = get_admin_test_keyboard(test, page=page)

    await callback.answer()
    try:
        await callback.message.edit_text(card, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass



# Feature 5: Toggle Max Attempts (1 marta vs Cheksiz)
@router.callback_query(F.data.startswith("adm_toggle_att:"))
async def toggle_attempts_callback(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)
    if not test:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    if test.max_attempts and test.max_attempts == 1:
        test.max_attempts = 0  # Unlimited
        msg = "🔓 Ushbu test uchun cheksiz topshirish yoqildi!"
    else:
        test.max_attempts = 1  # 1 attempt only
        msg = "🔒 Ushbu test uchun faqat 1 marta topshirish cheklovi o‘rnatildi!"

    await session.commit()
    await callback.answer(msg, show_alert=True)

    card = format_admin_test_card(test)
    kb = get_admin_test_keyboard(test, page=page)
    try:
        await callback.message.edit_text(card, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


# Feature 3: Leaderboard Channel Report Generator
@router.callback_query(F.data.startswith("adm_pub_res:"))
async def publish_test_results_callback(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    scoring_service = ScoringService(session)
    channel_repo = ChannelRepository(session)

    leaderboard_text = await scoring_service.generate_channel_leaderboard_text(test_id, limit=20)
    channels = await channel_repo.get_active_channels()

    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"📢 {ch.title} ga yuborish", callback_data=f"send_res_ch:{test_id}:{ch.channel_id}")])

    buttons.append([InlineKeyboardButton(text="◀️ Ortga", callback_data=f"adm_open_test:{test_id}:1")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.answer()
    await callback.message.answer(leaderboard_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("send_res_ch:"))
async def send_results_to_channel(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    channel_target = parts[2]

    scoring_service = ScoringService(session)
    leaderboard_text = await scoring_service.generate_channel_leaderboard_text(test_id, limit=25)

    try:
        chat_id = channel_target
        if not (chat_id.startswith("@") or chat_id.startswith("-100")) and chat_id.isdigit():
            chat_id = int(chat_id)
        await bot.send_message(chat_id=chat_id, text=leaderboard_text, parse_mode="HTML")
        await callback.answer("✅ Natijalar kanalga muvaffaqiyatli e'lon qilindi!", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Xatolik: Bot ushbu kanalda admin bo'lishi kerak.", show_alert=True)


@router.callback_query(F.data.startswith("adm_set_status:"))
async def change_status_callback(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    new_status = parts[2]

    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)
    if test:
        test.status = TestStatus(new_status)
        await session.commit()
        status_name = "Faol" if new_status == "active" else "Yopilgan"
        await callback.answer(f"✅ Test holati: {status_name}")
        card = format_admin_test_card(test)
        kb = get_admin_test_keyboard(test)
        try:
            await callback.message.edit_text(card, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data.startswith("adm_del:"))
async def delete_test_confirm_callback(callback: CallbackQuery, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)
    if not test:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, o'chirilsin", callback_data=f"adm_del_confirm:{test_id}"),
                InlineKeyboardButton(text="◀️ Orqaga", callback_data=f"adm_open_test:{test_id}:1")
            ]
        ]
    )
    await callback.answer()
    try:
        await callback.message.edit_text(
            f"🗑 <b>Testni o'chirishni tasdiqlaysizmi?</b>\n\n"
            f"📝 Test: <b>{html.escape(test.title or 'Test')}</b>\n"
            f"🔑 Kod: <code>{html.escape(test.code or '')}</code>\n\n"
            f"⚠️ <i>Barcha natijalar ham o'chiriladi!</i>",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_del_confirm:"))
async def delete_test_confirmed_callback(callback: CallbackQuery, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    test_repo = TestRepository(session)

    # ondelete="CASCADE" orqali natijalar avtomatik o'chadi
    deleted = await test_repo.delete(test_id)
    await session.commit()

    if deleted:
        await callback.answer("🗑 Test muvaffaqiyatli o'chirildi!", show_alert=True)
    else:
        await callback.answer("❌ O'chirishda xatolik yuz berdi.", show_alert=True)
        return

    tests = await test_repo.get_recent_tests(limit=50)
    if not tests:
        try:
            await callback.message.edit_text("📝 Bazada hozircha testlar mavjud emas.")
        except Exception:
            pass
        return
    text, kb = build_admin_tests_page(tests, page=1)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass





@router.callback_query(F.data.startswith("adm_clone:"))
async def clone_test_callback(callback: CallbackQuery, session: AsyncSession):
    test_id = int(callback.data.split(":")[1])
    test_service = TestService(session)
    cloned = await test_service.duplicate_test(test_id)
    await session.commit()
    if cloned:
        await callback.answer(f"✅ Nusxa yaratildi: {cloned.code}", show_alert=True)
    else:
        await callback.answer("Nusxalashda xatolik yuz berdi.", show_alert=True)

    test_repo = TestRepository(session)
    tests = await test_repo.get_recent_tests(limit=50)
    text, kb = build_admin_tests_page(tests, page=1)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_pass:"))
async def start_set_password(callback: CallbackQuery, state: FSMContext):
    test_id = int(callback.data.split(":")[1])
    await state.update_data(target_test_id=test_id)
    await state.set_state(AdminSetPasswordState.waiting_for_password)
    await callback.answer()
    await callback.message.answer(
        "🔐 <b>Test uchun yangi parol kiriting:</b>\n"
        "(Parolni o‘chirish uchun <code>0</code> yoki <code>yo'q</code> deb yozing)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminSetPasswordState.waiting_for_password)
async def process_password_input(message: Message, state: FSMContext, session: AsyncSession):
    pw = message.text.strip()
    data = await state.get_data()
    test_id = data.get("target_test_id")

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if test:
        if pw in ["0", "yoq", "yo'q", "none"]:
            test.password = None
            msg = "🔓 Test paroli olib tashlandi."
        else:
            test.password = pw
            msg = f"🔐 Test paroli <code>{html.escape(pw)}</code> qilib o‘rnatildi."
        await session.commit()
        await state.clear()
        await message.answer(msg, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_sched:"))
async def start_schedule_test(callback: CallbackQuery, state: FSMContext):
    test_id = int(callback.data.split(":")[1])
    await state.update_data(target_test_id=test_id)
    await state.set_state(AdminScheduleState.waiting_for_dates)
    await callback.answer()
    await callback.message.answer(
        "⏰ <b>Testning boshlanish va tugash vaqtini kiriting:</b>\n\n"
        "Format: <code>DD.MM.YYYY HH:MM - DD.MM.YYYY HH:MM</code>\n"
        "Misol: <code>21.08.2026 09:00 - 21.08.2026 21:00</code>\n\n"
        "(Cheklovni olib tashlash uchun <code>0</code> deb yozing)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminScheduleState.waiting_for_dates)
async def process_schedule_dates(message: Message, state: FSMContext, session: AsyncSession):
    raw = message.text.strip()
    data = await state.get_data()
    test_id = data.get("target_test_id")

    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        await state.clear()
        await message.answer("Test topilmadi.")
        return

    if raw == "0":
        test.start_time = None
        test.end_time = None
        test.status = TestStatus.ACTIVE
        await session.commit()
        await state.clear()
        await message.answer("✅ Vaqt cheklovlari olib tashlandi, test doimiy faol!")
        return

    try:
        parts = raw.split("-")
        st_parsed = datetime.strptime(parts[0].strip(), "%d.%m.%Y %H:%M").replace(tzinfo=UZB_TZ)
        et_parsed = datetime.strptime(parts[1].strip(), "%d.%m.%Y %H:%M").replace(tzinfo=UZB_TZ)

        test.start_time = st_parsed.astimezone(timezone.utc)
        test.end_time = et_parsed.astimezone(timezone.utc)
        test.status = TestStatus.SCHEDULED
        await session.commit()
        await state.clear()
        await message.answer(f"⏰ Test jadvali saqlandi: {raw}", parse_mode="HTML")
    except Exception:
        await message.answer("❌ Noto'g'ri format. Iltimos: <code>DD.MM.YYYY HH:MM - DD.MM.YYYY HH:MM</code> ko'rinishida kiriting:")


# --- Feature: Get Ready-Made Channel Announcement Post ---
@router.callback_query(F.data.startswith("adm_get_post:"))
async def get_test_post_template_callback(callback: CallbackQuery, bot: Bot, session: AsyncSession):
    await callback.answer()
    test_id = int(callback.data.split(":")[1])
    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        await callback.message.answer("❌ Test topilmadi.")
        return

    try:
        bot_user = await bot.get_me()
        bot_username = bot_user.username
    except Exception:
        bot_username = "tekshiruv2_bot"

    share_link = f"https://t.me/{bot_username}?start=test_{test.code}"
    q_count = test.total_questions if test.total_questions > 0 else (len(test.test_questions) if test.test_questions else 0)

    st_uzb = to_uzb_dt(test.start_time)
    et_uzb = to_uzb_dt(test.end_time)
    if st_uzb and et_uzb:
        sched_info = f"🗓 {st_uzb.strftime('%d.%m.%Y %H:%M')} dan {et_uzb.strftime('%d.%m.%Y %H:%M')} gacha"
    elif et_uzb:
        sched_info = f"🗓 {et_uzb.strftime('%d.%m.%Y %H:%M')} gacha"
    else:
        sched_info = "♾ Doimiy faol (Cheklovsiz)"

    post_text = (
        f"📝 <b>«{html.escape(test.title)}» testi boshlandi!</b>\n\n"
        f"🔑 <b>Test kodi:</b> <code>{test.code}</code>\n"
        f"❓ <b>Savollar soni:</b> {q_count} ta\n"
        f"⏱ <b>Test ishlash vaqti:</b> {test.time_limit_minutes} daqiqa\n"
        f"📅 <b>Faollik muddati:</b> {sched_info}\n\n"
        f"🚀 <b>Testni topshirish uchun quyidagi havolani bosing:</b>\n"
        f"👉 <a href=\"{share_link}\">Testni boshlash (Havola)</a>\n\n"
        f"<i>(Yoki @{bot_username} botiga kirib <code>{test.code}</code> kodini yuboring)</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Testni ochish (Havola)", url=share_link)],
            [InlineKeyboardButton(text="◀️ Test kartasiga qaytish", callback_data=f"adm_view_test:{test.id}")]
        ]
    )

    await callback.message.answer(
        "📢 <b>Kanal va guruhlar uchun tayyor e'lon matni:</b>\n\n"
        "<i>(Ushbu postni to‘g‘ridan-to‘g‘ri kanalingizga forward yoki nusxa qilib yuborishingiz mumkin)</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{post_text}\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# --- Feature: Edit Answer Key & Auto Recalculate Previous Results ---
@router.callback_query(F.data.startswith("adm_edit_key:"))
async def edit_test_key_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    test_id = int(callback.data.split(":")[1])
    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        await callback.message.answer("❌ Test topilmadi.")
        return

    await state.update_data(edit_test_id=test.id)
    await state.set_state(AdminEditKeyState.waiting_for_new_key)

    current_key_preview = test.answer_key or "Kiritilmagan"

    await callback.message.answer(
        f"✏️ <b>«{html.escape(test.title)}» testi kalitlarini tahrirlash</b>\n\n"
        f"🔑 <b>Hozirgi kalitlar:</b> <code>{html.escape(current_key_preview)}</code>\n\n"
        "Yangi to'g'ri kalitlarni yuboring:\n"
        "• <code>ABCDABCD...</code>\n"
        "• yoki <code>1.A 2.B 3.12 4.3/4 5.C</code>\n\n"
        "💡 <i>Yangi kalit kiritilgach, barcha o'quvchilar natijalari fon rejimida qayta hisoblanadi!</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminEditKeyState.waiting_for_new_key, F.text)
async def process_new_answer_key(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    text = message.text.strip()
    if text in ["❌ Bekor qilish", "🏠 Bosh menyu"]:
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=get_admin_main_keyboard())
        return

    data = await state.get_data()
    test_id = data.get("edit_test_id")
    test_repo = TestRepository(session)
    test = await test_repo.get_by_id(test_id)
    if not test:
        await state.clear()
        await message.answer("❌ Test topilmadi.", reply_markup=get_admin_main_keyboard())
        return

    parsed = ScoringService.parse_quick_answers(text)
    if not parsed or len(parsed) < 1:
        await message.answer(
            "❌ Kalitlar aniqlanmadi. Iltimos, to'g'ri formatda kiriting (Masalan: <code>ABCD...</code> yoki <code>1.A 2.B 3.12</code>):",
            parse_mode="HTML"
        )
        return

    all_single_letters = all(len(v) == 1 and v.isalpha() for v in parsed.values())
    if all_single_letters:
        key_str = "".join(parsed[i].upper() for i in sorted(parsed.keys()))
    else:
        key_str = " ".join(f"{i}.{parsed[i]}" for i in sorted(parsed.keys()))
    total_q = len(parsed)

    test.answer_key = key_str
    test.total_questions = total_q
    await session.commit()

    admin_id = message.from_user.id
    test_title = test.title

    # Immediately confirm to admin — bot stays responsive
    await message.answer(
        f"✅ <b>«{html.escape(test_title)}» testi kaliti saqlandi!</b>\n\n"
        f"🔑 <b>Yangi kalit:</b> <code>{html.escape(key_str)}</code>\n"
        f"❓ <b>Savollar soni:</b> {total_q} ta\n\n"
        f"🔄 <i>Natijalar qayta hisoblanmoqda... Tuganach xabar keladi.</i>",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()

    # Re-scoring runs in background — does NOT block the event loop
    async def _rescore_results():
        try:
            result_repo = ResultRepository(session)
            results = await result_repo.get_test_results(test_id)

            recalculated_count = 0
            correct_keys = ScoringService.parse_quick_answers(key_str)

            for r in results:
                attempt = r.attempt
                if attempt and attempt.option_order and "user_answers" in attempt.option_order:
                    user_answers_raw = attempt.option_order["user_answers"]
                    user_answers = {int(k): v for k, v in user_answers_raw.items()}

                    correct_count = 0
                    incorrect_count = 0
                    for idx, corr_val in correct_keys.items():
                        u_val = user_answers.get(idx)
                        if u_val is not None:
                            if ScoringService.are_answers_equivalent(u_val, corr_val):
                                correct_count += 1
                            else:
                                incorrect_count += 1

                    unanswered = max(0, total_q - (correct_count + incorrect_count))
                    percentage = round((correct_count / total_q * 100), 2) if total_q > 0 else 0.0
                    point_per_q = r.attempt.test.max_points / total_q if total_q > 0 else 1.0
                    total_score = round(correct_count * point_per_q, 2)

                    r.correct_count = correct_count
                    r.incorrect_count = incorrect_count
                    r.unanswered_count = unanswered
                    r.percentage = percentage
                    r.total_score = total_score
                    recalculated_count += 1

            await session.commit()

            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔄 <b>Qayta hisoblash yakunlandi!</b>\n\n"
                    f"📝 Test: <b>{html.escape(test_title)}</b>\n"
                    f"✅ <b>{recalculated_count} ta</b> o'quvchi natijasi avtomatik yangilandi!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Background re-scoring error: {e}")
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"❌ Qayta hisoblashda xatolik: {e}"
                )
            except Exception:
                pass

    import asyncio
    asyncio.create_task(_rescore_results())


# 📊 Test Xatolar Tahlili (Mistake Analytics)
@router.callback_query(F.data.startswith("adm_analytics:"))
async def admin_test_analytics_callback(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)
    if not test:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    scoring_service = ScoringService(session)
    analytics = await scoring_service.get_test_error_analytics(test_id)

    total_p = analytics.get("total_participants", 0)
    if total_p == 0:
        await callback.answer("Ushbu testni hali hech kim topshirmagan.", show_alert=True)
        return

    avg_pct = analytics.get("avg_percentage", 0.0)
    hardest = analytics.get("hardest_questions", [])
    easiest = analytics.get("easiest_questions", [])

    text = (
        f"📊 <b>«{html.escape(test.title)}» TESTI TAHLILI</b>\n\n"
        f"🔑 <b>Test kodi:</b> <code>{html.escape(test.code or '')}</code>\n"
        f"👥 <b>Jami ishtirokchilar:</b> {total_p} ta\n"
        f"📈 <b>O‘rtacha ko‘rsatkich:</b> {avg_pct}%\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"❌ <b>ENG KO‘P XATO QILINGAN SAVOLLAR:</b>\n"
    )

    if hardest:
        for idx, h in enumerate(hardest, start=1):
            text += f"<b>{idx}. {h['question_num']}-savol:</b> {h['incorrect_count']} ta xato (<b>{h['incorrect_pct']}%</b>)\n"
    else:
        text += "<i>Ma'lumot yo‘q</i>\n"

    text += (
        f"\n━━━━━━━━━━━━━━━━━\n"
        f"✅ <b>ENG OSON TOPILGAN SAVOLLAR:</b>\n"
    )

    if easiest:
        for idx, e in enumerate(easiest, start=1):
            text += f"<b>{idx}. {e['question_num']}-savol:</b> {e['correct_count']} ta to‘g‘ri (<b>{e['correct_pct']}%</b>)\n"
    else:
        text += "<i>Ma'lumot yo‘q</i>\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Test kartasiga qaytish", callback_data=f"adm_open_test:{test_id}:{page}")
            ]
        ]
    )

    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ✏️ Nomni o‘zgartirish (Edit Title)
@router.callback_query(F.data.startswith("adm_edit_title:"))
async def admin_edit_title_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)
    if not test:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    await state.set_state(AdminEditTitleState.waiting_for_new_title)
    await state.update_data(test_id=test_id, page=page)

    await callback.answer()
    await callback.message.answer(
        f"✏️ <b>«{html.escape(test.title)}»</b> testi uchun yangi nomni kiriting:\n\n"
        f"<i>(Masalan: 9-sinf Matematika 1-variant)</i>",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminEditTitleState.waiting_for_new_title)
async def admin_edit_title_submit(message: Message, state: FSMContext, session: AsyncSession):
    new_title = (message.text or "").strip()
    if not new_title:
        await message.answer("Iltimos, test nomini matn ko‘rinishida kiriting:")
        return

    data = await state.get_data()
    test_id = data.get("test_id")
    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)

    if not test:
        await message.answer("❌ Test topilmadi.", reply_markup=get_admin_main_keyboard())
        await state.clear()
        return

    test.title = new_title
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ <b>Test nomi muvaffaqiyatli o‘zgartirildi!</b>\n\n"
        f"📝 Yangi nom: <b>{html.escape(new_title)}</b>",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML"
    )


# 📎 Faylni yangilash (Edit/Upload New File)
@router.callback_query(F.data.startswith("adm_edit_file:"))
async def admin_edit_file_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    test_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)
    if not test:
        await callback.answer("Test topilmadi.", show_alert=True)
        return

    await state.set_state(AdminEditFileState.waiting_for_new_file)
    await state.update_data(test_id=test_id, page=page)

    await callback.answer()
    await callback.message.answer(
        f"📎 <b>«{html.escape(test.title)}»</b> testi uchun yangi savollar faylini (PDF yoki Rasm) yuboring:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminEditFileState.waiting_for_new_file)
async def admin_edit_file_submit(message: Message, state: FSMContext, session: AsyncSession):
    file_id = None
    file_unique_id = None

    if message.document:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_unique_id = message.photo[-1].file_unique_id
    else:
        await message.answer("Iltimos, faylni PDF hujjat yoki rasm ko‘rinishida yuboring:")
        return

    data = await state.get_data()
    test_id = data.get("test_id")
    test_repo = TestRepository(session)
    test = await test_repo.get_test_with_questions(test_id)

    if not test:
        await message.answer("❌ Test topilmadi.", reply_markup=get_admin_main_keyboard())
        await state.clear()
        return

    test.file_id = file_id
    test.file_unique_id = file_unique_id
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ <b>«{html.escape(test.title)}» testi savollar fayli yangilandi!</b>\n\n"
        f"Endi o‘quvchilar test kodini kiritganda ushbu yangi faylni yuklab olishadi.",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML"
    )




