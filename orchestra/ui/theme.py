"""Design tokens, dark/light ttk themes, and authoritative status mappings."""
from __future__ import annotations

from tkinter import font as tkfont
from tkinter import ttk

from ..execution_state import merge_candidate_ready

THEMES = {
    "dark": {
        "name": "dark",
        "canvas": "#0d1117",
        "sidebar": "#111827",
        "sidebar_border": "#1e293b",
        "header": "#111827",
        "panel": "#161d2b",
        "elevated": "#1e293b",
        "hover": "#253349",
        "active": "#1f3352",
        "border": "#2a364b",
        "border_strong": "#3b4b66",
        "text": "#f1f5f9",
        "text_secondary": "#cbd5e1",
        "muted": "#8b9bb4",
        "accent": "#3b82f6",
        "accent_hover": "#2563eb",
        "accent_text": "#ffffff",
        "danger": "#ef4444",
        "danger_hover": "#dc2626",
        "nav_fg": "#cbd5e1",
        "nav_muted": "#72839d",
        "nav_active_fg": "#ffffff",
        "terminal_bg": "#090d14",
        "terminal_fg": "#e5edf7",
        "tree_selected": "#1f3a60",
        "graph_bg": "#111827",
        "graph_edge": "#546b8c",
        "badges": {
            "success": ("#123225", "#5eead4", "#1d5b42"),
            "running": ("#142a4b", "#7cc4ff", "#255290"),
            "warning": ("#3a2912", "#fbbf24", "#714f1d"),
            "danger": ("#3d1820", "#fca5a5", "#7f2937"),
            "neutral": ("#1e293b", "#cbd5e1", "#334155"),
        },
        "graph_nodes": {
            "SUCCEEDED": ("#123225", "#2b7a57", "#d1fae5"),
            "RUNNING": ("#142a4b", "#3b82f6", "#e0f2fe"),
            "VERIFYING": ("#142a4b", "#38bdf8", "#e0f2fe"),
            "PREPARING": ("#142a4b", "#3b82f6", "#e0f2fe"),
            "FAILED": ("#3d1820", "#ef4444", "#fee2e2"),
            "AWAITING_TOOL": ("#3a2912", "#f59e0b", "#fef3c7"),
            "AWAITING_APPROVAL": ("#3a2912", "#f59e0b", "#fef3c7"),
            "CANCELLED": ("#1f2430", "#64748b", "#cbd5e1"),
            "NOT_EXECUTED": ("#1a202c", "#475569", "#94a3b8"),
            "QUEUED": ("#1a2232", "#475569", "#cbd5e1"),
        },
    },
    "light": {
        "name": "light",
        "canvas": "#f4f6fa",
        "sidebar": "#eaeff6",
        "sidebar_border": "#d0dae6",
        "header": "#ffffff",
        "panel": "#ffffff",
        "elevated": "#f1f5f9",
        "hover": "#e2e8f0",
        "active": "#dbeafe",
        "border": "#cbd5e1",
        "border_strong": "#94a3b8",
        "text": "#0f172a",
        "text_secondary": "#334155",
        "muted": "#52657c",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_text": "#ffffff",
        "danger": "#dc2626",
        "danger_hover": "#b91c1c",
        "nav_fg": "#1e293b",
        "nav_muted": "#64748b",
        "nav_active_fg": "#1d4ed8",
        "terminal_bg": "#0f1724",
        "terminal_fg": "#e5edf7",
        "tree_selected": "#dbeafe",
        "graph_bg": "#ffffff",
        "graph_edge": "#64748b",
        "badges": {
            "success": ("#dcfce7", "#166534", "#86efac"),
            "running": ("#dbeafe", "#1e40af", "#93c5fd"),
            "warning": ("#fef3c7", "#92400e", "#fcd34d"),
            "danger": ("#fee2e2", "#991b1b", "#fca5a5"),
            "neutral": ("#e2e8f0", "#334155", "#cbd5e1"),
        },
        "graph_nodes": {
            "SUCCEEDED": ("#e6f6ed", "#4ca97b", "#14532d"),
            "RUNNING": ("#e2eeff", "#3b82f6", "#1e3a8a"),
            "VERIFYING": ("#e0f2fe", "#0284c7", "#0c4a6e"),
            "PREPARING": ("#e2eeff", "#3b82f6", "#1e3a8a"),
            "FAILED": ("#ffe8e8", "#ef4444", "#7f1d1d"),
            "AWAITING_TOOL": ("#fff1d6", "#d97706", "#78350f"),
            "AWAITING_APPROVAL": ("#fff1d6", "#d97706", "#78350f"),
            "CANCELLED": ("#edf2f7", "#94a3b8", "#475569"),
            "NOT_EXECUTED": ("#f1f5f9", "#cbd5e1", "#64748b"),
            "QUEUED": ("#edf2f7", "#94a3b8", "#1e293b"),
        },
    },
}


def resolve_fonts(window):
    """Pick the sharpest cross-platform UI and monospace font families available."""
    names = {family.casefold(): family for family in tkfont.families(window)}
    ui_candidates = (
        "Segoe UI", "Malgun Gothic", "Noto Sans CJK KR", "NanumBarunGothic",
        "NanumGothic", "Ubuntu", "DejaVu Sans", "gothic",
    )
    mono_candidates = (
        "Cascadia Mono", "Consolas", "NanumGothicCoding",
        "DejaVu Sans Mono", "courier 10 pitch", "fixed",
    )
    ui_font = next((names[item.casefold()] for item in ui_candidates if item.casefold() in names), "TkDefaultFont")
    mono_font = next((names[item.casefold()] for item in mono_candidates if item.casefold() in names), "TkFixedFont")
    return ui_font, mono_font


def status_tone(state: str | None) -> str:
    """Map an authoritative job or task state to a semantic UI tone."""
    if state in ("SUCCEEDED", "MERGED", "READY"):
        return "success"
    if state in ("PREPARING", "RUNNING", "VERIFYING", "MERGING"):
        return "running"
    if state in ("AWAITING_TOOL", "AWAITING_APPROVAL", "RETRY_WAIT", "MERGE_QUEUED", "WAITING_REVIEW", "WAITING_QA"):
        return "warning"
    if state in ("FAILED", "QA_FAILED", "REJECTED"):
        return "danger"
    return "neutral"


def approval_state_info(job: dict | None, tasks: dict | None = None, events: list[dict] | None = None):
    """Derive authoritative Git & QA approval presentation state without altering backend rules."""
    if not job:
        return "WAITING_QA", "QA 대기", "neutral", False, ["작업을 선택하세요."]
    state = job.get("state")
    result = job.get("result") or {}
    tasks = tasks or {}
    events = events or []

    if state == "MERGED":
        return "MERGED", "병합 완료", "success", False, []
    if state in ("MERGE_QUEUED", "MERGING"):
        return "MERGING", "병합 중", "running", False, []
    if state == "CANCELLED":
        return "REJECTED", "승인 거절", "danger", False, ["작업이 취소되었거나 병합 승인이 거절되었습니다."]
    if state == "FAILED":
        reviews = [(row.get("result") or {}) for row in tasks.values() if row.get("state") == "FAILED"]
        blockers = [review["reason"] for review in reviews
                    if review.get("review") in ("failed", "invalid") and review.get("reason")]
        if blockers:
            return "REJECTED", "검토 거절", "danger", False, blockers
        reason = result.get("reason") or "통합 QA 또는 실행 단계가 실패했습니다."
        return "QA_FAILED", "QA 실패", "danger", False, [str(reason)]
    if state == "AWAITING_APPROVAL":
        blockers = []
        if not merge_candidate_ready(job):
            blockers.append("통합 QA를 통과한 유효한 후보 SHA가 필요합니다.")
        if blockers:
            return "QA_FAILED", "QA 실패", "danger", False, blockers
        return "READY", "승인 준비 완료", "success", True, []
    if state == "SUCCEEDED":
        return "COMPLETED", "완료 (병합 대상 없음)", "neutral", False, ["커밋할 변경 파일이 없어 병합 승인이 필요하지 않습니다."]
    if state == "VERIFYING":
        return "WAITING_QA", "QA 대기", "running", False, ["통합 QA 검증이 진행 중입니다."]

    review_pending = any(
        row.get("state") in ("PREPARING", "RUNNING", "QUEUED")
        and any(t.get("id") == task_id and t.get("role") == "reviewer" for t in (job.get("plan") or {}).get("tasks", []))
        for task_id, row in tasks.items()
    )
    if review_pending:
        return "WAITING_REVIEW", "검토 대기", "warning", False, ["독립 검토 단계가 완료되면 통합 QA가 실행됩니다."]
    return "WAITING_QA", "QA 대기", "warning", False, ["작업 실행 및 통합 QA 통과 후 병합 승인을 진행할 수 있습니다."]


def apply_ttk_theme(window, theme_name: str, ui_font: str, mono_font: str) -> dict:
    """Configure ttk widget styles cleanly for the requested palette."""
    palette = THEMES.get(theme_name, THEMES["dark"])
    style = ttk.Style()
    style.theme_use("clam")

    window.configure(bg=palette["canvas"])
    window.option_add("*Font", (ui_font, 10))

    style.configure(".", font=(ui_font, 10), background=palette["canvas"], foreground=palette["text"])
    style.configure("TFrame", background=palette["canvas"])
    style.configure("Header.TFrame", background=palette["header"])
    style.configure("Sidebar.TFrame", background=palette["sidebar"])
    style.configure("Card.TFrame", background=palette["panel"], bordercolor=palette["border"], relief="flat")
    style.configure("Elevated.TFrame", background=palette["elevated"], bordercolor=palette["border"], relief="flat")

    style.configure("TLabel", background=palette["canvas"], foreground=palette["text"])
    style.configure("Muted.TLabel", background=palette["canvas"], foreground=palette["muted"], font=(ui_font, 9))
    style.configure("Secondary.TLabel", background=palette["canvas"], foreground=palette["text_secondary"])
    style.configure("Heading.TLabel", background=palette["canvas"], foreground=palette["text"], font=(ui_font, 19, "bold"))
    style.configure("Subheading.TLabel", background=palette["canvas"], foreground=palette["muted"], font=(ui_font, 10))
    style.configure("Section.TLabel", background=palette["canvas"], foreground=palette["text"], font=(ui_font, 12, "bold"))

    style.configure("Header.TLabel", background=palette["header"], foreground=palette["text"], font=(ui_font, 10, "bold"))
    style.configure("HeaderMuted.TLabel", background=palette["header"], foreground=palette["muted"], font=(ui_font, 9))

    style.configure("Card.TLabel", background=palette["panel"], foreground=palette["muted"], font=(ui_font, 9))
    style.configure("CardBody.TLabel", background=palette["panel"], foreground=palette["text_secondary"], font=(ui_font, 10))
    style.configure("CardTitle.TLabel", background=palette["panel"], foreground=palette["text"], font=(ui_font, 11, "bold"))
    style.configure("CardMono.TLabel", background=palette["panel"], foreground=palette["text_secondary"], font=(mono_font, 9))
    style.configure("Metric.TLabel", background=palette["panel"], foreground=palette["text"], font=(ui_font, 20, "bold"))
    style.configure("Elevated.TLabel", background=palette["elevated"], foreground=palette["text_secondary"], font=(ui_font, 9))
    style.configure("ElevatedTitle.TLabel", background=palette["elevated"], foreground=palette["text"], font=(ui_font, 10, "bold"))

    style.configure(
        "TButton",
        padding=(12, 6),
        background=palette["elevated"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["elevated"],
        darkcolor=palette["elevated"],
        relief="flat",
        font=(ui_font, 9, "bold"),
    )
    style.map(
        "TButton",
        background=[("disabled", palette["panel"]), ("active", palette["hover"]), ("pressed", palette["active"])],
        foreground=[("disabled", palette["muted"])],
        bordercolor=[("focus", palette["accent"]), ("active", palette["border_strong"])],
    )

    style.configure(
        "Primary.TButton",
        padding=(13, 6),
        background=palette["accent"],
        foreground=palette["accent_text"],
        bordercolor=palette["accent"],
        lightcolor=palette["accent"],
        darkcolor=palette["accent"],
        relief="flat",
        font=(ui_font, 9, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", palette["elevated"]), ("active", palette["accent_hover"]), ("pressed", palette["accent_hover"])],
        foreground=[("disabled", palette["muted"]), ("active", palette["accent_text"])],
        bordercolor=[("disabled", palette["border"]), ("active", palette["accent_hover"])],
    )

    style.configure(
        "Danger.TButton",
        padding=(12, 6),
        background=palette["danger"],
        foreground="#ffffff",
        bordercolor=palette["danger"],
        relief="flat",
        font=(ui_font, 9, "bold"),
    )
    style.map(
        "Danger.TButton",
        background=[("disabled", palette["elevated"]), ("active", palette["danger_hover"])],
        foreground=[("disabled", palette["muted"]), ("active", "#ffffff")],
        bordercolor=[("disabled", palette["border"])],
    )

    style.configure(
        "Subtle.TButton",
        padding=(9, 5),
        background=palette["panel"],
        foreground=palette["text_secondary"],
        bordercolor=palette["border"],
        relief="flat",
        font=(ui_font, 9),
    )
    style.map(
        "Subtle.TButton",
        background=[("disabled", palette["panel"]), ("active", palette["hover"])],
        foreground=[("disabled", palette["muted"]), ("active", palette["text"])],
    )

    for tone, (bg, fg, _border) in palette["badges"].items():
        style.configure(
            f"Badge.{tone.capitalize()}.TLabel",
            background=bg,
            foreground=fg,
            padding=(8, 3),
            font=(ui_font, 9, "bold"),
        )

    style.configure(
        "Treeview",
        rowheight=32,
        background=palette["panel"],
        fieldbackground=palette["panel"],
        foreground=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["panel"],
        darkcolor=palette["panel"],
        relief="flat",
    )
    style.configure(
        "Treeview.Heading",
        padding=(8, 7),
        background=palette["elevated"],
        foreground=palette["text_secondary"],
        bordercolor=palette["border"],
        relief="flat",
        font=(ui_font, 9, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", palette["hover"])])
    style.map(
        "Treeview",
        background=[("selected", palette["tree_selected"])],
        foreground=[("selected", palette["text"])],
    )

    style.configure("TNotebook", background=palette["canvas"], bordercolor=palette["border"], tabmargins=(0, 2, 0, 0))
    style.configure(
        "TNotebook.Tab",
        padding=(12, 6),
        background=palette["elevated"],
        foreground=palette["muted"],
        bordercolor=palette["border"],
        font=(ui_font, 9, "bold"),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette["panel"]), ("active", palette["hover"])],
        foreground=[("selected", palette["text"]), ("active", palette["text_secondary"])],
    )

    style.configure(
        "TEntry",
        fieldbackground=palette["elevated"],
        foreground=palette["text"],
        insertcolor=palette["text"],
        bordercolor=palette["border"],
        lightcolor=palette["border"],
        darkcolor=palette["border"],
        padding=(8, 5),
    )
    style.map("TEntry", bordercolor=[("focus", palette["accent"])])

    style.configure(
        "TCombobox",
        fieldbackground=palette["elevated"],
        background=palette["elevated"],
        foreground=palette["text"],
        arrowcolor=palette["text_secondary"],
        bordercolor=palette["border"],
        padding=(6, 4),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", palette["elevated"])],
        foreground=[("readonly", palette["text"])],
        selectbackground=[("readonly", palette["elevated"])],
        selectforeground=[("readonly", palette["text"])],
        bordercolor=[("focus", palette["accent"])],
    )

    style.configure("TCheckbutton", background=palette["canvas"], foreground=palette["text"])
    style.map("TCheckbutton", background=[("active", palette["canvas"])])
    style.configure("Card.TCheckbutton", background=palette["panel"], foreground=palette["text"])
    style.map("Card.TCheckbutton", background=[("active", palette["panel"])])

    style.configure("TPanedwindow", background=palette["border"])
    style.configure("Sash", sashthickness=5, gripcount=0)
    style.configure(
        "Vertical.TScrollbar",
        background=palette["border_strong"],
        troughcolor=palette["panel"],
        bordercolor=palette["panel"],
        arrowcolor=palette["muted"],
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", palette["muted"]), ("!disabled", palette["border_strong"])],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=palette["border_strong"],
        troughcolor=palette["panel"],
        bordercolor=palette["panel"],
        arrowcolor=palette["muted"],
    )
    style.map(
        "Horizontal.TScrollbar",
        background=[("active", palette["muted"]), ("!disabled", palette["border_strong"])],
    )
    return palette
