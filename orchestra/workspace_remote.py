"""SSH environment, Worker runs and remote project file panels."""
from __future__ import annotations

import base64
import time
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import SECRET_FILE, atomic_bytes, atomic_json, require
from .desktop import STATES, formatted
from .execution_state import TERMINAL
from .observability import EVENT_LABELS, agent_rows
from .remote import MAX_FILE, metrics
from .ssh import SSHClient, pinned_key, scan_keys, ssh_env, trust_key
from .workspace import put_host, put_project, read_workspace, remove_profile
from .workspace_forms import Form


class RemoteWorkspace:
    def ssh(self, key):
        host = read_workspace(self.root)["hosts"].get(key)
        require(host, "등록된 SSH 호스트를 선택하세요.")
        return SSHClient(self.root, key, host)

    def environments_page(self):
        frame = self.base("실행 환경", "이 PC와 SSH 호스트의 연결, Worker 및 가용 도구를 관리합니다.")
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(4, weight=2)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "SSH 호스트 추가", lambda: self.host_dialog(), True)
        self.button(bar, "편집", lambda: self.action(lambda: self.host_dialog(self.selected_host())))
        self.button(bar, "연결 테스트", lambda: self.action(self.test_host))
        self.button(bar, "신뢰 지문", lambda: self.action(self.host_trust))
        self.button(bar, "터미널", lambda: self.action(self.host_terminal))
        self.button(bar, "삭제", lambda: self.action(self.delete_host))
        self.button(bar, "GPU 지표", lambda: self.action(self.measure_gpu), side="right")
        self.hosts_list = self.table(frame, 3, (("node", "실행 환경", 190), ("group", "그룹", 95),
                                                ("kind", "OS", 90), ("status", "최근 연결", 170)))
        self.hosts_list.bind("<<TreeviewSelect>>", lambda _: self.render_host())
        self.host_details = self.text(frame, 4)
        self.write(self.host_details, "이 PC를 선택해 리소스를 조회하거나 Linux SSH Worker를 등록하세요.", True)
        return frame

    def refresh_hosts(self):
        hosts = read_workspace(self.root)["hosts"]
        rows = [("local", ("이 PC", "로컬", "—", "사용 가능"))]
        for key, profile in hosts.items():
            saved = self.host_evidence.get(key, {})
            last = "최근 Worker 연결 성공" if saved.get("worker") else "최근 SSH 연결 성공" if saved.get("ssh") else "미확인"
            if saved.get("error"):
                last = "연결 실패"
            rows.append((key, (profile["name"], profile.get("group", "") or "—", profile["os"], last)))
        selected = self.hosts_list.selection()
        self.fill(self.hosts_list, rows, selected[0] if selected else None)

    def selected_host(self):
        selected = self.hosts_list.selection()
        require(selected, "실행 환경을 선택하세요.")
        return selected[0]

    def edit_host_profile(self, key):
        return read_workspace(self.root)["hosts"].get(key)

    def host_dialog(self, key=None):
        previous = self.edit_host_profile(key) if key else None
        require(key is None or previous, "편집할 SSH 호스트를 선택하세요.")
        old = previous or {}
        form = Form(self, "SSH 호스트 편집" if key else "SSH 호스트 추가",
                    "SSH Agent 또는 키 파일 경로를 사용합니다. 등록한 뒤 서버의 공개 지문을 확인하세요.")
        for field, label, default in (("name", "표시 이름", ""), ("group", "그룹", ""), ("host", "호스트/IP", ""),
                                      ("user", "사용자", ""), ("port", "포트", "22"), ("identity", "키 파일 경로", ""),
                                      ("directory", "터미널 시작 디렉터리", ""), ("worker_dir", "Worker 소스 디렉터리", ""),
                                      ("timeout", "연결 제한(초)", "8"), ("python", "Worker Python", "python3")):
            form.field(field, label, old.get(field, default))
        form.field("auth", "공개 키 인증", old.get("auth", "agent"), choices=("agent", "key", "agent+key"))
        form.field("os", "원격 OS", old.get("os", "linux"), choices=("linux", "windows"))
        form.note("Worker 소스 디렉터리에는 서버에 배치한 ModelOrchestration.pyw와 orchestra 폴더가 있어야 합니다.")
        def browse():
            file = filedialog.askopenfilename(parent=form, title="SSH 개인 키 파일 위치")
            if file:
                form.set("identity", file)
        self.button(form.footer, "키 파일 선택", browse)
        def save():
            values = form.values()
            for field in ("port", "timeout"):
                values[field] = int(values[field])
            referenced = key is not None and any(item["host"] == key for item in self.store.remote_runs())
            identifier = put_host(self.root, values, key, referenced=referenced)
            form.destroy()
            self.refresh_hosts()
            self.hosts_list.selection_set(identifier)
            self.render_host()
        form.controls("호스트 저장", save)

    def host_trust(self):
        key = self.selected_host()
        client = self.ssh(key)
        self.write(self.host_details, "서버에서 공개 키를 조회하는 중입니다…", True)

        def confirm(candidates):
            profile = client.profile
            before = pinned_key(self.root, key, profile)
            details = "\n".join(f"{fingerprint}   {data[0]}" for fingerprint, data in candidates.items())
            previous = f"\n기존에 신뢰한 지문  {before[1]}" if before else ""
            value = simpledialog.askstring("SSH 호스트 지문 확인",
                f'{profile["name"]}{previous}\n\n서버가 공개한 후보\n{details}\n\n'
                "서버 관리자 등 독립 경로로 확인한 지문을 입력하세요.", parent=self.window)
            if value:
                self.action(lambda: trust_key(self.root, key, profile, value.strip(), candidates))
            self.render_host()
        self.background(lambda: scan_keys(client.profile), confirm)

    def measure_gpu(self):
        self.selected_host()
        if messagebox.askyesno("GPU 지표 조회", "선택한 환경에서 읽기 전용 GPU 상태를 조회하시겠습니까?", parent=self.window):
            self.test_host(gpu=True)

    def test_host(self, gpu=False):
        key = self.selected_host()
        self.write(self.host_details, "관측 가능한 실행 환경 정보를 조회하는 중…", True)
        if key == "local":
            self.background(lambda: metrics(gpu=gpu), lambda value: self.record_host(key, {"resources": value}))
            return
        client = self.ssh(key)
        def measure():
            try:
                result = {"ssh": client.test()}
            except (ValueError, OSError, RuntimeError) as exc:
                return {"error": str(exc)}
            if client.profile["os"] == "linux" and client.profile.get("worker_dir"):
                try:
                    result["worker"] = client.call("info", gpu=gpu)
                except (ValueError, OSError, RuntimeError) as exc:
                    result["worker_error"] = str(exc)
            return result
        self.background(measure, lambda value: self.record_host(key, value))

    def record_host(self, key, value):
        self.host_evidence[key] = value | {"at": time.time()}
        self.refresh_hosts()
        if self.hosts_list.selection() == (key,):
            self.render_host()

    def render_host(self):
        if not self.hosts_list.selection():
            return
        key = self.hosts_list.selection()[0]
        saved = self.host_evidence.get(key, {})
        checked = f'\n측정 시각   {datetime.fromtimestamp(saved["at"]).isoformat(timespec="seconds")}' if saved else ""
        if key == "local":
            description = "이 PC · 연결 테스트로 CPU/RAM을 관측합니다."
        else:
            profile = self.edit_host_profile(key)
            if profile is None:
                return
            pin = pinned_key(self.root, key, profile)
            description = (f'{profile["user"]}@{profile["host"]}:{profile["port"]} · {profile["os"]}\n'
                           f'신뢰 지문   {pin[1] if pin else "등록 필요"}\n'
                           f'Worker 경로   {profile.get("worker_dir") or "—"}')
        if "worker" in saved:
            heartbeat = saved["worker"]["heartbeat"]
            observed = "미관측" if heartbeat is None else datetime.fromtimestamp(heartbeat).strftime("%Y-%m-%d %H:%M:%S")
            checked += f"\nWorker 하트비트   {observed}"
        self.write(self.host_details, description + checked + ("\n\n" + formatted(saved) if saved else ""), True)

    def host_terminal(self):
        key = self.selected_host()
        if key == "local":
            self.new_terminal()
        else:
            client = self.ssh(key)
            self.new_terminal(client.profile["name"], client.terminal(), env=ssh_env())

    def delete_host(self):
        key = self.selected_host()
        profile = self.edit_host_profile(key)
        require(profile, "삭제할 SSH 호스트를 선택하세요.")
        require(not any(item["host"] == key for item in self.store.remote_runs()),
                "복구 가능한 원격 실행 기록이 이 호스트를 참조하고 있습니다.")
        if messagebox.askyesno("SSH 프로필 삭제", f'{profile["name"]} 프로필을 삭제하시겠습니까?', parent=self.window):
            remove_profile(self.root, "hosts", key)
            self.host_evidence.pop(key, None)
            self.refresh_hosts()

    def remote_files(self, project):
        client = self.ssh(project["host"])
        form = Form(self, "원격 프로젝트 파일", project["path"], width=660)
        field = form.field("path", "상대 디렉터리", ".")
        listing = self.table(form.body, form.row, (("name", "파일", 320), ("type", "유형", 170)), height=10)
        listing.master.grid_configure(columnspan=2)
        form.row += 1
        note = form.note("서버에서 파일 목록을 가져옵니다.")
        rows = {}
        displayed = {"path": "."}
        def list_files():
            target = form.get("path") or "."
            def present(result):
                if not form.winfo_exists() or (form.get("path") or ".") != target:
                    return
                displayed["path"] = target
                rows.clear()
                rows.update((str(index), item) for index, item in enumerate(result))
                self.fill(listing, [(key, (row["name"], "디렉터리" if row["directory"] else "파일")) for key, row in rows.items()])
                note.configure(text=f"{len(result)} 항목 · 비밀 파일과 링크는 탐색에서 제외됩니다.")
            self.background(lambda: client.call("browse", repo=project["path"], path=target), present)
        def selected():
            require(listing.selection(), "파일 또는 디렉터리를 선택하세요.")
            item = rows[listing.selection()[0]]
            return item, (PurePosixPath(displayed["path"]) / item["name"]).as_posix()
        def navigate():
            item, target = selected()
            require(item["directory"], "디렉터리를 선택하세요.")
            form.set("path", target)
            list_files()
        def go_up():
            form.set("path", PurePosixPath(displayed["path"]).parent.as_posix())
            list_files()
        def download():
            item, target = selected()
            require(not item["directory"], "다운로드할 파일을 선택하세요.")
            output = filedialog.asksaveasfilename(parent=form, initialfile=item["name"])
            if not output:
                return
            def save(result):
                raw = base64.b64decode(result["content"], validate=True)
                require(len(raw) <= MAX_FILE, "다운로드 파일이 허용 크기를 초과합니다.")
                atomic_bytes(Path(output), raw)
                if form.winfo_exists():
                    note.configure(text="다운로드 완료")
            self.background(lambda: client.call("download", repo=project["path"], path=target), save)
        def task_context():
            item, target = selected()
            require(not item["directory"], "작업 읽기 범위에 추가할 파일을 선택하세요.")
            key = next((key for key, value in self.project_rows().items()
                        if value["path"] == project["path"] and value.get("host") == project["host"]), None)
            require(key is not None, "등록된 프로젝트를 찾을 수 없습니다.")
            saved = self.project_rows()[key]
            paths = list(dict.fromkeys([*saved.get("read_paths", []), target]))
            put_project(self.root, {"name": saved["name"], "path": saved["path"], "host": saved["host"], "branch": saved["branch"],
                                   "read_paths": paths}, key)
            note.configure(text="이 프로젝트의 기본 읽기 범위에 추가했습니다.")
        def upload():
            source = filedialog.askopenfilename(parent=form)
            if not source:
                return
            file = Path(source)
            require(not SECRET_FILE.search(file.name), "자격 증명 파일은 업로드할 수 없습니다.")
            require(file.is_file() and file.stat().st_size <= MAX_FILE, "200 KB 이하의 일반 파일이 필요합니다.")
            if messagebox.askyesno("원격 업로드 승인", f'{file.name}을 서버의 Worker 보관 폴더에 전송하시겠습니까?', parent=form):
                content = base64.b64encode(file.read_bytes()).decode()
                self.background(lambda: client.call("upload", repo=project["path"], name=file.name, content=content,
                                                    upload_id=uuid.uuid4().hex),
                                lambda result: note.configure(text=f'업로드 완료 · {result["path"]}') if form.winfo_exists() else None)
        listing.bind("<Double-1>", lambda _: self.action(navigate))
        field.bind("<Return>", lambda _: self.action(list_files))
        self.button(form.footer, "상위 폴더", lambda: self.action(go_up))
        self.button(form.footer, "다운로드", lambda: self.action(download))
        self.button(form.footer, "작업 읽기 범위에 추가", lambda: self.action(task_context))
        if self.host_evidence.get(project["host"], {}).get("worker", {}).get("allow_upload"):
            self.button(form.footer, "업로드", lambda: self.action(upload))
        form.controls("조회", list_files)
        list_files()

    def remote_runs_page(self):
        frame = self.base("원격 작업", "원격 Worker의 실제 상태와 이벤트를 불러옵니다.")
        frame.rowconfigure(3, weight=1)
        frame.rowconfigure(4, weight=2)
        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, sticky="ew")
        self.button(bar, "로컬 작업", lambda: self.show("jobs"))
        self.button(bar, "다시 연결", lambda: self.action(lambda: self.pull_remote(reconnect=True)), True)
        self.remote_controls = {}
        for action, label in (("cancel", "중지"), ("retry", "재시도"), ("merge", "병합 승인"), ("approval", "도구 승인")):
            self.remote_controls[action] = self.button(bar, label, lambda name=action: self.action(lambda: self.remote_action(name)))
            self.remote_controls[action].state(["disabled"])
        self.button(bar, "보고서 저장", self.remote_export, side="right")
        self.remote_list = self.table(frame, 3, (("run", "작업", 230), ("host", "호스트", 150),
                                                 ("status", "상태", 170), ("seen", "관측", 105)))
        self.remote_list.bind("<<TreeviewSelect>>", self.remote_selection_changed)
        self.remote_detail = self.text(frame, 4)
        self.write(self.remote_detail, "등록된 원격 프로젝트에서 작업을 시작하면 실행이 여기에 표시됩니다.", True)
        return frame

    def remote_selection_changed(self, _=None):
        selected = self.remote_list.selection()
        if selected and self.remote_selected != selected[0]:
            self.remote_selected = selected[0]
            self.render_remote()
            self.action(self.pull_remote)

    def refresh_remote(self):
        hosts = read_workspace(self.root)["hosts"]
        rows = []
        for item in self.store.remote_runs():
            cache = self.remote_cache.get(item["id"], {})
            state = cache.get("state")
            label = "연결 끊김" if cache.get("error") else STATES.get(state, state) if state else "원격 확인 대기"
            seen = datetime.fromtimestamp(cache["at"]).strftime("%H:%M:%S") if cache.get("at") else "—"
            rows.append((item["id"], (item["plan"]["title"], hosts.get(item["host"], {}).get("name", "—"), label, seen)))
        self.fill(self.remote_list, rows, self.remote_selected)

    def submit_remote_run(self, host, plan):
        self.remote_selected = self.store.queue_remote(host, plan)
        self.show("remote_runs")
        self.pull_remote(reconnect=True)

    def remote_run(self):
        row = next((item for item in self.store.remote_runs() if item["id"] == self.remote_selected), None)
        require(row, "원격 작업을 선택하세요.")
        return row

    def pull_remote(self, reconnect=False):
        row = self.remote_run()
        key = row["id"]
        if key in self.remote_pending:
            return
        client = self.ssh(row["host"])
        cached = self.remote_cache.get(key, {})
        if cached.get("error") and not reconnect:
            return
        if not row["remote_job"] and not reconnect:
            return
        self.remote_pending.add(key)
        previous = cached.get("events", [])
        cursor = previous[-1]["seq"] if previous else 0
        def pull():
            try:
                remote_id = row["remote_job"]
                if not remote_id:
                    receipt = client.call("submit", request_id=key, plan=row["plan"])
                    remote_id = receipt["id"]
                    self.store.remember_remote(key, remote_id)
                page = client.call("status", job=remote_id, after=cursor)
                return page | {"at": time.time(), "events": (previous + page["events"])[-600:]}
            except (ValueError, OSError, RuntimeError, KeyError) as exc:
                return cached | {"error": str(exc), "at": time.time()}
        def done(value):
            self.remote_pending.discard(key)
            self.remote_cache[key] = value
            self.refresh_remote()
            if self.remote_selected == key:
                self.render_remote()
        self.background(pull, done)

    def render_remote(self):
        key = self.remote_selected
        if not key:
            return
        value = self.remote_cache.get(key, {})
        state = value.get("state")
        live = not value.get("error")
        for action, button in self.remote_controls.items():
            active = live and state is not None and {
                "cancel": state not in TERMINAL | {"MERGING"}, "retry": state == "FAILED",
                "merge": state == "AWAITING_APPROVAL", "approval": state == "AWAITING_TOOL",
            }[action]
            button.state(["!disabled" if active else "disabled"])
        job = self.remote_run()
        items = value.get("tasks", [])
        agents = agent_rows({"plan": job["plan"], "state": state}, {item["id"]: item for item in items}, value.get("events", []))
        lines = [f'{job["plan"]["title"]} · {STATES.get(state, "미관측")}']
        if value.get("error"):
            lines.append(f'연결 오류 · {value["error"]}')
        if value.get("candidate"):
            lines.append(f'병합 후보 · {value["candidate"]}')
        for agent in agents:
            lines.append(f'{agent["id"]}   {agent["role"] or "—"}   {STATES.get(agent["state"], agent["state"])}   '
                         f'{agent["model"] or "—"} / {agent["harness"] or "—"}   도구 {agent["tools"]}회')
        for event in reversed(value.get("events", [])):
            clock = datetime.fromtimestamp(event["timestamp"]).strftime("%H:%M:%S")
            label = EVENT_LABELS.get(event["event_type"], event["event_type"])
            lines.append(f'{clock}  {event["task_id"] or "작업"}  {label}  {formatted(event["payload"])}')
        self.write(self.remote_detail, "\n".join(lines), True)

    def remote_action(self, name):
        row = self.remote_run()
        remote_id = row["remote_job"]
        require(remote_id, "원격 Worker에서 확인된 실행을 선택하세요.")
        client = self.ssh(row["host"])
        if name == "approval":
            def review(approvals):
                if not approvals:
                    return
                item = approvals[0]
                result = messagebox.askyesnocancel("원격 외부 쓰기 승인", f'{item["task"]} · {item["tool"]}\n{formatted(item["args"])}',
                                                   parent=self.window)
                if result is not None:
                    self.background(lambda: client.call("decide", job=remote_id, task=item["task"], key=item["key"], accept=result),
                                    lambda _: self.pull_remote(reconnect=True))
            self.background(lambda: client.call("approvals", job=remote_id), review)
            return
        candidate = self.remote_cache[row["id"]].get("candidate") if name == "merge" else None
        revision = self.remote_cache[row["id"]].get("approval_revision") if name == "merge" else None
        label = {"cancel": "중지", "retry": "재시도", "merge": "병합 승인"}[name]
        if messagebox.askyesno("원격 " + label, f'서버에서 {label}을 요청합니다.\n{candidate or ""}', parent=self.window):
            self.background(lambda: client.call("action", job=remote_id, action=name, candidate=candidate, approval_revision=revision),
                            lambda _: self.pull_remote(reconnect=True))

    def remote_export(self):
        def save():
            row = self.remote_run()
            data = self.remote_cache.get(row["id"])
            require(data and data.get("id"), "연결 후 받은 실행 상태가 필요합니다.")
            target = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                                 initialfile=f'worker-{data["id"]}.json')
            if target:
                atomic_json(Path(target), data)
        self.action(save)
