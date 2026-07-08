"""
YouTube Downloader - 단독 실행형 GUI 다운로더 (모던 UI / CustomTkinter)

- 별도의 서버가 필요 없습니다. yt-dlp 라이브러리를 직접 호출합니다.
- CustomTkinter 기반의 모던 GUI (둥근 카드 / 컬러 버튼).
- PyInstaller 로 단일 실행파일(.exe / 바이너리)로 빌드할 수 있습니다.

필요 패키지:
    pip install yt-dlp customtkinter

(선택) 고화질 영상+오디오 병합 및 mp3 변환에는 ffmpeg 가 필요합니다.
ffmpeg 가 없으면 단일 포맷(병합 불필요) 다운로드만 사용됩니다.
"""
import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

APP_TITLE = 'YouTube Downloader'
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


class DownloaderApp(ctk.CTk):
    """CustomTkinter 기반 메인 윈도우."""

    FORMAT_PRESETS = [
        ('최고 화질 (영상+음성)', 'bestvideo*+bestaudio/best', True),
        ('1080p 이하', 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', True),
        ('720p 이하', 'bestvideo[height<=720]+bestaudio/best[height<=720]', True),
        ('단일 파일(최고, 병합 불필요)', 'best', False),
        ('음성만 (MP3)', 'bestaudio/best', True),
    ]

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode('light')
        ctk.set_default_color_theme('blue')
        self.title(APP_TITLE)
        self.geometry('760x720')
        self.minsize(680, 640)
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

        self._build_ui()
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
        self._add_placeholder(self.url_text, '여기에 YouTube 동영상 URL을 입력하세요…')

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
        )
        self.av1_check.grid(row=2, column=1, columnspan=2, sticky='w', pady=(4, 2))

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
            "• 기본은 H.264(MP4) 우선이라 호환성이 좋습니다 (보통 최대 1080p).\n"
            "• 4K 등 초고화질이 필요하면 'AV1/VP9 허용' 을 체크하세요.\n"
            "• '음성만 (MP3)' 으로 오디오만 추출할 수 있습니다.",
        )

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.expanduser('~'))
        if folder:
            self.folder_var.set(folder)

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

        self.cancel_flag.clear()
        self.download_btn.configure(state='disabled')
        self.cancel_btn.configure(state='normal')
        self.progress.set(0)
        self.pct_label.configure(text='0%')
        self._clear_log()

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(urls, folder, preset, prefer_h264),
            daemon=True,
        )
        self.download_thread.start()

    def _cancel_download(self):
        self.cancel_flag.set()
        self.status_label.configure(text='취소 요청됨… 현재 항목 종료 후 중단합니다.')

    def _download_worker(self, urls, folder, preset, prefer_h264):
        label, fmt, needs_ffmpeg = preset
        is_audio = '음성만' in label
        ffmpeg_ok = has_ffmpeg()
        if needs_ffmpeg and not ffmpeg_ok:
            self.msg_queue.put(('log', f"⚠ '{label}' 은 ffmpeg 가 필요합니다. '단일 파일' 방식으로 대체합니다."))
            fmt = 'best'
            is_audio = False

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

        ydl_opts = {
            'format': fmt,
            'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
            'progress_hooks': [hook],
            'noprogress': True,
            'ignoreerrors': False,
            'restrictfilenames': True,
            'quiet': True,
            'no_warnings': True,
        }
        if prefer_h264 and not is_audio:
            ydl_opts['format_sort'] = ['vcodec:h264', 'acodec:aac']
            if ffmpeg_ok:
                ydl_opts['merge_output_format'] = 'mp4'
        _ff = ffmpeg_dir()
        if _ff:
            ydl_opts['ffmpeg_location'] = _ff
        if is_audio and ffmpeg_ok:
            ydl_opts['postprocessors'] = [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}
            ]

        if not is_audio:
            mode = 'H.264(MP4) 우선' if prefer_h264 else 'AV1/VP9 허용(최고화질)'
            self.msg_queue.put(('log', f'코덱: {mode}'))

        total_count = len(urls)
        success = 0
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for idx, url in enumerate(urls, 1):
                if self.cancel_flag.is_set():
                    break
                self.msg_queue.put(('log', f'[{idx}/{total_count}] {url}'))
                self.msg_queue.put(('progress', 0))
                try:
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
                except Exception as e:
                    self.msg_queue.put(('log', f'   ✗ 오류: {e}'))

        if self.cancel_flag.is_set():
            done_msg = f'중단됨 ({success}/{total_count} 완료)'
        else:
            done_msg = f'완료: {success}/{total_count} 개 다운로드'
        self.msg_queue.put(('done', done_msg))

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
