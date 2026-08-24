import asyncio
import logging
from typing import List, Tuple
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.system import RequiredChannel
from app.database.repositories.channel_repo import ChannelRepository

logger = logging.getLogger(__name__)


class ChannelService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.channel_repo = ChannelRepository(session)

    async def get_required_channels(self) -> List[RequiredChannel]:
        return await self.channel_repo.get_active_channels()

    async def _check_single_channel(self, bot: Bot, telegram_id: int, channel: RequiredChannel) -> Tuple[bool, RequiredChannel]:
        try:
            chat_id = channel.channel_id.strip()
            if not (chat_id.startswith("@") or chat_id.startswith("-100")):
                if chat_id.isdigit() or (chat_id.startswith("-") and chat_id[1:].isdigit()):
                    chat_id = int(chat_id)
            member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
            # Valid statuses for being subscribed: member, administrator, creator
            if member.status in ["left", "kicked"]:
                return False, channel
            elif member.status not in ["member", "administrator", "creator", "restricted"]:
                return False, channel
            elif member.status == "restricted" and not getattr(member, "is_member", True):
                return False, channel
            return True, channel
        except Exception as e:
            logger.warning(f"Error checking membership for user {telegram_id} in channel {channel.channel_id}: {e}")
            return False, channel

    async def check_user_subscriptions(self, bot: Bot, telegram_id: int) -> Tuple[bool, List[RequiredChannel]]:
        """
        Returns (is_all_subscribed, list_of_unsubscribed_channels)
        """
        channels = await self.get_required_channels()
        if not channels:
            return True, []

        tasks = [self._check_single_channel(bot, telegram_id, ch) for ch in channels]
        results = await asyncio.gather(*tasks)

        unsubscribed = [ch for is_sub, ch in results if not is_sub]
        return len(unsubscribed) == 0, unsubscribed
