# YouTube Downloader (GUI)

단독 실행형 YouTube 다운로더 데스크톱 앱. 별도 서버 없이 [yt-dlp](https://github.com/yt-dlp/yt-dlp)
라이브러리를 직접 호출하고, [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
기반의 모던 GUI(둥근 카드 / 컬러 버튼)를 제공합니다.

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
- 저장 폴더 선택, 진행 로그
- ffmpeg 가 없으면 자동으로 병합 불필요 단일 포맷으로 대체 (구간/자막 입히기도 ffmpeg 필요)

## 설치 & 실행

```bash
pip install -r requirements.txt
python youtube_downloader.py
```

고화질 영상+오디오 병합 및 MP3 변환에는 [ffmpeg](https://ffmpeg.org/) 가 필요합니다.
시스템 PATH 에 있거나, 실행파일과 같은 폴더(또는 PyInstaller 번들 안)에 `ffmpeg`(Windows 는 `ffmpeg.exe`)를 두면 자동 인식합니다.

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
- **릴리스**: `git tag v1.1.0 && git push origin v1.1.0` → 빌드 후 해당 태그 Release 에 exe 자동 첨부

`.github/workflows/build-macos.yml` 은 **macOS 러너에서 `.app` 을 자동 빌드**합니다
(Apple Silicon `arm64` + Intel `x86_64` 둘 다, ffmpeg 정적 바이너리 자동 번들, `.zip` 으로 패키징).

- **수동 실행**: Actions → *Build macOS App* → *Run workflow* → Artifacts 에서 `YouTubeDownloader-macos-<arch>.zip` 다운로드
- **릴리스**: 태그 푸시 시 각 아키텍처 `.zip` 이 Release 에 자동 첨부

> ⚠️ 코드 서명을 하지 않았으므로, 처음 실행할 때 "확인되지 않은 개발자" 경고가 뜹니다.
> **우클릭 → 열기** 로 한 번 허용하거나, 터미널에서 `xattr -dr com.apple.quarantine YouTubeDownloader.app` 을 실행하세요.

## 프로젝트 구조

```
youtube_downloader.py   # 앱 전체 (단일 파일)
make_icon.py            # 프로그램 아이콘 생성기 (icon.png / icon.ico / icon.icns)
icon.png / icon.ico / icon.icns  # 프로그램 아이콘 (창 / Windows exe / macOS app)
icons/                  # UI 아이콘 (link, gear, folder, video, download, activity, help, folder_blue)
requirements.txt
```

## 라이선스

개인용. yt-dlp / CustomTkinter / ffmpeg 등 각 의존성의 라이선스를 따릅니다.
