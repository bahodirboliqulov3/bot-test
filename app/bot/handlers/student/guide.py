import html
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.repositories.user_repo import UserRepository

router = Router(name="student_guide_and_settings")


def get_guide_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Testni qanday ishlayman?", callback_data="faq:how_to_test")
            ],
            [
                InlineKeyboardButton(text="⚡ Javob tekshirish (Bosqichma-bosqich)", callback_data="faq:quick_check")
            ],
            [
                InlineKeyboardButton(text="🔢 Raqamli & Kasrli testlar", callback_data="faq:numeric")
            ],
            [
                InlineKeyboardButton(text="🏆 Reyting va Ballar tizimi", callback_data="faq:rating")
            ],
            [
                InlineKeyboardButton(text="👨🏫 O‘qituvchilar uchun qo‘llanma", callback_data="faq:teacher")
            ],
            [
                InlineKeyboardButton(text="📨 Adminga murojaat yuborish", callback_data="student_support_prompt")
            ]
        ]
    )


@router.message(StateFilter("*"), F.text.in_(["📘 Qo‘llanma", "📘 Qo'llanma", "Qo‘llanma", "Qo'llanma", "ℹ️ Yordam", "ℹ️ Qo‘llanma va Yordam", "🆘 Yordam"]))
async def show_combined_guide_and_help(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "📘 <b>BOTDAN FOYDALANISH QO‘LLANMASI</b> 📚\n\n"
        "Platformamizdan to‘g‘ri, tezkor va qulay foydalanish uchun quyidagi mavzulardan birini tanlang:"
    )
    await message.answer(text, reply_markup=get_guide_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "faq:menu")
async def faq_menu_callback(callback: CallbackQuery):
    await callback.answer()
    text = (
        "📘 <b>BOTDAN FOYDALANISH QO‘LLANMASI</b> 📚\n\n"
        "Kerakli bo‘limni tanlang:"
    )
    try:
        await callback.message.edit_text(text, reply_markup=get_guide_keyboard(), parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data == "faq:how_to_test")
async def faq_how_to_test(callback: CallbackQuery):
    await callback.answer()
    text = (
        "📝 <b>Testni qanday ishlash kerak?</b>\n\n"
        "1. <b>«✅ Javobni tekshirish»</b> tugmasini bosing yoki to‘g‘ridan-to‘g‘ri test kodini yuboring (Masalan: <code>101</code>).\n"
        "2. Bot testni topadi va savollar sonini aytadi.\n"
        "3. Javoblaringizni yuborasiz (Masalan: <code>ABCD...</code> yoki <code>1.A 2.B 3.12</code>).\n"
        "4. Natijangiz, xatolar tahlili va to‘liq bahoyingiz bir zumda ekranda chiqadi! 🚀"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Barcha savollar", callback_data="faq:menu")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "faq:quick_check")
async def faq_quick_check(callback: CallbackQuery):
    await callback.answer()
    text = (
        "⚡ <b>Tezkor javob tekshirish:</b>\n\n"
        "<b>1-usul (Bosqichma-bosqich):</b>\n"
        "1️⃣ Avval test kodini yuborasiz: <code>101</code>\n"
        "2️⃣ Keyin javoblarni yuborasiz: <code>ABCDACBD...</code>\n\n"
        "<b>2-usul (Bitta xabarda):</b>\n"
        "👉 <code>101 ABCDACBDABCD</code>\n"
        "yoki\n"
        "👉 <code>101 1a 2b 3c 4d 5a</code>\n\n"
        "Bot avtomatik tarzda testingizni hisoblab, to‘liq baho va xatolar tahlilini chiqarib beradi! 🎯"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Barcha savollar", callback_data="faq:menu")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "faq:numeric")
async def faq_sat(callback: CallbackQuery):
    await callback.answer()
    text = (
        "🔢 <b>Raqamli va Kasrli savollar qanday ishlaydi?</b>\n\n"
        "Botimizda nafaqat <code>A, B, C, D</code> variantli, balki <b>yopiq / ochiq raqamli va kasrli</b> savollar ham qabul qilinadi!\n\n"
        "📌 <b>Kiritish qoidalari:</b>\n"
        "• <b>Kasrlar:</b> <code>3/4</code> deb yozsangiz ham, <code>0.75</code> deb yozsangiz ham to‘g‘ri hisoblanadi!\n"
        "• <b>Manfiy sonlar:</b> <code>-4.5</code> yoki <code>-9/2</code>\n"
        "• <b>Javob formati:</b> <code>1.A 2.B 3.12 4.3/4 5.-4.5 6.Toshkent</code>\n"
        "• <b>Vergul bilan:</b> <code>A, B, 12, 3/4, -4.5, Toshkent</code>\n\n"
        "Matematik jihatdan teng barcha javoblar bot tomonidan avtomatik to‘g‘ri deb qabul qilinadi! 🎯"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Barcha savollar", callback_data="faq:menu")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "faq:rating")
async def faq_rating(callback: CallbackQuery):
    await callback.answer()
    text = (
        "🏆 <b>Reyting va Ballar qanday hisoblanadi?</b>\n\n"
        "• Har bir to‘g‘ri ishlangan test sizga ballar va reyting o‘rnini oshirish imkonini beradi.\n"
        "• «🏆 Reyting» bo‘limida umumiy TOP-10 talikni hamda o‘z natijalaringizni jonli kuzatib borishingiz mumkin! 🥇"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Barcha savollar", callback_data="faq:menu")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "faq:teacher")
async def faq_teacher(callback: CallbackQuery):
    await callback.answer()
    text = (
        "👨‍🏫 <b>O‘qituvchilar va Repetitorlar uchun:</b>\n\n"
        "• <b>➕ Yangi test:</b> 20 soniyada yangi test yaratasiz (Nomi → Kod → Kalitlar → Vaqt).\n"
        "• <b>📎 Test fayli:</b> Botga fayl yuklash shart emas — PDF yoki test rasmini to‘g‘ridan-to‘g‘ri o‘z kanalingizga tashlaysiz. Bot faqat javoblarni tekshirib beradi.\n"
        "• <b>🔢 Raqamli va barcha formatlar:</b> Raqamli, kasrli (<code>0.75</code>, <code>3/4</code>) va variantli (<code>A,B,C,D</code>) barcha kalitlarni qabul qiladi.\n"
        "• <b>📊 Excel hisoboti:</b> Test tugagach, to‘liq o‘quvchilar tahlili va natijalari matritsasini Excel formatida yuklab olasiz! 📈"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Barcha savollar", callback_data="faq:menu")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

