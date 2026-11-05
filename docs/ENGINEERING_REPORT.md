# SolScribe 0.4.0 engineering evidence

Status: validated beta build on `codex/solscribe-040-remediation`. No merge, public release or environment publication is performed by this work. The functional 0.3 source branch and its history are preserved.

## A. Implemented improvements

Recoverable trash, shared-file ownership/refcounts, consistent backups/restores, failed-write drafts and interrupted-WAV recovery prioritize preserving user work. Live captions use absolute source time and overlapping context, stronger resampling, bounded buffers and explicit backlog/gap notices. Combined capture retains two originals and an aligned mix. Transcript comparison, bulk speaker correction, source-evidence actions, review state, safer optional local writing and improved rich exports complete the normal record/import → transcript → review → notes → edit → export workflow.

The existing purple light/dark appearance remains, with compact navigation and scrolling on scaled laptop windows. Recording input and Stop remain available. Slow recording finalization and archive operations run in background workers.

## B. Confirmed defects addressed

| Defect | Root-cause correction |
| --- | --- |
| Deleting one session could delete audio used elsewhere; location was treated as ownership | Explicit assets and reference ledger, conservative legacy/imported ownership, trash and separate confirmed unreferenced-owned-audio purge |
| Failed writes, migration and interrupted recording risked losing work | Draft-before-commit, transactional migrations with snapshots, preserved restore databases and bounded PCM header repair |
| Lost caption packets collapsed later timestamps | Capture-frame positions survive queue overflow; gaps reset overlap and remain visible in the source timeline |
| Nonoverlapping chunks cut speech context; box-average downsampling aliased | Word-time overlap reconciliation and stateful low-pass FIR decimation |
| Speaker corrections and notes could be overwritten on final transcription | Explicit before/after comparison, unambiguous speaker transfer, retained history and preserved notes |
| Optional writing service refusal surfaced raw errors instead of usable notes | Model availability checks, bounded requests, cancellation and transparent deterministic fallback |
| Conditional statements and missing metadata could become misleading assignments | Source commitment records, conditional/question rejection and explicit unknown owners/deadlines |
| A stalled local writing response did not always cancel promptly on Windows | Cancellation is polled during owned response reads; it no longer depends on cross-thread socket shutdown |
| Qt completion signals could arrive after a worker was already no longer running | Busy flags held through UI finished handling; protected navigation and shutdown |
| Large transcript loading resized every row; small windows hid useful workspace | Preallocated rows, visible-row sizing, compact controls and scrollable content |
| Rich-export conversion removed meaningful punctuation/markup content | Shared Markdown AST, literal/code/link/table handling and paginated document renderers |
| Windows rejected syncing a read-only temporary-file descriptor | Reopen staged output with write access before fsync; retain the atomic replacement and failure cleanup |
| SQLite transaction contexts left backup handles open on Windows | Explicit connection closing before atomic replacement, with a regression enforcing the file-handle contract |
| Saved malformed JSON was interpreted as empty content | Reject damaged content without overwriting original DB; recovery route preserves it |

## C. Architecture

Persistence, filesystem/recovery, audio packets/resampling/mixing, caption engine, evidence extraction, local HTTP writing and document parsing/rendering have independent modules. Qt adapters coordinate these services through dedicated presentation controllers. `storage.py` remains a compatibility facade. See [architecture](ARCHITECTURE.md) for module boundaries, time contracts and remaining native cancellation constraints.

## D. Executed validation

- Baseline functional 0.3 suite: **47 passed**, 0 failed, 8.87 seconds (Linux/Python 3.12).
- Windows main suite: **124 passed**, 0 failed, 0 errors, 49.16 seconds on Python 3.11.9 x64.
- Windows scaling: **75 additional case executions passed** (25 release regressions at each of 100%, 125% and 200%; the main suite ran at 150%).
- Real speech integration: **source and packaged runs passed** on an 11.135-second synthetic spoken WAV; expected keywords were recognized, captions arrived before Stop, and the final tail drained without skipped source time.
- Windows executable and installer: **built successfully**. Packaged startup passed in both themes with source Python paths removed. Two installation/uninstallation cycles passed, preserving a pre-0.4 meeting, edited notes, speaker name, WAV frames and conservative legacy ownership through migration and reinstallation.
- Dependency consistency and static undefined-name checks: passed (`pip check`, `ruff F821,F822,F823`). Deprecated Node 20 action versions were replaced with reviewed, immutable current action commits.
- Deterministic coverage includes shared/legacy media, trash, restore hashes/traversal, drafts, live-PID protection, corrupt-DB quarantine, time gaps/overlap, resampling, two-source mixing/drift/failure, transcript corrections, local HTTP cancellation, action evidence, review state, compact layout and Unicode/long-table export.
- Final Linux suite: **124 passed**, 0 failed, 35.17 seconds ([JUnit XML](validation/final-linux.xml)), including slow-stop UI responsiveness and final-decoder cancellation cleanup.

One earlier Linux run exceeded its 120-second watchdog near the end. Isolated exports (9 tests) and the full diagnostic rerun passed; the stall was not reproduced. It is not represented as a successful run.

[Windows run 42001168415](https://github.com/zibah04/Solscribe/actions/runs/42001168415) completed successfully in 7m39s on source `b551cf5da1e8bc0d75065c98f1a3b1406dd5ea85`. JUnit XML, raw packaging warnings, measurements, exact dependency versions, source identity, checksums and signing status are uploaded. Earlier failures exposed the Windows fsync/cancellation defects and a test-harness assumption about Inno's numbered uninstaller; those were corrected before this passing run. These checks do not establish physical device reliability.

GitHub check results, measurements and artifact metadata were inspected through the permitted API. The environment blocks GitHub's separate blob download host, so full raw logs and binary artifact contents were not downloaded locally. The linked GitHub artifacts remain downloadable by the user. No network configuration was changed.

## E. Actual performance

These are single cloud runs with synthetic data. The UI measurements include imports and first window after the benchmark's standard-library bootstrap, with the speech model unloaded. They do not certify an 8 GB laptop.

| Measurement | Linux | Windows |
| --- | ---: | ---: |
| Imports → first window | 0.598 s | 0.570 s |
| Idle RSS, no speech model | 86.8 MB | 85.9 MB |
| Load/render 10,000 rows | 0.747 s | 0.300 s |
| RSS after loading rows | 116.4 MB | 117.7 MB |
| Quick-note generation | 0.527 s | 0.421 s |
| Persist all rows | 0.266 s | 0.294 s |

Linux used Python 3.12.14, Intel Xeon Platinum 8573C, 5 logical CPUs and 35.7 GB visible RAM. The Windows runner used build 26100, Python 3.11.9 x64, AMD Family 25 Model 1, 4 logical CPUs and 16 GiB RAM. [Linux JSON](validation/performance-linux.json) and [Windows JSON](validation/performance-windows.json) record the exact workload and environment.

Both synthetic 90-minute source-clock streams retained 16,000 context frames and at most 256 timing samples, with approximately 0.462 MB peak traced allocations. A fake recognizer isolated buffer retention; this is not 90 minutes of physical recording or a native speech-model memory test.

Real tiny/int8 CPU recognition consumed 11.135 seconds of prequeued synthetic speech. Source readiness was 3.723 s, first caption including readiness 4.307 s, and decode/drain 3.137 s (real-time factor 0.282). The packaged run reused the downloaded model: readiness 0.749 s, first caption 1.316 s, decode/drain 3.104 s (factor 0.279). Mean packaged decode-window processing was 0.490 s. See [source speech JSON](validation/speech-source-metrics.json) and [packaged speech JSON](validation/speech-packaged-metrics.json). Prequeued input timings are **not physical microphone end-to-end caption latency**; cold downloads and actual hardware can differ.

## F. Remaining limits

- Physical mic/loopback quality, combined source alignment/drift, device disconnection and long recording behavior need the target-device acceptance checklist. Software loopback clock estimates are not hardware-exact. Combined capture has no acoustic echo cancellation; headphones help avoid playback leaking through the microphone. Sources already lost cannot be recovered; saved originals are retained for inspection.
- Real Ollama model quality and long semantic consistency remain unverified. English rules miss some commitments; source audits do not prove model correctness. Human review is required.
- A fresh consumer Windows VM without developer runtimes was not independently tested; the packaged checks ran on the Windows build runner with Python paths removed.
- Native speech-model loading/decoding cancellation is cooperative. Low-memory/8 GB operation, real screen-reader use, complex-script/RTL exports and subjective note quality need independent tests.
- No diarization, translation, encrypted vault, automatic updates or cross-device syncing. The last three transcript revisions are retained in the database; a history-restore UI is not included.
- No legitimate signing certificate was available. Signing preparation supports a protected pre-provisioned certificate; it does not sign Inno's generated uninstaller or create a trusted publisher on its own.
- Full archives include owned media; imported recordings remain external links. DB snapshots alone do not contain audio. Files/backups/drafts are unencrypted.

See [Windows acceptance](WINDOWS_ACCEPTANCE.md) for reproducible physical-device and remote-update handoff checks.

## G. Release artifacts

- [Download Windows bundle](https://github.com/zibah04/Solscribe/actions/runs/42001168415/artifacts/13403061934) — 282.5 MB; contains `Output/SolScribe-Setup-0.4.0.exe`, `SolScribe-Portable-Windows.zip`, guides, dependency/build identity, signing status and checksums.
- [Download validation evidence](https://github.com/zibah04/Solscribe/actions/runs/42001168415/artifacts/13401784822) — JUnit/scaling reports, console output, install/uninstall logs, packaging warnings and measurements.
- [SHA256 sums](validation/SHA256SUMS.txt): installer `56804ea0291ca01f6824247a398aea0b6cdcc99b781282e27fbb348721e50efa`; portable ZIP `8062926cedcd1da9894cc1ef87788f20cf899586d173a4fdbc3d5d39610d5d11`.
- GitHub Windows artifact digest: `sha256:04910e4c54c8beca9fc32f20987789858273396399e6e115bfeee778d5e2c3a0`.
- Source branch: [`codex/solscribe-040-remediation`](https://github.com/zibah04/Solscribe/tree/codex/solscribe-040-remediation). Built commit: `b551cf5da1e8bc0d75065c98f1a3b1406dd5ea85`; subsequent evidence documentation does not change application code.
- [Draft PR #1 targeting main](https://github.com/zibah04/Solscribe/pull/1).

Extract the Windows bundle and run its installer, or extract the portable ZIP and keep the whole application folder together. Downloads have 30-day Actions retention and may require GitHub sign-in. No merge, public release or environment publication has occurred. Treat this build as unsigned; the download includes its Authenticode status, and no signing credential was supplied by this task.

## H. Engineering verdict

**Beta.** Substantial implementation and deterministic validation improve data safety, timing, workflow and maintainability. Hardware acceptance, 8 GB measurements, signing and independent semantic/accessibility review remain release gates. Passing unit tests or building an installer does not justify a production-ready claim.
