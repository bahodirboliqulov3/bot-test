from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.bot.filters.admin_filter import IsAdminFilter
from app.bot.keyboards.reply_keyboards import get_cancel_keyboard
from app.bot.states.admin_states import AdminChannelState
from app.database.models.system import RequiredChannel
from app.database.repositories.channel_repo import ChannelRepository
from app.services.channel_service import ChannelService
import logging

logger = logging.getLogger(__name__)

router = Router(name="admin_channels_manage")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


@router.message(F.text == "📢 Majburiy kanallar")
async def list_required_channels_handler(message: Message, session: AsyncSession):
    channel_repo = ChannelRepository(session)
    channels = await channel_repo.get_all()

    text = f"📢 <b>Majburiy kanallar ro‘yxati ({len(channels)} ta):</b>\n\n"
    if not channels:
        text += "<i>Hozircha majburiy kanal ulanmagan.</i>\n\n"
    else:
        for ch in channels:
            status_icon = "🟢 Faol" if ch.is_active else "🔴 O'chirilgan"
            text += f"🔹 <b>{ch.title}</b> (<code>{ch.channel_id}</code>) — {status_icon}\n   🔗 {ch.invite_link}\n\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi kanal qo‘shish", callback_data="adm_add_channel")],
            [InlineKeyboardButton(text="❌ Kanalni o‘chirish", callback_data="adm_del_channel_prompt")]
        ]
    )

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_add_channel")
async def start_add_channel(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminChannelState.waiting_for_channel_id)
    await callback.answer()
    await callback.message.answer(
        "➕ <b>Majburiy kanal qo‘shish:</b>\n\n"
        "1. Avval @tekshiruv2_bot ni kanalingizga qo‘shib, unga <b>Admin</b> huquqini bering;\n"
        "2. So‘ngra kanalingizdan <b>istalgan bitta postni shu yerga FORWARD (uzatish) qiling</b>, yoki kanal <code>@username</code> (yoki <code>-100...</code> ID) sini yuboring:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(AdminChannelState.waiting_for_channel_id)
async def process_channel_id(message: Message, state: FSMContext, bot: Bot):
    chat_id = None
    chat_title = None

    # Forward qilingan xabarni tekshirish
    if message.forward_origin and hasattr(message.forward_origin, "chat"):
        chat_id = message.forward_origin.chat.id
        chat_title = message.forward_origin.chat.title
    elif message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        chat_title = message.forward_from_chat.title
    elif message.text:
        raw_input = message.text.strip()
        chat_id = ChannelService.normalize_channel_id(raw_input)

    if not chat_id:
        await message.answer("❌ Kanal ma'lumoti aniqlanmadi. Iltimos, kanaldan postni forward qiling yoki @username kiriting.")
        return

    # Telegram orqali jonli tekshirish
    try:
        chat = await bot.get_chat(chat_id)
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
        auto_title = chat_title or chat.title
        auto_link = f"https://t.me/{chat.username}" if chat.username else None

        # Agar yopiq kanal bo'lsa, avtomatik taklif linkini olish
        if not auto_link:
            try:
                invite = await bot.create_chat_invite_link(chat.id, name="Test Bot Invite")
                auto_link = invite.invite_link
            except Exception:
                auto_link = None

        final_id = str(chat.id) if not chat.username else f"@{chat.username}"

        await state.update_data(
            channel_id=final_id,
            title=auto_title,
            invite_link=auto_link
        )

        if auto_link:
            await state.set_state(AdminChannelState.waiting_for_invite_link)
            await message.answer(
                f"✅ <b>Kanal topildi va bot adminligi tasdiqlandi!</b>\n\n"
                f"📢 Nomi: <b>{auto_title}</b>\n"
                f"🆔 ID: <code>{chat.id}</code>\n"
                f"🔗 Havola: <code>{auto_link}</code>\n\n"
                f"Ushbu havola ma'qul bo'lsa <b>\"Ha\"</b> yoki <b>\"Tayyor\"</b> deb yozing, yoki boshqa taklif havolasini kiriting:",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
        else:
            await state.set_state(AdminChannelState.waiting_for_invite_link)
            await message.answer(
                f"✅ <b>Kanal topildi: {auto_title}</b> (Yopiq kanal)\n\n"
                "Kanalga a'zo bo'lish havolasini (invite link) kiriting:\n(Masalan: <code>https://t.me/+AbCd...</code>)",
                reply_markup=get_cancel_keyboard(),
                parse_mode="HTML"
            )
    except Exception as e:
        logger.warning(f"Error validating channel {chat_id}: {e}")
        await message.answer(
            f"❌ <b>Kanalga ulanib bo'lmadi!</b>\n\n"
            f"Sabab: Bot kanalda admin emas yoki kanal manzili noto'g'ri (<code>{chat_id}</code>).\n\n"
            f"Iltimos, botni kanalga admin qilib, kanaldan bitta postni bu yerga forward qiling.",
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
    buttons.append([InlineKeyboardButton(text="💥 Barcha kanallarni tozalash", callback_data="adm_del_all_ch")])

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
    await callback.message.answer("✅ Kanal majburiy ro'yxatdan o'chirildi.")


@router.callback_query(F.data == "adm_del_all_ch")
async def delete_all_channels_callback(callback: CallbackQuery, session: AsyncSession):
    channel_repo = ChannelRepository(session)
    channels = await channel_repo.get_all()
    for ch in channels:
        await channel_repo.delete(ch.id)
    await callback.answer("🗑 Barcha kanallar tozalandi!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("✅ Barcha majburiy kanallar tozalandi.")
