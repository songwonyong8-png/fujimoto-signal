# 아이폰 매매신호등 F9-A 반영 안내

기존 GitHub 저장소에 덮어쓸 파일은 **총 9개**입니다.

### 저장소 최상위(root): 8개
- `index.html` — 새 아이폰 화면
- `app.js` — F9-A 가상 전략 현황 표시
- `sw.js` — 홈 화면 캐시 버전 갱신
- `manifest.webmanifest` — 앱 이름
- `update_data.py` — 매일 시세 갱신 + 백테스트 연동
- `signal_snapshot.py` — F9-A 주문 후보·단계별 가상 보유 현황
- `test_signal_snapshot.py` — 신규 자동 검증
- `README.md` — 기능 및 유의사항

### `.github/workflows/`: 1개
- `.github/workflows/daily.yml` — 자동 실행 설정 (기존 파일 덮어쓰기)

### 설치 검증
1. root 파일 8개를 업로드 후 Commit.
2. `.github/workflows/daily.yml` 파일을 기존 GitHub 폴더에 등록/덮어쓰기 후 Commit.
3. GitHub Actions의 `Daily OHLCV and F9-A iPhone Signals`에서 `Run workflow` 실행.
4. 완료 후 `data/NVDA.json` 등 4개 JSON에 `"strategy": {"version":"F9-A",...}`가 생겼는지 확인.
5. iPhone 홈 화면 앱/Safari에서 새로고침. 점수제 대신 `1차/2차/3차 보유와 다음 거래일 주문 후보`가 보여야 합니다.

### F9 연구 결과를 어떻게 반영했나요?
- 매수: RSI 반등 1/9 → MACD 골든크로스 2/9 → 엄격 일목균형표 돌파 6/9.
- 매도: 1차 RSI 30 이하, 2차 MACD 데드크로스, 3차 F9-A 구름대 하단 종가 이탈.
- 매도 B/C 모델은 분석 참고만. RSI70 익절과 양봉 강제 확인은 제외.
- 오늘 종가 신호는 **다음 거래일 시가의 주문 후보**이며 당일 주문 체결 아님.
- 화면의 가상 보유는 개인 증권사와 연결되지 않습니다.
- 200종목은 **F9 연구 대상**이고, 모바일의 기본 일일 갱신 감시 대상은 기존 4종목(DRAM/NVDA/MU/AMD)입니다.
