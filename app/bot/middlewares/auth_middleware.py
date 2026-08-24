from collections.abc import Awaitable, Callable
from typing import Any, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, TelegramObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database.models.user import User
from app.database.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService


class AuthMiddleware(BaseMiddleware):
    def __init__(self, cache_ttl: int = 120):
        self.cache_ttl = cache_ttl

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        session: AsyncSession = data.get("session")
        user = data.get("event_from_user")
        state: FSMContext = data.get("state")

        if user and session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_telegram_id(user.id)
            if not db_user:
                auth_service = AuthService(session)
                db_user = await auth_service.get_or_create_user(
                    telegram_id=user.id,
                    first_name=user.first_name or "Foydalanuvchi",
                    last_name=user.last_name or "",
                    username=user.username,
                    phone_number="",
                    school="",
                    grade=""
                )
                await session.commit()

            if db_user:
                if db_user.is_blocked:
                    if isinstance(event, Message):
                        await event.answer("🚫 Sizning akkauntingiz admin tomonidan bloklangan.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Sizning akkauntingiz bloklangan.", show_alert=True)
                    return
                data["current_user"] = db_user

                # Check if old wiped user clicked an old reply button without /start
                is_admin = (user.id == settings.OWNER_ID)
                if not is_admin:
                    auth_service = AuthService(session)
                    is_admin = await auth_service.is_admin(user.id)

                if not is_admin and (not db_user.phone_number or not db_user.school):
                    current_state = await state.get_state() if state else None
                    is_in_reg = current_state and current_state.startswith("RegistrationState")
                    if isinstance(event, Message) and event.text:
                        is_start = event.text.startswith("/start")
                        if not is_start and not is_in_reg:
                            await event.answer(
                                "⚠️ <b>Platforma yangilandi!</b>\n\n"
                                "Botdan to'liq foydalanish uchun iltimos, <b>/start</b> buyrug'ini bosing va qaytadan ro'yxatdan o'ting.",
                                reply_markup=ReplyKeyboardRemove(),
                                parse_mode="HTML"
                            )
                            return

        return await handler(event, data)
