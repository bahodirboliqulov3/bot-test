from datetime import datetime, timezone
import html
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.result import Achievement, AttemptStatus, Result, StudentAnswer, TestAttempt
from app.database.models.test import Question, Test
from app.database.repositories.result_repo import AchievementRepository, AttemptRepository, ResultRepository
from app.database.repositories.test_repo import TestRepository

logger = logging.getLogger(__name__)


class ScoringService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.result_repo = ResultRepository(session)
        self.attempt_repo = AttemptRepository(session)
        self.test_repo = TestRepository(session)
        self.achievement_repo = AchievementRepository(session)

    @staticmethod
    def parse_math_val(val: str) -> Optional[float]:
        v = val.strip().replace(" ", "").replace("‘", "'").replace("`", "'").replace("’", "'").replace(",", ".")
        if "/" in v:
            parts = v.split("/")
            if len(parts) == 2:
                try:
                    num = float(parts[0])
                    den = float(parts[1])
                    if den != 0:
                        return num / den
                except ValueError:
                    pass
        try:
            return float(v)
        except ValueError:
            return None

    CYR_TO_LAT_MAP = {
        'А': 'A', 'а': 'A',
        'Б': 'B', 'б': 'B',
        'В': 'B', 'в': 'B',
        'С': 'C', 'с': 'C',
        'Д': 'D', 'д': 'D',
        'Е': 'E', 'е': 'E',
        'Ф': 'F', 'ф': 'F',
        'Г': 'G', 'г': 'G',
        'Х': 'X', 'х': 'X',
        'О': 'O', 'о': 'O',
        'Р': 'P', 'р': 'P',
        'Т': 'T', 'т': 'T',
        'К': 'K', 'к': 'K',
        'М': 'M', 'м': 'M',
        'У': 'Y', 'у': 'Y',
        'Н': 'N', 'н': 'N',
    }

    @classmethod
    def normalize_str(cls, s: str) -> str:
        res = s.strip().upper().replace("‘", "'").replace("`", "'").replace("’", "'").replace("ʻ", "'")
        # Replace cyrillic single letters
        if len(res) == 1 and res in cls.CYR_TO_LAT_MAP:
            return cls.CYR_TO_LAT_MAP[res]
        return res

    @classmethod
    def are_answers_equivalent(cls, user_ans: Optional[str], correct_key: Optional[str]) -> bool:
        if not user_ans or not correct_key:
            return False
        u = cls.normalize_str(str(user_ans))
        options = re.split(r"\||;|\s+or\s+|\s+yoki\s+", str(correct_key), flags=re.IGNORECASE)
        for opt in options:
            opt_clean = cls.normalize_str(opt)
            if u == opt_clean:
                return True
            u_num = cls.parse_math_val(u)
            opt_num = cls.parse_math_val(opt_clean)
            if u_num is not None and opt_num is not None:
                if abs(u_num - opt_num) < 1e-3:
                    return True
        return False

    @classmethod
    def parse_quick_answers(cls, text: str) -> Dict[int, str]:
        cleaned = text.strip()
        if not cleaned:
            return {}

        # 1. Pure continuous letters: "ABCDABCD..." or "ABCDEFGH..."
        if re.fullmatch(r"[A-Za-zА-Яа-я]+", cleaned):
            return {idx: cls.normalize_str(char) for idx, char in enumerate(cleaned, start=1)}

        # 2. Check for explicit question numbers: e.g. "1.A 2.B 3.C 4.0.75" or "1a 2b 3c" or "1:A, 2:B"
        # We ensure the digit is followed by an actual separator and value, and not part of a decimal like 0.75
        numbered_pattern = r"(?:^|[\s,;\n])([1-9]\d{0,2})[\s\-:.\)=]+([^\s,;\n]+)"
        matches = re.findall(numbered_pattern, cleaned)
        if matches and len(matches) >= 2:
            # Check if numbers are sequential or unique question indices
            q_nums = [int(m[0]) for m in matches]
            if len(q_nums) == len(set(q_nums)) and 1 in q_nums:
                answers: Dict[int, str] = {}
                for q_num, ans in matches:
                    val = ans.strip()
                    answers[int(q_num)] = cls.normalize_str(val)
                return answers

        # 3. Comma / Semicolon / Newline delimited list: e.g. "a,b,c,0.75" or "A, B, C, 3/4" or "12, 0.75, A, B"
        delim = None
        if "," in cleaned:
            delim = ","
        elif ";" in cleaned:
            delim = ";"
        elif "\n" in cleaned:
            delim = "\n"

        if delim:
            parts = [p.strip() for p in cleaned.split(delim) if p.strip()]
            if len(parts) >= 1:
                res: Dict[int, str] = {}
                for idx, p in enumerate(parts, start=1):
                    # If part is like '1.A' or '1:A' or '1a'
                    sub_m = re.match(r"^(\d{1,3})[\s\-:.\)=]*(.*)$", p)
                    if sub_m and sub_m.group(2) and not p.replace(',', '.').replace('/', '').replace('-', '').replace('.', '').isdigit():
                        q_n = int(sub_m.group(1))
                        v = sub_m.group(2).strip()
                        res[q_n] = cls.normalize_str(v if v else p)
                    else:
                        res[idx] = cls.normalize_str(p)
                return res

        # 4. Whitespace tokens (e.g. "A B C D E F G 12 3/4 0.75")
        tokens = cleaned.split()
        if len(tokens) > 1:
            return {
                idx: cls.normalize_str(t)
                for idx, t in enumerate(tokens, start=1)
            }

        # Single item
        return {1: cls.normalize_str(cleaned)}

    @staticmethod
    def parse_direct_code_and_answers(text: str) -> Optional[Tuple[str, str]]:
        t = text.strip()
        if t.startswith("/") or t.startswith("http") or t in ["❌ Bekor qilish", "🏠 Bosh menyu"]:
            return None

        # 1. Separators: space, *, #, :, -, /, comma, semicolon
        # e.g. '101*ABCD', '101 # ABCD', '101 ABCD', 'TEST-101: ABCD', 'TEST-A8F2K a,b,c,0.75'
        m = re.match(
            r"^(TEST-[A-Za-z0-9_\-]+|[A-Za-z0-9_\-]{2,24})[\s*#:;,\-_/]+([A-Za-z0-9\s\-:.,/=;|\(\)\[\]\+‘`\'’]+)$",
            t
        )
        if m:
            code = m.group(1).upper().lstrip("#/")
            ans = m.group(2).strip()
            if any(c.isalnum() for c in ans):
                return code, ans

        # 2. Continuous number + letters: e.g. '101ABCDABCD' or '502ABCD'
        m2 = re.match(r"^(\d{2,8})([A-Za-z]{3,})$", t)
        if m2:
            return m2.group(1).upper(), m2.group(2).upper()

        return None

    @staticmethod
    def get_progress_bar(percentage: float, total_blocks: int = 10) -> str:
        filled_blocks = int(round((percentage / 100) * total_blocks))
        filled_blocks = max(0, min(total_blocks, filled_blocks))
        empty_blocks = total_blocks - filled_blocks
        return "🟩" * filled_blocks + "⬜" * empty_blocks

    @staticmethod
    def get_user_rank_title(tests_count: int, avg_percentage: float = 0.0) -> Tuple[str, str, str]:
        if tests_count >= 50 and avg_percentage >= 80:
            return "👑 Professor / Daho", "👑", "Siz eng oliy darajadasiz! 🏆"
        elif tests_count >= 25:
            return "🎓 Ekspert / Akademik", "🎓", f"Keyingi daraja: 👑 Professor ({50 - tests_count} ta test qoldi)"
        elif tests_count >= 10:
            return "⚡ Bilimdon", "⚡", f"Keyingi daraja: 🎓 Ekspert ({25 - tests_count} ta test qoldi)"
        elif tests_count >= 3:
            return "📚 Izlanuvchi", "📚", f"Keyingi daraja: ⚡ Bilimdon ({10 - tests_count} ta test qoldi)"
        else:
            return "🌱 Boshlovchi", "🌱", f"Keyingi daraja: 📚 Izlanuvchi ({3 - tests_count} ta test qoldi)"

    @staticmethod
    def get_grade_info(percentage: float) -> Tuple[str, str, str]:
        if percentage == 100:
            return (
                "⭐️⭐️⭐️⭐️⭐️ 5+ (Mutlaq Daho)",
                "🔥 Qoyilmaqom! Barcha savollarga 100% to‘g‘ri javob berdingiz!",
                "🎉🥳🔥 <b>DAHOSIZ! 100% REKORD NATIJA!</b>\nSiz hech qanday xatosiz mutlaq g‘olib bo‘ldingiz! 🏆"
            )
        elif percentage >= 90:
            return (
                "⭐️⭐️⭐️⭐️⭐️ 5 (A'lo)",
                "🔥 Haqiqiy bilimdon natijasi! Juda yuqori daraja!",
                "🌟 <b>A'LO DARAJA!</b> Zo‘r natija ko‘rsatdingiz! 🚀"
            )
        elif percentage >= 75:
            return (
                "⭐️⭐️⭐️⭐️ 4 (Yaxshi)",
                "👍 Zo‘r natija! Ozgina mashq qilsangiz, 100% ga chiqasiz!",
                "👏 <b>YAXSHI HARAKAT!</b> Bilimingiz mustahkam! 💪"
            )
        elif percentage >= 55:
            return (
                "⭐️⭐️⭐️ 3 (Qoniqarli)",
                "💪 Yomon emas, ammo siz bundan ham yaxshiroq qila olasiz!",
                "💡 <b>HARAKATDA BARAKAT!</b> Xatolar ustida ishlab, qayta topshiring! 📈"
            )
        else:
            return (
                "⭐️⭐️ 2 (Qayta tayyorgarlik)",
                "💪 Tushkunlikka tushmang! Har bir xato — bu yangi bilim demakdir!",
                "🌱 <b>TUSHKUNLIKKA TUSHMANNG!</b> Keyingi safar albatta yuqori ball olasiz! 💪✨"
            )

    @classmethod
    def build_visual_breakdown(cls, correct_keys: Dict[int, str], user_answers: Dict[int, str]) -> str:
        total_q = len(correct_keys)
        if total_q == 0:
            return ""

        rows_count = (total_q + 2) // 3
        text_lines = ["\n📊 <b>Javoblar Tahlili:</b>"]

        for r in range(rows_count):
            col_items = []
            for col in range(3):
                q_num = r + 1 + (col * rows_count)
                if q_num <= total_q:
                    raw_corr = str(correct_keys.get(q_num, "-"))
                    corr_esc = html.escape(raw_corr)
                    user_ans = user_answers.get(q_num)

                    if user_ans is not None and cls.are_answers_equivalent(user_ans, raw_corr):
                        badge = f"<b>{q_num}</b>.🟢 {corr_esc}"
                    elif user_ans is None or user_ans == "—":
                        badge = f"<b>{q_num}</b>.⚪ ({corr_esc})"
                    else:
                        u_esc = html.escape(str(user_ans))
                        badge = f"<b>{q_num}</b>.🔴 {u_esc} <i>({corr_esc})</i>"
                    col_items.append(badge)
            text_lines.append("  |  ".join(col_items))

        return "\n".join(text_lines)

    async def get_test_rank(self, test_id: int, user_result_id: int) -> Tuple[int, int]:
        results = await self.result_repo.get_test_results(test_id)
        total_participants = len(results)
        rank = 1
        for idx, r in enumerate(results, start=1):
            if r.id == user_result_id:
                rank = idx
                break
        return rank, total_participants

    async def generate_channel_leaderboard_text(self, test_id: int, limit: int = 20) -> str:
        test = await self.test_repo.get_by_id(test_id)
        if not test:
            return "Test topilmadi."

        results = await self.result_repo.get_test_results(test_id)
        if not results:
            return f"📢 <b>\"{test.title}\"</b> testi bo‘yicha hali qatnashchilar yo‘q."

        total_participants = len(results)
        avg_score = sum(r.percentage for r in results) / total_participants
        pass_count = sum(1 for r in results if r.percentage >= test.pass_percentage)

        text = (
            f"🏆 <b>\"{test.title}\" TESTI CHEMPIONLARI</b>\n"
            f"🔑 Test kodi: <code>{test.code}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for idx, r in enumerate(results[:limit], start=1):
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            elif idx <= 10:
                medal = f"<b>{idx}.</b> 🎖"
            else:
                medal = f"<b>{idx}.</b>"

            user_name = r.user.full_name if r.user else "O'quvchi"
            region = f"({r.user.school})" if (r.user and r.user.school and r.user.school != "O‘zbekiston") else ""
            minutes, seconds = divmod(r.time_spent_seconds, 60)
            time_str = f"{minutes}m {seconds}s" if r.time_spent_seconds > 0 else ""

            text += f"{medal} <b>{user_name}</b> {region}\n"
            text += f"   └ 📊 <b>{r.percentage}%</b> ({r.correct_count}/{r.correct_count + r.incorrect_count + r.unanswered_count} ta) • {time_str}\n\n"

        text += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Jami ishtirokchilar:</b> {total_participants} nafar\n"
            f"📈 <b>O‘rtacha ko‘rsatkich:</b> {avg_score:.1f}%\n"
            f"🎉 <b>Muvaffaqiyatli topshirganlar:</b> {pass_count} nafar\n"
            f"📅 <b>Sana:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"🤖 <i>Testni bot orqali tekshirish: @tekshiruv2_bot</i>"
        )
        return text

    async def complete_attempt(self, attempt_id: int) -> Result:
        attempt = await self.attempt_repo.get_by_id(attempt_id)
        if not attempt:
            raise ValueError("Attempt topilmadi")

        test = await self.test_repo.get_test_with_questions(attempt.test_id)
        if not test:
            raise ValueError("Test topilmadi")

        now = datetime.now(timezone.utc)
        attempt.finished_at = now
        started = attempt.started_at.replace(tzinfo=timezone.utc) if attempt.started_at.tzinfo is None else attempt.started_at
        time_spent = int((now - started).total_seconds())
        attempt.time_spent_seconds = max(1, time_spent)
        attempt.status = AttemptStatus.COMPLETED

        student_answers = await self.attempt_repo.get_answers_for_attempt(attempt_id)
        answer_map = {ans.question_id: ans for ans in student_answers}

        total_questions = len(test.test_questions) if test.test_questions else test.total_questions
        correct_count = 0
        incorrect_count = 0
        total_score = 0.0
        max_possible_score = sum(tq.question.points for tq in test.test_questions) if test.test_questions else test.max_points

        # Penalty factor: how many points to deduct per wrong answer
        # 0.0 = no penalty, 0.25 = Penalty (-0.25 per wrong), 1.0 = full point deducted
        penalty_factor = getattr(test, 'penalty_per_wrong', 0.0) or 0.0

        for tq in test.test_questions:
            q = tq.question
            if q.id in answer_map:
                ans = answer_map[q.id]
                if ans.is_correct:
                    correct_count += 1
                    total_score += q.points
                else:
                    incorrect_count += 1
                    # Apply penalty deduction
                    total_score -= q.points * penalty_factor

        # Score cannot go below 0
        total_score = max(0.0, total_score)

        unanswered_count = max(0, total_questions - (correct_count + incorrect_count))
        percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0.0
        percentage = round(percentage, 2)

        existing_result = await self.result_repo.get_by_attempt_id(attempt_id)
        if existing_result:
            existing_result.correct_count = correct_count
            existing_result.incorrect_count = incorrect_count
            existing_result.unanswered_count = unanswered_count
            existing_result.total_score = round(total_score, 2)
            existing_result.max_score = round(max_possible_score, 2)
            existing_result.percentage = percentage
            existing_result.time_spent_seconds = attempt.time_spent_seconds
            res = existing_result
        else:
            res = await self.result_repo.create(
                attempt_id=attempt.id,
                user_id=attempt.user_id,
                test_id=test.id,
                correct_count=correct_count,
                incorrect_count=incorrect_count,
                unanswered_count=unanswered_count,
                total_score=round(total_score, 2),
                max_score=round(max_possible_score, 2),
                percentage=percentage,
                time_spent_seconds=attempt.time_spent_seconds
            )

        await self._check_achievements(attempt.user_id, res)
        await self._auto_issue_certificate(attempt.user_id, test, res)
        return res

    async def evaluate_quick_submission(
        self,
        test_id: int,
        user_id: int,
        raw_answers: str
    ) -> Tuple[Result, str]:
        from app.database.models.test import TestStatus

        test = await self.test_repo.get_test_with_questions(test_id)
        if not test:
            raise ValueError("Test topilmadi")

        now_utc = datetime.now(timezone.utc)

        # 1. Start time check
        if test.start_time:
            st = test.start_time.replace(tzinfo=timezone.utc) if test.start_time.tzinfo is None else test.start_time
            if now_utc < st:
                raise ValueError(f"⏳ Ushbu test hali boshlanmadi. Boshlanish vaqti: {test.start_time.strftime('%d.%m.%Y %H:%M')}")

        # 2. Expiration and Completed status check
        if test.status in [TestStatus.FINISHED, TestStatus.ARCHIVED]:
            raise ValueError("⛔ Ushbu test yakunlangan! Belgilangan vaqt tugaganligi sababli yangi javoblar qabul qilinmaydi.")

        if test.end_time:
            et = test.end_time.replace(tzinfo=timezone.utc) if test.end_time.tzinfo is None else test.end_time
            if now_utc > et:
                test.status = TestStatus.FINISHED
                await self.session.commit()
                raise ValueError("⛔ Ushbu testning belgilangan vaqti tugagan! Test yakunlandi va yangi javoblar qabul qilinmaydi.")

        # 3. Check Attempts Limit (Feature 5)
        if test.max_attempts and test.max_attempts > 0:
            user_results = await self.result_repo.get_user_results(user_id)
            user_test_results = [r for r in user_results if r.test_id == test.id]
            if len(user_test_results) >= test.max_attempts:
                prev = user_test_results[0]
                raise ValueError(
                    f"⚠️ Siz ushbu testni allaqachon topshirgansiz!\n"
                    f"🔒 Qoidalarga ko‘ra, ushbu testda faqat {test.max_attempts} marta qatnashish mumkin.\n\n"
                    f"📊 Sizning rasmiy natijangiz: {prev.percentage}% ({prev.correct_count} ta to‘g‘ri)."
                )

        parsed = self.parse_quick_answers(raw_answers)
        if not parsed:
            raise ValueError("Javoblar aniqlanmadi. Format: `1-A 2-B 3-C` yoki `ABCDACBD...`")

        if test.answer_key:
            correct_keys = self.parse_quick_answers(test.answer_key)
            total_questions = len(correct_keys)

            # Javoblar soni kam yoki ko'p bo'lsa qabul qilmaslik
            user_answers_count = len(parsed)
            if user_answers_count < total_questions:
                raise ValueError(
                    f"Siz {user_answers_count} ta javob yubordingiz, lekin ushbu testda {total_questions} ta savol bor!\n\n"
                    f"Iltimos, barcha {total_questions} ta savolga to‘liq javob yuboring."
                )
            elif user_answers_count > total_questions:
                raise ValueError(
                    f"Siz {user_answers_count} ta javob yubordingiz, lekin ushbu testda faqat {total_questions} ta savol bor!\n\n"
                    f"Iltimos, faqat {total_questions} ta savol javobini yuboring."
                )

            correct_count = 0
            incorrect_count = 0

            for idx, correct_opt in correct_keys.items():
                user_opt = parsed.get(idx)
                if user_opt:
                    if self.are_answers_equivalent(user_opt, correct_opt):
                        correct_count += 1
                    else:
                        incorrect_count += 1

            unanswered = max(0, total_questions - (correct_count + incorrect_count))
            point_per_q = test.max_points / total_questions if total_questions > 0 else 1.0
            penalty_factor = getattr(test, 'penalty_per_wrong', 0.0) or 0.0
            raw_score = correct_count * point_per_q - incorrect_count * point_per_q * penalty_factor
            total_score = round(max(0.0, raw_score), 2)
            percentage = round((total_score / test.max_points * 100), 2) if test.max_points > 0 else 0.0

            attempt = await self.attempt_repo.create(
                test_id=test.id,
                user_id=user_id,
                attempt_number=1,
                status=AttemptStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                time_spent_seconds=60,
                question_order=list(correct_keys.keys()),
                option_order={
                    "user_answers": {str(k): v for k, v in parsed.items()},
                    "correct_keys": {str(k): v for k, v in correct_keys.items()}
                }
            )

            res = await self.result_repo.create(
                attempt_id=attempt.id,
                user_id=user_id,
                test_id=test.id,
                correct_count=correct_count,
                incorrect_count=incorrect_count,
                unanswered_count=unanswered,
                total_score=total_score,
                max_score=test.max_points,
                percentage=percentage,
                time_spent_seconds=attempt.time_spent_seconds
            )

            await self._check_achievements(user_id, res)
            await self._auto_issue_certificate(user_id, test, res)

            visual_grid = self.build_visual_breakdown(correct_keys, parsed)
            return res, visual_grid

        else:
            correct_keys = {}
            for idx, tq in enumerate(test.test_questions, start=1):
                correct_keys[idx] = tq.question.correct_option.upper()
            total_questions = len(correct_keys)

            user_answers_count = len(parsed)
            if user_answers_count < total_questions:
                raise ValueError(
                    f"Siz {user_answers_count} ta javob yubordingiz, lekin ushbu testda {total_questions} ta savol bor!\n\n"
                    f"Iltimos, barcha {total_questions} ta savolga to‘liq javob yuboring."
                )
            elif user_answers_count > total_questions:
                raise ValueError(
                    f"Siz {user_answers_count} ta javob yubordingiz, lekin ushbu testda faqat {total_questions} ta savol bor!\n\n"
                    f"Iltimos, faqat {total_questions} ta savol javobini yuboring."
                )

            attempt = await self.attempt_repo.create(
                test_id=test.id,
                user_id=user_id,
                attempt_number=1,
                status=AttemptStatus.IN_PROGRESS,
                started_at=datetime.now(timezone.utc),
                question_order=[tq.question.id for tq in test.test_questions],
                option_order={
                    "user_answers": {str(k): v for k, v in parsed.items()},
                    "correct_keys": {str(k): v for k, v in correct_keys.items()}
                }
            )

            for idx, tq in enumerate(test.test_questions, start=1):
                q = tq.question
                user_ans = parsed.get(idx)
                if user_ans:
                    is_correct = (user_ans.upper() == q.correct_option.upper())
                    pts = q.points if is_correct else 0.0
                    await self.attempt_repo.save_answer(
                        attempt_id=attempt.id,
                        question_id=q.id,
                        selected_option=user_ans.upper(),
                        is_correct=is_correct,
                        points_earned=pts
                    )

            res = await self.complete_attempt(attempt.id)
            visual_grid = self.build_visual_breakdown(correct_keys, parsed)
            return res, visual_grid

    async def _auto_issue_certificate(self, user_id: int, test: Test, result: Result) -> None:
        pass

    async def _check_achievements(self, user_id: int, result: Result) -> None:
        if not await self.achievement_repo.has_badge(user_id, "first_test"):
            await self.achievement_repo.create(
                user_id=user_id,
                badge_type="first_test",
                title="🚀 Birinchi qadam",
                description="Platformada birinchi testni muvaffaqiyatli topshirdingiz!"
            )

        if result.percentage >= 100.0 and not await self.achievement_repo.has_badge(user_id, "perfect_score"):
            await self.achievement_repo.create(
                user_id=user_id,
                badge_type="perfect_score",
                title="🎯 100% Natija",
                description="Testdan maksimal 100% natija qayd etdingiz!"
            )

    async def get_test_error_analytics(self, test_id: int) -> dict:
        """
        Analyzes mistake distribution per question for a given test.
        """
        test = await self.test_repo.get_test_with_questions(test_id)
        if not test:
            return {}

        results = await self.result_repo.get_test_results(test_id)
        total_participants = len(results)
        if total_participants == 0:
            return {
                "total_participants": 0,
                "avg_percentage": 0.0,
                "question_stats": [],
                "hardest_questions": [],
                "easiest_questions": []
            }

        avg_percentage = sum(r.percentage for r in results) / total_participants

        # Load correct answer keys
        correct_keys = self.parse_quick_answers(test.answer_key or "")
        total_questions = len(correct_keys)
        if total_questions == 0:
            return {
                "total_participants": total_participants,
                "avg_percentage": avg_percentage,
                "question_stats": [],
                "hardest_questions": [],
                "easiest_questions": []
            }

        # Count errors per question
        stats = {q_idx: {"correct": 0, "incorrect": 0, "correct_ans": correct_keys[q_idx]} for q_idx in range(1, total_questions + 1)}

        for r in results:
            user_ans_dict = {}
            if r.attempt and r.attempt.option_order and isinstance(r.attempt.option_order, dict):
                raw_u = r.attempt.option_order.get("user_answers", {})
                for k, v in raw_u.items():
                    try:
                        user_ans_dict[int(k)] = str(v)
                    except (ValueError, TypeError):
                        pass

            for q_idx in range(1, total_questions + 1):
                user_ans = user_ans_dict.get(q_idx)
                corr_ans = correct_keys.get(q_idx)
                if user_ans and corr_ans and self.are_answers_equivalent(user_ans, corr_ans):
                    stats[q_idx]["correct"] += 1
                else:
                    stats[q_idx]["incorrect"] += 1

        question_stats = []
        for q_idx, data in stats.items():
            err_count = data["incorrect"]
            err_pct = (err_count / total_participants * 100) if total_participants > 0 else 0.0
            corr_count = data["correct"]
            corr_pct = (corr_count / total_participants * 100) if total_participants > 0 else 0.0
            question_stats.append({
                "question_num": q_idx,
                "correct_key": data["correct_ans"],
                "incorrect_count": err_count,
                "incorrect_pct": round(err_pct, 1),
                "correct_count": corr_count,
                "correct_pct": round(corr_pct, 1)
            })

        hardest = sorted(question_stats, key=lambda x: x["incorrect_count"], reverse=True)
        easiest = sorted(question_stats, key=lambda x: x["correct_count"], reverse=True)

        return {
            "total_participants": total_participants,
            "avg_percentage": round(avg_percentage, 1),
            "question_stats": question_stats,
            "hardest_questions": hardest[:5],
            "easiest_questions": easiest[:5]
        }

