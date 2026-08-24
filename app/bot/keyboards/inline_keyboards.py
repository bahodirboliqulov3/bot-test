from typing import Dict, List, Optional
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.database.models.test import Test, TestStatus


def get_channel_subscription_keyboard(channels: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"📢 {ch.title}", url=ch.invite_link)])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_channel_subs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_test_item_keyboard(test_id: int, is_saved: bool = False, is_author: bool = False) -> InlineKeyboardMarkup:
    save_text = "🔖 Saqlanganlardan o'chirish" if is_saved else "🔖 Testni saqlash"
    buttons = [
        [InlineKeyboardButton(text="▶️ Testni boshlash", callback_data=f"start_test:{test_id}")],
        [InlineKeyboardButton(text=save_text, callback_data=f"toggle_save:{test_id}")],
    ]
    if is_author:
        buttons.append([
            InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_test:{test_id}"),
            InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"delete_test:{test_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_quiz_question_keyboard(
    attempt_id: int,
    current_index: int,
    total_questions: int,
    selected_option: Optional[str] = None,
    allow_backtracking: bool = True,
    available_options: Optional[List[str]] = None
) -> InlineKeyboardMarkup:
    options = available_options or ["A", "B", "C", "D", "E"]
    opt_buttons = []
    for opt in options:
        prefix = "🔘"
        if selected_option == opt:
            prefix = "🟢"
        opt_buttons.append(
            InlineKeyboardButton(
                text=f"{prefix} {opt}",
                callback_data=f"ans:{attempt_id}:{current_index}:{opt}"
            )
        )

    # Chunk option buttons into rows of up to 4
    opt_rows = [opt_buttons[i:i + 4] for i in range(0, len(opt_buttons), 4)]

    nav_row = []
    if allow_backtracking and current_index > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"nav:{attempt_id}:{current_index - 1}"))
    
    nav_row.append(InlineKeyboardButton(text="📋 Savollar", callback_data=f"overview:{attempt_id}"))

    if current_index < total_questions:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"nav:{attempt_id}:{current_index + 1}"))

    bottom_row = [
        InlineKeyboardButton(text="🏁 Testni yakunlash", callback_data=f"finish_confirm:{attempt_id}")
    ]

    keyboard = [
        *opt_rows,
        nav_row,
        bottom_row
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_quiz_overview_keyboard(attempt_id: int, total_questions: int, answered_indices: set[int]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(1, total_questions + 1):
        status_icon = "✅" if i in answered_indices else "▫️"
        row.append(InlineKeyboardButton(text=f"{status_icon} {i}", callback_data=f"nav:{attempt_id}:{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(text="🏁 Testni yakunlash", callback_data=f"finish_confirm:{attempt_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_quiz_finish_confirm_keyboard(attempt_id: int, current_index: int = 1) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yakunlash", callback_data=f"finish_test:{attempt_id}"),
                InlineKeyboardButton(text="↩️ Davom etish", callback_data=f"nav:{attempt_id}:{current_index}")
            ]
        ]
    )


def get_result_actions_keyboard(result_id: int, test_id: int, share_text: str = "") -> InlineKeyboardMarkup:
    import urllib.parse
    if not share_text:
        share_url = f"https://t.me/share/url?url=https://t.me/tekshiruv2_bot&text={urllib.parse.quote('Telegram Test Platformasida o‘z bilimingizni sinab ko‘ring! 🎯')}"
    else:
        share_url = f"https://t.me/share/url?url=https://t.me/tekshiruv2_bot&text={urllib.parse.quote(share_text)}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 Xatolarni ko‘rish", callback_data=f"view_mistakes:{result_id}"),
                InlineKeyboardButton(text="📄 PDF natija", callback_data=f"pdf_result:{result_id}")
            ],
            [
                InlineKeyboardButton(text="📤 Ulashish", url=share_url)
            ]
        ]
    )


def get_confirmation_keyboard(confirm_action: str, cancel_action: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha / Tasdiqlash", callback_data=confirm_action),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=cancel_action)
            ]
        ]
    )


def get_pagination_keyboard(prefix: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"{prefix}:page:{current_page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"{prefix}:page:{current_page + 1}"))
    buttons.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_matrix_solver_keyboard(
    test_id: int,
    total_questions: int,
    current_q: int,
    user_answers: Dict[int, str],
    page: int = 1,
    page_size: int = 20
) -> InlineKeyboardMarkup:
    start_q = (page - 1) * page_size + 1
    end_q = min(total_questions, page * page_size)
    total_pages = (total_questions + page_size - 1) // page_size

    grid_rows = []
    current_row = []
    for q in range(start_q, end_q + 1):
        ans = user_answers.get(q)
        if q == current_q:
            disp = f":{ans}" if ans else ""
            label = f"▶️ {q}{disp}"
        else:
            if ans:
                disp_ans = ans if len(ans) <= 4 else ans[:3] + "…"
                label = f"{q}: {disp_ans}"
            else:
                label = f"{q}: ⚪"
        current_row.append(InlineKeyboardButton(text=label, callback_data=f"mat_sel:{test_id}:{q}:{page}"))
        if len(current_row) == 5:
            grid_rows.append(current_row)
            current_row = []
    if current_row:
        grid_rows.append(current_row)

    # Multi-page nav
    if total_pages > 1:
        pag_row = []
        if page > 1:
            pag_row.append(InlineKeyboardButton(text="◀️ 1-20", callback_data=f"mat_pag:{test_id}:{current_q}:{page - 1}"))
        pag_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            pag_row.append(InlineKeyboardButton(text="21-40 ▶️", callback_data=f"mat_pag:{test_id}:{current_q}:{page + 1}"))
        grid_rows.append(pag_row)

    # Option buttons for current question
    cur_ans = user_answers.get(current_q, "")
    opt_row = []
    for opt in ["A", "B", "C", "D", "E"]:
        prefix = "🟢" if cur_ans.upper() == opt else ""
        text = f"{prefix} {opt}".strip()
        opt_row.append(InlineKeyboardButton(text=text, callback_data=f"mat_ans:{test_id}:{current_q}:{opt}:{page}"))
    grid_rows.append(opt_row)

    # Action row (Type custom number / fraction, Clear)
    action_row = [
        InlineKeyboardButton(text="⌨️ Kasr / Raqam yozish", callback_data=f"mat_type:{test_id}:{current_q}:{page}"),
        InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"mat_clear:{test_id}:{current_q}:{page}")
    ]
    grid_rows.append(action_row)

    # Navigation (Prev / Next question)
    nav_row = []
    if current_q > 1:
        prev_page = (current_q - 2) // page_size + 1
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"mat_sel:{test_id}:{current_q - 1}:{prev_page}"))
    nav_row.append(InlineKeyboardButton(text=f"🎯 {current_q}-savol", callback_data="noop"))
    if current_q < total_questions:
        next_page = current_q // page_size + 1
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"mat_sel:{test_id}:{current_q + 1}:{next_page}"))
    grid_rows.append(nav_row)

    # Finish button
    answered_count = len(user_answers)
    grid_rows.append([
        InlineKeyboardButton(
            text=f"🏁 Testni yakunlash ({answered_count}/{total_questions})",
            callback_data=f"mat_fin_prompt:{test_id}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=grid_rows)


def get_matrix_finish_confirm_keyboard(test_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, yakunlansin!", callback_data=f"mat_fin_confirm:{test_id}"),
                InlineKeyboardButton(text="↩️ Davom etish", callback_data=f"mat_resume:{test_id}")
            ]
        ]
    )
