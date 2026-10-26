# 아이폰 Safari로 v11 올리는 방법

1. 이 ZIP 파일을 아이폰 **파일 앱**에 저장한 뒤 길게 누르고 **압축 해제**합니다.
2. Safari에서 [저장소 최상위 폴더](https://github.com/songwonyong8-png/fujimoto-signal)를 엽니다.
3. `Add file` → `Upload files`에서 압축 해제한 **5개의 코드 파일**을 선택합니다.
   - `index.html`
   - `app.js`
   - `sw.js`
   - `update_screener.py`
   - `test_screener_f9a.py`
4. 기존 파일명과 같으므로 기존 파일을 **교체**하는지 확인합니다. `Commit changes`로 `main`에 반영합니다. 파일을 직접 업로드해 덮어쓰는 기능이 보이지 않으면 해당 파일을 열고 연필 모양 `Edit file`에서 내용을 교체하세요.
5. **기존 YAML은 수정하지 마세요.** [Actions → Daily F9-A 200-stock iPhone Screener](https://github.com/songwonyong8-png/fujimoto-signal/actions/workflows/daily.yml) → `Run workflow` → `main` → `Run workflow`.
6. 갱신 결과가 초록색 체크이면 `data/screener_f9a.json`에 모든 사용가능 종목의 120일 매물대와 40일 MACD 시계열이 반영됩니다.
7. [아이폰 페이지](https://songwonyong8-png.github.io/fujimoto-signal/)에서 종목명을 눌러 차트의 **POC · VAL · VAH**와 MACD 색깔을 확인하세요.

**보유정보 안전:** 기존 아이폰 브라우저의 `localStorage`는 덮어쓰지 않습니다. 다만 홈 화면 설치 앱과 Safari 브라우저는 보유 내역이 따로 저장될 수 있으므로 **백업·복원**에서 JSON 파일을 먼저 저장하는 것이 안전합니다.

**GitHub Pages는 공개될 수 있습니다.** 개인 수량·평균단가는 iPhone 로컬 저장소에만 남고 GitHub 작업에 업로드하지 않습니다.
