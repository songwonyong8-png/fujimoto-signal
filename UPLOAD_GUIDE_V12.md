# 아이폰에서 GitHub에 v12 업로드하기

**YAML 변경은 필요 없습니다.** 기존 코스피 100·나스닥 100·DRAM ETF 감시와 개인 보유정보 관리 기능을 유지한 채 RSI 설명과 차트 표시만 개선합니다.

1. ChatGPT에서 `Fujimoto_iPhone_v12_RSI반등_차트겹침개선.zip`을 아이폰 **파일** 앱에 저장한 뒤 압축 해제합니다.
2. Safari에서 [GitHub 저장소](https://github.com/songwonyong8-png/fujimoto-signal)로 이동합니다.
3. 최상위 폴더의 `index.html`을 누르고 **연필(Edit this file)** 버튼으로 편집한 뒤, ZIP 내부의 같은 이름 파일 내용으로 전체 교체하고 `Commit changes`합니다. `app.js`, `sw.js`, `update_screener.py`, `test_screener_f9a.py`도 동일하게 교체합니다.
   - 컴퓨터 또는 Safari 데스크톱 모드를 사용하시면 저장소 상단 **Add file → Upload files**에서 이 다섯 파일을 한 번에 업로드해 동명 파일을 덮어쓸 수 있습니다. GitHub UI에서 대량 업로드가 제한되면 각 파일 편집 방식으로 진행하세요.
   - **백테스트 파일, `data/`, `daily.yml`은 건드리지 않습니다.**
4. [GitHub Actions의 Daily F9-A](https://github.com/songwonyong8-png/fujimoto-signal/actions/workflows/daily.yml)에서 `Run workflow` → `main` → `Run workflow`를 실행합니다.
5. 초록색 체크가 뜨고 GitHub Pages 배포가 성공하면 [아이폰 매매신호등](https://songwonyong8-png.github.io/fujimoto-signal/)에서 새로고침하고 종목을 누릅니다.
6. 상세 화면에 **`RSI가 왜 1차 반등인가요?`** 섹션이 나타나면 성공입니다.

### 자주 보는 문제

- **RSI 변화 내용이 나오지 않음:** `update_screener.py`가 GitHub에 적용됐는지, Actions가 성공해 `data/screener_f9a.json`을 새로 생성했는지 확인하세요.
- **예전 화면이 남음:** Safari에서 직접 사이트를 새로고침하세요. 홈 화면 바로가기 앱은 별도 캐시·저장공간을 사용할 수 있습니다.
- **GitHub Actions가 Fail:** 실패한 실행 링크를 보내거나 '실패 확인'이라고 말씀해 주시면 실행 로그를 확인해 원인을 분석할 수 있습니다.
- **보유 수량·평단:** 기존 로컬 저장키가 유지됩니다. 단, Safari의 웹사이트 데이터 삭제나 앱 재설치는 저장 내역을 지울 수 있으므로 먼저 **백업·복원 → 내 보유내역 파일로 백업**을 사용하세요.
