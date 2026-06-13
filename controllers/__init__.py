"""controllers — адаптеры между UI и сервисами + миксины экранов
(ThemeTarget/I18nTarget). Реэкспорты ниже использует app.py."""

from controllers.clipboard_controller import ClipboardController
from controllers.i18n_target import I18nTarget
from controllers.navigation_controller import NavigationController
from controllers.notification_controller import NotificationController
from controllers.theme_controller import ThemeController
from controllers.theme_target import ThemeTarget
from controllers.tools_controller import ToolsController
from controllers.window_controller import WindowController

__all__ = ["ClipboardController", "I18nTarget", "NavigationController",
           "NotificationController", "ThemeController", "ThemeTarget",
           "ToolsController", "WindowController"]
