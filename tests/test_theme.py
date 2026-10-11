"""Our CSS classes must not collide with Quasar/NiceGUI utility classes.

Regression: `yt-btn sm` / `yt-danger md` hid «Limpiar cola», «Abrir registro» and «Reintentar fallidas»,
because Quasar's `.sm` / `.md` breakpoint classes are `display: none !important` on desktop widths.
"""
import re
from pathlib import Path

import nicegui

from pista.ui import app as app_module, components, player, theme

UI_FILES = [Path(m.__file__) for m in (app_module, components, player, theme)]


def framework_classes() -> set[str]:
    css = "".join(p.read_text("utf-8", "ignore") for p in Path(nicegui.__file__).parent.glob("static/**/*.css"))
    return set(re.findall(r"\.([a-zA-Z_][\w-]*)", css))


def our_classes() -> set[str]:
    """Bare (non-Tailwind) class names we style in theme.CSS."""
    names = set(re.findall(r"\.([a-z][\w-]*)", theme.CSS)) - {"nicegui-content"}
    return {n for n in names if not n.startswith("q-")}  # q-* are deliberate overrides of Quasar elements


def test_theme_classes_do_not_collide_with_framework_css():
    assert sorted(our_classes() & framework_classes()) == []


def test_ui_code_does_not_use_quasar_breakpoint_classes():
    breakpoints = {"xs", "sm", "md", "lg", "xl"}
    used = set()
    for f in UI_FILES:
        for literal in re.findall(r'"([^"]*\byt-[^"]*)"', f.read_text("utf-8")):
            used |= set(literal.split()) & breakpoints
    assert used == set()
