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
- 저장 폴더 선택, 진행 로그
- ffmpeg 가 없으면 자동으로 병합 불필요 단일 포맷으로 대체

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
  --add-data "icons;icons" \
  --add-binary "ffmpeg.exe;." \
  --name YouTubeDownloader youtube_downloader.py

# macOS / Linux (경로 구분자는 콜론)
pyinstaller --noconfirm --onefile --windowed \
  --add-data "icons:icons" \
  --add-binary "ffmpeg:." \
  --name YouTubeDownloader youtube_downloader.py
```

`icon.ico` / `icon.png` 가 있으면 `--icon` 및 `--add-data` 로 함께 포함하면 창 아이콘으로 사용됩니다.

## 프로젝트 구조

```
youtube_downloader.py   # 앱 전체 (단일 파일)
icons/                  # UI 아이콘 (link, gear, folder, video, download, activity, help, folder_blue)
requirements.txt
```

## 라이선스

개인용. yt-dlp / CustomTkinter / ffmpeg 등 각 의존성의 라이선스를 따릅니다.
