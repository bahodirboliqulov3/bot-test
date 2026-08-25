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
        if not raw_input:
            return ""
        raw = str(raw_input).strip().strip("\"'<>[]()")
        # If public t.me link: https://t.me/channel_name or t.me/channel_name
        if "t.me/" in raw:
            parts = raw.split("t.me/")[-1].split("?")[0].replace("/", "").strip()
            if not parts.startswith("+") and not parts.startswith("joinchat") and " " not in parts and parts:
                return f"@{parts}"

        # If numeric ID (e.g. -1001234567890 or 1234567890)
        if (raw.startswith("-") and raw[1:].isdigit()) or raw.isdigit():
            return int(raw)
        
        # If username without @ (and no spaces)
        if not raw.startswith("@") and " " not in raw and not raw.startswith("http") and raw:
            return f"@{raw}"
        return raw

    def extract_chat_id(self, channel: RequiredChannel):
        """
        Kanal ID yoki havola (invite_link) dan Telegram chat identifikatorini aniqlaydi.
        """
        raw_id = self.normalize_channel_id(channel.channel_id)
        if isinstance(raw_id, int) or (isinstance(raw_id, str) and raw_id.startswith("@")):
            return raw_id

        # Agar channel_id noto'g'ri bo'lsa, invite_link dan ajratib olish
        raw_link = self.normalize_channel_id(channel.invite_link)
        if isinstance(raw_link, int) or (isinstance(raw_link, str) and raw_link.startswith("@")):
            return raw_link

        return raw_id

    async def _check_single_channel(self, bot: Bot, telegram_id: int, channel: RequiredChannel) -> Tuple[bool, RequiredChannel]:
        chat_id = self.extract_chat_id(channel)
        
        # 1. Asosiy chat_id orqali tekshirish
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=telegram_id)
            if member.status in ["member", "administrator", "creator"]:
                return True, channel
            elif member.status == "restricted" and getattr(member, "is_member", True):
                return True, channel
            return False, channel
        except Exception as e1:
            logger.warning(f"Kanal {channel.title} (chat_id: {chat_id}) a'zolik tekshiruvida xatolik: {e1}")

        # 2. Agar invite_link boshqacha bo'lsa, u orqali ham sinab ko'rish
        link_id = self.normalize_channel_id(channel.invite_link)
        if link_id and link_id != chat_id and (isinstance(link_id, int) or str(link_id).startswith("@")):
            try:
                member = await bot.get_chat_member(chat_id=link_id, user_id=telegram_id)
                if member.status in ["member", "administrator", "creator"]:
                    return True, channel
                elif member.status == "restricted" and getattr(member, "is_member", True):
                    return True, channel
                return False, channel
            except Exception as e2:
                logger.warning(f"Kanal {channel.title} (link_id: {link_id}) tekshiruvida xatolik: {e2}")

        # 3. Agar bot umuman kanalga ulanolmasa (bot admin emas yoki kanal o'chgan bo'lsa),
        # butun bot o'quvchilar uchun qotib qolmasligi uchun ruxsat beriladi:
        logger.error(f"⚠️ '{channel.title}' kanaliga bot ulanolmadi (bot admin emas yoki ID xato). O'quvchilar qotmasligi uchun o'tkazib yuborildi.")
        return True, channel

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
