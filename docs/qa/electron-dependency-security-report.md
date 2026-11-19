# Electron Dependency Security and Linux Packaging QA Report

- **Date**: 2026-11-19
- **Workspace**: `@orchestration/desktop` (`model-orchestration-workspace`)
- **Target Toolchain**: Node.js `v24.14.1`, npm `11.11.0`, Python `3.11.5`, Electron `45.4.1`, `electron-builder` `26.18.0`
- **Status**: Resolved (0 production vulnerabilities, 0 full-tree vulnerabilities via scoped `minimatch@11.0.9` override; Linux packaging & E2E verified; Windows packaging/runtime `NOT_VERIFIED`)

## 1. Initial Dependency State

Prior to remediation, a previous `npm audit fix --force` run had loosened the `electron-builder` version range in [apps/desktop/package.json](../../apps/desktop/package.json) without resolving the underlying transitive vulnerability:

- `apps/desktop/package.json`: `"electron-builder": "^26.18.0"` (drifted from pinned `"26.18.0"`)
- `package-lock.json`: workspace dependency range drifted to `"^26.18.0"`
- Root [package.json](../../package.json): no `devDependencies` and no `overrides`
- Installed packaging stack:
  - `electron-builder`: `26.18.0` (direct `devDependency` of `@orchestration/desktop`)
  - `app-builder-lib`: `26.18.0`
  - `dmg-builder`: `26.18.0`
  - `electron-builder-squirrel-windows`: `26.18.0`
  - `@electron/universal`: `2.0.3`
  - `electron`: `45.4.1`
- Initial `npm audit --omit=dev`: `0` vulnerabilities (`3` production entries in audit metadata, `@orchestration/desktop` has no runtime `dependencies`)
- Initial `npm audit`: `6` moderate vulnerabilities across `357` audited packages (`3` prod, `355` dev, `76` optional, `13` peer), with `npm audit fix --force` proposing a breaking downgrade to `electron-builder@25.1.0`
- Initial `minimatch` installations (`npm ls minimatch --all`):
  - `node_modules/minimatch`: `10.2.6` (vulnerable)
  - `node_modules/@electron/universal/node_modules/minimatch`: `9.0.9` (vulnerable)
  - `node_modules/@electron/asar/node_modules/minimatch`: `3.1.5` (unaffected by `GHSA-g3hv-75wg-m249`)
  - `node_modules/dir-compare/node_modules/minimatch`: `3.1.5` (unaffected)
  - `node_modules/glob/node_modules/minimatch`: `3.1.5` (unaffected)
  - `node_modules/filelist/node_modules/minimatch`: `5.1.9` (unaffected)

## 2. Root Cause Analysis

`npm audit --json` confirmed that all **six** moderate audit findings originated from a **single underlying advisory** on `minimatch`:

- **Advisory ID**: `GHSA-g3hv-75wg-m249` (npm advisory source `1244623`, `CVE-2026-118764`, `CWE-405`)
- **Title**: `minimatch has potential denial of service via globparts amplification`
- **Affected Version Range**: `>=7.0.0 <11.0.1`
- **Minimum Patched Release**: `11.0.1` (target selected: `11.0.9`, which also includes later v11 fixes such as `CVE-2026-27903`)

Because `GHSA-g3hv-75wg-m249` affects `minimatch` `7.0.0` through `11.0.0`, only the two transitive `9.0.9` and `10.2.6` installations were vulnerable. npm's vulnerability propagation graph rolled those two vulnerable `minimatch` nodes upward into six package-level entries (`minimatch`, `@electron/universal`, `app-builder-lib`, `dmg-builder`, `electron-builder-squirrel-windows`, and `electron-builder`).

The remaining four `minimatch` installations (`3.1.5` and `5.1.9`) are below `7.0.0`, do not contain the `firstPhasePreProcess()` `**/..` amplification path targeted by `GHSA-g3hv-75wg-m249`, and must not be blindly overridden to v11 due to major API changes relative to v3/v5.

All affected dependencies are **development and build-time packaging dependencies only** (`dev: true` in `package-lock.json`). The packaged Electron application (`app.asar`) contains zero `node_modules` dependencies and bundles only compiled main/preload/renderer code (`react` and `react-dom` are bundled at build time by Vite).

## 3. Vulnerability Dependency Tree

### Affected Paths (Before Remediation)

```text
@orchestration/desktop@0.1.0 (workspace: apps/desktop, devDependency)
└── electron-builder@26.18.0  [direct, dev, build-time]
    ├── dmg-builder@26.18.0  [transitive, dev, build-time]
    │   └── app-builder-lib@26.18.0 (deduped)
    └── app-builder-lib@26.18.0  [transitive, dev, build-time]
        ├── minimatch@10.2.6 (^10.2.5)  <-- VULNERABLE (GHSA-g3hv-75wg-m249)
        ├── @electron/universal@2.0.3  [transitive, dev, build-time]
        │   └── minimatch@9.0.9 (^9.0.3)  <-- VULNERABLE (GHSA-g3hv-75wg-m249)
        └── electron-builder-squirrel-windows@26.18.0  [transitive, peer/dev, build-time]
            └── app-builder-lib@26.18.0 (deduped)
```

### Related Non-Vulnerable Paths Audited (`minimatch`, `glob`, `rimraf`, `boolean`)

| Package | Version | Classification | Parent Path | Advisory Status |
| --- | --- | --- | --- | --- |
| `minimatch` | `3.1.5` | Transitive, dev, build-time | `@electron/asar@3.4.1` (`^3.0.4`) | Unaffected by `GHSA-g3hv-75wg-m249` |
| `minimatch` | `3.1.5` | Transitive, dev, build-time | `glob@7.2.3` (`^3.1.1`) <- `@electron/asar@3.4.1`, `rimraf@2.6.3` | Unaffected by `GHSA-g3hv-75wg-m249` |
| `minimatch` | `3.1.5` | Transitive, dev, build-time | `dir-compare@4.2.0` (`^3.0.5`) <- `@electron/universal@2.0.3` | Unaffected by `GHSA-g3hv-75wg-m249` |
| `minimatch` | `5.1.9` | Transitive, dev, build-time | `filelist@1.0.6` (`^5.0.1`) <- `jake@10.9.4` <- `ejs@3.1.10` | Unaffected by `GHSA-g3hv-75wg-m249` |
| `glob` | `7.2.3` | Transitive, dev, build-time | `@electron/asar@3.4.1`, `rimraf@2.6.3` | 0 audit findings |
| `rimraf` | `2.6.3` | Transitive, dev/peer, build-time | `temp@0.9.4` <- `electron-winstaller@5.4.0` <- `electron-builder-squirrel-windows@26.18.0` | 0 audit findings |
| `boolean` | `3.2.0` | Transitive, dev/optional, build-time | `global-agent@3.0.0`, `roarr@2.15.4` <- `@electron/get@3.1.0` | 0 audit findings |

## 4. Remediation Strategy

### Option A: Official Upstream Update (Evaluated and Ruled Out)

Registry inspection of `electron-builder` tags (`latest`: `26.18.0`, `v26`: `26.18.1`, `next`: `27.0.0-alpha.14`):

- `electron-builder@26.18.1` depends on `app-builder-lib@26.18.1`, which still specifies `"minimatch": "^10.2.5"` and `"@electron/universal": "2.0.3"` (`"minimatch": "^9.0.3"`). Upgrading to `26.18.1` does not resolve `GHSA-g3hv-75wg-m249`.
- `electron-builder@27.0.0-alpha.14` is an unstable alpha release and its `app-builder-lib@27.0.0-alpha.14` still specifies `"minimatch": "^10.2.5"` (even though it upgrades `@electron/universal` to `^3.0.6`).
- Downgrading to `electron-builder@25.1.0` is destabilizing and explicitly prohibited.

### Option B: Scoped Dependency Override to `minimatch@11.0.9` (Selected and Verified)

Because no stable upstream `electron-builder` release removes the vulnerable `minimatch` ranges, a parent- and range-scoped npm override was evaluated and verified against every consumer of `minimatch` in the dependency tree.

#### Consumer API & Compatibility Evidence

1. **Runtime / Engine Constraints**:
   - `minimatch@11.0.9` (published `2026-11-16`, `latest` tag) supports dual CommonJS (`./dist/commonjs/index.js`) and ESM (`./dist/esm/index.js`) exports and declares `"engines": { "node": "20 || >=22" }`.
   - Repository requires Node `>=24.14.0 <25` and runs on `v24.14.1`.
   - New transitive dependencies of `minimatch@11.0.9`: `brace-expansion@5.0.13` (`^5.0.12`) and `@isaacs/nonrecursive-glob-match@1.1.0` (`^1.1.0`), both clean in `npm audit`.

2. **`app-builder-lib@26.18.0` Inspection**:
   - `node_modules/app-builder-lib/out/fileMatcher.js` imports `{ Minimatch } from "minimatch"`, instantiates `new Minimatch(pattern, { dot: true })`, and passes instances to `filter.js`.
   - `node_modules/app-builder-lib/out/util/filter.js` accesses `pattern.set` in `hasMagic(pattern)` (checking `set.length > 1` or `typeof i !== "string"`), `pattern.negate`, and `pattern.match(path, stat.isDirectory() && !pattern.negate)`.
   - `app-builder-lib` does **not** call any APIs removed in `minimatch@11` (`makeRe`, `Minimatch#regexp`, `MMRegExp`, `matchOne`, `slashSplit`, `AST`, `debug`). In `minimatch@11.0.9`, `Minimatch#set` contains `string | Matcher | GLOBSTAR`, where non-string elements are objects (`Matcher`) or symbol (`GLOBSTAR`), preserving `typeof i !== "string"` and `set.length` semantics in `hasMagic()`.

3. **`@electron/universal@2.0.3` Inspection**:
   - `dist/cjs/index.js`, `dist/cjs/asar-utils.js`, `dist/esm/index.js`, and `dist/esm/asar-utils.js` only import the named export `minimatch` and invoke `minimatch(file, pattern, { matchBase: true })`.
   - Note: `@electron/universal@2.0.3`'s `dist/esm/index.js` contains extensionless relative imports (`./asar-utils`), which fail raw Node ESM loading independently of `minimatch`; `app-builder-lib` loads `@electron/universal` via its CommonJS entrypoint (`dist/cjs/index.js`).

4. **Runtime Verification Performed on Node `v24.14.1`**:
   - Verified `require.resolve("minimatch/package.json", { paths: [...] })` resolves:
     - `app-builder-lib` -> `11.0.9`
     - `@electron/universal` -> `11.0.9`
     - `@electron/asar`, `glob`, `dir-compare` -> `3.1.5`
     - `filelist` -> `5.1.9`
   - Verified `app-builder-lib`'s `FileMatcher`, `hasMagic`, and `createFilter` against all patterns from [apps/desktop/packaging/electron-builder.json](../../apps/desktop/packaging/electron-builder.json) and `builder-debug.yml`, including directory partial matching (`stat.isDirectory()`), non-magic directory expansion (`assets` -> `assets/**/*`), Windows backslash normalization, `hasMagic` on brace expressions, and exclusion filters.
   - Verified `@electron/universal` CJS require + `minimatch(..., { matchBase: true })`, `minimatch` ESM import, `app-builder-lib` & `electron-builder` CJS loads, and `@electron/asar` `listPackage`.

#### Workspace Override Propagation Fix (`npm 11.11.0` / `@npmcli/arborist`)

During lockfile synchronization, investigation in `@npmcli/arborist` revealed an npm `11.11.0` workspace quirk: when `electron-builder` is only declared inside a workspace (`apps/desktop`) and `node_modules/@orchestration/desktop` exists as a symlink, `loadVirtual` and `loadActual` attach root `overrides` to the `Link` node rather than `Link.target` (`apps/desktop`). Without a direct root edge, `npm install` ignored root `overrides` and `npm ls` failed with `ELSPROBLEMS` (`invalid: minimatch@11.0.9`).

To make the scoped override deterministic and reproducible across `npm install`, `npm ci`, and `npm ls`, the exact pin `"electron-builder": "26.18.0"` was mirrored into root `package.json` `devDependencies` alongside the scoped `overrides`:

```json
{
  "devDependencies": {
    "electron-builder": "26.18.0"
  },
  "overrides": {
    "app-builder-lib@26.18.0": {
      "minimatch@^10.2.5": "11.0.9",
      "@electron/universal@2.0.3": {
        "minimatch@^9.0.3": "11.0.9"
      }
    }
  }
}
```

This adds zero packages to `node_modules`, preserves zero runtime dependencies (`npm audit --omit=dev` stays 0), leaves `minimatch@3.1.5` and `5.1.9` untouched, and cleanly propagates the override through `app-builder-lib@26.18.0` and `@electron/universal@2.0.3`.

### Option C: Accepted Residual Risk (Not Needed)

Because Option B resolved all 6 findings with full compatibility evidence and reproducible clean installs (`npm ci` and `npm ls` exit `0`), falling back to Option C was unnecessary.

## 5. Modified Files

- [apps/desktop/package.json](../../apps/desktop/package.json): restored exact `"electron-builder": "26.18.0"` pin (removed `^26.18.0` drift from working tree).
- [package.json](../../package.json): added `"devDependencies": { "electron-builder": "26.18.0" }` and scoped `"overrides"` pinning `app-builder-lib@26.18.0 -> minimatch@^10.2.5` and `app-builder-lib@26.18.0 -> @electron/universal@2.0.3 -> minimatch@^9.0.3` to `11.0.9`.
- [package-lock.json](../../package-lock.json): synchronized via `npm install` and verified via `npm ci`; diff against `HEAD` shows only root `devDependencies.electron-builder`, `minimatch` `10.2.6 -> 11.0.9`, addition of `@isaacs/nonrecursive-glob-match@1.1.0`, and removal of nested `@electron/universal/node_modules/{minimatch,brace-expansion,balanced-match}`. No other packages drifted.
- [electron-dependency-security-report.md](electron-dependency-security-report.md): this QA report.
- Existing untracked working-tree file (`on 변경 확인`) was preserved untouched.

## 6. Final Package Versions

| Package | Version | Role / Scope |
| --- | --- | --- |
| `electron` | `45.4.1` | Direct devDependency (`apps/desktop`) |
| `electron-builder` | `26.18.0` | Exact pin in `apps/desktop` and root `devDependencies` |
| `app-builder-lib` | `26.18.0` | Transitive dev/build-time (`overridden` child edge) |
| `dmg-builder` | `26.18.0` | Transitive dev/build-time |
| `electron-builder-squirrel-windows` | `26.18.0` | Transitive peer/dev/build-time |
| `@electron/universal` | `2.0.3` | Transitive dev/build-time (`overridden` child edge) |
| `@electron/asar` | `3.4.1` | Transitive dev/build-time |
| `minimatch` (hoisted) | `11.0.9` | Overridden for `app-builder-lib` and `@electron/universal` |
| `@isaacs/nonrecursive-glob-match` | `1.1.0` | Transitive dep of `minimatch@11.0.9` |
| `brace-expansion` (hoisted) | `5.0.13` | Transitive dep of `minimatch@11.0.9` |
| `minimatch` (`@electron/asar`, `glob`, `dir-compare`) | `3.1.5` | Preserved unchanged |
| `minimatch` (`filelist`) | `5.1.9` | Preserved unchanged |
| `glob` | `7.2.3` | Preserved unchanged |
| `rimraf` | `2.6.3` | Preserved unchanged |
| `boolean` | `3.2.0` | Preserved unchanged (optional) |
| `typescript` | `7.0.2` | Direct devDependency (`apps/desktop`) |
| `vite` | `8.3.8` | Direct devDependency (`apps/desktop`) |
| `@playwright/test` | `1.65.1` | Direct devDependency (`apps/desktop`) |
| `react` / `react-dom` | `19.3.1` | Direct devDependencies (`apps/desktop`, bundled by Vite) |

### Final `npm ls minimatch --all` Output

```text
model-orchestration-workspace@ /home/jhkim/tools/full-orchestration
└─┬ electron-builder@26.18.0
  └─┬ app-builder-lib@26.18.0 overridden
    ├─┬ @electron/asar@3.4.1
    │ ├─┬ glob@7.2.3
    │ │ └── minimatch@3.1.5
    │ └── minimatch@3.1.5
    ├─┬ @electron/universal@2.0.3 overridden
    │ ├─┬ dir-compare@4.2.0
    │ │ └── minimatch@3.1.5
    │ └── minimatch@11.0.9 deduped
    ├─┬ ejs@3.1.10
    │ └─┬ jake@10.9.4
    │   └─┬ filelist@1.0.6
    │     └── minimatch@5.1.9
    └── minimatch@11.0.9 overridden
```

## 7. `npm audit` Results

| Check | Before Remediation | After Remediation |
| --- | --- | --- |
| `npm audit --omit=dev` | `0` vulnerabilities | `0` vulnerabilities |
| `npm audit` (full) | `6` moderate (`GHSA-g3hv-75wg-m249`) | `0` vulnerabilities (`found 0 vulnerabilities`) |
| `npm ci` reproducibility | N/A | PASS (`added 304 packages, and audited 306 packages in 3s`, `found 0 vulnerabilities`) |
| `npm install --dry-run` | N/A | PASS (`up to date in 475ms`) |
| `npm ls ... --all` | Exited 0 (vulnerable tree) | Exited 0 (zero `ELSPROBLEMS`) |

## 8. Linux Packaging Results

Packaging and runtime checks were executed via [scripts/qa/verify.mjs](../../scripts/qa/verify.mjs) (`npm run verify -- --package`) and direct `xvfb-run` Playwright invocations.

**Display & Host Environment Notes**:

- `DISPLAY` is unset on this Linux host; GUI tests used `xvfb-run -a` with `LIBGL_ALWAYS_SOFTWARE=1`.
- The IDE agent shell exports `ELECTRON_RUN_AS_NODE=1`, which causes any launched Electron binary to boot as a Node.js REPL instead of Chromium unless unset (`env -u ELECTRON_RUN_AS_NODE`). That initial launch failure was diagnosed via direct stderr (`Welcome to Node.js v24.22.3`) as a host shell environment artifact, not an application bug.
- `/dev/fuse`, `/usr/bin/fusermount`, and `/usr/bin/fusermount3` are available on the host, allowing both direct FUSE AppImage execution and `APPIMAGE_EXTRACT_AND_RUN=1` testing.

### Build Artifacts and Integrity

- `apps/desktop/release/Model Orchestration Preview-0.1.0.AppImage`:
  - Size: `125,811,201` bytes (`-rwxr-xr-x`)
  - Type: `ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, for GNU/Linux 2.6.18, stripped`
  - SHA-256: `6a7211965b811cfce7812b5d5b69aa672930772cb8982f03de60cf7b2def8c41`
  - `--appimage-version`: `Version: effcebc` (exit `0`)
- `apps/desktop/release/linux-unpacked/model-orchestration-preview`:
  - Type: `ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked`
- `apps/desktop/release/linux-unpacked/resources/app.asar`:
  - SHA-256: `f4e68c6fd20d614c81b11d9e36445f2130912212de2660b58bb66e9f0bd143cd`
  - Contents (`25` entries verified via `@electron/asar.listPackage`):
    - `/package.json`
    - `/build/main/adapters/{filesystem,openssh,process}.js`
    - `/build/main/core/{configuration,dag,execution,mcp,worker}.js`
    - `/build/main/electron/{config,legacy-store,main,preload}.js`
    - `/build/main/src/contracts.js`
    - `/build/renderer/index.html` and `/build/renderer/assets/{index-8YAnK9Cw.css,index-D0uXL-2J.js}`
  - Verified excluded: `node_modules`, `release`, `.git`, `.ts` source files, `.d.ts` declarations.

### Packaged Runtime, SQLite, and Supervisor E2E Results

| Target / Mode | Command | Result | Coverage Verified |
| --- | --- | --- | --- |
| `linux-unpacked` (`model-orchestration-preview`) | `env -u ELECTRON_RUN_AS_NODE npm run verify -- --package` (`xvfb-run -a`) | **4/4 PASS** (`20.1s`) | Window launch, read-only IPC & security (`nodeRequire` undefined, `window.open` denied, path traversal rejected), SQLite schema read/recovery & live refresh, first-run missing store non-creation, real Python QA failure evidence, live Python Supervisor detach + `SIGKILL` crash resilience + clean shutdown |
| AppImage (`APPIMAGE_EXTRACT_AND_RUN=1`) | `env -u ELECTRON_RUN_AS_NODE npm run verify -- --package` (`xvfb-run -a`) | **4/4 PASS** (`27.8s`) | Same 4 Playwright E2E scenarios via AppImage extract-and-run |
| AppImage (Direct FUSE mount) | `env -u ELECTRON_RUN_AS_NODE -u APPIMAGE_EXTRACT_AND_RUN LIBGL_ALWAYS_SOFTWARE=1 ORCHESTRA_PREVIEW_EXECUTABLE=...AppImage timeout 60 xvfb-run -a npm run test:e2e` | **4/4 PASS** (`34.8s`) | Same 4 Playwright E2E scenarios mounted directly via host FUSE |

### Cross-Platform Windows Verification Status

- **Status**: **`NOT_VERIFIED`**
- **Reason**: Host is Linux (`6.8.0-149-generic`) without `wine`, `wine64`, or `makensis` installed, so `npm run package:windows` (`electron-builder --win nsis`) and Windows installer tests cannot execute locally.
- **Required Windows CI Verification** (per [.github/workflows/cross-platform.yml](../../.github/workflows/cross-platform.yml) on `windows-2025` and [windows-native-verification.md](../internal/windows-native-verification.md)):
  - `npm ci`
  - `npm run verify -- --ui --package`
  - `pwsh -NoProfile -File ./scripts/qa/verify-windows-installer.ps1`

## 9. Regression Test Results

All final regression checks ran after `package.json`, `apps/desktop/package.json`, and `package-lock.json` were finalized and `npm ci` succeeded:

| Suite | Scope | Result | Timing / Notes |
| --- | --- | --- | --- |
| Production build | `tsc -p tsconfig.core.json && tsc -p tsconfig.main.json && tsc -p tsconfig.renderer.json && vite build` | **PASS** | `16` modules transformed, `vite v8.3.8`, `1.77s` |
| Node.js unit & contract suite | `node --test "build/main/tests/*.test.js"` | **25/25 PASS** | `5083.21ms`, 0 failed, 0 skipped |
| Python regression & native adapter suite | `python -m unittest discover -s tests -v` | **41 run: 39 PASS, 2 SKIPPED** | `58.347s`; skipped cases require native Windows (`test_windows_atomic_save_keeps_read_only_file`, `test_worktree_guard_rejects_a_real_windows_junction`) |
| Integrated packaging verification | `env -u ELECTRON_RUN_AS_NODE npm run verify -- --package` | **PASS** | Includes build, 25 Node tests, 41 Python tests, `package:linux`, unpacked E2E (4/4), and AppImage extract-and-run E2E (4/4) |
| Direct FUSE AppImage E2E | Playwright `desktop.spec.ts` against final AppImage without `APPIMAGE_EXTRACT_AND_RUN` | **4/4 PASS** | `34.8s` |
| Documentation Markdown lint | `./scripts/docs/node_modules/.bin/markdownlint-cli2 --no-globs docs/qa/electron-dependency-security-report.md` | **PASS** | `0` issues on the new report (`check_doc_structure.py` also passed across 50 Markdown files) |

## 10. Remaining Risks

1. **Windows NSIS Packaging and Native Runtime (`NOT_VERIFIED`)**: While `electron-builder@26.18.0`, `electron-builder-squirrel-windows@26.18.0`, and `app-builder-lib`'s Windows file-matching patterns remain compatible in static and Linux checks, actual NSIS executable generation, installer persistence, Job Object / ConPTY behavior, and Windows-only regression cases have not been executed on `windows-2025`.
2. **macOS Universal Binary Path (`@electron/universal`)**: `@electron/universal@2.0.3` with overridden `minimatch@11.0.9` was verified via CommonJS module loading and direct `minimatch(..., { matchBase: true })` calls, not an actual macOS `universal` bundle build (not configured in [electron-builder.json](../../apps/desktop/packaging/electron-builder.json)).
3. **Override Maintenance Coupling**: Root `package.json` pins `electron-builder` to `"26.18.0"` alongside `"app-builder-lib@26.18.0"` and `"@electron/universal@2.0.3"` keys inside `overrides`. Any future upgrade of `electron-builder` must update or remove those override keys in lockstep.
4. **Deprecated Transitive Build-Time Utilities**: `npm ci` emits deprecation notices for `glob@7.2.3`, `rimraf@2.6.3`, `inflight@1.0.6`, and optional `boolean@3.2.0` inside `electron-builder` / `@electron/asar` / `electron-winstaller`. None currently trigger `npm audit` findings, and overriding them across major versions (`glob@7 -> 11`, `rimraf@2 -> 6`) without upstream `electron-builder` support would break API compatibility.

## 11. Follow-up Actions

1. Execute the Windows verification workflow on a `windows-2025` runner (or clean Windows host) per [windows-native-verification.md](../internal/windows-native-verification.md) (`npm ci`, `npm run verify -- --ui --package`, `pwsh -NoProfile -File ./scripts/qa/verify-windows-installer.ps1`) and update Windows status once observed.
2. Periodically check new `electron-builder` `26.x` or stable `27.x` releases for an upstream bump of `app-builder-lib` to `minimatch >= 11.0.1` and `@electron/universal >= 3.0.4`, at which point the scoped `overrides` block and root `devDependencies.electron-builder` mirror can be removed cleanly.
3. Keep `npm audit` and `npm audit --omit=dev` as separate release checks so build-time packaging dependencies cannot obscure runtime production status.
