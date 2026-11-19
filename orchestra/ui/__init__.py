"""Modular Orca-inspired UI design system for the Tk workspace."""
from __future__ import annotations

from .components import (
    Card,
    CollapsibleSection,
    EmptyState,
    MetricCard,
    StatusBadge,
    style_listbox_widget,
    style_text_widget,
)
from .strings import LOCALES, NAV_GROUPS, STRINGS, state_label, t
from .theme import THEMES, apply_ttk_theme, approval_state_info, resolve_fonts, status_tone

__all__ = [
    "Card",
    "CollapsibleSection",
    "EmptyState",
    "LOCALES",
    "MetricCard",
    "NAV_GROUPS",
    "STRINGS",
    "StatusBadge",
    "THEMES",
    "apply_ttk_theme",
    "approval_state_info",
    "resolve_fonts",
    "state_label",
    "status_tone",
    "style_listbox_widget",
    "style_text_widget",
    "t",
]
