# F안 v6 — 블로그를 참고한 매수 신호와 단계별 매도 (연구용)

원문: https://myrichlife.tistory.com/643
저장소: https://github.com/songwonyong8-png/fujimoto-signal

## 시작하기

1. ZIP 압축을 해제합니다. **ZIP 파일 자체를 GitHub에 올리지 마세요.**
2. `backtest_f_v6.py`, `test_backtest_f_v6.py`를 저장소 최상위 경로에 업로드합니다.
   - https://github.com/songwonyong8-png/fujimoto-signal/upload/main
3. `.github/workflows/`에 `backtest-f-v6.yml`을 생성하고 내용을 복사합니다.
   - https://github.com/songwonyong8-png/fujimoto-signal/tree/main/.github/workflows
4. YAML을 커밋하면 자동 실행되고, Actions → `F v6 Article-Inspired Ichimoku and RSI Exits`에서도 수동 실행할 수 있습니다.
   - https://github.com/songwonyong8-png/fujimoto-signal/actions
5. 정상 완료 후 GitHub 폴더 `reports/f_signal_article_v6/`에 결과가 저장됩니다.

## 비교 전략

- `F5_A_cloud`, `F5_A_cloud_vp`: 기존 F5-A 독립 매도 비교군을 변경 없이 실행.
- `F6_breakout_cloud`: RSI 반등+양봉(1/9) → MACD 골든크로스(2/9) → 일목 강세 정렬과 당일 구름대 상단 돌파(6/9).
- `F6_trend_cloud`: 위와 같지만 최근 20거래일 내 구름대 돌파 이력을 가진 확인된 상승 정렬도 3차 매수에 허용.
- `_vp` 버전: 3차 신호에 이전 120거래일 거래량 매물대(PoC) 근접 조건도 추가.

### F6 매도

- 3차 매수분(6/9): 종가가 일목 구름대 하단 미만으로 내려가면 다음 거래일 시가 매도.
- 2차 매수분(2/9): MACD 데드크로스 시 해당 물량만 다음 시가 매도.
- 1차 매수분(1/9): RSI <=30으로 재하락하거나, RSI가 아래에서 70 이상으로 상향 진입하면 해당 물량만 다음 시가 매도.
- 독립 물량 관리. 한 번 매도한 단계를 같은 매매 주기에서 재매수하지 않음. 고정 40일 매도 없음.
- 수수료 편도 0.1%, 전액 현금 시작, 공매도 및 차입 없음.

## 정확성·한계

- **저자의 매매를 완전히 복제한 것이 아닙니다.** 원문에서 주관적으로 언급한 판단을 일봉의 명시적 조건으로 바꾼 연구용 구현입니다.
- 원문은 5분봉/호가창을 주로 참고하지만 **이 백테스트는 일봉만 사용**합니다. 5분봉 검증은 수행하지 않습니다.
- 재무 성장/배당 성장 종목선정은 과거 발표 당시 알 수 있던 재무 데이터 없이는 소급 검증이 왜곡됩니다. 기본 `F6_FUNDAMENTAL_GATE='off'`이며, 보고서에 필터 미적용을 명시합니다.
- 재무성장 검증을 수행하려면 출처와 **최초 공개일**이 명시된 `research_inputs/fundamentals_asof.csv`를 사용해야 합니다. 이 CSV는 ZIP의 헤더 템플릿만 제공되며 가상의 과거 실적을 채우지 않습니다.
- CSV 컬럼: `symbol,available_date,revenue_yoy,net_income_yoy,dividend_yoy,source_url`. 성장률은 소수 표현(예: 10%=0.10), 3종 모두 양수여야 통과합니다. 최근 공개 550일 이내 자료만 사용합니다.
- 데이터를 검증·준비한 다음 YAML의 `F6_FUNDAMENTAL_GATE`를 `strict`로 바꾸고 실행합니다. **현재는 strict로 변경하지 마세요.** 빈 템플릿을 넣으면 매수 기회가 0이 됩니다.
- 2026-10-24 구성종목 스냅샷을 과거에 소급 적용하므로 생존자 편향이 있습니다. Yahoo 가격 데이터 소스, 무배당/무세금/무슬리피지 가정, 실제 매매 가능성 등은 별도 검증이 필요합니다.
- 40/80/120거래일은 신호가 같은 F5/F6 비교를 위한 *평가 시점*이지 강제 매도일이 아닙니다. 서로 다른 기간의 표본은 중복될 수 있습니다.
- F5 전체기간 기준 비교는 다른 매수·매도 이후 다음 기회가 달라 직접 동등하지 않을 수 있으므로 `paired_cohorts.csv`의 같은 첫 신호·같은 최종일 비교도 함께 확인하세요.

## 저장되는 결과

- `report.md`: 검증 결과 표와 데이터 한계
- `summary.csv`: 전략/종목/기간별 수익률, MDD, 거래 수, 투자 노출률, 단계별 매수·매도 횟수
- `trades.csv`: 매매 주기별 실현 또는 미청산 평가손익
- `fills.csv`: 체결 날짜, 매수·매도 원인, 물량
- `paired_cohorts.csv`: 같은 첫 RSI 신호의 F5 vs F6 비교 (40/80/120거래일)
- `run_metadata.json`: 자료 범위, 재무 필터 적용 여부, 실패 종목

## 단위 테스트

로컬 검증: 2026-10-24에 기존 v3-v5 회귀 테스트 포함 총 74개 통과. 모의 일봉을 이용한 전체 보고서 출력 성공.
**실제 종목 데이터를 사용하는 F6 최종 백테스트는 이 ZIP을 업로드하고 GitHub Actions를 실행한 뒤 확인해야 합니다.**
