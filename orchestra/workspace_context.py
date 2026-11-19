"""Read-only Files and Git panels for the active desktop project."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tkinter as tk
from pathlib import Path, PurePosixPath
from tkinter import ttk

from .core import Invalid, Temporary, require
from .platform.desktop import open_directory
from .project_files import (
    MAX_FILE, SEARCH_RESULTS, _preview_text, _safe_path, browse_project,
    project_file_diff, project_file_visible, project_git_status, read_project_file, search_project_files,
)


class WorkspaceContext:
    """Shared workspace panel. All file and Git I/O goes through background tasks."""

    def _context_label(self, ko, en):
        return en if getattr(self, "locale", "ko") == "en" else ko

    def build_workspace_context(self, parent):
        label = self._context_label
        self.context_book = ttk.Notebook(parent)
        self.context_project = None
        self.context_git_branch = None
        self._context_generation = 0
        self._context_listing = 0
        self._context_git = {}
        self._context_files = {}
        self._context_file_pending = set()
        self._context_file_loaded = set()
        self._context_search_active = False
        self._context_menu = None

        files = ttk.Frame(self.context_book, padding=5)
        files.columnconfigure(0, weight=1)
        files.rowconfigure(1, weight=3)
        files.rowconfigure(3, weight=2)
        bar = ttk.Frame(files)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.context_file_query = tk.StringVar(self.window)
        self.context_search = ttk.Entry(bar, textvariable=self.context_file_query, width=10)
        self.context_search.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.context_search.bind("<Return>", lambda _: self.search_workspace_files())
        ttk.Button(bar, text=label("찾기", "Find"), width=5, padding=3,
                   command=self.search_workspace_files).grid(row=0, column=1, padx=(0, 4))
        ttk.Button(bar, text=label("새로 읽기", "Reload"), width=7, padding=3,
                   command=self.refresh_workspace_context).grid(row=0, column=2)
        self.context_file_tree = self._context_tree(files, ("status",), (label("Git", "Git"),), row=1)
        self.context_file_tree.bind("<<TreeviewOpen>>", self._context_expand)
        self.context_file_tree.bind("<Double-1>", self._context_file_double_click)
        self.context_file_tree.bind("<Return>", lambda _: self.preview_workspace_file())
        self.context_file_tree.bind("<Button-3>", self._context_file_menu)
        self.context_file_tree.bind("<Shift-F10>", self._context_file_menu)
        self.context_files_note = ttk.Label(files, style="Muted.TLabel", wraplength=225)
        self.context_files_note.grid(row=2, column=0, sticky="w")
        self.context_file_preview = self.text(files, 3, height=6)
        self.context_book.add(files, text=label("파일", "Files"))

        git = ttk.Frame(self.context_book, padding=5)
        git.columnconfigure(0, weight=1)
        git.rowconfigure(1, weight=3)
        git.rowconfigure(2, weight=2)
        git_bar = ttk.Frame(git)
        git_bar.grid(row=0, column=0, sticky="ew")
        self.context_git_note = ttk.Label(git_bar, style="Muted.TLabel", wraplength=160)
        self.context_git_note.pack(side="left", fill="x", expand=True)
        ttk.Button(git_bar, text=label("새로 읽기", "Reload"), command=self.refresh_workspace_context).pack(side="right")
        self.context_git_tree = self._context_tree(git, ("status",), (label("상태", "Status"),), row=1)
        self.context_git_tree.bind("<Double-1>", lambda _: self.preview_workspace_diff())
        self.context_git_tree.bind("<Return>", lambda _: self.preview_workspace_diff())
        self.context_git_preview = self.text(git, 2, height=6)
        self.context_book.add(git, text="Git")
        self._context_clear()
        return self.context_book

    def _context_tree(self, frame, columns, headers, *, row):
        body = ttk.Frame(frame)
        body.grid(row=row, column=0, sticky="nsew", pady=4)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        tree = ttk.Treeview(body, columns=columns, show="tree headings", selectmode="browse", height=7)
        tree.heading("#0", text=self._context_label("경로", "Path"))
        tree.column("#0", width=135, minwidth=75)
        for column, title in zip(columns, headers):
            tree.heading(column, text=title)
            tree.column(column, width=50, minwidth=42, stretch=False, anchor="center")
        scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return tree

    def _context_clear(self):
        label = self._context_label
        for tree in (self.context_file_tree, self.context_git_tree):
            tree.delete(*tree.get_children())
        self._context_git.clear()
        self._context_files.clear()
        self._context_file_pending.clear()
        self._context_file_loaded.clear()
        self._context_search_active = False
        self.context_git_branch = None
        message = label("프로젝트를 선택하세요.", "Select a project.")
        self.context_files_note.configure(text=message)
        self.context_git_note.configure(text=message)
        self.write(self.context_file_preview, "", True)
        self.write(self.context_git_preview, "", True)

    def set_workspace_context(self, project_id, project, *, refresh=False):
        if not hasattr(self, "context_book"):
            return
        selection = (project_id, project["path"], project.get("host")) if project else None
        if selection == self.context_project and not refresh:
            return
        self.context_project = selection
        self._context_generation += 1
        self._context_listing += 1
        self.context_file_query.set("")
        self._context_clear()
        if not selection:
            return
        self._context_load_directory(".")
        _, root, host = selection
        self.context_git_note.configure(text=self._context_label("Git 상태 확인 중…", "Reading Git status…"))
        self._context_request(lambda: self._context_git_status(root, host), self._context_present_git,
                              self.context_git_note, remote=bool(host))

    def _context_git_status(self, root, host):
        if not host:
            branch, rows = project_git_status(Path(root))
            return branch, rows, False
        result = self.ssh(host).worker_git("git_status", repo=root)
        branch, rows, truncated = result["branch"], result["changes"], result["truncated"]
        require((branch is None or isinstance(branch, str)) and isinstance(rows, dict) and len(rows) <= 300
                and type(truncated) is bool, "Invalid Worker Git response.")
        return branch, {name: state for name, state in rows.items() if project_file_visible(name)
                        and isinstance(state, str) and len(state) == 2
                        and set(state) <= set(" MADRCTU?!")}, truncated

    def refresh_workspace_context(self):
        if self.context_project:
            key, path, host = self.context_project
            self.set_workspace_context(key, {"path": path, "host": host}, refresh=True)

    def focus_workspace_file_search(self):
        self.context_book.select(0)
        self.context_search.focus_set()
        self.context_search.select_range(0, "end")

    def _context_request(self, work, present, note=None, *, current=lambda: True, remote=False):
        generation = self._context_generation

        def read():
            try:
                return True, work()
            except Temporary:
                if not remote:
                    return False, self._context_label("읽기 요청이 지연되었습니다. 다시 읽으세요.",
                                                      "The read timed out. Try reloading.")
                return False, self._context_label("Worker 연결이 끊겼습니다. 연결을 확인하고 다시 읽으세요.",
                                                  "Worker disconnected. Check the connection and reload.")
            except Invalid as error:
                if remote and str(error) == "지원하지 않는 Worker 요청입니다.":
                    return False, self._context_label("이 Worker는 Git 보기를 지원하지 않습니다. Worker를 업데이트하세요.",
                                                      "Update the Worker to use the Git view.")
                return False, self.workspace_error(error)
            except (OSError, RuntimeError, ValueError, TypeError, KeyError):
                return False, self._context_label("선택한 정보를 읽을 수 없습니다.", "Could not read the selected information.")

        def done(result):
            if generation != self._context_generation or not current() or not self.context_book.winfo_exists():
                return
            ok, value = result
            if ok:
                present(value)
            elif note is not None:
                note.configure(text=value)
            else:
                present(value)

        self.background(read, done)

    def _context_load_directory(self, relative):
        if not self.context_project or relative in self._context_file_pending or relative in self._context_file_loaded:
            return
        _, path, host = self.context_project
        generation = self._context_listing
        self._context_file_pending.add(relative)
        self.context_files_note.configure(text=self._context_label("목록을 읽는 중…", "Reading files…"))

        def read():
            if not host:
                return browse_project(Path(path), relative)
            rows = self.ssh(host).call("browse", repo=path, path=relative)
            entries = [(PurePosixPath(relative, row["name"]).as_posix(), bool(row["directory"])) for row in rows
                       if isinstance(row["name"], str) and "/" not in row["name"]]
            return [row for row in entries if project_file_visible(row[0])], len(rows) >= 300

        def show(result):
            self._context_file_pending.discard(relative)
            if isinstance(result, str):
                self.context_files_note.configure(text=result)
                return
            entries, truncated = result
            self._context_file_loaded.add(relative)
            parent = "" if relative == "." else relative
            self.context_file_tree.delete(*self.context_file_tree.get_children(parent))
            self._context_insert_files(parent, entries)
            suffix = self._context_label(" · 표시 한도 도달", " · Limit reached") if truncated else ""
            if host:
                suffix += self._context_label(" · 펼친 폴더만 검색", " · Search loaded folders")
            self.context_files_note.configure(text=f'{len(entries)} {self._context_label("개 항목", "entries")}{suffix}')

        self._context_request(read, show, current=lambda: generation == self._context_listing, remote=bool(host))

    def _context_insert_files(self, parent, entries, *, search=False):
        for path, directory in entries:
            self._context_files[path] = directory
            icon = "▸" if directory else "‹›" if PurePosixPath(path).suffix in {".py", ".ts", ".js", ".sh", ".rs"} else "◇"
            title = path if search else PurePosixPath(path).name
            self.context_file_tree.insert(parent, "end", iid=path, text=f"{icon}  {title}",
                                          values=(self._context_git.get(path, ""),))
            if directory:
                self.context_file_tree.insert(path, "end", iid=path + ":", text="…")

    def _context_expand(self, _):
        relative = self.context_file_tree.focus()
        if not self._context_search_active and self._context_files.get(relative):
            self._context_load_directory(relative)

    def _context_file_double_click(self, event):
        selected = self.context_file_tree.identify_row(event.y)
        if selected in self._context_files and not self._context_files[selected]:
            self.context_file_tree.selection_set(selected)
            self.preview_workspace_file()

    def search_workspace_files(self):
        if not self.context_project:
            return
        query = self.context_file_query.get().strip().casefold()
        if not query:
            self.refresh_workspace_context()
            return
        _, path, host = self.context_project
        self._context_listing += 1
        generation = self._context_listing
        self._context_search_active = True
        loaded = [(relative, False) for relative, directory in self._context_files.items()
                  if not directory and query in relative.casefold()]
        self._context_file_pending.clear()
        self._context_file_loaded.clear()
        self.context_files_note.configure(text=self._context_label("파일 검색 중…", "Searching files…"))

        def read():
            return (sorted(loaded)[:SEARCH_RESULTS], len(loaded) > SEARCH_RESULTS) if host else search_project_files(Path(path), query)

        def show(result):
            entries, truncated = result
            self.context_file_tree.delete(*self.context_file_tree.get_children())
            if not host:
                self._context_files.clear()
            self._context_insert_files("", entries, search=True)
            suffix = self._context_label(" · 검색 한도 도달", " · Limit reached") if truncated else ""
            if host:
                suffix += self._context_label(" · 펼친 폴더만 검색", " · Loaded folders only")
            self.context_files_note.configure(text=f'{len(entries)} {self._context_label("개 결과", "matches")}{suffix}')

        self._context_request(read, show, self.context_files_note, current=lambda: generation == self._context_listing)

    def _context_selected_file(self):
        selected = self.context_file_tree.selection()
        if selected and selected[0] in self._context_files:
            return selected[0], self._context_files[selected[0]]
        return None, False

    def preview_workspace_file(self):
        relative, directory = self._context_selected_file()
        if not self.context_project or not relative or directory:
            return
        _, root, host = self.context_project
        self.write(self.context_file_preview, self._context_label("미리 보기를 읽는 중…", "Loading preview…"), True)

        def read():
            if not host:
                return _preview_text(read_project_file(Path(root), relative))
            require(project_file_visible(relative), "보호된 파일입니다.")
            raw = base64.b64decode(self.ssh(host).call("download", repo=root, path=relative)["content"], validate=True)
            require(len(raw) <= MAX_FILE, "200 KB 이하의 파일만 미리 볼 수 있습니다.")
            return _preview_text(raw)

        self._context_request(read, lambda value: self.write(self.context_file_preview, f"{relative}\n\n{value}", True),
                              current=lambda: self._context_selected_file()[0] == relative, remote=bool(host))

    def _context_present_git(self, result):
        branch, rows, truncated = result
        self.context_git_branch = branch
        self._context_git = rows
        name = branch if branch and branch != "(detached)" else self._context_label("분리 HEAD", "Detached HEAD")
        count = f"{len(rows)}+" if truncated else str(len(rows))
        self.context_git_note.configure(text=f"{name} · {count} {self._context_label('개 변경', 'changes')}")
        self.context_git_tree.delete(*self.context_git_tree.get_children())
        for path, state in sorted(rows.items()):
            self.context_git_tree.insert("", "end", iid=path, text=path, values=(state,))
        for path in self._context_files:
            if self.context_file_tree.exists(path):
                self.context_file_tree.item(path, values=(rows.get(path, ""),))
        help_text = self._context_label("M 수정 · A 추가 · D 삭제 · ?? 미추적\n파일을 두 번 눌러 Diff를 봅니다.",
                                        "M modified · A added · D deleted · ?? untracked\nDouble-click a path to inspect its diff.")
        self.write(self.context_git_preview, help_text, True)

    def preview_workspace_diff(self):
        selected = self.context_git_tree.selection()
        if not self.context_project or not selected or selected[0] not in self._context_git:
            return
        path = selected[0]
        _, root, host = self.context_project
        state = self._context_git[path]
        self.write(self.context_git_preview, self._context_label("Diff를 읽는 중…", "Reading diff…"), True)

        def read():
            if not host:
                return project_file_diff(Path(root), path, state)
            result = self.ssh(host).worker_git("git_diff", repo=root, path=path)
            require(result["path"] == path and isinstance(result["diff"], str)
                    and len(result["diff"].encode("utf-8")) <= MAX_FILE, "Invalid Worker Git response.")
            return result["diff"]

        self._context_request(read,
                              lambda value: self.write(self.context_git_preview, self.w(value) if value else self._context_label(
                                  "표시할 텍스트 변경이 없습니다.", "There are no text changes to display."), True),
                              current=lambda: self.context_git_tree.selection() == (path,), remote=bool(host))

    def _context_file_menu(self, event):
        if getattr(event, "num", None) == 3:
            row = self.context_file_tree.identify_row(event.y)
            if row not in self._context_files:
                return
            self.context_file_tree.selection_set(row)
        relative, directory = self._context_selected_file()
        if not relative or not self.context_project:
            return
        label = self._context_label
        if self._context_menu is not None:
            self._context_menu.destroy()
        menu = self._context_menu = tk.Menu(self.context_file_tree, tearoff=False)
        if not directory:
            menu.add_command(label=label("미리 보기", "Preview"), command=self.preview_workspace_file)
        menu.add_command(label=label("경로 복사", "Copy path"), command=lambda: self.action(lambda: self._context_file_action("copy")))
        if not self.context_project[2]:
            if not directory:
                menu.add_command(label=label("외부 편집기에서 열기", "Open in external editor"),
                                 command=lambda: self.action(lambda: self._context_file_action("edit")))
            menu.add_command(label=label("파일 관리자에서 보기", "Show in file manager"),
                             command=lambda: self.action(lambda: self._context_file_action("reveal")))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _context_file_action(self, action):
        relative, directory = self._context_selected_file()
        if not relative or not self.context_project:
            return
        _, root, host = self.context_project
        if action == "copy":
            path = str(PurePosixPath(root, relative) if host else _safe_path(Path(root), relative))
            self.window.clipboard_clear()
            self.window.clipboard_append(path)
            return
        path = _safe_path(Path(root), relative)
        if action == "reveal":
            open_directory(path if directory else path.parent)
            return
        require(path.is_file(), "편집기로 열 일반 파일을 선택하세요.")
        choices = ("notepad.exe",) if os.name == "nt" else ("code", "gedit", "kate", "mousepad", "xed", "leafpad")
        executable = next((found for name in choices if (found := shutil.which(name))), None)
        require(executable, "지원하는 외부 GUI 편집기를 찾지 못했습니다.")
        subprocess.Popen([executable, str(path)], cwd=path.parent)
