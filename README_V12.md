# Fujimoto Signal 아이폰 매매신호등 v12

## 변경 사항

### 1. 1차 RSI 반등 신호의 실제 근거

201종목 일봉 스캐너가 기존 F9-A 엔진에서 계산한 `sig.rsi`를 그대로 사용하여 `rsi_rebound` 필드를 추가합니다.

**기존 매수 규칙과 동일한 세 조건을 표시합니다.**

1. 신호일 **직전 5거래일** 중(신호일 자체 제외) RSI(14) **30 이하**가 한 번 이상 있었는가? 그 가운데 가장 낮은 RSI 값과 날짜는 무엇인가?
2. 신호일 RSI(14)가 **30 이상 48 이하**인가?
3. 신호일 **종가가 전 거래일 종가보다 높은가?**

종목 상세 화면에서 최근 14거래일 RSI선, RSI 30 및 48 기준선, 전일→현재 RSI 상승폭, 과매도 날짜, 세 조건의 충족/미충족을 보여 줍니다. 시세 데이터가 이전 형식이면 근거를 만들지 않고 GitHub Actions 갱신이 필요하다고 표시합니다.

**신호 판정과 차트 분석은 별개입니다.** 이 변경으로 F9-A 백테스트의 1:2:6 매수/매도 규칙은 바뀌지 않습니다. RSI값 하나만으로 실제 주문을 실행하지 않으며, 일봉 종가로 판정된 다음 거래일 시가를 참고합니다.

### 2. 거래량 기반 가격 매물대 라벨 겹침 수정

- 기존 SVG `viewBox=440×240` → `440×370`으로 확대.
- 왼쪽 **종가/매물대 그래프**와 오른쪽 **가격·이름 전용 열**을 분리.
- POC, VAL, VAH, 현재가, 내 평균단가를 **가격이 겹쳐도 서로 다른 정해진 높이**에 표시.
- 같은 가격대끼리 선이 겹쳐도 텍스트가 겹치지 않게 연결선을 사용.
- MACD와 매물대 그래프, 201개 종목명 표기 기능은 v11 내용을 모두 포함.

매물대는 일봉 대표가격(H+L+C)/3에 하루 거래량을 배분해 계산한 120일 추정 가격분포입니다. 실제 체결량·호가 데이터가 아니며 매수가를 보장하지 않습니다.

### 3. 보유정보 보존

`localStorage`의 기존 저장키 `fujimoto-user-holdings-v1` 및 백업·복원 포맷은 변경하지 않았습니다. 아이폰 브라우저에 저장되어 있으며 GitHub에 업로드되지 않습니다.

## 설치

기존 GitHub 저장소의 **최상위 폴더**에서 아래 5개 파일만 교체합니다.

- `index.html`
- `app.js`
- `sw.js`
- `update_screener.py`
- `test_screener_f9a.py`

**기존 `.github/workflows/daily.yml`은 수정하지 않습니다.**

[GitHub Actions 실행](https://github.com/songwonyong8-png/fujimoto-signal/actions/workflows/daily.yml) → `Run workflow` → `main` → `Run workflow`.

성공하면 [아이폰 페이지](https://songwonyong8-png.github.io/fujimoto-signal/)를 새로고침합니다. 최신 일봉의 `rsi_rebound` 데이터가 필요하므로, 파일만 업로드한 상태에서는 RSI 설명이 나타나지 않을 수 있습니다.

## 검증

- 기존 신호 계산 및 신규 RSI 증거 테스트 포함 `python -m unittest test_signal_snapshot test_backtest_f_v9 test_screener_f9a -q`: **56 tests OK**.
- `node --check app.js` 통과.
- 로컬 Chromium에 실제 HTML/JS를 주입해 **320 / 375 / 430px** 3종 화면 검사 통과.
- **5개 가격표 텍스트가 가격상 인접하더라도 공간상 겹치지 않음**을 SVG 텍스트 bounding box로 확인.
- 화면 확인에 사용한 가격/보유정보는 **모의 데이터**이며 실제 투자신호를 의미하지 않습니다.
