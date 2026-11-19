# 테스트와 빌드

## 개발 환경

앱 코드는 Python 3.11 이상 표준 라이브러리와 Tcl/Tk를 사용합니다. 외부 실행 의존성은 Git, 선택한 Model Runtime 및 CLI입니다. 앱 실행에 Node.js나 Docker가 필요하지 않습니다. Node.js는 문서 Markdown 검사에 사용합니다.

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
