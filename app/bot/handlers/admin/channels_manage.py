from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.bot.filters.admin_filter import IsAdminFilter
from app.bot.keyboards.reply_keyboards import get_cancel_keyboard
from app.bot.states.admin_states import AdminChannelState
from app.database.models.system import RequiredChannel
from app.database.repositories.channel_repo import ChannelRepository

router = Router(name="admin_channels_manage")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


@router.message(F.text == "📢 Majburiy kanallar")
async def list_required_channels_handler(message: Message, session: AsyncSession):
    channel_repo = ChannelRepository(session)
    channels = await channel_repo.get_all()

    text = f"📢 Majburiy kanallar ro‘yxati ({len(channels)} ta):\n\n"
    for ch in channels:
        status_icon = "🟢 Faol" if ch.is_active else "🔴 O'chirilgan"
        text += f"🔹 <b>{ch.title}</b> (<code>{ch.channel_id}</code>) — {status_icon}\n   🔗 <code>{ch.invite_link}</code>\n\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi kanal qo‘shish", callback_data="adm_add_channel")],
            [InlineKeyboardButton(text="❌ Kanalni o‘chirish", callback_data="adm_del_channel_prompt")]
        ]
    )

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_add_channel")
async def start_add_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminChannelState.waiting_for_title)
    await callback.answer()
    await callback.message.answer(
        "➕ Kanal nomini kiriting:\n(Masalan: Rasmiy Yangiliklar)",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


from app.services.channel_service import ChannelService
import logging

logger = logging.getLogger(__name__)


@router.message(AdminChannelState.waiting_for_title)
async def process_channel_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminChannelState.waiting_for_channel_id)
    await message.answer(
        "Kanal ID yoki @username kiriting:\n(Masalan: <code>@mening_kanalim</code> yoki <code>-1001234567890</code>):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminChannelState.waiting_for_channel_id)
async def process_channel_id(message: Message, state: FSMContext, bot: Bot):
    raw_input = message.text.strip()
    norm_id = ChannelService.normalize_channel_id(raw_input)
    
    # Telegram orqali jonli tekshirish
    try:
        chat = await bot.get_chat(norm_id)
        bot_user = await bot.get_me()
        bot_member = await bot.get_chat_member(chat.id, bot_user.id)
        
        if bot_member.status not in ["administrator", "creator"]:
            await message.answer(
                f"⚠️ <b>Bot \"{chat.title}\" kanalida ADMIN emas!</b>\n\n"
                f"Iltimos, avval @{bot_user.username} ni kanalingizga qo‘shib, unga <b>Adminlik huquqini</b> bering, so‘ng qaytadan yuboring.",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
            return

        # Bot kanalda admin ekanligi tasdiqlandi!
        auto_title = chat.title
        auto_link = f"https://t.me/{chat.username}" if chat.username else None
        
        data = await state.get_data()
        final_title = data.get("title") or auto_title

        await state.update_data(
            channel_id=str(chat.id) if not chat.username else f"@{chat.username}",
            title=final_title,
            invite_link=auto_link
        )
        
        if auto_link:
            await state.set_state(AdminChannelState.waiting_for_invite_link)
            await message.answer(
                f"✅ <b>Kanal topildi va bot adminligi tasdiqlandi!</b>\n\n"
                f"📢 Nomi: <b>{final_title}</b>\n"
                f"🆔 ID: <code>{chat.id}</code>\n"
                f"🔗 Havola: <code>{auto_link}</code>\n\n"
                f"Ushbu havola ma'qul bo'lsa <b>\"Ha\"</b> yoki <b>\"Tayyor\"</b> deb yozing, yoki boshqa taklif havolasini kiriting:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        else:
            await state.set_state(AdminChannelState.waiting_for_invite_link)
            await message.answer(
                f"✅ <b>Kanal topildi: {final_title}</b> (Yopiq/Private kanal)\n\n"
                "Kanalga a'zo bo'lish havolasini (invite link) kiriting:\n(Masalan: <code>https://t.me/+AbCd...</code>)",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.warning(f"Error validating channel {raw_input}: {e}")
        # Agar get_chat o'xshamasa (masalan bot hali qo'shilmagan), kiritilgan ID ni qabul qilib link so'rash
        await state.update_data(channel_id=str(norm_id))
        await state.set_state(AdminChannelState.waiting_for_invite_link)
        await message.answer(
            f"ℹ️ Kanal kiritildi: <code>{norm_id}</code>\n\n"
            "<i>(Eslatma: Bot ushbu kanalda admin bo'lishi shart!)</i>\n\n"
            "Kanalga a'zo bo'lish havolasini (link) kiriting:\n(Masalan: https://t.me/mening_kanalim):",
            reply_markup=get_cancel_keyboard(),
            parse_mode="HTML"
        )


@router.message(AdminChannelState.waiting_for_invite_link)
async def process_channel_link(message: Message, state: FSMContext, session: AsyncSession):
    text_input = message.text.strip()
    data = await state.get_data()
    
    if text_input.lower() in ["ha", "tayyor", "ok", "+"] and data.get("invite_link"):
        link = data["invite_link"]
    else:
        link = text_input

    title = data.get("title") or "Kanal"
    channel_id = str(data["channel_id"])

    channel_repo = ChannelRepository(session)
    await channel_repo.create(
        title=title,
        channel_id=channel_id,
        invite_link=link,
        is_active=True
    )

    await state.clear()
    await message.answer(
        f"✅ <b>\"{title}\"</b> majburiy kanallar ro‘yxatiga muvaffaqiyatli qo‘shildi!\n\n"
        f"🆔 ID: <code>{channel_id}</code>\n"
        f"🔗 Havola: <code>{link}</code>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_del_channel_prompt")
async def delete_channel_prompt(callback: CallbackQuery, session: AsyncSession):
    channel_repo = ChannelRepository(session)
    channels = await channel_repo.get_all()
    if not channels:
        await callback.answer("Kanallar mavjud emas.", show_alert=True)
        return

    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"🗑 {ch.title}", callback_data=f"adm_del_ch:{ch.id}")])

    await callback.answer()
    await callback.message.answer(
        "O'chirmoqchi bo'lgan kanalni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("adm_del_ch:"))
async def delete_channel_callback(callback: CallbackQuery, session: AsyncSession):
    ch_id = int(callback.data.split(":")[1])
    channel_repo = ChannelRepository(session)
    await channel_repo.delete(ch_id)
    await callback.answer("🗑 Kanal o'chirildi!")
    try:
        await callback.message.delete()
    except Exception:
        pass
