from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_student_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="✅ Javobni tekshirish")],
        [KeyboardButton(text="📊 Natijalarim"), KeyboardButton(text="🏆 Reyting")],
        [KeyboardButton(text="👤 Profilim"), KeyboardButton(text="📘 Qo‘llanma")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="👨‍💼 Admin Paneli")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_admin_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="➕ Yangi test yaratish"), KeyboardButton(text="🔑 Tezkor kalit qo‘shish")],
        [KeyboardButton(text="📝 Testlar boshqaruvi"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="👥 O‘quvchilar"), KeyboardButton(text="⚙️ Sozlamalar")],
        [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🏠 O‘quvchi rejimi")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")],
            [KeyboardButton(text="🏠 Bosh menyu")]
        ],
        resize_keyboard=True
    )


def get_phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="⬅️ Ortga"), KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )


def get_step_back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Ortga"), KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )
