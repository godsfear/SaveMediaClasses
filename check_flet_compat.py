"""
check_flet_compat.py — проверка совместимости с Flet 0.85.x.
Запускать перед каждым коммитом: python check_flet_compat.py
"""
import re, sys, pathlib

errors = []
root   = pathlib.Path(__file__).parent

rules = [
    # (описание, паттерн начала виджета, запрещённый аргумент внутри блока)
    ("ft.Dropdown — on_change в конструкторе",  r'ft\.Dropdown\(',   'on_change'),
    ("ft.TextButton — text= в конструкторе",    r'ft\.TextButton\(', r'text\s*='),
]

for py in root.rglob("*.py"):
    if "__pycache__" in str(py):
        continue
    src = py.read_text(encoding="utf-8")
    for desc, start_pat, bad_arg in rules:
        for m in re.finditer(start_pat, src):
            start = m.start()
            depth, i = 0, start
            while i < len(src):
                if   src[i] == '(': depth += 1
                elif src[i] == ')':
                    depth -= 1
                    if depth == 0: break
                i += 1
            block = src[start:i]
            if re.search(bad_arg, block):
                line_no = src[:start].count('\n') + 1
                errors.append(f"{py}:{line_no} — {desc}")

if errors:
    print("✗ Найдены несовместимости с Flet 0.85.x:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("✓ Flet 0.85.x совместимость OK")
