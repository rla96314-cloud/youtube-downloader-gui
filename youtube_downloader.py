"""
Video Downloader - YouTube · 치지직(CHZZK) · SOOP 단독 실행형 GUI 다운로더 (CustomTkinter)

- 별도의 서버가 필요 없습니다. yt-dlp 라이브러리를 직접 호출합니다.
- 치지직 다시보기/클립은 yt-dlp 내장 추출기가 현재(2026.08) ABR_HLS 영상에서 깨져 있어
  (KeyError 'sourceURL'), 네이버 VOD 플레이백 API(JSON)를 직접 읽는 자체 추출기를 씁니다.
- CustomTkinter 기반의 모던 GUI (둥근 카드 / 컬러 버튼).
- PyInstaller 로 단일 실행파일(.exe / 바이너리)로 빌드할 수 있습니다.

필요 패키지:
    pip install yt-dlp customtkinter

(선택) 고화질 영상+오디오 병합 및 mp3 변환에는 ffmpeg 가 필요합니다.
ffmpeg 가 없으면 단일 포맷(병합 불필요) 다운로드만 사용됩니다.
"""
import os
import re
import sys
import json
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

try:
    from PIL import Image
except ImportError:
    Image = None

# ── yt-dlp 자동 업데이트 ────────────────────────────────────────────
# 번들된 yt-dlp 는 시간이 지나면 유튜브 변경으로 다운로드가 막힌다(HTTP 403 등).
# 실행 시 PyPI 에서 최신 yt-dlp 휠(순수 파이썬)을 받아 사용자 폴더에 풀어 두고,
# meta_path 파인더로 그 버전을 우선 import 한다(프리징된 내장본보다 우선).
_YTDLP_UPDATED = False


def _ytdlp_cache_dir():
    if sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support/YouTubeDownloader')
    elif os.name == 'nt':
        base = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                            'YouTubeDownloader')
    else:
        base = os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share'),
                            'YouTubeDownloader')
    return os.path.join(base, 'yt-dlp')


def _ensure_latest_ytdlp(timeout=6):
    """최신 yt-dlp 휠을 캐시에 준비하고 그 폴더 경로를 반환(없으면 None).
    네트워크 부담을 줄이려 하루 1회만 온라인 확인한다."""
    import ssl
    import json
    import shutil
    import zipfile
    import datetime
    import urllib.request

    cache = _ytdlp_cache_dir()
    try:
        os.makedirs(cache, exist_ok=True)
    except Exception:
        return None

    # SSL 검증용 CA 번들 (python.org 파이썬/프리징 앱은 시스템 CA 가 없을 수 있어 certifi 사용).
    # 코드를 내려받으므로 검증은 절대 끄지 않는다 — 실패 시 업데이트를 건너뛴다.
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            ctx = ssl.create_default_context()
        except Exception:
            ctx = None

    def _read(p):
        try:
            with open(p, encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            return None

    def _write(p, s):
        try:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(s)
        except Exception:
            pass

    installed = _read(os.path.join(cache, 'installed.txt'))
    cur = os.path.join(cache, installed) if installed else None
    have = bool(cur) and os.path.isdir(os.path.join(cur, 'yt_dlp'))
    today = datetime.date.today().isoformat()

    if have and _read(os.path.join(cache, 'last_check.txt')) == today:
        return cur  # 오늘 이미 확인 → 네트워크 생략

    try:
        req = urllib.request.Request('https://pypi.org/pypi/yt-dlp/json',
                                     headers={'User-Agent': 'YouTubeDownloader'})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            data = json.load(r)
        latest = data['info']['version']
        wheel = next((u['url'] for u in data['urls'] if u['filename'].endswith('.whl')), None)
        _write(os.path.join(cache, 'last_check.txt'), today)
    except Exception:
        return cur if have else None  # 오프라인 등 → 캐시본 사용

    if not latest or not wheel or (installed == latest and have):
        return cur if have else None

    try:
        tmp = os.path.join(cache, 'download.whl')
        with urllib.request.urlopen(wheel, timeout=timeout, context=ctx) as r, open(tmp, 'wb') as f:
            shutil.copyfileobj(r, f)
        target = os.path.join(cache, latest)
        tdir = target + '.tmp'
        shutil.rmtree(tdir, ignore_errors=True)
        with zipfile.ZipFile(tmp) as z:
            z.extractall(tdir)          # 휠(zip)을 폴더로 추출
        shutil.rmtree(target, ignore_errors=True)
        os.replace(tdir, target)        # 원자적 교체
        try:
            os.remove(tmp)
        except Exception:
            pass
        _write(os.path.join(cache, 'installed.txt'), latest)
        return target
    except Exception:
        return cur if have else None


def _activate_ytdlp_update():
    """준비된 최신 yt-dlp 를 우선 import 하도록 meta_path 파인더를 설치."""
    global _YTDLP_UPDATED
    try:
        d = _ensure_latest_ytdlp()
    except Exception:
        d = None
    if not d or not os.path.isdir(os.path.join(d, 'yt_dlp')):
        return
    import importlib.abc
    import importlib.machinery

    class _YtdlpFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == 'yt_dlp':
                return importlib.machinery.PathFinder.find_spec(name, [d])
            if name.startswith('yt_dlp.'):
                return importlib.machinery.PathFinder.find_spec(name, path)
            return None

    sys.meta_path.insert(0, _YtdlpFinder())
    _YTDLP_UPDATED = True


_activate_ytdlp_update()

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

APP_TITLE = 'Video Downloader — YouTube · 치지직 · SOOP'
APP_VERSION = '1.2.0'
BG = '#EEF3FB'
CARD = '#FFFFFF'
HEADING = '#1F2A37'
SUBTLE = '#9AA7B8'
ACCENT = '#3B82F6'
ACCENT_HOVER = '#2563EB'
BORDER = '#E9EEF6'


def ffmpeg_dir():
    """번들된 ffmpeg 가 들어 있는 폴더 경로를 반환합니다 (없으면 None)."""
    exe = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass and os.path.exists(os.path.join(meipass, exe)):
        return meipass
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(here, exe)):
        return here
    return None


def has_ffmpeg():
    """시스템 PATH, 내장 번들, 또는 같은 폴더에서 ffmpeg 를 찾습니다."""
    import shutil
    return shutil.which('ffmpeg') is not None or ffmpeg_dir() is not None


def resource_path(name):
    """번들/소스 모두에서 리소스 파일 경로를 찾습니다."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ── 플랫폼 판별 ──────────────────────────────────────────────────────
# (표시 이름, URL 정규식). 생방송 URL 은 별도로 걸러서 안내만 한다.
PLATFORMS = [
    ('YouTube', re.compile(r'(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/', re.I)),
    ('치지직', re.compile(r'chzzk\.naver\.com/', re.I)),
    ('SOOP', re.compile(r'(?:sooplive\.co\.kr|afreecatv\.com)/', re.I)),
]
LIVE_URL_RE = re.compile(
    r'chzzk\.naver\.com/live/|play\.sooplive\.co\.kr/|play\.afreecatv\.com/', re.I)


def detect_platform(url):
    for name, rx in PLATFORMS:
        if rx.search(url):
            return name
    return None


# ── 치지직(CHZZK) 다시보기 / 클립 자체 추출기 ───────────────────────
# yt-dlp 의 chzzk:video 는 vodStatus == 'ABR_HLS' 영상을 DASH(XML) 로 받아 파싱하다
# KeyError('sourceURL') 로 죽는다 (yt-dlp#17063). 같은 엔드포인트가 Accept: application/json
# 이면 JSON 을 주므로 그걸 직접 읽어 포맷 목록을 만들고, 다운로드/후처리는 yt-dlp 에 맡긴다.
#   - video/mp4  : 단일 MP4(영상+음성, 짧은 영상에만 있음)
#   - video/mp2t : HLS 미디어 플레이리스트(otherAttributes.m3u, 긴 다시보기는 이것만)
#   - audio/mp4  : 음성 전용 단일 m4a (MP3 변환용)
CHZZK_VIDEO_RE = re.compile(r'https?://(?:www\.|m\.)?chzzk\.naver\.com/(?:video|embed/vod)/(?P<id>\d+)', re.I)
CHZZK_CLIP_RE = re.compile(r'https?://(?:www\.|m\.)?chzzk\.naver\.com/(?:clips|embed/clip)/(?P<id>[\w-]+)', re.I)
CHZZK_API = 'https://api.chzzk.naver.com/service'
NAVER_PLAYBACK = 'https://apis.naver.com/neonplayer/vodplay/v2/playback/'


class ChzzkError(Exception):
    """사용자에게 그대로 보여줄 치지직 추출 오류 (성인 인증 등)."""


def _ydl_json(ydl, url, query=None):
    """yt-dlp 의 네트워크 스택(쿠키/프록시 포함)으로 JSON 을 받는다."""
    from urllib.parse import urlencode
    from yt_dlp.networking import Request
    if query:
        url = f'{url}?{urlencode(query)}'
    req = Request(url, headers={
        'Accept': 'application/json',
        'Referer': 'https://chzzk.naver.com/',
        'Origin': 'https://chzzk.naver.com',
    })
    with ydl.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def _ensure_nnb_cookie(ydl):
    """api.chzzk.naver.com 의 AES 키 엔드포인트는 네이버 기기식별 쿠키 `NNB` 가 없으면 403 을 준다.
    (값은 아무거나 OK — 실측) 브라우저 쿠키를 쓰는 중이면 진짜 값이 있으니 건드리지 않는다."""
    import http.cookiejar
    import random
    import string
    for c in ydl.cookiejar:
        if c.name == 'NNB' and 'naver.com' in (c.domain or ''):
            return
    val = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    ydl.cookiejar.set_cookie(http.cookiejar.Cookie(
        0, 'NNB', val, None, False, '.naver.com', True, True, '/', True,
        True, None, True, None, None, {}))  # discard=True → cookies.txt 에 저장되지 않음


def _ydl_bytes(ydl, url, referer):
    from yt_dlp.networking import Request
    with ydl.urlopen(Request(url, headers={'Referer': referer})) as resp:
        return resp.read()


def _chzzk_hls_format(ydl, rep, m3u, referer, tmpdir, common):
    """HLS 표현(video/mp2t) 하나를 yt-dlp 포맷으로.

    원본 m3u8 는 그대로 못 쓴다:
      - 짧은 다시보기: 세그먼트 줄에 서명 쿼리(`?_lsu_sa_=…`)가 빠져 있어 404 → DASH segmentTemplate 의 쿼리를 붙인다
      - 긴 다시보기(AES): 키 URL 이 NNB 쿠키+Referer 를 요구 → 키를 미리 받아 data: URI 로 심는다
    그래서 플레이리스트를 로컬 파일로 재작성해 file: URL 로 넘긴다. 네이티브 HLS 다운로더는
    `hls_media_playlist_data` 로 내용을 직접 받고, 구간 잘라받기(ffmpeg) 는 file: 입력을 읽는다
    (yt-dlp 가 -protocol_whitelist 를 붙여 준다; `enable_file_urls` 필요).
    """
    import pathlib
    from urllib.parse import urljoin, urlsplit
    text = _ydl_bytes(ydl, m3u, referer).decode('utf-8', 'replace')
    media_tpl = ((rep.get('segmentTemplate') or {}).get('media')) or ''
    seg_query = urlsplit(media_tpl).query  # '_lsu_sa_=…' 또는 ''
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('#EXT-X-KEY') and 'URI="' in s:
            uri = re.search(r'URI="([^"]+)"', s).group(1)
            key = _ydl_bytes(ydl, urljoin(m3u, uri), referer)
            if len(key) != 16:
                raise ChzzkError(f'AES 키를 받지 못했습니다 ({len(key)} bytes).')
            # 키를 로컬 파일로 두고 절대 file:// URI 로 가리킨다.
            #  - 네이티브: 절대 URI 는 urljoin 을 건너뛰고 그대로 urlopen (enable_file_urls)
            #  - ffmpeg: -protocol_whitelist file + -allowed_extensions ALL 로 읽음
            #  (data: URI 는 네이티브 urljoin 이 None 을 주고, hls_aes.key 를 쓰면 ffmpeg 구간컷이 막혀 둘 다 탈락)
            key_path = os.path.join(tmpdir, f"{rep.get('id') or common.get('height')}.key")
            with open(key_path, 'wb') as kf:
                kf.write(key)
            s = s.replace(f'URI="{uri}"', f'URI="{pathlib.Path(key_path).as_uri()}"')
        elif s.startswith('#EXT-X-MAP') and 'URI="' in s:
            uri = re.search(r'URI="([^"]+)"', s).group(1)
            s = s.replace(f'URI="{uri}"', f'URI="{urljoin(m3u, uri)}"')
        elif not s.startswith('#'):
            s = urljoin(m3u, s)
            if seg_query and '?' not in s:
                s = f'{s}?{seg_query}'
        out.append(s)
    content = '\n'.join(out) + '\n'
    path = os.path.join(tmpdir, f"{rep.get('id') or common.get('height')}.m3u8")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return {
        'format_id': f"hls-{common.get('height')}p",
        'url': pathlib.Path(path).as_uri(),
        'hls_media_playlist_data': content,
        'ext': 'mp4',
        'protocol': 'm3u8_native',
        'downloader_options': {'ffmpeg_args': ['-allowed_extensions', 'ALL']},
        **common,
    }


def _chzzk_formats(ydl, playback, referer):
    import tempfile
    tmpdir = None
    formats = []
    for period in playback.get('period') or []:
        for aset in period.get('adaptationSet') or []:
            mime = aset.get('mimeType') or ''
            for rep in aset.get('representation') or []:
                base = ((rep.get('baseURL') or [{}])[0] or {}).get('value')
                codecs = [c.strip() for c in (rep.get('codecs') or '').split(',') if c.strip()]
                acodec = next((c for c in codecs if c.startswith('mp4a')), None)
                vcodec = next((c for c in codecs if not c.startswith('mp4a')), None)
                height = rep.get('height')
                bw = rep.get('bandwidth')
                common = {
                    'width': rep.get('width'),
                    'height': height,
                    'tbr': bw / 1000 if bw else None,
                    'vcodec': vcodec or 'avc1',
                    'acodec': acodec or 'mp4a.40.2',
                }
                try:
                    common['fps'] = int(float(rep.get('frameRate'))) if rep.get('frameRate') else None
                except ValueError:
                    common['fps'] = None
                if mime == 'video/mp4' and base:
                    # 단일 MP4 (영상+음성) — 짧은 다시보기/클립에만 있음.
                    # CDN 이 이 URL 은 재생 속도 근처로 쓰로틀링해서(실측 144p 0.16MB/s) HLS 보다 훨씬 느리다
                    # → preference 를 낮춰 같은 화질의 HLS 가 먼저 뽑히게 하고, 폴백으로만 남긴다.
                    formats.append({
                        'format_id': f'http-{height}p', 'url': base, 'ext': 'mp4',
                        'protocol': 'https', 'preference': -1, **common,
                    })
                elif mime == 'video/mp2t':
                    m3u = (rep.get('otherAttributes') or {}).get('m3u')
                    if not m3u:
                        continue
                    if tmpdir is None:
                        tmpdir = tempfile.mkdtemp(prefix='chzzk-hls-')
                    formats.append(_chzzk_hls_format(ydl, rep, m3u, referer, tmpdir, common))
                elif mime.startswith('audio/') and base:
                    # 음성 전용 단일 m4a (byte-range 세그먼트지만 파일 하나) — MP3 변환용
                    formats.append({
                        'format_id': 'audio', 'url': base, 'ext': 'm4a', 'protocol': 'https',
                        'vcodec': 'none', 'acodec': acodec or 'mp4a.40.2',
                        'asr': rep.get('audioSamplingRate'), 'tbr': common['tbr'],
                    })
    return formats


def chzzk_extract(ydl, url):
    """치지직 다시보기/클립 URL → yt-dlp info dict. 해당 URL 이 아니면 None.
    (실패 시 예외 → 호출 측에서 yt-dlp 내장 추출기로 폴백)"""
    m = CHZZK_VIDEO_RE.match(url)
    if m:
        vid = m.group('id')
        meta = (_ydl_json(ydl, f'{CHZZK_API}/v3/videos/{vid}') or {}).get('content') or {}
        if not meta:
            raise ChzzkError('영상 정보를 가져올 수 없습니다 (삭제됐거나 비공개 영상).')
        channel = meta.get('channel') or {}
        info = {
            'id': vid,
            'title': meta.get('videoTitle') or vid,
            'thumbnail': meta.get('thumbnailImageUrl'),
            'duration': meta.get('duration'),
            'view_count': meta.get('readCount'),
            'channel': channel.get('channelName'),
            'channel_id': channel.get('channelId'),
            'uploader': channel.get('channelName'),
            'live_status': 'was_live' if meta.get('liveOpenDate') else 'not_live',
        }
        if meta.get('publishDateAt'):
            info['timestamp'] = meta['publishDateAt'] / 1000
    else:
        m = CHZZK_CLIP_RE.match(url)
        if not m:
            return None
        cid = m.group('id')
        meta = (_ydl_json(ydl, f'{CHZZK_API}/v1/play-info/clip/{cid}') or {}).get('content') or {}
        if not meta:
            raise ChzzkError('클립 정보를 가져올 수 없습니다 (삭제됐거나 비공개 클립).')
        owner = meta.get('ownerChannel') or {}
        info = {
            'id': cid,
            'title': meta.get('contentTitle') or cid,
            'channel': owner.get('channelName'),
            'channel_id': owner.get('channelId'),
            'uploader': owner.get('channelName'),
            'view_count': meta.get('readCount'),
        }

    video_id, in_key = meta.get('videoId'), meta.get('inKey')
    if not video_id or not in_key:
        if meta.get('adult'):
            raise ChzzkError('성인 인증이 필요한 영상입니다. 옵션에서 네이버에 로그인된 브라우저 쿠키를 지정하세요.')
        raise ChzzkError(f"재생 정보가 없습니다 (vodStatus={meta.get('vodStatus')}).")

    _ensure_nnb_cookie(ydl)
    playback = _ydl_json(ydl, NAVER_PLAYBACK + video_id,
                         {'key': in_key, 'env': 'real', 'lc': 'ko_KR', 'cpl': 'ko_KR'})
    formats = _chzzk_formats(ydl, playback, referer=url)
    if not formats:
        raise ChzzkError('재생 가능한 포맷을 찾지 못했습니다.')
    info.update({
        'formats': formats,
        'webpage_url': url,
        'http_headers': {'Referer': 'https://chzzk.naver.com/'},
    })
    return info


class DownloaderApp(ctk.CTk):
    """CustomTkinter 기반 메인 윈도우."""

    FORMAT_PRESETS = [
        ('최고 화질 (영상+음성)', 'bestvideo*+bestaudio/best', True),
        ('1080p 이하', 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', True),
        ('720p 이하', 'bestvideo[height<=720]+bestaudio/best[height<=720]', True),
        ('단일 파일(최고, 병합 불필요)', 'best', False),
        ('음성만 (MP3)', 'bestaudio/best', True),
    ]

    # 자막 옵션: (표시 이름, 내부 모드)
    SUBS_OPTIONS = [
        ('자막 없음', 'none'),
        ('자막 파일(SRT)', 'file'),
        ('영상에 입히기', 'embed'),
    ]

    # 로그인 쿠키 옵션: (표시 이름, 내부 값) — 성인 인증/구독자 전용 영상용.
    # 브라우저 이름은 yt-dlp `cookiesfrombrowser` 값, 'file' 은 cookies.txt 파일.
    COOKIE_OPTIONS = [
        ('사용 안 함', None),
        ('Chrome', 'chrome'),
        ('Edge', 'edge'),
        ('Whale', 'whale'),
        ('Firefox', 'firefox'),
        ('쿠키 파일(cookies.txt)', 'file'),
    ]

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode('light')
        ctk.set_default_color_theme('blue')
        self.title(APP_TITLE)
        self.geometry('760x790')
        self.minsize(680, 700)
        self.configure(fg_color=BG)
        self._set_window_icon()

        self.font_title = ctk.CTkFont(family='Malgun Gothic', size=15, weight='bold')
        self.font_label = ctk.CTkFont(family='Malgun Gothic', size=13)
        self.font_body = ctk.CTkFont(family='Malgun Gothic', size=13)
        self.font_btn = ctk.CTkFont(family='Malgun Gothic', size=14, weight='bold')

        self.msg_queue = queue.Queue()
        self.download_thread = None
        self.cancel_flag = threading.Event()

        self.format_var = tk.StringVar(value=self.FORMAT_PRESETS[0][0])
        self.allow_av1_var = tk.BooleanVar(value=False)
        self.folder_var = tk.StringVar(value=os.path.join(os.path.expanduser('~'), 'Downloads'))
        # 추가 기능용 상태
        self.playlist_var = tk.BooleanVar(value=False)
        self.clip_var = tk.BooleanVar(value=False)
        self.clip_start_var = tk.StringVar(value='')
        self.clip_end_var = tk.StringVar(value='')
        self.subs_var = tk.StringVar(value=self.SUBS_OPTIONS[0][0])
        self.subs_lang_var = tk.StringVar(value='ko,en')
        self.cookie_var = tk.StringVar(value=self.COOKIE_OPTIONS[0][0])
        self.cookie_file_var = tk.StringVar(value='')

        self._build_ui()
        self._enable_clipboard_shortcuts()
        self._log_ytdlp_version()
        self.after(100, self._poll_queue)

        if yt_dlp is None:
            messagebox.showerror(
                APP_TITLE,
                'yt-dlp 가 설치되어 있지 않습니다.\n\n터미널에서 다음을 실행하세요:\n    pip install yt-dlp',
            )

    def _set_window_icon(self):
        try:
            ico = resource_path('icon.ico')
            png = resource_path('icon.png')
            if os.name == 'nt' and os.path.exists(ico):
                self.iconbitmap(ico)
                return
            if os.path.exists(png):
                self._icon_img = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_img)
                return
        except Exception:
            pass

    def _log_ytdlp_version(self):
        """시작 시 사용 중인 yt-dlp 버전/출처를 로그에 남긴다(검증용 파일도 기록)."""
        try:
            if yt_dlp is None:
                return
            ver = getattr(getattr(yt_dlp, 'version', None), '__version__', '?')
            src = '자동 최신화' if _YTDLP_UPDATED else '내장'
            self._log(f'Video Downloader v{APP_VERSION} · yt-dlp {ver} ({src}) · YouTube / 치지직 / SOOP')
            try:
                with open(os.path.join(_ytdlp_cache_dir(), 'last_run.txt'), 'w', encoding='utf-8') as f:
                    f.write(f'version={ver}\nfile={getattr(yt_dlp, "__file__", "?")}\nupdated={_YTDLP_UPDATED}\n')
            except Exception:
                pass
        except Exception:
            pass

    def _enable_clipboard_shortcuts(self):
        """붙여넣기/복사/잘라내기를 확실히 지원합니다.

        macOS 에서 한글 등 비-라틴 입력소스가 켜져 있으면 ⌘+V 의 keysym 이 달라져
        Tk 기본 붙여넣기 바인딩이 동작하지 않는 문제가 있습니다. 그래서
        (1) 키보드 레이아웃과 무관한 **우클릭 컨텍스트 메뉴** 를 기본 제공하고,
        (2) ⌘/Ctrl 단축키도 위젯 레벨에서 직접(클립보드 수동) 처리합니다."""

        def _del_sel(w):
            try:
                w.delete('sel.first', 'sel.last')
            except Exception:
                pass

        def do_paste(w):
            try:
                text = self.clipboard_get()
            except Exception:
                return
            try:
                _del_sel(w)
                w.insert('insert', text)
            except Exception:
                pass

        def do_copy(w):
            try:
                sel = w.get('sel.first', 'sel.last')
            except Exception:
                sel = ''
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)

        def do_cut(w):
            do_copy(w)
            _del_sel(w)

        def do_select_all(w):
            try:
                if isinstance(w, tk.Text):
                    w.tag_add('sel', '1.0', 'end-1c')
                else:
                    w.select_range(0, 'end')
            except Exception:
                pass

        # 우클릭 컨텍스트 메뉴 (현재 위젯 대상)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='잘라내기', command=lambda: do_cut(self._ctx_widget))
        menu.add_command(label='복사', command=lambda: do_copy(self._ctx_widget))
        menu.add_command(label='붙여넣기', command=lambda: do_paste(self._ctx_widget))
        menu.add_separator()
        menu.add_command(label='전체 선택', command=lambda: do_select_all(self._ctx_widget))
        self._ctx_widget = None

        def popup(e):
            self._ctx_widget = e.widget
            try:
                e.widget.focus_set()
            except Exception:
                pass
            try:
                menu.tk_popup(e.x_root, e.y_root)
            finally:
                menu.grab_release()
            return 'break'

        is_mac = sys.platform == 'darwin'

        def wire(w):
            # ⌘(mac)/Ctrl(그 외) 단축키 — 위젯 레벨 + break 로 기본동작 중복 방지
            mod = 'Command' if is_mac else 'Control'
            for keys, fn in (('vV', do_paste), ('cC', do_copy), ('xX', do_cut), ('aA', do_select_all)):
                for k in keys:
                    w.bind(f'<{mod}-{k}>', lambda e, f=fn: (f(e.widget), 'break')[1])
            # 우클릭: mac 은 Button-2 / Control-클릭, 공통 Button-3
            for seq in ('<Button-3>', '<Button-2>', '<Control-Button-1>'):
                w.bind(seq, popup)

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, (tk.Entry, tk.Text)):
                    wire(child)
                walk(child)

        walk(self)

    def _icon(self, name, size):
        """icons/<name>.png 를 CTkImage 로 로드 (없으면 None)."""
        if Image is None:
            return None
        path = resource_path(os.path.join('icons', name + '.png'))
        if not os.path.exists(path):
            return None
        img = Image.open(path)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

    def _card(self, parent):
        """둥근 흰색 카드 프레임."""
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18, border_width=1, border_color=BORDER)

    def _heading(self, parent, icon_name, text):
        row = ctk.CTkFrame(parent, fg_color='transparent')
        ctk.CTkLabel(
            row,
            text='  ' + text,
            font=self.font_title,
            text_color=HEADING,
            image=self._icon(icon_name, 22),
            compound='left',
        ).pack(side='left')
        return row

    def _build_ui(self):
        outer = ctk.CTkFrame(self, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=18, pady=14)

        # ── URL 카드 ────────────────────────────────────────────────
        card_url = self._card(outer)
        card_url.pack(fill='x', pady=(0, 14))
        head = self._heading(card_url, 'link', '동영상 URL (여러 개는 줄바꿈으로 구분)')
        head.pack(fill='x', padx=18, pady=(14, 0))
        ctk.CTkButton(
            head,
            text='',
            image=self._icon('help', 22),
            width=30,
            height=30,
            corner_radius=15,
            fg_color='transparent',
            hover_color='#EAF0F8',
            command=self._show_help,
        ).pack(side='right')
        self.url_text = ctk.CTkTextbox(
            card_url,
            height=92,
            font=self.font_body,
            corner_radius=12,
            border_width=1,
            border_color='#CFE0FB',
            fg_color='#FFFFFF',
            text_color=HEADING,
        )
        self.url_text.pack(fill='x', padx=18, pady=(8, 16))
        self._add_placeholder(
            self.url_text,
            'YouTube · 치지직(다시보기/클립) · SOOP(다시보기/클립) URL을 입력하세요…')

        # ── 옵션 카드 ───────────────────────────────────────────────
        card_opt = self._card(outer)
        card_opt.pack(fill='x', pady=(0, 14))
        self._heading(card_opt, 'gear', '옵션').pack(fill='x', padx=18, pady=(14, 6))

        grid = ctk.CTkFrame(card_opt, fg_color='transparent')
        grid.pack(fill='x', padx=18, pady=(0, 16))
        grid.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            grid,
            text='  저장 폴더',
            font=self.font_label,
            text_color=HEADING,
            image=self._icon('folder', 20),
            compound='left',
        ).grid(row=0, column=0, sticky='w', pady=8, padx=(0, 14))
        self.folder_entry = ctk.CTkEntry(
            grid,
            textvariable=self.folder_var,
            font=self.font_body,
            height=42,
            corner_radius=10,
            fg_color='#FFFFFF',
            border_color=BORDER,
        )
        self.folder_entry.grid(row=0, column=1, sticky='ew', pady=8)
        ctk.CTkButton(
            grid,
            text='  찾아보기…',
            image=self._icon('folder_blue', 18),
            compound='left',
            width=140,
            height=42,
            corner_radius=10,
            font=self.font_label,
            fg_color='#FFFFFF',
            text_color=ACCENT,
            border_width=1,
            border_color='#D8E3F5',
            hover_color='#F2F6FF',
            command=self._choose_folder,
        ).grid(row=0, column=2, padx=(12, 0), pady=8)

        ctk.CTkLabel(
            grid,
            text='  화질/형식',
            font=self.font_label,
            text_color=HEADING,
            image=self._icon('video', 20),
            compound='left',
        ).grid(row=1, column=0, sticky='w', pady=8, padx=(0, 14))
        self.format_menu = ctk.CTkComboBox(
            grid,
            variable=self.format_var,
            values=[p[0] for p in self.FORMAT_PRESETS],
            font=self.font_body,
            height=42,
            corner_radius=10,
            state='readonly',
            fg_color='#FFFFFF',
            text_color=HEADING,
            border_color=BORDER,
            button_color='#FFFFFF',
            button_hover_color='#EEF3FB',
            dropdown_fg_color='#FFFFFF',
            dropdown_text_color=HEADING,
            dropdown_hover_color='#EAF1FB',
            command=lambda _=None: self._sync_option_states(),
        )
        self.format_menu.grid(row=1, column=1, columnspan=2, sticky='ew', pady=8)

        self.av1_check = ctk.CTkCheckBox(
            grid,
            text='  AV1/VP9 허용 (4K 등 초고화질 / 미체크 시 H.264 MP4 우선)',
            variable=self.allow_av1_var,
            font=self.font_body,
            text_color='#55606E',
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            checkbox_width=20,
            checkbox_height=20,
            command=self._sync_option_states,
        )
        self.av1_check.grid(row=2, column=1, columnspan=2, sticky='w', pady=(4, 2))

        # ── 자막 ────────────────────────────────────────────────────
        ctk.CTkLabel(
            grid,
            text='  자막',
            font=self.font_label,
            text_color=HEADING,
            image=self._icon('subs', 20),
            compound='left',
        ).grid(row=3, column=0, sticky='w', pady=8, padx=(0, 14))
        subs_row = ctk.CTkFrame(grid, fg_color='transparent')
        subs_row.grid(row=3, column=1, columnspan=2, sticky='ew', pady=8)
        self.subs_menu = ctk.CTkComboBox(
            subs_row,
            variable=self.subs_var,
            values=[o[0] for o in self.SUBS_OPTIONS],
            font=self.font_body,
            height=42,
            width=180,
            corner_radius=10,
            state='readonly',
            fg_color='#FFFFFF',
            text_color=HEADING,
            border_color=BORDER,
            button_color='#FFFFFF',
            button_hover_color='#EEF3FB',
            dropdown_fg_color='#FFFFFF',
            dropdown_text_color=HEADING,
            dropdown_hover_color='#EAF1FB',
            command=lambda _=None: self._sync_option_states(),
        )
        self.subs_menu.pack(side='left')
        self.subs_lang_entry = ctk.CTkEntry(
            subs_row,
            textvariable=self.subs_lang_var,
            font=self.font_body,
            height=42,
            width=120,
            corner_radius=10,
            fg_color='#FFFFFF',
            border_color=BORDER,
            placeholder_text='ko,en',
        )
        self.subs_lang_entry.pack(side='left', padx=(10, 0))
        ctk.CTkLabel(
            subs_row, text='  언어(쉼표 구분, 자동자막 포함)', font=self.font_body, text_color=SUBTLE
        ).pack(side='left', padx=(8, 0))

        # ── 재생구간 잘라받기 ───────────────────────────────────────
        self.clip_check = ctk.CTkCheckBox(
            grid,
            text='  구간 잘라받기',
            variable=self.clip_var,
            font=self.font_body,
            text_color='#55606E',
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            checkbox_width=20,
            checkbox_height=20,
            command=self._sync_option_states,
        )
        self.clip_check.grid(row=4, column=0, sticky='w', pady=8, padx=(0, 14))
        clip_row = ctk.CTkFrame(grid, fg_color='transparent')
        clip_row.grid(row=4, column=1, columnspan=2, sticky='ew', pady=8)
        self.clip_start_entry = ctk.CTkEntry(
            clip_row, textvariable=self.clip_start_var, font=self.font_body,
            height=42, width=90, corner_radius=10, fg_color='#FFFFFF',
            border_color=BORDER, placeholder_text='시작',
        )
        self.clip_start_entry.pack(side='left')
        ctk.CTkLabel(clip_row, text='  ~  ', font=self.font_body, text_color=SUBTLE).pack(side='left')
        self.clip_end_entry = ctk.CTkEntry(
            clip_row, textvariable=self.clip_end_var, font=self.font_body,
            height=42, width=90, corner_radius=10, fg_color='#FFFFFF',
            border_color=BORDER, placeholder_text='끝',
        )
        self.clip_end_entry.pack(side='left')
        ctk.CTkLabel(
            clip_row, text='  예: 1:30  ·  빈칸이면 처음/끝까지', font=self.font_body, text_color=SUBTLE
        ).pack(side='left', padx=(8, 0))

        # ── 플레이리스트 ────────────────────────────────────────────
        self.playlist_check = ctk.CTkCheckBox(
            grid,
            text='  재생목록 전체 받기 (하위폴더 + 순번으로 저장)',
            variable=self.playlist_var,
            font=self.font_body,
            text_color='#55606E',
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            checkbox_width=20,
            checkbox_height=20,
        )
        self.playlist_check.grid(row=5, column=1, columnspan=2, sticky='w', pady=(2, 4))

        # ── 로그인 쿠키 (성인 인증 / 구독자 전용) ──────────────────
        ctk.CTkLabel(
            grid,
            text='  로그인 쿠키',
            font=self.font_label,
            text_color=HEADING,
            image=self._icon('folder_blue', 20),
            compound='left',
        ).grid(row=6, column=0, sticky='w', pady=8, padx=(0, 14))
        cookie_row = ctk.CTkFrame(grid, fg_color='transparent')
        cookie_row.grid(row=6, column=1, columnspan=2, sticky='ew', pady=8)
        self.cookie_menu = ctk.CTkComboBox(
            cookie_row,
            variable=self.cookie_var,
            values=[o[0] for o in self.COOKIE_OPTIONS],
            font=self.font_body,
            height=42,
            width=200,
            corner_radius=10,
            state='readonly',
            fg_color='#FFFFFF',
            text_color=HEADING,
            border_color=BORDER,
            button_color='#FFFFFF',
            button_hover_color='#EEF3FB',
            dropdown_fg_color='#FFFFFF',
            dropdown_text_color=HEADING,
            dropdown_hover_color='#EAF1FB',
            command=lambda _=None: self._sync_option_states(),
        )
        self.cookie_menu.pack(side='left')
        self.cookie_file_btn = ctk.CTkButton(
            cookie_row,
            text='파일…',
            width=70,
            height=42,
            corner_radius=10,
            font=self.font_label,
            fg_color='#FFFFFF',
            text_color=ACCENT,
            border_width=1,
            border_color='#D8E3F5',
            hover_color='#F2F6FF',
            command=self._choose_cookie_file,
        )
        self.cookie_file_btn.pack(side='left', padx=(10, 0))
        self.cookie_hint = ctk.CTkLabel(
            cookie_row, text='  성인 인증·구독자 전용 영상일 때만', font=self.font_body, text_color=SUBTLE
        )
        self.cookie_hint.pack(side='left', padx=(8, 0))

        self._sync_option_states()

        # ── 버튼 ────────────────────────────────────────────────────
        btns = ctk.CTkFrame(outer, fg_color='transparent')
        btns.pack(side='bottom', fill='x', pady=(14, 0))
        self.download_btn = ctk.CTkButton(
            btns,
            text='   다운로드 시작',
            image=self._icon('download', 22),
            compound='left',
            font=self.font_btn,
            height=52,
            width=210,
            corner_radius=14,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._start_download,
        )
        self.download_btn.pack(side='left')
        self.cancel_btn = ctk.CTkButton(
            btns,
            text='✕   취소',
            font=self.font_btn,
            height=52,
            width=130,
            corner_radius=14,
            fg_color='#FFFFFF',
            text_color='#55606E',
            border_width=1,
            border_color=BORDER,
            hover_color='#F2F5FA',
            command=self._cancel_download,
            state='disabled',
        )
        self.cancel_btn.pack(side='left', padx=12)

        # ── 진행 상태 카드 ──────────────────────────────────────────
        card_prog = self._card(outer)
        card_prog.pack(fill='both', expand=True)
        self._heading(card_prog, 'activity', '진행 상태').pack(fill='x', padx=18, pady=(14, 6))

        prow = ctk.CTkFrame(card_prog, fg_color='transparent')
        prow.pack(fill='x', padx=18)
        self.progress = ctk.CTkProgressBar(prow, height=10, corner_radius=6, progress_color=ACCENT)
        self.progress.pack(side='left', fill='x', expand=True)
        self.progress.set(0)
        self.pct_label = ctk.CTkLabel(prow, text='0%', font=self.font_label, text_color=ACCENT, width=44)
        self.pct_label.pack(side='right', padx=(10, 0))

        self.status_label = ctk.CTkLabel(
            card_prog, text='대기 중', font=self.font_body, text_color=SUBTLE, anchor='w'
        )
        self.status_label.pack(fill='x', padx=18, pady=(8, 4))

        self.log_text = ctk.CTkTextbox(
            card_prog,
            font=self.font_body,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
            fg_color='#FFFFFF',
            text_color='#55606E',
        )
        self.log_text.pack(fill='both', expand=True, padx=18, pady=(0, 16))
        self._add_placeholder(self.log_text, '진행 상태가 여기에 표시됩니다…')

        if not has_ffmpeg():
            self._log('⚠ ffmpeg 를 찾지 못했습니다. 고화질 병합/MP3 변환이 제한됩니다.')

    def _add_placeholder(self, textbox, text):
        """CTkTextbox 에 간단한 플레이스홀더를 구현합니다."""
        textbox._ph_text = text
        textbox._ph_active = True
        textbox.insert('1.0', text)
        textbox.configure(text_color=SUBTLE)

        def on_focus_in(_):
            if getattr(textbox, '_ph_active', False):
                textbox.delete('1.0', 'end')
                textbox.configure(text_color=HEADING)
                textbox._ph_active = False

        def on_focus_out(_):
            if not textbox.get('1.0', 'end').strip():
                textbox.insert('1.0', textbox._ph_text)
                textbox.configure(text_color=SUBTLE)
                textbox._ph_active = True

        textbox.bind('<FocusIn>', on_focus_in)
        textbox.bind('<FocusOut>', on_focus_out)

    def _textbox_value(self, textbox):
        if getattr(textbox, '_ph_active', False):
            return ''
        return textbox.get('1.0', 'end')

    def _show_help(self):
        messagebox.showinfo(
            APP_TITLE,
            "사용법\n\n"
            "1) 동영상 URL 을 입력합니다 (여러 개는 줄바꿈으로 구분).\n"
            "2) 저장 폴더와 화질/형식을 선택합니다.\n"
            "3) [다운로드 시작] 을 누릅니다.\n\n"
            "지원 사이트\n"
            "• YouTube — 영상 / 재생목록 / 쇼츠\n"
            "• 치지직 — 다시보기(chzzk.naver.com/video/…) / 클립(chzzk.naver.com/clips/…)\n"
            "• SOOP — 다시보기·클립(vod.sooplive.co.kr/player/…)\n"
            "  (생방송 녹화는 지원하지 않습니다. 다시보기 URL 을 넣어 주세요.)\n\n"
            "• 기본은 H.264(MP4) 우선이라 호환성이 좋습니다 (보통 최대 1080p).\n"
            "• 4K 등 초고화질이 필요하면 'AV1/VP9 허용' 을 체크하세요.\n"
            "• '음성만 (MP3)' 으로 오디오만 추출할 수 있습니다.\n"
            "• 성인 인증·구독자 전용 영상은 '로그인 쿠키' 에서 로그인된 브라우저를 고르세요.\n"
            "  (Chrome 이 안 되면 Firefox 나 cookies.txt 파일을 써 보세요.)",
        )

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.expanduser('~'))
        if folder:
            self.folder_var.set(folder)

    def _current_subs_mode(self):
        label = self.subs_var.get()
        return next((mode for name, mode in self.SUBS_OPTIONS if name == label), 'none')

    def _sync_option_states(self):
        """포맷/체크박스 상태에 따라 관련 입력칸을 활성/비활성화합니다."""
        is_audio = '음성만' in self.format_var.get()
        # 자막은 영상에만 의미가 있음
        self.subs_menu.configure(state='disabled' if is_audio else 'readonly')
        if is_audio:
            self.subs_var.set(self.SUBS_OPTIONS[0][0])
        subs_on = (not is_audio) and self._current_subs_mode() != 'none'
        self.subs_lang_entry.configure(state='normal' if subs_on else 'disabled')
        # 구간 입력칸
        clip_on = self.clip_var.get()
        self.clip_start_entry.configure(state='normal' if clip_on else 'disabled')
        self.clip_end_entry.configure(state='normal' if clip_on else 'disabled')
        # 쿠키 파일 선택 버튼은 '쿠키 파일' 모드에서만
        mode = self._current_cookie_mode()
        self.cookie_file_btn.configure(state='normal' if mode == 'file' else 'disabled')
        if mode == 'file':
            path = self.cookie_file_var.get()
            self.cookie_hint.configure(text=f'  {os.path.basename(path)}' if path else '  cookies.txt 파일을 선택하세요')
        elif mode:
            self.cookie_hint.configure(text=f'  {self.cookie_var.get()} 에 네이버/SOOP 로그인이 되어 있어야 합니다')
        else:
            self.cookie_hint.configure(text='  성인 인증·구독자 전용 영상일 때만')

    def _current_cookie_mode(self):
        label = self.cookie_var.get()
        return next((mode for name, mode in self.COOKIE_OPTIONS if name == label), None)

    def _choose_cookie_file(self):
        path = filedialog.askopenfilename(
            title='cookies.txt 선택',
            filetypes=[('쿠키 파일', '*.txt'), ('모든 파일', '*.*')],
        )
        if path:
            self.cookie_file_var.set(path)
        self._sync_option_states()

    @staticmethod
    def _fmt_secs(sec):
        sec = int(round(sec))
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

    @staticmethod
    def _parse_time(text):
        """'90' / '1:30' / '1:02:03' → 초(float). 빈칸이면 None, 형식오류면 False."""
        text = (text or '').strip()
        if not text:
            return None
        try:
            parts = [float(p) for p in text.split(':')]
        except ValueError:
            return False
        seconds = 0.0
        for p in parts:
            seconds = seconds * 60 + p
        return seconds

    def _start_download(self):
        if yt_dlp is None:
            messagebox.showerror(APP_TITLE, 'yt-dlp 가 설치되어 있지 않습니다.')
            return
        urls = [u.strip() for u in self._textbox_value(self.url_text).splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning(APP_TITLE, '다운로드할 URL 을 입력하세요.')
            return
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning(APP_TITLE, '저장 폴더를 선택하세요.')
            return
        os.makedirs(folder, exist_ok=True)

        preset = next(p for p in self.FORMAT_PRESETS if p[0] == self.format_var.get())
        prefer_h264 = not self.allow_av1_var.get()

        # 구간 잘라받기 옵션 파싱/검증
        clip = None
        if self.clip_var.get():
            start = self._parse_time(self.clip_start_var.get())
            end = self._parse_time(self.clip_end_var.get())
            if start is False or end is False:
                messagebox.showwarning(APP_TITLE, "구간 시간 형식이 올바르지 않습니다.\n예: 90  ·  1:30  ·  1:02:03")
                return
            if start is None and end is None:
                messagebox.showwarning(APP_TITLE, '구간 잘라받기를 켰다면 시작 또는 끝 시간을 입력하세요.')
                return
            if start is not None and end is not None and end <= start:
                messagebox.showwarning(APP_TITLE, '끝 시간은 시작 시간보다 커야 합니다.')
                return
            clip = (start if start is not None else 0.0,
                    end if end is not None else float('inf'))

        cookie_mode = self._current_cookie_mode()
        cookie_file = self.cookie_file_var.get().strip()
        if cookie_mode == 'file' and not os.path.isfile(cookie_file):
            messagebox.showwarning(APP_TITLE, "'쿠키 파일' 을 골랐다면 cookies.txt 파일을 선택하세요.")
            return

        extra = {
            'playlist': self.playlist_var.get(),
            'clip': clip,
            'subs': self._current_subs_mode(),
            'subs_langs': self.subs_lang_var.get(),
            'cookies': (cookie_mode, cookie_file),
        }

        self.cancel_flag.clear()
        self.download_btn.configure(state='disabled')
        self.cancel_btn.configure(state='normal')
        self.progress.set(0)
        self.pct_label.configure(text='0%')
        self._clear_log()

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(urls, folder, preset, prefer_h264, extra),
            daemon=True,
        )
        self.download_thread.start()

    def _cancel_download(self):
        self.cancel_flag.set()
        self.status_label.configure(text='취소 요청됨… 현재 항목 종료 후 중단합니다.')

    def _download_worker(self, urls, folder, preset, prefer_h264, extra=None):
        extra = extra or {}
        playlist = bool(extra.get('playlist'))
        clip = extra.get('clip')
        subs_mode = extra.get('subs', 'none')
        subs_langs = extra.get('subs_langs', 'ko,en')

        label, fmt, needs_ffmpeg = preset
        is_audio = '음성만' in label
        ffmpeg_ok = has_ffmpeg()
        if needs_ffmpeg and not ffmpeg_ok:
            self.msg_queue.put(('log', f"⚠ '{label}' 은 ffmpeg 가 필요합니다. '단일 파일' 방식으로 대체합니다."))
            fmt = 'best'
            is_audio = False
        # 구간/자막 후처리도 ffmpeg 가 필요
        if clip and not ffmpeg_ok:
            self.msg_queue.put(('log', '⚠ 구간 잘라받기는 ffmpeg 가 필요합니다. 전체 영상으로 받습니다.'))
            clip = None
        if subs_mode == 'embed' and not ffmpeg_ok:
            self.msg_queue.put(('log', '⚠ 자막 입히기는 ffmpeg 가 필요합니다. 자막 파일(SRT)로 대체합니다.'))
            subs_mode = 'file'

        def hook(d):
            if self.cancel_flag.is_set():
                raise yt_dlp.utils.DownloadError('사용자에 의해 취소됨')
            status = d.get('status')
            if status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                pct = downloaded / total * 100 if total else 0
                speed = d.get('speed') or 0
                self.msg_queue.put(('progress', pct))
                self.msg_queue.put(('status', f'다운로드 중… {pct:5.1f}%  ({speed / 1024 / 1024:.2f} MB/s)'))
                return
            if status == 'finished':
                self.msg_queue.put(('status', '후처리 중… (병합/변환)'))
                return

        if playlist:
            outtmpl = os.path.join(folder, '%(playlist_title)s', '%(playlist_index)s. %(title)s.%(ext)s')
        else:
            outtmpl = os.path.join(folder, '%(title)s.%(ext)s')

        ydl_opts = {
            'format': fmt,
            'outtmpl': outtmpl,
            'progress_hooks': [hook],
            'noprogress': True,
            'ignoreerrors': False,
            # restrictfilenames 는 한글을 전부 '_' 로 바꿔 '피파랜드 (part 1)' → 'part_1' 이 되고
            # 같은 이름끼리 덮어쓰기/건너뛰기가 난다. 한글은 살리고 Windows 금지문자만 치환.
            'restrictfilenames': False,
            'windowsfilenames': True,
            # 치지직 HLS 는 재작성한 로컬 플레이리스트(file:)를 ffmpeg 에 넘긴다 (_chzzk_hls_format 참고)
            'enable_file_urls': True,
            # HLS 조각을 병렬로 받아 속도 확보 (치지직/SOOP 다시보기는 전부 HLS)
            'concurrent_fragment_downloads': 6,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': not playlist,
        }
        cookie_mode, cookie_file = (extra or {}).get('cookies') or (None, '')
        if cookie_mode == 'file' and cookie_file:
            ydl_opts['cookiefile'] = cookie_file
            self.msg_queue.put(('log', f'쿠키: 파일 {os.path.basename(cookie_file)}'))
        elif cookie_mode:
            ydl_opts['cookiesfrombrowser'] = (cookie_mode,)
            self.msg_queue.put(('log', f'쿠키: {cookie_mode} 브라우저에서 읽기'))
        if prefer_h264 and not is_audio:
            # 순서 주의: h264 선호(vcodec) → 해상도(res) → aac 선호(acodec).
            # 예전엔 ['vcodec:h264','acodec:aac'] 라 acodec 이 res 보다 우선순위가 높아,
            # 고해상도 영상전용 스트림 대신 저해상도 muxed(H.264+AAC) 스트림이 뽑혀
            # 720p(영상에 따라 360p)로 떨어졌다. res 를 acodec 앞에 넣어 해결.
            ydl_opts['format_sort'] = ['vcodec:h264', 'res', 'acodec:aac']
            if ffmpeg_ok:
                ydl_opts['merge_output_format'] = 'mp4'
        _ff = ffmpeg_dir()
        if _ff:
            ydl_opts['ffmpeg_location'] = _ff

        postprocessors = []
        if is_audio and ffmpeg_ok:
            postprocessors.append(
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}
            )

        # 구간 잘라받기
        if clip:
            from yt_dlp.utils import download_range_func
            ydl_opts['download_ranges'] = download_range_func(None, [clip])
            ydl_opts['force_keyframes_at_cuts'] = True
            s, e = clip
            rng = f"{self._fmt_secs(s)} ~ {'끝' if e == float('inf') else self._fmt_secs(e)}"
            self.msg_queue.put(('log', f'구간: {rng}'))

        # 자막 (영상에만)
        if not is_audio and subs_mode != 'none':
            langs = [l.strip() for l in subs_langs.split(',') if l.strip()] or ['ko', 'en']
            ydl_opts['writesubtitles'] = True
            ydl_opts['writeautomaticsub'] = True
            ydl_opts['subtitleslangs'] = langs
            if subs_mode == 'file':
                ydl_opts['subtitlesformat'] = 'srt/best'
                postprocessors.append({'key': 'FFmpegSubtitlesConvertor', 'format': 'srt'})
                self.msg_queue.put(('log', f"자막: 파일(SRT) [{', '.join(langs)}]"))
            else:  # embed
                postprocessors.append({'key': 'FFmpegEmbedSubtitle'})
                self.msg_queue.put(('log', f"자막: 영상에 입히기 [{', '.join(langs)}]"))

        if postprocessors:
            ydl_opts['postprocessors'] = postprocessors

        if not is_audio:
            mode = 'H.264(MP4) 우선' if prefer_h264 else 'AV1/VP9 허용(최고화질)'
            self.msg_queue.put(('log', f'코덱: {mode}'))
        if playlist:
            self.msg_queue.put(('log', '재생목록 전체 다운로드 모드'))

        total_count = len(urls)
        success = 0
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for idx, url in enumerate(urls, 1):
                if self.cancel_flag.is_set():
                    break
                platform = detect_platform(url)
                self.msg_queue.put(('log', f'[{idx}/{total_count}] {(platform + " · ") if platform else ""}{url}'))
                self.msg_queue.put(('progress', 0))
                if LIVE_URL_RE.search(url):
                    self.msg_queue.put(('log', '   ✗ 생방송 URL 은 지원하지 않습니다. 다시보기/클립 URL 을 넣어 주세요.'))
                    continue
                try:
                    info = None
                    if platform == '치지직':
                        info = self._download_chzzk(ydl, url)
                    if info is None:
                        info = ydl.extract_info(url, download=True)
                    if info is not None:
                        title = info.get('title', url)
                        self.msg_queue.put(('log', f'   ✓ 완료: {title}'))
                        success += 1
                    else:
                        self.msg_queue.put(('log', '   ✗ 실패 (정보 추출 불가)'))
                except yt_dlp.utils.DownloadError as e:
                    if self.cancel_flag.is_set():
                        self.msg_queue.put(('log', '   ■ 취소됨'))
                        break
                    self.msg_queue.put(('log', f'   ✗ 오류: {e}'))
                except ChzzkError as e:
                    self.msg_queue.put(('log', f'   ✗ 치지직: {e}'))
                except Exception as e:
                    self.msg_queue.put(('log', f'   ✗ 오류: {e}'))

        if self.cancel_flag.is_set():
            done_msg = f'중단됨 ({success}/{total_count} 완료)'
        else:
            done_msg = f'완료: {success}/{total_count} 개 다운로드'
        self.msg_queue.put(('done', done_msg))

    def _download_chzzk(self, ydl, url):
        """치지직 다시보기/클립을 자체 추출기로 받는다. 자체 추출이 불가능하면 None
        (→ 호출 측이 yt-dlp 내장 추출기로 시도). 사용자용 오류는 ChzzkError 로 전파."""
        try:
            ie_result = chzzk_extract(ydl, url)
        except ChzzkError:
            raise
        except Exception as e:  # 네트워크/API 변경 등 → 내장 추출기로 폴백
            self.msg_queue.put(('log', f'   · 자체 추출 실패({e.__class__.__name__}), yt-dlp 내장 추출기로 재시도'))
            return None
        if ie_result is None:
            return None
        ie = ydl.get_info_extractor('CHZZKVideo')
        ydl.add_default_extra_info(ie_result, ie, url)
        n_hls = sum(1 for f in ie_result['formats'] if f.get('protocol') == 'm3u8_native')
        n_http = sum(1 for f in ie_result['formats'] if f.get('ext') == 'mp4' and f.get('protocol') == 'https')
        self.msg_queue.put(('log', f"   · 치지직: {ie_result.get('title')}  (MP4 {n_http}개 · HLS {n_hls}개)"))
        return ydl.process_ie_result(ie_result, download=True)

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == 'progress':
                    self.progress.set(payload / 100)
                    self.pct_label.configure(text=f'{int(payload)}%')
                elif kind == 'status':
                    self.status_label.configure(text=payload)
                elif kind == 'log':
                    self._log(payload)
                elif kind == 'done':
                    self.status_label.configure(text=payload)
                    self.progress.set(0)
                    self.pct_label.configure(text='0%')
                    self.download_btn.configure(state='normal')
                    self.cancel_btn.configure(state='disabled')
                    self._log('─' * 40)
                    self._log(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _log(self, text):
        if getattr(self.log_text, '_ph_active', False):
            self.log_text.delete('1.0', 'end')
            self.log_text.configure(text_color='#55606E')
            self.log_text._ph_active = False
        self.log_text.insert('end', text + '\n')
        self.log_text.see('end')

    def _clear_log(self):
        self.log_text.delete('1.0', 'end')
        self.log_text._ph_active = False


def main():
    app = DownloaderApp()
    app.mainloop()


if __name__ == '__main__':
    main()
