import logging
from collections.abc import Awaitable, Callable
from typing import Any, Dict
from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.auth_service import AuthService
from app.services.channel_service import ChannelService

logger = logging.getLogger(__name__)


class RequiredChannelMiddleware(BaseMiddleware):
    """
    Har bir xabar, reply tugma va inline tugma bosilganda obunani to‘g‘ridan-to‘g‘ri tekshiradi.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Update, Message yoki CallbackQuery ni to'g'ri aniqlash
        real_event = event
        if isinstance(event, Update):
            real_event = event.message or event.callback_query or event.chat_member or event.my_chat_member
            if not real_event:
                return await handler(event, data)

        # Chat member o'zgarishlarini o'tkazib yuborish
        if not isinstance(real_event, (Message, CallbackQuery)):
            return await handler(event, data)

        user = data.get("event_from_user")
        bot: Bot = data.get("bot")
        session: AsyncSession = data.get("session")

        if not user or not bot or not session:
            return await handler(event, data)

        # /start buyrug'i va tekshirish tugmasiga ruxsat berish
        if isinstance(real_event, Message) and real_event.text and real_event.text.startswith("/start"):
            return await handler(event, data)
        if isinstance(real_event, CallbackQuery) and real_event.data in ["check_channel_subs", "cancel"]:
            return await handler(event, data)

        # Majburiy kanallarga a'zolikni barcha foydalanuvchilar (shu jumladan adminlar) uchun har safar jonli tekshirish
        channel_service = ChannelService(session)
        is_subbed, unsubs = await channel_service.check_user_subscriptions(bot, user.id)

        if not is_subbed and unsubs:
            buttons = []
            for ch in unsubs:
                buttons.append([InlineKeyboardButton(text=f"📢 {ch.title}", url=ch.invite_link)])
            buttons.append([
                InlineKeyboardButton(text="✅ A'zo bo'ldim, tekshirish", callback_data="check_channel_subs")
            ])
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)

            msg_text = (
                "⛔ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling!</b>\n\n"
                "A'zo bo'lgach, <b>✅ A'zo bo'ldim, tekshirish</b> tugmasini bosing."
            )

            if isinstance(real_event, Message):
                await real_event.answer(msg_text, reply_markup=kb, parse_mode="HTML")
            elif isinstance(real_event, CallbackQuery):
                await real_event.answer("⛔ Avval kanallarga a'zo bo'ling!", show_alert=True)
                try:
                    await real_event.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
            return

        return await handler(event, data)
