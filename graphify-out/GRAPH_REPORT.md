# Graph Report - .  (2026-06-20)

## Corpus Check
- 59 files · ~85,273 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1247 nodes · 3813 edges · 57 communities (51 shown, 6 thin omitted)
- Extraction: 66% EXTRACTED · 34% INFERRED · 0% AMBIGUOUS · INFERRED: 1300 edges (avg confidence: 0.51)
- Token cost: 130,666 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_UI Controllers & Localization|UI Controllers & Localization]]
- [[_COMMUNITY_App Bootstrap & Tools Control|App Bootstrap & Tools Control]]
- [[_COMMUNITY_Config Package & Tool Params|Config Package & Tool Params]]
- [[_COMMUNITY_Tool Spec Abstraction|Tool Spec Abstraction]]
- [[_COMMUNITY_Download Repository (DB)|Download Repository (DB)]]
- [[_COMMUNITY_History Screen|History Screen]]
- [[_COMMUNITY_Notifications & Window Events|Notifications & Window Events]]
- [[_COMMUNITY_Navigation & AppBar|Navigation & AppBar]]
- [[_COMMUNITY_Theme Widget Binding|Theme Widget Binding]]
- [[_COMMUNITY_Orchestrator Tests|Orchestrator Tests]]
- [[_COMMUNITY_Config Manager & Persistence|Config Manager & Persistence]]
- [[_COMMUNITY_Screen & Provider Protocols|Screen & Provider Protocols]]
- [[_COMMUNITY_Download Manager (Concurrency)|Download Manager (Concurrency)]]
- [[_COMMUNITY_Logging & App Services|Logging & App Services]]
- [[_COMMUNITY_Tool Registry & Installers|Tool Registry & Installers]]
- [[_COMMUNITY_Application Paths|Application Paths]]
- [[_COMMUNITY_Provider Tests|Provider Tests]]
- [[_COMMUNITY_Event Bus & Orchestrator|Event Bus & Orchestrator]]
- [[_COMMUNITY_Base Tool Implementation|Base Tool Implementation]]
- [[_COMMUNITY_Config Logic Tests|Config Logic Tests]]
- [[_COMMUNITY_Provider Command Building|Provider Command Building]]
- [[_COMMUNITY_Aria2c Provider|Aria2c Provider]]
- [[_COMMUNITY_yt-dlp Provider|yt-dlp Provider]]
- [[_COMMUNITY_README Features & Stack|README Features & Stack]]
- [[_COMMUNITY_URL Parsing|URL Parsing]]
- [[_COMMUNITY_Logger Adapter & DI|Logger Adapter & DI]]
- [[_COMMUNITY_Binary & Param Configs|Binary & Param Configs]]
- [[_COMMUNITY_Locale Loading & Language|Locale Loading & Language]]
- [[_COMMUNITY_Download Submission API|Download Submission API]]
- [[_COMMUNITY_Main Screen Handlers|Main Screen Handlers]]
- [[_COMMUNITY_Settings Screen UI|Settings Screen UI]]
- [[_COMMUNITY_Subprocess Provider Base|Subprocess Provider Base]]
- [[_COMMUNITY_Theme Config Defaults|Theme Config Defaults]]
- [[_COMMUNITY_Subtitle Parameters|Subtitle Parameters]]
- [[_COMMUNITY_Version Classification|Version Classification]]
- [[_COMMUNITY_Settings Screen Widgets|Settings Screen Widgets]]
- [[_COMMUNITY_Main Screen State Sync|Main Screen State Sync]]
- [[_COMMUNITY_Snapshot Tests|Snapshot Tests]]
- [[_COMMUNITY_Quality Parameters|Quality Parameters]]
- [[_COMMUNITY_Clipboard Monitoring|Clipboard Monitoring]]
- [[_COMMUNITY_Tool Config Accessors|Tool Config Accessors]]
- [[_COMMUNITY_Main GUI Screenshot|Main GUI Screenshot]]
- [[_COMMUNITY_History Screen Screenshot|History Screen Screenshot]]
- [[_COMMUNITY_Download Manager Tests|Download Manager Tests]]
- [[_COMMUNITY_Window Config|Window Config]]
- [[_COMMUNITY_Timeouts Config|Timeouts Config]]
- [[_COMMUNITY_Torrent Bencode Decoder|Torrent Bencode Decoder]]
- [[_COMMUNITY_Aria2c File Finalization|Aria2c File Finalization]]
- [[_COMMUNITY_App Icon Imagery|App Icon Imagery]]
- [[_COMMUNITY_Magnet Info-Hash|Magnet Info-Hash]]
- [[_COMMUNITY_Event Subscription|Event Subscription]]
- [[_COMMUNITY_Provider Factories|Provider Factories]]
- [[_COMMUNITY_Provider URL Resolution|Provider URL Resolution]]
- [[_COMMUNITY_Managers Package|Managers Package]]
- [[_COMMUNITY_Download Snapshot Module|Download Snapshot Module]]
- [[_COMMUNITY_Screens Package|Screens Package]]
- [[_COMMUNITY_Subtitle Preset Test|Subtitle Preset Test]]

## God Nodes (most connected - your core abstractions)
1. `Services` - 84 edges
2. `SettingsChangedEvent` - 81 edges
3. `Locale` - 81 edges
4. `MainScreen` - 80 edges
5. `SettingsScreen` - 69 edges
6. `AppState` - 68 edges
7. `DownloadSnapshot` - 67 edges
8. `AppClosingEvent` - 66 edges
9. `ThemeTarget` - 64 edges
10. `DownloadCompletedEvent` - 60 edges

## Surprising Connections (you probably didn't know these)
- `Page` --uses--> `Services`  [INFERRED]
  controllers/theme_controller.py → services.py
- `E` --uses--> `DownloadSnapshot`  [INFERRED]
  events.py → managers/snapshot.py
- `Aria2cConfig` --uses--> `Locale`  [INFERRED]
  state.py → i18n.py
- `ThemeConfig` --uses--> `Locale`  [INFERRED]
  state.py → i18n.py
- `YtDlpConfig` --uses--> `Locale`  [INFERRED]
  state.py → i18n.py

## Import Cycles
- 1-file cycle: `screens/history_screen.py -> screens/history_screen.py`
- 1-file cycle: `screens/main_screen.py -> screens/main_screen.py`
- 1-file cycle: `screens/settings_screen.py -> screens/settings_screen.py`
- 1-file cycle: `controllers/tools_controller.py -> controllers/tools_controller.py`

## Hyperedges (group relationships)
- **SaveMedia Core Technology Stack** — readme_savemedia, readme_ytdlp, readme_ffmpeg, readme_flet, readme_python [EXTRACTED 1.00]

## Communities (57 total, 6 thin omitted)

### Community 0 - "UI Controllers & Localization"
Cohesion: 0.06
Nodes (120): AlertDialog, AppBar, ClipboardUrlEvent, Connection, Control, Page, I18nTarget, controllers/i18n_target.py — миксин для смены языка без ручного перечисления вид (+112 more)

### Community 1 - "App Bootstrap & Tools Control"
Cohesion: 0.05
Nodes (66): _is_session_closed(), Exception, Page, SaveMediaApp, hex_to_flet(), ThemeConfig, Применить ThemeConfig ко всем зарегистрированным виджетам.         Экранам не ну, Any (+58 more)

### Community 2 - "Config Package & Tool Params"
Cohesion: 0.07
Nodes (29): config/constants.py — константы приложения: интервалы, лимиты, сетевые параметры, config — пакет конфигурации приложения (бывший монолитный config.py).  Состав:, config/runtime.py — персистируемые настройки окружения: геометрия окна и сетевые, config/theme.py — оформление: семантические токены (ThemeConfig), именованные на, Flet-цвет по карте «ключ → токен» из активной палитры., token_color(), Aria2cConfig, Aria2cParameters (+21 more)

### Community 3 - "Tool Spec Abstraction"
Cohesion: 0.08
Nodes (34): AsyncClient, InstallContext, ManualInstallRequired, managers/tool_specs.py — единая абстракция внешнего инструмента (yt-dlp, ffmpeg,, Всё, что нужно ToolSpec.install() для скачивания/распаковки., Поднимается из ToolSpec.install(), если автоматическая установка невозможна, Контракт одного инструмента. ToolsManager работает только с этим интерфейсом., Список бинарников инструмента (первый/помеченный is_primary — главный). (+26 more)

### Community 4 - "Download Repository (DB)"
Cohesion: 0.06
Nodes (27): DownloadRepository, Однократно проставить content_hash старым magnet-записям (btih из URL)., Отписаться от всех событий шины. Вызывать при уничтожении объекта., Запись по task_id (для уведомлений: имя из meta.title)., Самая свежая УСПЕШНО завершённая загрузка того же контента (для         предупре, Сохранить JPEG-байты thumbnail в БД., Сохранить JSON-метаданные из yt-dlp., Удалить запись из истории. (+19 more)

### Community 5 - "History Screen"
Cohesion: 0.11
Nodes (18): DownloadRecord, HistoryScreen, Применить ThemeConfig к виджетам экрана.          Карточки записей и фильтры рен, Статичные тексты — по регистрации (apply_language); динамика —         фильтры и, Строка ошибки на карточке. Если сохранён вывод процесса — сама строка         кл, Диалог с хвостом вывода упавшего процесса (последние строки —         DownloadMa, Возобновить незавершённую (или повторить неудачную/отменённую)         загрузку:, Запустить раздачу торрента фоном: реконструируем снимок в seed-режиме и (+10 more)

### Community 6 - "Notifications & Window Events"
Cohesion: 0.08
Nodes (25): download_display_name(), Человекочитаемое имя загрузки из URL.      magnet — параметр dn (display name),, build_ps_script(), build_toast_xml(), NotificationController, NotificationController — системные уведомления о финале загрузки.  Ответственнос, Зарегистрировать AppUserModelID в HKCU (идемпотентно). Без этого     CreateToast, XML тоста WinRT; текст экранируется (XML-сущности).      title оставлять пустым (+17 more)

### Community 7 - "Navigation & AppBar"
Cohesion: 0.10
Nodes (13): Flet-цвет для severity события из токенов активной темы., severity_color(), NavigationController, Цвет иконок/заголовка поверх шапки — основной текст активной палитры         (па, Иконка переключателя: показываем целевой режим., Привести иконки/заголовок текущей шапки в соответствие с режимом., Обновить иконку и tooltip кнопки прокси по текущему state., Обновить иконку и tooltip кнопки слежения за буфером по state. (+5 more)

### Community 8 - "Theme Widget Binding"
Cohesion: 0.07
Nodes (21): Button, Container, Text, ft.ProgressBar / ft.Text, которым ставится .color = progress_color., ft.Text, которым ставится .color = text_color., ft.Text вторичного уровня — .color = text_secondary_color., ft.Text приглушённый (хинты, таймстемпы, пустые состояния) — .color = text_muted, Вложенные контейнеры/чипы — .bgcolor = surface_color. (+13 more)

### Community 9 - "Orchestrator Tests"
Cohesion: 0.12
Nodes (19): Запрос из истории: возобновить незавершённую (или повторить неудачную)     загру, ResumeDownloadEvent, FakeDB, FakeDM, FakeThumbs, make_orch(), Тесты DownloadOrchestrator: проверки перед запуском, исходы, события, сопутствую, test_launch_emits_accepted_and_saves_meta_for_aria2c() (+11 more)

### Community 10 - "Config Manager & Persistence"
Cohesion: 0.09
Nodes (23): AppState, ConfigManager, Any, Загрузить runtime-версии из секции "tool_versions".          Мягкая миграция: ес, Быстрое чтение только геометрии окна до полной загрузки., Сериализует AppState → config.json., Читает config.json и возвращает заполненный AppState.         При любой ошибке в, Загрузить режим + две палитры + именованные наборы из блока "theme".          По (+15 more)

### Community 11 - "Screen & Provider Protocols"
Cohesion: 0.06
Nodes (18): Page, Контракт экрана, который умеет применять тему., screens — список экранов в порядке применения темы.                   Новый экра, Применить текущую тему из state ко всем экранам, странице и барам., Themeable, DownloadProvider, Проверить что URL подходит для этого провайдера., Теги строк постобработки для отображения в UI. (+10 more)

### Community 12 - "Download Manager (Concurrency)"
Cohesion: 0.09
Nodes (11): DownloadManager, Текущий лимит одновременных загрузок (кламп на случай мусора в конфиге)., Дождаться свободного слота. Лимит перечитывается на каждой проверке., Слот как контекст-менеджер (бывший asyncio.Semaphore в _run)., Уже идёт загрузка с этим URL? Нельзя качать тот же URL дважды         одновреме, Временные папки активных загрузок (чтобы ручная очистка их не трогала)., Поставить на паузу: убить процесс (partial и .aria2 остаются для докачки)., Снять с паузы: перезапустить загрузку (та же .part/<id> + --continue). (+3 more)

### Community 13 - "Logging & App Services"
Cohesion: 0.11
Nodes (15): configure_logging(), LinePrefixFormatter, SourceFilter, NamedTheme, Any, Снимок палитры под именем + режим, для которого она задумана., Runtime-состояние версий одного бинарника. НЕ часть статической конфигурации., VersionState (+7 more)

### Community 14 - "Tool Registry & Installers"
Cohesion: 0.11
Nodes (16): InstallContext, Aria2cTool, build_default_tools(), FfmpegTool, ToolBinary, managers/tool_registry.py — конкретные инструменты и реестр по умолчанию.  Здесь, Один логический инструмент, поставляющий три бинарника одним zip-архивом.     Ав, Один бинарник aria2c. Релизы — на GitHub, в zip-архиве сборки под Windows     (a (+8 more)

### Community 15 - "Application Paths"
Cohesion: 0.12
Nodes (12): Path, AppPaths, Записываемая папка для скачиваемых инструментов (data_dir, фолбэк — app_dir)., Windows-иконка (.ico) — для реестра уведомлений (IconUri)., Все пути приложения, производные от app_dir.      app_dir  — корень рядом с .exe, Определить корневую папку: рядом с .exe (frozen) или рядом с исходниками., Папка в профиле пользователя по конвенции платформы., Можно ли создавать/писать файлы внутри path (создаёт его при необходимости). (+4 more)

### Community 16 - "Provider Tests"
Cohesion: 0.12
Nodes (18): DownloadSnapshot, Тесты провайдеров: парсинг прогресса, сборка команд, реестр, торрент-утилиты., Пресет "best" (пустые args) не перебивает пользовательский -f из extra_args., С дефолтными настройками формат не задаётся вовсе (yt-dlp сам берёт best)., Брошенная торрент-загрузка без .aria2 сверяется по хешам, а не качается     зано, Пресет качества идёт ПОСЛЕ extra_args — его -f переопределяет формат., snap(), test_aria2_check_integrity_only_for_hashed_content() (+10 more)

### Community 17 - "Event Bus & Orchestrator"
Cohesion: 0.13
Nodes (16): EventBus, Минималистичная синхронная шина событий.      Использование:         bus = Event, Синхронно вызвать всех подписчиков данного типа события., DownloadOrchestrator, Any, DownloadSnapshot, managers/download_orchestrator.py — оркестрация запуска загрузок.  Решения уровн, Запустить загрузку по готовому снимку: задача в менеджер + событие для         U (+8 more)

### Community 18 - "Base Tool Implementation"
Cohesion: 0.15
Nodes (8): BaseTool, ToolConfig, Общая база для всех инструментов (реализует ToolSpec).      Главное, что она даё, Дефолтная статическая конфигурация инструмента (единый источник истины)., Конфиг инструмента из state; дефолт, если state или ключа нет., Список бинарников инструмента — прямое отображение cfg.binaries.         Реализа, Главный бинарник инструмента (по is_primary; иначе — первый)., Переопределяется инструментом, которому нужен внешний рантайм (см. ToolSpec).

### Community 19 - "Config Logic Tests"
Cohesion: 0.12
Nodes (9): is_valid_hex(), Тесты чистой логики пакета config: миграции from_dict, утилиты, severity., Нетронутый старый дефолт (с -f bestvideo+bestaudio/best) → новый без формата., test_extra_args_legacy_default_migrates(), test_get_fallback_bool(), test_hex_to_flet(), test_is_valid_hex(), test_safe_int() (+1 more)

### Community 20 - "Provider Command Building"
Cohesion: 0.16
Nodes (11): safe_str(), _dir_size(), is_playlist_url(), DownloadSnapshot, providers.py — протоколы и реализации провайдеров инструментов.  DownloadProvide, CLI-строка из конфига → список аргументов. Кривые кавычки пользователя     не ро, Эвристика «ссылка на плейлист» — для шаблона пути загрузки и пометки     в метад, Удалить временные подпапки <download_dir>/<part_dirname> (незавершённые/ (+3 more)

### Community 21 - "Aria2c Provider"
Cohesion: 0.12
Nodes (9): Aria2cProvider, Самостоятельный загрузчик прямых ссылок (HTTP/HTTPS/FTP/SFTP/magnet/metalink), Временная папка <download>/.part/<id> текущей загрузки ('' для seed)., Истинная строка прогресса контента — не сидинг и не служебная фаза.          У m, Auto-режим: True если ссылка ведёт на ФАЙЛ/торрент (→ aria2c), иначе это, test_aria2_build_command_uses_part_dir(), test_aria2_magnet_metadata_phase_suppressed(), test_aria2_move_multiple_files_points_to_dir() (+1 more)

### Community 22 - "yt-dlp Provider"
Cohesion: 0.12
Nodes (6): Провайдер загрузок на базе yt-dlp.     Один экземпляр = одна загрузка., Получить thumbnail как JPEG-байты и метаданные из yt-dlp:           1. --dump-si, YtDlpProvider, Получить превью и метаданные, сохранить в БД и оповестить шину.         Ошибки н, test_ytdlp_observe_line_audio_and_existing(), test_ytdlp_observe_line_tracks_final_path()

### Community 23 - "README Features & Stack"
Cohesion: 0.15
Nodes (17): Automatic yt-dlp and ffmpeg Updates, Download History, Features, ffmpeg, Flet, Localization (Russian + English), main.py, MIT License (+9 more)

### Community 24 - "URL Parsing"
Cohesion: 0.20
Nodes (14): parse_url_lines(), Разобрать многострочный текст в список ссылок: по строке на ссылку, без     пуст, extract_download_urls(), Строки-ссылки из произвольного текста (буфер обмена): схема загрузки     (http/h, Тесты разбора многострочного поля URL (пакетная загрузка, буфер обмена)., Пути к .torrent и magnet-ссылки могут содержать пробелы — строка не режется., test_crlf_input(), test_duplicates_removed() (+6 more)

### Community 25 - "Logger Adapter & DI"
Cohesion: 0.15
Nodes (7): get_logger(), page — Flet Page.         svc  — DI-контейнер (через svc.bus публикуются Setting, LoggerAdapter, provider_factories — реестр {ключ: callable без аргументов → новый DownloadProvi, Настоящее имя содержимого из .torrent (info.name) — оно в метаданных торрента, torrent_name(), EventBus

### Community 26 - "Binary & Param Configs"
Cohesion: 0.19
Nodes (7): BinaryDef, Параметры yt-dlp: каждый группирует состояние переключателя и CLI-аргументы., Статическое описание одного бинарника инструмента: имя файла + флаг версии., YtDlpParameters, default_tools_config(), ToolConfig, Дефолтная конфигурация всех инструментов — собирается из самих инструментов.

### Community 27 - "Locale Loading & Language"
Cohesion: 0.21
Nodes (5): Папка с locale/*.json. Внедрённый paths, иначе — автоопределение (для тестов/изо, Загрузить locale/<lang>.json и вернуть Strings.         Если lang не указан, исп, Вернуть доступный язык для системной локали или английский., Сопоставить код языка с файлами locale/*.json и откатиться на en., Вернуть список (code, native_name) доступных языков.         Имя читается из сам

### Community 28 - "Download Submission API"
Cohesion: 0.21
Nodes (6): Запуск после подтверждения повтора — проверка истории пропускается., Пачка ссылок: запускаем валидные, остальные возвращаем как leftover.         Про, Конкретный провайдер для ссылки: "auto" решает реестр, иначе — выбор., Валидна ли ссылка для провайдера, который её получит., Имя для карточки/истории. Для .torrent — реальное имя из метаданных         торр, Одна ссылка: полный набор проверок, включая повтор по истории         (по URL/ко

### Community 29 - "Main Screen Handlers"
Cohesion: 0.26
Nodes (3): Слежение за буфером поймало ссылки — дописать новые строками в поле.         Заг, Перевести исход оркестратора в реакцию UI (статус-бар/диалог/поле)., Пачка ссылок: запущенные строки убираются из поля, проблемные         (невалидны

### Community 30 - "Settings Screen UI"
Cohesion: 0.20
Nodes (12): Cookies Source Selector, Download Behavior Toggles, ffmpeg Binary Dependency, ffplay Binary Dependency, Local Dependencies Panel, Network Proxy Setting, Quality Parameters / yt-dlp Arguments, SaveMedia Application (+4 more)

### Community 31 - "Subprocess Provider Base"
Cohesion: 0.17
Nodes (6): Базовая реализация для провайдеров, гоняющих внешний CLI-процесс.      Инкапсули, По умолчанию провайдер качает сразу в папку назначения — temp-папки нет., По умолчанию провайдеру нечего собирать из вывода., По умолчанию финальный путь неизвестен., По умолчанию — строка как есть. Подклассы переопределяют под свой формат., _SubprocessProvider

### Community 32 - "Theme Config Defaults"
Cohesion: 0.18
Nodes (7): Семантические токены оформления. Дефолты поля = тёмная палитра, поэтому     Them, Мягкая миграция: отсутствующие/пустые ключи берутся из тёмных дефолтов., ThemeConfig, test_theme_defaults_are_dark(), test_theme_from_dict_empty_values_fall_back(), test_theme_from_dict_garbage_input(), test_theme_from_dict_soft_migration()

### Community 33 - "Subtitle Parameters"
Cohesion: 0.18
Nodes (8): ParamSubtitles, Субтитры: выбранный режим + карта режим → шаблон CLI-аргументов.      value: "of, CLI-аргументы выбранного режима ('' для off/неизвестного шаблона).          Код, test_subtitles_all(), test_subtitles_auto_uses_ui_language(), test_subtitles_default_off(), test_subtitles_language_value_uses_lang_template(), test_subtitles_roundtrip()

### Community 34 - "Version Classification"
Cohesion: 0.25
Nodes (10): classify_version(), Определить статус по локальной и удалённой версии. Единый источник истины., True если удалённую версию удалось получить (можно обновлять)., Подлежит ли бинарник обновлению. Обновляем только если есть валидная удалённая в, remote_is_known(), status_needs_update(), Тесты classify_version / status_needs_update — единый источник сравнения версий., test_classify_version() (+2 more)

### Community 35 - "Settings Screen Widgets"
Cohesion: 0.20
Nodes (5): Привести метку папки в соответствие со state.download_path.          Источник ис, Привести переключатель cookies в соответствие с выбранным браузером.          Ис, Пункты дропдауна из карты пресетов; переводится только "best"., Пункты дропдауна; языки подписываются их именами из locale-файлов., Статичные тексты — по регистрации (apply_language); здесь только         динамик

### Community 36 - "Main Screen State Sync"
Cohesion: 0.24
Nodes (3): Выбор в дропдауне ("auto"|"yt-dlp"|"aria2c"); неизвестное → "auto"., Ключи дропдауна: off + языки локализации + auto + all., Мультивыбор локальных .torrent/.metalink — пути добавляются строками         в п

### Community 37 - "Snapshot Tests"
Cohesion: 0.20
Nodes (6): Тесты DownloadSnapshot: реконструкция из params, сборка из state, иммутабельност, Цикл from_state → asdict (как пишет БД) → from_params сохраняет параметры., test_from_state_defaults(), test_from_state_resolves_quality_args(), test_from_state_resolves_subtitles_args(), test_roundtrip_through_asdict()

### Community 38 - "Quality Parameters"
Cohesion: 0.22
Nodes (6): ParamQuality, CLI-аргументы выбранного пресета ('' для best или неизвестного ключа)., Качество видео: выбранный пресет + карта пресет → CLI-аргументы.      Карта реда, test_quality_defaults(), test_quality_roundtrip(), test_quality_selected_args()

### Community 39 - "Clipboard Monitoring"
Cohesion: 0.28
Nodes (5): clipboard_file_paths(), ClipboardController, ClipboardController — слежение за буфером обмена.  Ответственность:   - Фоновый, Пути файлов из буфера обмена (копирование в проводнике Windows).      Читает CF_, Цикл опроса; запускается один раз (page.run_task в app.py) и живёт         до за

### Community 40 - "Tool Config Accessors"
Cohesion: 0.29
Nodes (5): Aria2cConfig, ToolConfig, Дефолтный конфиг конкретного инструмента из реестра — fallback для аксессоров., _tool_default(), YtDlpConfig

### Community 41 - "Main GUI Screenshot"
Cohesion: 0.32
Nodes (8): SaveMedia (yt-dlp GUI) Application, Audio Only (MP3) Toggle, Use Cookies (Yandex Browser) Toggle, Download Folder Setting, Download Manager Panel, Download Queue Panel, SaveMedia Main GUI Screenshot, yt-dlp Backend

### Community 42 - "History Screen Screenshot"
Cohesion: 0.32
Nodes (8): Completed Status Indicator, Dark Theme UI Design, Download History Entry Card, Entry Actions (Open Folder / Delete), History Filter Tabs (All/Completed/Errors/Cancelled), Download History Screen, History Stats Summary (Total/Success/Failure/Avg), YouTube Source URL

### Community 43 - "Download Manager Tests"
Cohesion: 0.32
Nodes (6): make_dm(), Тесты слотов параллельности DownloadManager: динамический лимит, кламп., Задача ждёт слот; увеличение лимита + SettingsChangedEvent её пропускает., test_at_capacity_uses_dynamic_limit(), test_max_parallel_default_and_clamp(), test_slot_waiting_respects_limit_increase()

### Community 44 - "Window Config"
Cohesion: 0.33
Nodes (3): Any, WindowConfig, test_window_defaults_on_garbage()

### Community 45 - "Timeouts Config"
Cohesion: 0.33
Nodes (5): Сетевые таймауты (секунды), персистятся в config.json — раньше были     захардко, TimeoutsConfig, test_timeouts_garbage_values(), test_timeouts_rejects_nonpositive_except_card_fade(), test_timeouts_roundtrip()

### Community 46 - "Torrent Bencode Decoder"
Cohesion: 0.33
Nodes (6): _bdecode(), Минимальный bencode-декодер (int/str/list/dict). Возвращает (значение, next_i)., btih (v1) из .torrent: SHA-1 от ИСХОДНЫХ байтов словаря info (не перекодируем —, torrent_infohash(), test_bdecode_roundtrip(), test_torrent_name_and_infohash()

### Community 48 - "App Icon Imagery"
Cohesion: 0.60
Nodes (5): SaveMedia Application, Optical Data Disc (DATA), Film Strip Reel, SaveMedia App Icon, Media Archival / Preservation

### Community 49 - "Magnet Info-Hash"
Cohesion: 0.67
Nodes (3): magnet_btih(), BitTorrent info-hash (btih) из magnet-ссылки в нижнем регистре; '' если нет., test_magnet_btih()

### Community 51 - "Provider Factories"
Cohesion: 0.67
Nodes (3): provider_factories(), Фабрики провайдеров для DownloadManager (один экземпляр = одна загрузка)., test_provider_factories_create_fresh_instances()

### Community 52 - "Provider URL Resolution"
Cohesion: 0.67
Nodes (3): Auto-режим: ссылку забирает первый провайдер реестра, заявивший на неё     права, resolve_provider_for_url(), test_resolve_provider_for_url()

## Knowledge Gaps
- **27 isolated node(s):** `Logger`, `LoggerAdapter`, `Switch`, `Button`, `Divider` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AppState` connect `Tool Spec Abstraction` to `UI Controllers & Localization`, `App Bootstrap & Tools Control`, `Snapshot Tests`, `Tool Config Accessors`, `Orchestrator Tests`, `Config Manager & Persistence`, `Logging & App Services`, `Tool Registry & Installers`, `Provider Tests`, `Event Bus & Orchestrator`, `Base Tool Implementation`, `Download Snapshot Module`, `Logger Adapter & DI`, `Binary & Param Configs`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Why does `DownloadSnapshot` connect `UI Controllers & Localization` to `App Bootstrap & Tools Control`, `Tool Spec Abstraction`, `Download Repository (DB)`, `History Screen`, `Snapshot Tests`, `Orchestrator Tests`, `Screen & Provider Protocols`, `Download Manager (Concurrency)`, `Provider Tests`, `Event Bus & Orchestrator`, `Event Subscription`, `Provider Command Building`, `Aria2c Provider`, `yt-dlp Provider`, `Download Snapshot Module`, `Subprocess Provider Base`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `Services` connect `UI Controllers & Localization` to `App Bootstrap & Tools Control`, `Tool Spec Abstraction`, `Download Repository (DB)`, `History Screen`, `Notifications & Window Events`, `Navigation & AppBar`, `Clipboard Monitoring`, `Config Manager & Persistence`, `Screen & Provider Protocols`, `Download Manager (Concurrency)`, `Logging & App Services`, `Application Paths`, `Event Bus & Orchestrator`?**
  _High betweenness centrality (0.090) - this node is a cross-community bridge._
- **Are the 72 inferred relationships involving `Services` (e.g. with `AlertDialog` and `Exception`) actually correct?**
  _`Services` has 72 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `SettingsChangedEvent` (e.g. with `AlertDialog` and `Exception`) actually correct?**
  _`SettingsChangedEvent` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 62 inferred relationships involving `Locale` (e.g. with `AlertDialog` and `AppBar`) actually correct?**
  _`Locale` has 62 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `MainScreen` (e.g. with `AlertDialog` and `Exception`) actually correct?**
  _`MainScreen` has 31 INFERRED edges - model-reasoned connections that need verification._