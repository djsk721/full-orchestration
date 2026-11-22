"""Modular Orca-inspired UI design system for the Tk workspace."""
from __future__ import annotations

from .components import (
    Card,
    CollapsibleSection,
    EmptyState,
    MetricCard,
    NavRow,
    SearchBox,
    SettingsSection,
    StatusBadge,
    Tooltip,
    retheme_widget_tree,
    style_listbox_widget,
    style_text_widget,
)
from .strings import LOCALES, NAV_GROUPS, PRIMARY_NAV, STRINGS, state_label, t
from .theme import DIMENSIONS, SPACING, THEMES, TYPE_SCALE, apply_ttk_theme, approval_state_info, resolve_fonts, status_tone

__all__ = [
    "Card",
    "CollapsibleSection",
    "DIMENSIONS",
    "EmptyState",
    "LOCALES",
    "MetricCard",
    "NAV_GROUPS",
    "NavRow",
    "PRIMARY_NAV",
    "SPACING",
    "STRINGS",
    "SearchBox",
    "SettingsSection",
    "StatusBadge",
    "THEMES",
    "TYPE_SCALE",
    "Tooltip",
    "apply_ttk_theme",
    "approval_state_info",
    "resolve_fonts",
    "retheme_widget_tree",
    "state_label",
    "status_tone",
    "style_listbox_widget",
    "style_text_widget",
    "t",
]
