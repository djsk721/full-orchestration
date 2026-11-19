# 테스트와 빌드

## 개발 환경

앱 코드는 Python 3.11 이상 표준 라이브러리와 Tcl/Tk를 사용합니다. 외부 실행 의존성은 Git, 선택한 Model Runtime 및 CLI입니다. Tk 데스크톱과 Supervisor에는 Node.js가 필요하지 않습니다. Node.js 24는 TypeScript 대시보드와 검증 도구에 사용합니다.

## 테스트 및 QA

```bash
python -m unittest discover -s tests -v
```

`tests/test_orchestra.py`는 임시 Git 저장소, loopback HTTP, 모의 CLI와 별도 Supervisor를 사용합니다. DAG 실행과 병합 승인, QA 실패, Runtime Gate, MCP 전환·롤백·쓰기 승인, 백그라운드 복구를 다룹니다. 방화벽 또는 샌드박스는 임시 loopback 소켓을 허용해야 합니다.

운영 호스트에서는 GUI 실행, 외부 CLI의 로그인과 버전, 실제 Runtime의 Model·Context·도구 Probe, 승인 및 Background Execution을 점검합니다. Harness A/B 비교에서는 기준 커밋, Model, 명세, QA 및 시간 상한을 고정하고 실행별 JSON 보고서를 저장하세요. 사용량 누락 수와 모델 호출 집계를 함께 비교합니다.

## Windows 빌드 및 배포

Windows에서 아래 명령을 실행합니다. `-InstallBuildDependency`는 PyInstaller 6.x를 설치합니다. 이미 설치했다면 스위치를 생략합니다.

```powershell
.\Build-Windows.ps1 -InstallBuildDependency
```

출력은 `dist\ModelOrchestration\ModelOrchestration.exe`입니다. `--onedir` 빌드이므로 `dist\ModelOrchestration`의 번들 전체를 함께 배포합니다. 깨끗한 Windows 환경에서 앱 실행, Git PATH, QA 전용 작업, Supervisor 실행과 종료를 점검한 뒤 배포물을 공유하세요.

## 공통 검증과 운영체제별 검사

```bash
npm ci
python -m pip install -r requirements-desktop.txt
npm run verify -- --ui --package
```

Linux와 Windows에서 같은 명령으로 TypeScript, Python, 두 데스크톱 UI 및 네이티브 어댑터 계약을 확인합니다. Python이나 데스크톱 없이 검증하려면 `npm run verify -- --core-only`를 사용하세요. Linux에서는 `--ssh`를 추가해 격리된 OpenSSH와 Worker를 확인할 수 있습니다. Windows ConPTY, Job Object 및 설치 프로그램은 Windows에서 나온 결과로만 판정합니다.

Tk 워크플로는 스크립트로 응답하는 모델 API에 연결해 프로젝트 등록부터 승인된 Git 병합까지 실제 Supervisor로 검증합니다. Electron 테스트는 실제 QA 명령이 실행 중일 때 앱을 강제 종료하고, 다시 열어 결과를 확인합니다. 설치된 CLI를 점검하려면 `--harness`를 추가하세요. CLI 시작, 자격 증명 유무, 인증된 모델 실행은 각각 판정합니다.
