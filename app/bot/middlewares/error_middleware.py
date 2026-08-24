from collections.abc import Awaitable, Callable
import logging
import traceback
from typing import Any, Dict
from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject
from app.config import settings

logger = logging.getLogger(__name__)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Unhandled bot exception in {event.__class__.__name__}: {e}\n{tb}")

            # Notify user
            error_message = "❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
            if isinstance(event, Message):
                try:
                    await event.answer(error_message)
                except Exception:
                    pass
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer(error_message, show_alert=True)
                except Exception:
                    pass

            # Notify admin owner automatically
            try:
                bot: Bot = data.get("bot")
                if bot:
                    import html
                    user_info = ""
                    if isinstance(event, Message) and event.from_user:
                        user_info = f"👤 Foydalanuvchi: <code>{event.from_user.id}</code> (@{html.escape(event.from_user.username or '-')})\n"
                        user_info += f"💬 Xabar: <code>{html.escape((event.text or '')[:100])}</code>\n"
                    elif isinstance(event, CallbackQuery) and event.from_user:
                        user_info = f"👤 Foydalanuvchi: <code>{event.from_user.id}</code> (@{html.escape(event.from_user.username or '-')})\n"
                        user_info += f"🔘 Callback: <code>{html.escape(event.data or '')}</code>\n"

                    # Trim traceback to last 800 chars to fit in message
                    tb_trimmed = tb[-800:] if len(tb) > 800 else tb

                    admin_msg = (
                        f"🚨 <b>Bot xatoligi yuz berdi!</b>\n\n"
                        f"{user_info}"
                        f"❗ <b>Xatolik:</b> <code>{html.escape(str(e)[:200])}</code>\n\n"
                        f"📋 <b>Traceback:</b>\n<pre>{html.escape(tb_trimmed)}</pre>"
                    )
                    await bot.send_message(
                        chat_id=settings.OWNER_ID,
                        text=admin_msg,
                        parse_mode="HTML"
                    )
            except Exception as notify_err:
                logger.warning(f"Could not notify admin about error: {notify_err}")

            return None
