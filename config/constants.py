"""
config/constants.py — константы приложения: интервалы, лимиты, сетевые
параметры, дефолтные URL и CLI-аргументы инструментов.

Только значения (без классов и логики) — модуль ни от чего не зависит.
"""

import os

# ── Константы приложения ──────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 6 * 3600
DEFAULT_MAX_PARALLEL   = 5       # одновременных загрузок по умолчанию (settings.max_parallel)
MAX_PARALLEL_CEILING   = 50      # верхняя граница клампа (защита от опечатки в config.json)
CLIPBOARD_POLL_SECONDS = 1.0     # период опроса буфера обмена (слежение за ссылками)
CLIPBOARD_MAX_CHARS    = 4000    # длиннее — это документ, а не ссылки; игнорируем
ERROR_TAIL_LINES       = 20      # сколько последних строк вывода хранить для диагностики ошибки
CARD_LINGER_SECONDS    = 3       # сколько карточка висит после финала/паузы перед удалением
SEED_LOG_INTERVAL_SECONDS = 600  # как часто логировать строку раздачи aria2 (SEED спамит ~1/с)
PERSIST_DEBOUNCE_SECONDS  = 1.0  # пауза тишины перед записью config.json (правка цвета
                                 # шлёт SettingsChangedEvent на каждый символ)

# ── Сетевые константы (chunk / timeout) ──────────────────────────────────────
YT_DLP_CHUNK_SIZE      = 8_192   # байт/итерацию при скачивании yt-dlp
FFMPEG_CHUNK_SIZE      = 16_384  # байт/итерацию при скачивании ffmpeg zip
ARIA2_CHUNK_SIZE       = 16_384  # байт/итерацию при скачивании aria2 zip
THUMBNAIL_TIMEOUT      = 15.0    # секунд — общий async-таймаут скачивания thumbnail
THUMBNAIL_SOCK_TIMEOUT = 10      # секунд — connect-таймаут httpx для thumbnail

DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads")
DEFAULT_PROXY_ADDRESS = "socks5://127.0.0.1:1080"
# Дополнительные аргументы yt-dlp. Формата (-f) здесь больше НЕТ — выбором
# формата владеют пресеты качества (DEFAULT_QUALITY_PRESETS): при "best" yt-dlp
# использует свой встроенный дефолт bestvideo*+bestaudio/best (тот же результат),
# при явном пресете его -f добавляется после этих аргументов.
DEFAULT_YT_DLP_ARGS   = "--merge-output-format mp4"
# Старый дефолт (формат + контейнер) — для мягкой миграции сохранённых конфигов.
_LEGACY_YT_DLP_ARGS   = "-f bestvideo+bestaudio/best --merge-output-format mp4"

DEFAULT_YT_API_URL          = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DEFAULT_YT_DOWNLOAD_URL     = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    if os.name == "nt" else
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
)
DEFAULT_FFMPEG_VERSION_URL  = "https://www.gyan.dev/ffmpeg/builds/release-version"
DEFAULT_FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"

# aria2 публикует релизы на GitHub. Имя ассета содержит версию
# (aria2-X.Y.Z-win-64bit-buildN.zip), поэтому стабильного "latest"-URL на сам
# zip нет: и проверка версии, и установка идут через releases/latest API —
# Aria2cTool.install() сам находит нужный ассет в ответе. Отсюда оба URL равны.
DEFAULT_ARIA2_VERSION_URL   = "https://api.github.com/repos/aria2/aria2/releases/latest"
DEFAULT_ARIA2_DOWNLOAD_URL  = "https://api.github.com/repos/aria2/aria2/releases/latest"

# Фиксированные CLI-флаги aria2c для скачивания. ВАЖНО (от них зависит логика
# приложения): --summary-interval=0 (парсинг прогресса по \r-строке без спама),
# --auto-save-interval=1 (контрольный .aria2 актуален для pause/resume),
# --continue=true (докачка), --seed-time=0 (не сидировать торрент после докачки).
# Для торрент/metalink-ссылок Aria2cProvider.build_command дополнительно
# добавляет --check-integrity=true (структурно, в коде): докачка брошенной
# загрузки без контрольного .aria2 идёт по хешам кусков, а не с нуля.
DEFAULT_ARIA2_ARGS          = ("--summary-interval=0 --console-log-level=warn "
                               "--continue=true --auto-file-renaming=false "
                               "--allow-overwrite=true --auto-save-interval=1 --seed-time=0")
DEFAULT_ARIA2_PART_DIRNAME  = ".part"   # подпапка временных загрузок в папке назначения
# Флаги РАЗДАЧИ (seed): проверить уже скачанные файлы и раздавать без лимита по
# ratio (0.0 = без лимита), пока пользователь не остановит. --check-integrity нужен,
# т.к. контрольный .aria2 удаляется после докачки (его перемещаем/чистим).
DEFAULT_ARIA2_SEED_ARGS     = ("--summary-interval=0 --console-log-level=warn "
                               "--check-integrity=true --seed-ratio=0.0 --bt-detach-seed-only=false")

# Браузеры для cookies (--cookies-from-browser): (ключ, i18n-ключ имени).
# Единый реестр: дропдаун в настройках и переключатель главного экрана строятся
# из него — добавление браузера не требует правок в экранах.
COOKIE_BROWSERS = [
    ("none",    "cookies_none"),
    ("chrome",  "cookies_chrome"),
    ("yandex",  "cookies_yandex"),
    ("firefox", "cookies_firefox"),
    ("edge",    "cookies_edge"),
    ("opera",   "cookies_opera"),
]
