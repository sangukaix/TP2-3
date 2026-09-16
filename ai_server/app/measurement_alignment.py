"""Repair an explicit share/growth denominator mix-up; preserve original for audit."""
import re


def align_night_growth(text):
    if not ('야간' in text and '증가율' in text and re.search(r'전년[^,;\n]{0,25}야간', text)):
        return text
    wrong = r'분모\s*[:=：]\s*전체\s*방문자\s*수'
    if not re.search(wrong, text):
        return text
    text = re.sub(r'분자\s*[:=：]\s*야간\s*시간대\s*방문자\s*수',
                  '분자: 이번 기간 야간 방문자 수 − 전년 같은 기간 야간 방문자 수', text)
    text = re.sub(wrong, '분모: 전년 같은 기간 야간 방문자 수', text)
    text = text.replace('원자료: 한국관광 데이터랩',
                        '원자료: 동일 시간·관측 범위의 야간 방문 집계(사업 담당자가 확보할 자료)')
    return text + (' 비교 대상은 전년 같은 기간·시간대·관측 범위입니다. 기준값이 0이면 증가율 대신 인원 차이를 표시합니다. '
                   '현재 월별 데이터랩 합계만으로 야간 실적을 계산하지 않습니다.')
