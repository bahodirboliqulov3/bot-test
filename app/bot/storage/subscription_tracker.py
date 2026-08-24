"""
Subscription Tracker — In-memory fast lookup.
Foydalanuvchi kanaldan chiqqanda darhol bloklanadi (0ms kechikish).
"""


class SubscriptionTracker:
    """
    Real-time kanalga a'zolik holati tracker.
    - Kanaldan chiqsa: darhol unsubscribed ga qo'shiladi
    - Kanalga kirsa: darhol unsubscribed dan o'chiriladi
    - Birinchi marta kirganda: API orqali bir marta tekshiriladi
    """
    _verified: set = set()       # Tasdiqlangan foydalanuvchilar
    _unsubscribed: set = set()   # Kanaldan chiqqan foydalanuvchilar

    @classmethod
    def mark_subscribed(cls, user_id: int):
        cls._verified.add(user_id)
        cls._unsubscribed.discard(user_id)

    @classmethod
    def mark_unsubscribed(cls, user_id: int):
        cls._unsubscribed.add(user_id)
        cls._verified.discard(user_id)

    @classmethod
    def is_verified(cls, user_id: int) -> bool:
        return user_id in cls._verified

    @classmethod
    def is_blocked(cls, user_id: int) -> bool:
        return user_id in cls._unsubscribed

    @classmethod
    def is_unknown(cls, user_id: int) -> bool:
        """Birinchi marta — hali tekshirilmagan"""
        return user_id not in cls._verified and user_id not in cls._unsubscribed
