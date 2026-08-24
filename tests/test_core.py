from app.services.scoring_service import ScoringService

def test_quick_answers_parsing_letters():
    parsed = ScoringService.parse_quick_answers('ABCDABCD')
    assert parsed == {
        1: 'A', 2: 'B', 3: 'C', 4: 'D',
        5: 'A', 6: 'B', 7: 'C', 8: 'D'
    }

def test_quick_answers_parsing_numbered():
    parsed = ScoringService.parse_quick_answers('1.A 2.B 3.C 4.D 5.12 6.3/4')
    assert parsed[1] == 'A'
    assert parsed[2] == 'B'
    assert parsed[5] == '12'
    assert parsed[6] == '3/4'

def test_quick_answers_parsing_sat_comma_and_mixed():
    parsed1 = ScoringService.parse_quick_answers('a,b,c,0.75')
    assert parsed1 == {1: 'A', 2: 'B', 3: 'C', 4: '0.75'}

    parsed2 = ScoringService.parse_quick_answers('A, B, 3/4, 0.75, 12')
    assert parsed2 == {1: 'A', 2: 'B', 3: '3/4', 4: '0.75', 5: '12'}

    parsed3 = ScoringService.parse_quick_answers('1a, 2b, 3 3/4')
    assert parsed3 == {1: 'A', 2: 'B', 3: '3/4'}

def test_math_equivalence():
    assert ScoringService.are_answers_equivalent('3/4', '0.75')
    assert ScoringService.are_answers_equivalent('0.5', '1/2')
    assert ScoringService.are_answers_equivalent('-4.5', '-9/2')
    assert ScoringService.are_answers_equivalent('A', 'a')
    assert ScoringService.are_answers_equivalent('С', 'C')

def test_direct_code_and_answers_parsing():
    assert ScoringService.parse_direct_code_and_answers('101 ABCD') == ('101', 'ABCD')
    assert ScoringService.parse_direct_code_and_answers('101*ABCD') == ('101', 'ABCD')
    assert ScoringService.parse_direct_code_and_answers('101#ABCD') == ('101', 'ABCD')
    assert ScoringService.parse_direct_code_and_answers('101-ABCD') == ('101', 'ABCD')
    assert ScoringService.parse_direct_code_and_answers('101: ABCD') == ('101', 'ABCD')
    assert ScoringService.parse_direct_code_and_answers('101ABCDABCD') == ('101', 'ABCDABCD')

def test_visual_breakdown_rendering():
    correct = {1: 'A', 2: 'B', 3: 'C'}
    user_ans = {1: 'A', 2: 'D', 3: 'C'}
    grid = ScoringService.build_visual_breakdown(correct, user_ans)
    assert '1.🟢 A' in grid
    assert '2.🔴 D' in grid
    assert '3.🟢 C' in grid

def test_user_tenure_display():
    from app.bot.handlers.student.main_menu import get_user_tenure_display
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    assert 'kunlik' in get_user_tenure_display(now - timedelta(days=5))
    assert 'oylik' in get_user_tenure_display(now - timedelta(days=60))

if __name__ == '__main__':
    test_quick_answers_parsing_letters()
    test_quick_answers_parsing_numbered()
    test_math_equivalence()
    test_direct_code_and_answers_parsing()
    test_visual_breakdown_rendering()
    test_user_tenure_display()
    print('ALL_UNIT_TESTS_PASSED_100_PERCENT')
