"""
Chat Member Update Handler.
Foydalanuvchi kanalga kirsa/chiqsa — real-vaqtda SubscriptionTracker yangilanadi.
Bot kanalda admin bo'lishi SHART.
"""
import logging
from aiogram import Router, Bot, F
from aiogram.types import ChatMemberUpdated
from sqlalchemy.ext.asyncio import AsyncSession
from app.bot.storage.subscription_tracker import SubscriptionTracker
from app.services.channel_service import ChannelService

logger = logging.getLogger(__name__)
router = Router()


@router.chat_member()
async def on_chat_member_updated(update: ChatMemberUpdated, bot: Bot, session: AsyncSession):
    """
    Kanal a'zolik holati o'zgarganda chaqiriladi.
    """
    channel_service = ChannelService(session)
    required_channels = await channel_service.get_required_channels()

    # Faqat majburiy kanallar uchun ishlaydi
    chat_username = f"@{update.chat.username}" if update.chat.username else str(update.chat.id)
    chat_id_str = str(update.chat.id)

    is_required = any(
        ch.channel_id in (chat_username, chat_id_str, str(update.chat.id))
        for ch in required_channels
    )

    if not is_required:
        return

    user_id = update.new_chat_member.user.id
    new_status = update.new_chat_member.status

    if new_status in ("member", "administrator", "creator"):
        # ✅ Kanalga a'zo bo'ldi — blokni olib tashla
        SubscriptionTracker.mark_subscribed(user_id)
        logger.info(f"User {user_id} joined required channel {chat_username} -> unblocked")

    elif new_status in ("left", "kicked", "restricted"):
        # ⛔ Kanaldan chiqdi — darhol blokla
        SubscriptionTracker.mark_unsubscribed(user_id)
        logger.info(f"User {user_id} left required channel {chat_username} -> BLOCKED instantly")
