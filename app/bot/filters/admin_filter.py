from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.repositories.user_repo import AdminRepository
from app.database.session import async_session_factory

# Super Admins / Owners who always pass admin checks without DB latency
SUPER_ADMIN_IDS = {1112241172, 8420258761, settings.OWNER_ID}


class IsAdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, session: AsyncSession = None, **kwargs) -> bool:
        user_id = event.from_user.id if event.from_user else 0
        if user_id in SUPER_ADMIN_IDS:
            return True

        try:
            if session:
                admin_repo = AdminRepository(session)
                return await admin_repo.is_admin(user_id, settings.OWNER_ID)
            else:
                async with async_session_factory() as s:
                    admin_repo = AdminRepository(s)
                    return await admin_repo.is_admin(user_id, settings.OWNER_ID)
        except Exception:
            return False
