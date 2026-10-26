# 아이폰으로 F9-A 포트폴리오 화면 설치

## 업로드 위치 (폴더를 정확히 지켜야 합니다)

### ① 저장소 최상위 폴더 — 7개

https://github.com/songwonyong8-png/fujimoto-signal/upload/main

- `index.html` **덮어쓰기**
- `app.js` **덮어쓰기**
- `sw.js` **덮어쓰기**
- `manifest.webmanifest` **덮어쓰기**
- `update_screener.py` 신규
- `test_screener_f9a.py` 신규
- `README_PORTFOLIO_V10.md` 신규 (선택)

### ② data 폴더 — 1개

https://github.com/songwonyong8-png/fujimoto-signal/tree/main/data

- `screener_f9a.json` 신규 (`data/screener_f9a.json` 경로)

### ③ .github/workflows 폴더 — 1개

https://github.com/songwonyong8-png/fujimoto-signal/tree/main/.github/workflows

- `daily.yml` **기존 파일 덮어쓰기** (`.github/workflows/daily.yml` 경로)

**다른 Python 백테스트 파일은 삭제하지 마세요.** 기존 F3~F9 엔진을 새 스캐너에서 가져옵니다.

## 아이폰에서 폴더 업로드

1. Safari에서 해당 GitHub 폴더를 열고 GitHub에 로그인합니다.
2. 상단 `Add file` → `Upload files`를 누릅니다. 화면에서 숨겨진 경우 사파리 페이지 설정에서 **데스크탑 웹 사이트 요청**을 사용합니다.
3. `Choose your files`를 눌러 아이폰 파일 앱에서 해당 파일을 선택합니다.
4. 기존과 같은 이름으로 업로드하면 GitHub가 파일 변경을 감지합니다. 아래 `Commit changes` 버튼으로 main에 저장합니다.
5. YAML은 `.github/workflows` **폴더 안**에서 파일을 열어 편집하고, 새 `daily.yml`의 내용을 전체 복사·붙여넣는 방식이 더 확실할 수 있습니다.

## 최초 자동 갱신

https://github.com/songwonyong8-png/fujimoto-signal/actions/workflows/daily.yml

`Run workflow` → `main` → `Run workflow`를 누릅니다. 정상 완료 시 `data/screener_f9a.json`에 201종목의 매매 신호가 갱신됩니다. 최초 데이터 업로드 이전에는 목록은 보이지만 개별 매매 신호가 '신호 보류'로 나타나는 것이 정상입니다.

### 완료 후 주소

https://songwonyong8-png.github.io/fujimoto-signal/

iPhone 사파리에서 접속하고 필요하면 공유 메뉴에서 **홈 화면에 추가**를 누르세요.

## 보유 내역 입력

- 목록에서 보유 종목 선택 → `매수 기록` → 수량과 체결 가격 입력 → 해당 보유 단계(1/2/3차) 선택 → 저장
- 이미 가지고 있는 종목은 `직접 수정` → **전체 수량과 실제 평균단가** 입력
- 추가 매수는 `매수 기록`을 사용하면 평균단가가 가중평균으로 자동 변경됩니다.
- 일부 매도는 `매도 기록`을 사용하면 평균단가는 유지되고 수량이 감소합니다.
- 화면 위 `백업·복원`으로 기기의 로컬 보유정보를 별도 JSON으로 백업하십시오.

## 오류 진단

- 페이지가 예전 모양: 홈 화면 앱 완전히 종료 후 다시 열기, Safari에서 새로고침, `sw.js` 업로드 여부 확인.
- 목록은 나오지만 매수/매도 신호가 없음: Actions에서 `Daily F9-A 200-stock iPhone Screener` 성공 여부, `data/screener_f9a.json` 파일의 `fresh_count` 확인.
- GH Actions 실패: Run Details에서 어떤 단계가 빨간색인지 확인 (대부분 데이터 수집 실패나 Git 저장 충돌).
