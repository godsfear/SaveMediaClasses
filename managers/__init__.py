"""
managers — доменные движки и сервисы приложения.

__init__ намеренно пуст: импортируйте модули по полному пути
(from managers.tools_manager import ToolsManager). Реэкспорты здесь создавали
цикл state → managers.tool_registry → managers.__init__ → config_manager → state,
из-за которого state был вынужден импортировать реестр инструментов лениво.
"""
