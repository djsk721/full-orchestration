# Provider integration verification

**Authenticated external inference: NOT VERIFIED.** The user authorized one Codex smoke using a test-only profile and selected Codex. The test-only profile path and model ID were unavailable during this candidate run. The shared login was left alone and no external inference request was sent.

| Harness | CLI startup | Authentication | Inference and tools |
| --- | --- | --- | --- |
| Codex 0.170.0 | PASS | The default CLI reports stored credentials. Dedicated profile and remote account validity are NOT VERIFIED. | External inference, model identity, token usage, duration and completion are unobserved. |
| OpenCode 2.2.7 | PASS | External Provider authentication NOT VERIFIED | Real CLI against scripted loopback responses. Worktree read, cancellation, HTTP failure and execution history pass. |
| Gemini CLI 0.66.0 | PASS in native Linux harness run | NOT VERIFIED | Discovery-only in this app. The restricted sandbox startup probe returned exit 46. |
| Antigravity 1.5.12 | PASS | NOT VERIFIED | Discovery-only in this app. |
| Managed | Python execution PASS | External endpoint NOT VERIFIED | Scripted inference, actual worktree modification and QA, HTTP timeout recovery and MCP journal protection pass. |

## Authorized Codex smoke entry point

`scripts/qa/codex_external_smoke.py` uses a separately provisioned file-backed test login, a synthetic empty working directory and a fixed response marker. It copies the dedicated auth file into a private temporary directory so the supplied file is left intact. The default invocation checks CLI startup and structural credential presence. An execute invocation starts one Codex turn and saves only a redacted JSON record. The wrapper performs no automatic retry. Codex handles its own transport behavior. [Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference)

```bash
python scripts/qa/codex_external_smoke.py --profile /path/to/test-profile --model MODEL_ID
# After explicitly authorizing the inference
python scripts/qa/codex_external_smoke.py --profile /path/to/test-profile --model MODEL_ID \
  --execute --report /path/to/new/rc-codex.json
```

The preflight does not interpret a CLI exit code as proof of a usable credential. Codex 0.170.0 reported a login for a synthetic empty auth object. The harness now rejects that empty fixture, exits before inference and writes no inference report. The JSONL parser separately passed synthetic checks for completion, failure and redaction.

The redacted record includes the locally assigned verification ID, provider, requested model, observed model when present, duration, actual usage when available, expected-reply verification and final status. It omits the original CLI transcript and session identity. This entry point verifies CLI inference when run successfully. Full application Harness execution and hosted tool behavior are separate acceptance items.
