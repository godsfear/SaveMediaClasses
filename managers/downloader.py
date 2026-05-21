import asyncio
import os
import re
import shlex
import subprocess

from config import safe_str


class Downloader:

    def __init__(self, base_dir: str, tools_dir: str) -> None:
        self.base_dir  = base_dir
        self.tools_dir = tools_dir
        self._ext      = ".exe" if os.name == "nt" else ""

    def resolve_yt_dlp(self) -> str:
        filename = f"yt-dlp{self._ext}"
        p_root   = os.path.join(self.base_dir,  filename)
        p_tools  = os.path.join(self.tools_dir, filename)
        return p_root if os.path.exists(p_root) else (p_tools if os.path.exists(p_tools) else "")

    # Оригинальная сборка команды из start_media_download
    def build_command(self, yt_dlp_exe: str, url: str, download_path: str,
                      proxy_enabled: bool, proxy_address: str,
                      cookies_enabled: bool, cookies_browser: str,
                      playlist_enabled: bool, embed_metadata: bool,
                      audio_only: bool, yt_dlp_args: str,
                      clean_titles: bool, save_to_source: bool) -> list:
        cmd_args = [yt_dlp_exe]

        if proxy_enabled and safe_str(proxy_address).strip():
            cmd_args.extend(["--proxy", safe_str(proxy_address).strip()])

        if cookies_enabled and cookies_browser != "none":
            cmd_args.extend(["--cookies-from-browser", safe_str(cookies_browser)])

        cmd_args.append("--yes-playlist" if playlist_enabled else "--no-playlist")

        if embed_metadata:
            cmd_args.extend(["--embed-metadata", "--embed-thumbnail"])

        if audio_only:
            cmd_args.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        else:
            c_args = safe_str(yt_dlp_args).strip()
            if c_args:
                try:
                    cmd_args.extend(shlex.split(c_args))
                except ValueError:
                    cmd_args.extend(c_args.split())

        is_pl  = "list=" in url.lower() or "playlist" in url.lower()
        t_name = "%(title)s.%(ext)s" if clean_titles else "%(title)s [%(id)s].%(ext)s"
        t_path = os.path.join("%(playlist_title)s", "%(playlist_index)s - " + t_name) if playlist_enabled and is_pl else t_name
        if save_to_source: t_path = os.path.join("%(extractor_key)s", t_path)
        if download_path:  t_path = os.path.join(download_path, t_path)

        cmd_args.extend(["-o", t_path, "--newline", url])
        return cmd_args

    def build_env(self) -> dict:
        env = os.environ.copy()
        sep = ";" if os.name == "nt" else ":"
        env["PATH"] = f"{self.tools_dir}{sep}{self.base_dir}{sep}{env.get('PATH', '')}"
        return env

    # Оригинальный запуск процесса из start_media_download
    async def run(self, cmd_args: list, on_line, on_finish) -> None:
        proc_startup = None
        if os.name == "nt":
            proc_startup = subprocess.STARTUPINFO()
            proc_startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        sub_proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self.build_env(),
            startupinfo=proc_startup
        )

        while True:
            line_raw = await sub_proc.stdout.readline()
            if not line_raw: break
            line_text = line_raw.decode('utf-8', errors='replace').strip()
            if line_text:
                on_line(line_text)

        await sub_proc.wait()
        on_finish(sub_proc.returncode)

    @staticmethod
    def parse_progress(line: str) -> float | None:
        if "[download]" in line and "%" in line:
            match = re.search(r"([0-9.]+)%", line)
            if match:
                try:
                    return float(match.group(1)) / 100.0
                except ValueError:
                    pass
        return None
