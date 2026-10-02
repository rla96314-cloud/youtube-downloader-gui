# Video Downloader (GUI) — YouTube · 치지직 · SOOP

단독 실행형 동영상 다운로더 데스크톱 앱. 별도 서버 없이 [yt-dlp](https://github.com/yt-dlp/yt-dlp)
라이브러리를 직접 호출하고, [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
기반의 모던 GUI(둥근 카드 / 컬러 버튼)를 제공합니다.

## 지원 사이트

| 사이트 | 지원 URL | 비고 |
|---|---|---|
| **YouTube** | 영상 · 쇼츠 · 재생목록 | yt-dlp 내장 |
| **치지직** | 다시보기 `chzzk.naver.com/video/{번호}` · 클립 `chzzk.naver.com/clips/{ID}` | **자체 추출기** (아래 참고) |
| **SOOP** | 다시보기·클립 `vod.sooplive.co.kr/player/{번호}` (여러 파트면 `(part N)` 로 나눠 저장) | yt-dlp 내장 (`soop`) |

생방송(`chzzk.naver.com/live/…`, `play.sooplive.co.kr/…`) 녹화는 지원하지 않습니다 — 다시보기 URL 을 넣어 주세요.
성인 인증·구독자 전용 영상은 **로그인 쿠키** 옵션에서 네이버/SOOP 에 로그인된 브라우저(Chrome/Edge/Whale/Firefox)나
`cookies.txt` 파일을 고르면 됩니다. (Windows 의 Chrome 은 쿠키 암호화 때문에 못 읽는 경우가 있어요 → Firefox 나 cookies.txt 권장)

### 치지직 자체 추출기를 쓰는 이유

yt-dlp 의 `chzzk:video` 는 2026.08 현재 `vodStatus == ABR_HLS` 인 다시보기에서 `KeyError('sourceURL')` 로 죽습니다
([yt-dlp#17063](https://github.com/yt-dlp/yt-dlp/issues/17063)). 그래서 네이버 VOD 플레이백 API 를 직접 읽습니다:

- `api.chzzk.naver.com/service/v3/videos/{번호}` (클립은 `v1/play-info/clip/{ID}`) → `videoId` + `inKey`
- `apis.naver.com/neonplayer/vodplay/v2/playback/{videoId}?key=…` 를 **`Accept: application/json`** 으로 받으면 DASH 대신 JSON 이 옴
  - `video/mp4` : 단일 MP4(영상+음성). 짧은 영상/클립에만 있고, CDN 이 재생속도 근처로 쓰로틀링해서 느림 → 폴백용
  - `video/mp2t` : 화질별 HLS 미디어 플레이리스트(`otherAttributes.m3u`). 긴 다시보기는 이것만 있음
  - `audio/mp4` : 음성 전용 m4a (MP3 변환용)
- HLS 플레이리스트는 그대로 못 써서 **로컬 파일로 재작성**해 `file:` URL 로 넘깁니다
  - 짧은 다시보기: 세그먼트 줄에 서명 쿼리(`?_lsu_sa_=…`)가 빠져 있어 404 → DASH `segmentTemplate.media` 의 쿼리를 붙임
  - 긴 다시보기(AES-128): 키 URL(`…/encryption/videos/{videoId}/aes_key`)이 **`NNB` 쿠키 + Referer** 없으면 403
    (값은 아무거나 OK) → 키를 미리 받아 로컬 `.key` 파일로 두고 절대 `file://` URI 로 가리킴
  - 네이티브 HLS 다운로더는 `hls_media_playlist_data` 로 내용을 받고, 구간 잘라받기는 ffmpeg 가 `file:` 입력을 읽음
    (`enable_file_urls` + `-allowed_extensions ALL`)
- 다운로드/병합/MP3/구간/자막 후처리는 전부 yt-dlp 에 맡깁니다. 자체 추출이 실패하면 yt-dlp 내장 추출기로 재시도합니다.

> 이 저장소의 소스는 배포된 `YouTubeDownloader.exe`(PyInstaller 단일 실행파일, Python 3.12)를
> 역어셈블하여 원본과 동일하게 복원한 것입니다.

## 기능

- 여러 URL 일괄 다운로드 (줄바꿈으로 구분, 순차 처리)
- 실시간 진행률 · 속도(MB/s) 표시, 취소 버튼
- 화질/형식 프리셋
  - 최고 화질 (영상+음성) — `bestvideo*+bestaudio/best`
  - 1080p 이하 — `bestvideo[height<=1080]+bestaudio/best[height<=1080]`
  - 720p 이하 — `bestvideo[height<=720]+bestaudio/best[height<=720]`
  - 단일 파일(최고, 병합 불필요) — `best`
  - 음성만 (MP3) — `bestaudio/best` → 192kbps MP3 추출
- 코덱 선택: 기본은 **H.264(MP4) 우선**(호환성↑, 보통 최대 1080p), 체크 시 **AV1/VP9 허용**(4K 등 초고화질)
- **구간 잘라받기** ✂ — 시작~끝 시간(`90` · `1:30` · `1:02:03`)만 잘라서 저장 (빈칸이면 처음/끝까지). 키프레임 정렬로 정확히 컷
- **재생목록 전체 받기** 📚 — 재생목록 URL 을 통째로. `재생목록이름/순번. 제목` 형태로 하위폴더 저장
- **자막** 💬 — 자막 파일(SRT) 별도 저장 / 영상에 입히기(내장) 선택, 언어 코드 지정(기본 `ko,en`, 자동생성 자막 포함)
- **로그인 쿠키** 🍪 — 브라우저(Chrome/Edge/Whale/Firefox) 쿠키 또는 `cookies.txt` 로 성인 인증·구독자 전용 영상
- 저장 폴더 선택, 진행 로그
- 파일명은 한글 그대로 저장 (Windows 금지문자만 치환). v1.1 까지는 `restrictfilenames` 라 한글이 전부 `_` 로 바뀌었음
- HLS 조각 6개 병렬 다운로드
- ffmpeg 가 없으면 자동으로 병합 불필요 단일 포맷으로 대체 (구간/자막 입히기도 ffmpeg 필요)

## 설치 & 실행

```bash
pip install -r requirements.txt
python youtube_downloader.py
```

고화질 영상+오디오 병합 및 MP3 변환에는 [ffmpeg](https://ffmpeg.org/) 가 필요합니다.
시스템 PATH 에 있거나, 실행파일과 같은 폴더(또는 PyInstaller 번들 안)에 `ffmpeg`(Windows 는 `ffmpeg.exe`)를 두면 자동 인식합니다.

## yt-dlp 자동 업데이트

번들된 yt-dlp 는 시간이 지나면 유튜브 변경으로 다운로드가 막힙니다(HTTP 403 등).
그래서 **앱을 켤 때 PyPI 에서 최신 yt-dlp 를 받아 우선 사용**합니다 — 재빌드 없이도 최신 상태가 유지됩니다.

- 최신 휠(순수 파이썬)을 사용자 폴더에 받아 두고, `meta_path` 파인더로 내장본보다 우선 import.
  프리징된 실행파일에서도 내장 yt-dlp 를 제치고 최신본을 씁니다.
- 네트워크 부담을 줄이려 **하루 1회만** 확인하며, 오프라인이면 마지막에 받아둔 버전(없으면 내장본)을 사용합니다.
- SSL 인증은 번들된 `certifi` CA 로 검증합니다(코드를 받으므로 검증을 끄지 않음).
- 캐시 위치: macOS `~/Library/Application Support/YouTubeDownloader/yt-dlp`,
  Windows `%LOCALAPPDATA%\YouTubeDownloader\yt-dlp`. 이 폴더를 지우면 다음 실행 때 다시 받습니다.
- 앱 시작 시 진행 로그에 현재 `yt-dlp <버전> · (자동 최신화|내장)` 이 표시됩니다.

## 단일 실행파일 빌드 (PyInstaller)

```bash
pip install pyinstaller

# Windows
pyinstaller --noconfirm --onefile --windowed \
  --icon icon.ico \
  --add-data "icons;icons" \
  --add-data "icon.ico;." --add-data "icon.png;." \
  --add-binary "ffmpeg.exe;." \
  --name YouTubeDownloader youtube_downloader.py

# macOS (.app 번들 — onedir + icns)
pyinstaller --noconfirm --onedir --windowed \
  --icon icon.icns \
  --add-data "icons:icons" \
  --add-data "icon.icns:." --add-data "icon.png:." \
  --add-binary "ffmpeg:." \
  --name YouTubeDownloader youtube_downloader.py
# → dist/YouTubeDownloader.app

# Linux (단일 실행파일)
pyinstaller --noconfirm --onefile --windowed \
  --add-data "icons:icons" --add-data "icon.png:." \
  --add-binary "ffmpeg:." \
  --name YouTubeDownloader youtube_downloader.py
```

프로그램 아이콘: `icon.ico`(Windows) / `icon.icns`(macOS) / `icon.png`(창 아이콘·리눅스).
아이콘을 바꾸려면 `make_icon.py` 를 수정한 뒤 `python make_icon.py` 로 셋 다 다시 생성하세요.

### 자동 빌드 (GitHub Actions)

`.github/workflows/build-windows.yml` 이 **Windows 러너에서 exe 를 자동 빌드**합니다 (ffmpeg.exe 자동 번들).
PyInstaller 는 크로스 컴파일이 안 되므로 Windows exe 는 이 워크플로(또는 실제 Windows PC)에서만 만들 수 있습니다.

- **수동 실행**: 저장소 → Actions → *Build Windows EXE* → *Run workflow* → 완료 후 Artifacts 에서 `YouTubeDownloader.exe` 다운로드
- **릴리스**: `git tag v1.2.0 && git push origin v1.2.0` → 빌드 후 해당 태그 Release 에 exe 자동 첨부

`.github/workflows/build-macos.yml` 은 **macOS 러너에서 `.app` 을 자동 빌드**합니다
(Apple Silicon `arm64` + Intel `x86_64` 둘 다, ffmpeg 정적 바이너리 자동 번들, `.zip` 으로 패키징).

- **수동 실행**: Actions → *Build macOS App* → *Run workflow* → Artifacts 에서 `YouTubeDownloader-macos-<arch>.zip` 다운로드
- **릴리스**: 태그 푸시 시 각 아키텍처 `.zip` 이 Release 에 자동 첨부

> ⚠️ 코드 서명을 하지 않았으므로, 처음 실행할 때 "확인되지 않은 개발자" 경고가 뜹니다.
> **우클릭 → 열기** 로 한 번 허용하거나, 터미널에서 `xattr -dr com.apple.quarantine YouTubeDownloader.app` 을 실행하세요.

## 프로젝트 구조

```
youtube_downloader.py   # 앱 전체 (단일 파일: GUI + 치지직 자체 추출기)
make_icon.py            # 프로그램 아이콘 생성기 (icon.png / icon.ico / icon.icns)
icon.png / icon.ico / icon.icns  # 프로그램 아이콘 (창 / Windows exe / macOS app)
icons/                  # UI 아이콘 (link, gear, folder, video, download, activity, help, folder_blue)
requirements.txt
```

## 라이선스

개인용. yt-dlp / CustomTkinter / ffmpeg 등 각 의존성의 라이선스를 따릅니다.
