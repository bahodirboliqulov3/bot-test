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

    @staticmethod
    def normalize_channel_id(raw_input: str):
        raw = str(raw_input).strip()
        # If public t.me link: https://t.me/channel_name or t.me/channel_name
        if "t.me/" in raw:
            parts = raw.split("t.me/")[-1].replace("/", "").strip()
            if not parts.startswith("+") and not parts.startswith("joinchat"):
                raw = f"@{parts}"

        # If numeric ID (e.g. -1001234567890 or 1234567890)
        if (raw.startswith("-") and raw[1:].isdigit()) or raw.isdigit():
            return int(raw)
        elif not raw.startswith("@"):
            return f"@{raw}"
        return raw

    async def _check_single_channel(self, bot: Bot, telegram_id: int, channel: RequiredChannel) -> Tuple[bool, RequiredChannel]:
        try:
            chat_id = self.normalize_channel_id(channel.channel_id)
            member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
            # Valid statuses for being subscribed: member, administrator, creator
            if member.status in ["member", "administrator", "creator"]:
                return True, channel
            elif member.status == "restricted" and getattr(member, "is_member", True):
                return True, channel
            return False, channel
        except Exception as e:
            logger.warning(f"Error checking membership for user {telegram_id} in channel {channel.channel_id} (normalized: {self.normalize_channel_id(channel.channel_id)}): {e}")
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
