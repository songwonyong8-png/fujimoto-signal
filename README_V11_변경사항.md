# Fujimoto Signal 아이폰 페이지 v11 — 한글 종목명 · 매물대 · MACD 차트

2026-10-26 기준, `songwonyong8-png/fujimoto-signal` v10을 보존하여 업그레이드합니다.

## 이번 개선

- **코스피 100종목 전체**를 종목명으로 보여 줍니다. 기존 44개 + 신규 56개, 종목코드도 상세정보에 유지합니다. 고정 2026-10-25 시총 상위 100종목 스냅샷 기준입니다. 미국 종목명의 기존 표기는 유지합니다.
- **최근 120거래일 일봉 거래량 추정 매물대**를 기존 종가 차트 위에 그립니다.
  - **POC**: 거래량이 가장 많이 몰린 가격 구간의 중앙값(32개 구간 중 최대)
  - **VAL/VAH**: POC에서 인접 거래량을 합쳐서 70%에 이른 연속 가격 범위의 하단/상단
  - 가격대별 가로 막대, 3개 기준가에 해당하는 가로선, 현재가, **사용자가 입력한 평균단가(보유 종목)**를 한 화면에 표시
  - 각 가격의 현재가 대비 이격률, 현재가 아래 가장 가까운 기준가를 설명
- **MACD를 그래프로**: 파란 MACD선, 노란 시그널선, 양·음의 히스토그램. 숫자값을 읽기 어려워도 '상승 모멘텀 우위/하락 모멘텀 우위', '상승 힘 확대/하락 압력 감소'와 골든·데드크로스를 바로 확인 가능합니다.
- **기존 F9-A 1:2:6 RSI→MACD→일목균형표 매수 신호와 A형 단계별 매도 규칙은 변경하지 않았습니다.**
- **보유 수량, 평균단가, 매수·매도 기록, 로컬 저장/백업** 코드는 그대로 유지하며, 기존 localStorage 키 `fujimoto-user-holdings-v1`도 유지합니다.

## 매물대 추정에 대한 중요한 한계

해당 데이터는 호가창이나 거래소의 *실제 가격별 체결 수량*이 아닙니다. 하루의 **대표가격(H+L+C)/3에 그날 총 거래량을 배분**하여 최근 120거래일을 32가격 구간으로 나눈 대용 추정치입니다. 특히 장중 가격 이동이 심한 날에는 오차가 있을 수 있으며 분할·권리락·데이터 제공자의 조정 방식도 영향을 줍니다. POC나 VAL은 지지/매수 적정 가격을 보장하지 않습니다. 다음 거래일 가격 변동 또는 체결 호가는 별도 확인하세요.

## 설치 파일 및 순서

1. GitHub 저장소 **최상위 폴더**의 `index.html`, `app.js`, `sw.js`, `update_screener.py`, `test_screener_f9a.py`를 이 패키지 동명 파일로 **덮어씁니다**.
2. `.github/workflows/daily.yml`은 **변경하지 않습니다**. v10의 기존 작업이 새 `test_screener_f9a.py`, `update_screener.py`를 바로 실행합니다.
3. [Daily workflow](https://github.com/songwonyong8-png/fujimoto-signal/actions/workflows/daily.yml) → **Run workflow** → main → Run workflow.
4. 초록 체크 확인 후 GitHub Pages 배포가 끝나면 [아이폰 사이트](https://songwonyong8-png.github.io/fujimoto-signal/)에서 새로고침합니다. 홈 화면 앱 캐시가 오래됐을 경우 사이트를 Safari로 직접 열거나 앱을 종료 후 재실행합니다.

**주의:** Python 주가 갱신 실행 전에는 한글 종목명은 즉시 표시할 수 있지만, 신규 매물대·MACD 시계열이 들어 있는 `data/screener_f9a.json`이 생성되지 않아 새 그래프가 완성되지 않습니다. 시세 JSON은 직접 덮어쓰지 마세요.

## 로컬 검증

- `python -m unittest test_signal_snapshot.py test_backtest_f_v9.py test_screener_f9a.py -v`: 51개 통과
- `node --check app.js`: 구문 검사 통과
- 차트 생성 함수 DOM 단위 테스트: 매물대 3개·현재가/평균단가·MACD 두 선과 막대·데이터 누락시 보류 확인

기존 백테스트 F3~F9 파일, 200개 종목 CSV, 보유정보 저장구조, GitHub Actions YAML은 수정하지 않습니다.
