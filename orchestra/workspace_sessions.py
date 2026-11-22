"""Project-scoped interactive terminals for the Tk workspace."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from tkinter import messagebox, ttk

from .core import Invalid, require
from .processes import env_for_process, executable, run
from .ssh import ssh_env
from .supervisor import read_config
from .terminal import TerminalView, operator_shell
from .workspace import opencode_model_provider, read_workspace, scan_clis


AI_CLIS = ("OpenCode", "Codex", "Gemini CLI", "Antigravity", "Claude Code")
MODEL_FLAGS = {"Codex": "codex", "OpenCode": "opencode"}


@dataclass(frozen=True)
class TerminalModel:
    provider: str
    identifier: str
    executable: str | None = None


@dataclass(frozen=True)
class Recipe:
    kind: str
    project: str | None = None
    profile: str | None = None
    model: str | None = None

    def identity(self):
        return self.kind, self.project, self.profile

    def descriptor(self):
        return {"kind": self.kind, "project": self.project, "profile": self.profile, "model": self.model}


@dataclass
class TerminalTab:
    frame: ttk.Frame
    title: str
    recipes: list[Recipe]
    views: list = field(default_factory=list)
    args: list = field(default_factory=list)
    orient: str = "horizontal"
    sash: float = .5
    pane: ttk.Panedwindow | None = None
    placeholder: ttk.Frame | None = None
    archived: bool = False
    active_panel: int = 0


class WorkspaceSessions:
    def init_workspace_sessions(self, book):
        self.terminal_book = book
        self.terminals = {}
        self.terminal_tabs = {}

    def _terminal_changed(self):
        notify = getattr(self, "workspace_session_changed", None)
        if notify:
            notify()

    def _terminal_project(self, project_id):
        if project_id:
            project = self.project_rows().get(project_id)
            require(project, self.w("터미널의 프로젝트를 다시 등록하세요."))
            return project
        return {}

    def available_terminal_models(self, cli):
        """Return registry profiles with an explicit compatible CLI model argument."""
        adapter = MODEL_FLAGS.get(cli)
        if not adapter:
            return {}
        registry = read_config(self.root)
        profiles = {}
        for key, model in registry["models"].items():
            harnesses = [registry["harnesses"][name] for name in model.get("harnesses", ())
                         if registry["harnesses"][name]["kind"] == adapter]
            if not harnesses:
                continue
            # A Runtime route alone cannot configure a standalone interactive CLI.
            target = model.get("cli_model") or (model["model"] if not model.get("runtime") else None)
            if cli == "OpenCode":
                provider = opencode_model_provider(target)
                attached = next((item for item in harnesses if item.get("trusted")), None)
                if provider and attached and not model.get("runtime"):
                    profiles[key] = TerminalModel(provider, target, attached["executable"])
            elif isinstance(target, str) and 0 < len(target) <= 200 and not target.startswith("-") and "\0" not in target:
                profiles[key] = TerminalModel(model["provider"], target)
        return profiles

    def _terminal_title(self, recipe):
        if recipe.kind == "ai":
            return recipe.profile
        if recipe.kind == "ssh":
            return self.host_name(recipe.profile)
        return self.w("로컬 셸")

    def _terminal_args(self, recipe):
        project = self._terminal_project(recipe.project)
        if recipe.kind == "ssh":
            client = self.ssh(recipe.profile)
            remote_cwd = project.get("path") if project.get("host") == recipe.profile else None
            return client.terminal(remote_cwd), None, ssh_env()
        require(not project.get("host"), self.w("원격 프로젝트의 작업 디렉터리는 SSH 셸에서 열 수 있습니다."))
        cwd = Path(project["path"]) if project else None
        if recipe.kind == "local":
            return operator_shell(), cwd, None
        model = None
        if recipe.model:
            model = self.available_terminal_models(recipe.profile).get(recipe.model)
            require(model, self.w("이 CLI에서 시작 모델로 사용할 수 있는 설정을 선택하세요."))
        if recipe.profile == "OpenCode" and model:
            path = executable(model.executable)
            code, output = run([path, "--version"], env=env_for_process(), timeout=5, limit=4096)
            version = re.search(rb"(?im)^(?:opencode[ \t]+)?v?([12])\.\d+\.\d+\b", output)
            require(code == 0 and version,
                    self.w("시작 모델을 지정하려면 OpenCode 1.x 또는 2.x 실행 파일이 필요합니다."))
            # OpenCode 2's full-screen entry point has no --model flag.
            mode = ["mini", "--standalone"] if version[1] == b"2" else []
            return [path, *mode, "--model", model.identifier], cwd, None
        detected = scan_clis().get(recipe.profile)
        if not detected:
            message = (
                "{0}의 Windows 실행 파일(.exe 또는 .com)을 PATH에 추가하세요." if sys.platform == "win32"
                else "{0} 실행 파일이 PATH에 없습니다. CLI를 설치한 뒤 다시 실행하세요."
            )
            raise Invalid(self.w(message, recipe.profile))
        args = [executable(detected)]
        if model:
            args.extend(["--model", model.identifier])
        return args, cwd, None

    def _terminal_tab(self, title, recipes, orient="horizontal", sash=.5):
        frame = ttk.Frame(self.terminal_book, padding=(4, 4))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tab = TerminalTab(frame, title, list(recipes), orient=orient, sash=sash)
        key = str(frame)
        self.terminal_tabs[key] = tab
        self.terminals[key] = frame, tab.views
        self.terminal_book.add(frame, text=title[:28])
        return key, tab

    def _terminal_view(self, args):
        argv, cwd, env = args
        view = TerminalView(self.terminal_book, argv, cwd, env, font=self.mono_font, palette=self.palette, locale=self.locale)
        view.surface.bind("<FocusIn>", lambda _: self._terminal_panel_focused(view), add="+")
        return view

    def _terminal_panel_focused(self, view):
        tab = self.terminal_tabs.get(self.terminal_book.select())
        if tab and view in tab.views:
            tab.active_panel = tab.views.index(view)
            self._terminal_changed()

    def _set_terminal_pane(self, tab):
        # Sibling terminal widgets stay alive when the geometry manager is replaced.
        if tab.pane:
            for view in tab.pane.panes():
                tab.pane.forget(view)
            tab.pane.destroy()
        tab.pane = ttk.Panedwindow(tab.frame, orient=tab.orient)
        tab.pane.grid(row=0, column=0, sticky="nsew")
        tab.pane.bind("<ButtonRelease-1>", lambda _: self._record_terminal_sash(tab), add="+")
        for recipe, view in zip(tab.recipes, tab.views):
            view.set_session_label(title=self._terminal_title(recipe) if recipe.kind != "custom" else tab.title)
            tab.pane.add(view, weight=1)
        tab.frame.after_idle(lambda: self._position_terminal_sash(tab))

    def _record_terminal_sash(self, tab):
        if tab.pane and len(tab.views) == 2:
            size = tab.pane.winfo_width() if tab.orient == "horizontal" else tab.pane.winfo_height()
            if size > 2:
                tab.sash = max(.12, min(.88, tab.pane.sashpos(0) / size))
        self._terminal_changed()

    @staticmethod
    def _position_terminal_sash(tab):
        if tab.pane and tab.pane.winfo_exists() and len(tab.views) == 2:
            size = tab.pane.winfo_width() if tab.orient == "horizontal" else tab.pane.winfo_height()
            if size > 2:
                tab.pane.sashpos(0, round(size * tab.sash))

    def _start_terminal(self, title, recipe, args):
        key, tab = self._terminal_tab(title, [recipe])
        try:
            tab.views.append(self._terminal_view(args))
            tab.args.append(args)
            self._set_terminal_pane(tab)
        except BaseException:
            self.remove_terminal(key)
            raise
        self.focus_terminal(key)
        return key

    def _existing_terminal(self, recipe):
        for key, tab in self.terminal_tabs.items():
            if not tab.archived and any(other.identity() == recipe.identity() for other in tab.recipes):
                return key
        return None

    def _open_recipe(self, recipe):
        if key := self._existing_terminal(recipe):
            tab = self.terminal_tabs[key]
            index, current = next((index, other) for index, other in enumerate(tab.recipes)
                                  if other.identity() == recipe.identity())
            self.focus_terminal(key, index)
            if recipe.kind == "ai" and recipe.model is not None:
                if current.model != recipe.model:
                    return self.change_terminal_model(recipe.profile, recipe.model, key)
            return key
        return self._start_terminal(self._terminal_title(recipe), recipe, self._terminal_args(recipe))

    def new_terminal(self, title=None, argv=None, cwd=None, env=None, *, project_id=None):
        """Compatibility path for UI actions that already own validated argv."""
        title = title or self.w("로컬 셸")
        if argv is None and cwd is None and env is None and project_id is None:
            return self.local_project_shell()
        recipe = Recipe("custom", project_id)
        return self._start_terminal(title, recipe, (argv or operator_shell(), cwd, env))

    def local_project_shell(self):
        project_id = self.project_id
        project = self._terminal_project(project_id)
        return self._open_recipe(Recipe("local", project_id if not project.get("host") else None))

    def project_terminal(self, project):
        project_id = next((key for key, item in self.project_rows().items() if item == project), None)
        if project.get("host"):
            return self.action(lambda: self.open_ssh_terminal(project["host"], project_id))
        return self.action(lambda: self._open_recipe(Recipe("local", project_id)))

    def open_ai_terminal(self, name, project_id=None, model=None):
        require(name in AI_CLIS, self.w("지원되는 AI CLI를 선택하세요."))
        project_id = self.project_id if project_id is None else project_id
        return self._open_recipe(Recipe("ai", project_id, name, model))

    def open_ssh_terminal(self, host, project_id=None):
        if project_id is None and self.project_id:
            if self._terminal_project(self.project_id).get("host") == host:
                project_id = self.project_id
        return self._open_recipe(Recipe("ssh", project_id, host))

    def focus_terminal(self, key, panel=None):
        tab = self.terminal_tabs.get(key)
        require(tab, self.w("터미널 탭을 찾을 수 없습니다."))
        self.show("workspace" if "workspace" in self.pages else "terminals")
        if self.terminal_book.tab(tab.frame, "state") == "hidden":
            self.terminal_book.add(tab.frame)
        self.terminal_book.select(tab.frame)
        if tab.views:
            if type(panel) is int and 0 <= panel < len(tab.views):
                tab.active_panel = panel
            tab.views[tab.active_panel].surface.focus_set()
        self._terminal_changed()
        return key

    def split_terminal(self, orient="horizontal", kind=None):
        key = self.terminal_book.select()
        tab = self.terminal_tabs.get(key)
        require(tab and tab.views and not tab.archived, self.w("실행했던 터미널 탭을 선택하세요."))
        require(orient in ("horizontal", "vertical"), self.w("분할 방향이 올바르지 않습니다."))
        if len(tab.views) == 1:
            first = tab.recipes[0]
            if kind in AI_CLIS:
                recipe = Recipe("ai", first.project, kind)
                existing = self._existing_terminal(recipe)
                if existing:
                    require(existing != key, self.w("이 탭에 해당 CLI가 이미 열려 있습니다."))
                    source = self.terminal_tabs[existing]
                    require(len(source.views) == 1, self.w("다른 탭의 분할을 해제하거나 복원한 뒤 합치세요."))
                    source.pane.forget(source.views[0])
                    tab.views.append(source.views.pop())
                    tab.args.append(source.args[0])
                    tab.recipes.append(source.recipes[0])
                    self.remove_terminal(existing)
                else:
                    self._append_terminal(tab, recipe, self._terminal_args(recipe))
            elif kind == "local":
                project_id = first.project if not self._terminal_project(first.project).get("host") else None
                recipe = Recipe("local", project_id)
                self._append_terminal(tab, recipe, self._terminal_args(recipe))
            elif first.kind == "ssh":
                self._append_terminal(tab, first, self._terminal_args(first))
            elif first.kind == "custom":
                self._append_terminal(tab, first, tab.args[0])
            else:
                recipe = Recipe("local", first.project)
                self._append_terminal(tab, recipe, self._terminal_args(recipe))
        tab.orient = orient
        tab.sash = .5
        self._set_terminal_pane(tab)
        return self.focus_terminal(key, len(tab.views) - 1)

    def _append_terminal(self, tab, recipe, args):
        view = self._terminal_view(args)
        tab.recipes.append(recipe)
        tab.args.append(args)
        tab.views.append(view)

    def reset_terminal_layout(self):
        key = self.terminal_book.select()
        tab = self.terminal_tabs.get(key)
        require(tab and tab.views, self.w("배치를 복원할 터미널 탭을 선택하세요."))
        if len(tab.views) == 2:
            view = tab.views.pop()
            tab.pane.forget(view)
            recipe = tab.recipes.pop()
            _, second = self._terminal_tab(tab.title if recipe.kind == "custom" else self._terminal_title(recipe), [recipe])
            second.args.append(tab.args.pop())
            second.views.append(view)
            self._set_terminal_pane(second)
            tab.active_panel = 0
        tab.orient = "horizontal"
        tab.sash = .5
        self._set_terminal_pane(tab)
        return self.focus_terminal(key)

    def reset_terminal_split(self):
        tab = self.terminal_tabs.get(self.terminal_book.select())
        require(tab and len(tab.views) == 2, self.w("분할된 터미널 탭을 선택하세요."))
        tab.sash = .5
        self._position_terminal_sash(tab)
        self._terminal_changed()

    def hide_terminal(self, key=None):
        tab = self.terminal_tabs.get(key or self.terminal_book.select())
        if tab:
            self.terminal_book.hide(tab.frame)
            self._terminal_changed()

    def close_terminal_view(self, key=None):
        key = key or self.terminal_book.select()
        tab = self.terminal_tabs.get(key)
        if not tab:
            return
        if not any(not view.closed.is_set() for view in tab.views):
            self.remove_terminal(key)
            return
        action = messagebox.askyesnocancel(self.w("터미널 탭 닫기"),
            self.w("예: 화면만 숨기고 세션 유지\n아니요: 터미널 프로세스 종료\n취소: 탭을 열어 두기"),
            parent=self.window)
        if action is True:
            self.hide_terminal(key)
        elif action is False:
            self.remove_terminal(key)

    def remove_terminal(self, key=None):
        key = key or self.terminal_book.select()
        tab = self.terminal_tabs.pop(key, None)
        if not tab:
            return
        for view in tab.views:
            view.close()
            view.destroy()
        self.terminals.pop(key, None)
        self.terminal_book.forget(tab.frame)
        tab.frame.destroy()
        self._terminal_changed()

    def _reopen_tab(self, key, recipes, panel=None):
        tab = self.terminal_tabs[key]
        if not tab.views:
            arguments = [self._terminal_args(recipe) for recipe in recipes]
            views = []
            try:
                for args in arguments:
                    views.append(self._terminal_view(args))
            except BaseException:
                for view in views:
                    view.close()
                    view.destroy()
                raise
            if tab.placeholder:
                tab.placeholder.destroy()
                tab.placeholder = None
            tab.views.extend(views)
            tab.args.extend(arguments)
            tab.recipes = list(recipes)
            self._set_terminal_pane(tab)
            return self.focus_terminal(key)

        panel = tab.active_panel if panel is None else panel
        recipe, old_view = recipes[panel], tab.views[panel]
        args = self._terminal_args(recipe) if recipe.kind != "custom" else tab.args[panel]
        if not old_view.closed.is_set() and not messagebox.askyesno(self.w("터미널 다시 시작"),
                self.w("선택한 터미널을 종료하고 새 세션을 열까요? 이전 출력은 별도 탭에 남습니다."),
                parent=self.window):
            return key
        if tab.archived:
            return self._start_terminal(tab.title, recipe, args)
        new_view = self._terminal_view(args)
        old_view.close()
        self._record_terminal_sash(tab)
        tab.pane.forget(old_view)
        old_recipe = tab.recipes[panel]
        old_title = tab.title if old_recipe.kind == "custom" else self._terminal_title(old_recipe)
        _, archive = self._terminal_tab(self.w("종료 · ") + old_title, [old_recipe])
        archive.archived = True
        archive.views.append(old_view)
        archive.args.append(tab.args[panel])
        self._set_terminal_pane(archive)
        tab.recipes[panel], tab.views[panel], tab.args[panel] = recipe, new_view, args
        self._set_terminal_pane(tab)
        return self.focus_terminal(key, panel)

    def reopen_terminal(self):
        key = self.terminal_book.select()
        require(key in self.terminal_tabs, self.w("다시 열 터미널 탭을 선택하세요."))
        tab = self.terminal_tabs[key]
        if tab.archived:
            for recipe in tab.recipes:
                if recipe.kind != "custom" and (existing := self._existing_terminal(recipe)):
                    return self.focus_terminal(existing)
        return self._reopen_tab(key, tab.recipes)

    def change_terminal_model(self, cli, model, key=None):
        key = key or self.terminal_book.select()
        tab = self.terminal_tabs.get(key)
        require(tab and not tab.archived and model in self.available_terminal_models(cli),
                self.w("선택한 CLI의 시작 모델 설정을 확인하세요."))
        panel = next((index for index, recipe in enumerate(tab.recipes)
                      if recipe.kind == "ai" and recipe.profile == cli), None)
        require(panel is not None, self.w("선택한 탭에 해당 CLI가 없습니다."))
        current = tab.recipes[panel]
        if current.model == model:
            return self.focus_terminal(key, panel)
        recipes = tab.recipes.copy()
        recipes[panel] = Recipe(current.kind, current.project, current.profile, model)
        return self._reopen_tab(key, recipes, panel)

    def terminal_rows(self, project_id=None):
        rows = []
        for key, tab in self.terminal_tabs.items():
            hidden = self.terminal_book.tab(tab.frame, "state") == "hidden"
            for index, recipe in enumerate(tab.recipes):
                if project_id is not None and recipe.project != project_id:
                    continue
                view = tab.views[index] if tab.views else None
                alive = view is not None and not view.closed.is_set()
                pid = None
                if alive:
                    process = getattr(view.pty, "process", None) or getattr(view.pty, "pty", None)
                    pid = getattr(process, "pid", None)
                status = (self.w("복원 대기") if tab.placeholder else self.w("실행 중") if alive else
                          self.w("연결 종료") if recipe.kind == "ssh" and not tab.archived else self.w("종료됨"))
                title = tab.title if recipe.kind == "custom" or tab.archived else self._terminal_title(recipe)
                rows.append({"id": key, "panel": index, "row_id": f"{key}:{index}", "title": title,
                             "project": recipe.project, "kind": recipe.kind, "profile": recipe.profile,
                             "model": recipe.model, "status": status, "pids": [pid] if type(pid) is int else [],
                             "hidden": hidden, "panes": len(tab.views), "archived": tab.archived})
        return rows

    def terminal_descriptors(self):
        return [descriptor for _, descriptor in self.terminal_layout_entries()]

    def terminal_layout_entries(self):
        for key in self.terminal_book.tabs():
            tab = self.terminal_tabs.get(key)
            if not tab or tab.archived or tab.recipes[0].kind == "custom":
                continue
            sash = tab.sash
            if tab.pane and len(tab.views) == 2:
                size = tab.pane.winfo_width() if tab.orient == "horizontal" else tab.pane.winfo_height()
                if size > 2:
                    sash = max(.12, min(.88, tab.pane.sashpos(0) / size))
            yield key, {"recipes": [recipe.descriptor() for recipe in tab.recipes if recipe.kind != "custom"],
                        "orient": tab.orient, "sash": sash,
                        "hidden": self.terminal_book.tab(tab.frame, "state") == "hidden"}

    def restore_terminal_descriptors(self, descriptors=None):
        if not isinstance(descriptors, list):
            return {}
        projects = self.project_rows()
        hosts = read_workspace(self.root)["hosts"]
        restored = {}
        for index, value in enumerate(descriptors[:40]):
            if not isinstance(value, dict) or not isinstance(value.get("recipes"), list):
                continue
            recipes = []
            for item in value["recipes"][:2]:
                if not isinstance(item, dict) or not all(item.get(key) is None or isinstance(item.get(key), str)
                                                         for key in ("kind", "project", "profile", "model")):
                    continue
                recipe = Recipe(item.get("kind"), item.get("project"), item.get("profile"), item.get("model"))
                if (recipe.project is not None and recipe.project not in projects
                        or recipe.kind not in ("local", "ai", "ssh")
                        or recipe.kind == "ai" and recipe.profile not in AI_CLIS
                        or recipe.kind == "ssh" and recipe.profile not in hosts):
                    continue
                recipes.append(recipe)
            if not recipes or self._existing_terminal(recipes[0]):
                continue
            orient = "vertical" if value.get("orient") == "vertical" else "horizontal"
            sash = value.get("sash")
            sash = sash if type(sash) in (float, int) and .12 <= sash <= .88 else .5
            key, tab = self._terminal_tab(self._terminal_title(recipes[0]), recipes, orient, sash)
            tab.placeholder = ttk.Frame(tab.frame, padding=24)
            tab.placeholder.grid(row=0, column=0, sticky="nsew")
            ttk.Label(tab.placeholder, text=self.w("저장된 터미널 배치"), style="Section.TLabel").pack(anchor="w")
            ttk.Label(tab.placeholder, text=self.w("새 프로세스로 계속하려면 세션을 다시 여세요.")).pack(anchor="w", pady=8)
            self.button(tab.placeholder, self.w("세션 열기"), lambda saved=key: self.action(
                lambda: self._reopen_tab(saved, self.terminal_tabs[saved].recipes)), True)
            if value.get("hidden") is True:
                self.terminal_book.hide(tab.frame)
            restored[f"terminal/{index}"] = key
        return restored

    def close_workspace_sessions(self):
        for tab in self.terminal_tabs.values():
            for view in tab.views:
                view.close()
