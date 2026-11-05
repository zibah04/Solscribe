# SolScribe 0.4.0 engineering evidence

Status: beta preparation on `codex/solscribe-040-remediation`. No merge, public release or environment publication is performed by this work. The functional 0.3 source branch and its history are preserved.

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
| Qt completion signals could arrive after a worker was already no longer running | Busy flags held through UI finished handling; protected navigation and shutdown |
| Large transcript loading resized every row; small windows hid useful workspace | Preallocated rows, visible-row sizing, compact controls and scrollable content |
| Rich-export conversion removed meaningful punctuation/markup content | Shared Markdown AST, literal/code/link/table handling and paginated document renderers |
| Saved malformed JSON was interpreted as empty content | Reject damaged content without overwriting original DB; recovery route preserves it |

## C. Architecture

Persistence, filesystem/recovery, audio packets/resampling/mixing, caption engine, evidence extraction, local HTTP writing and document parsing/rendering have independent modules. Qt adapters coordinate these services through dedicated presentation controllers. `storage.py` remains a compatibility facade. See [architecture](ARCHITECTURE.md) for module boundaries, time contracts and remaining native cancellation constraints.

## D. Executed validation

- Baseline functional 0.3 suite: **47 passed**, 0 failed, 8.87 seconds (Linux/Python 3.12).
- Expanded suite before the final worker checks: **120 passed**, 0 failed, 32.10 seconds.
- Static undefined-name checks: passed (`ruff F821,F822,F823`).
- Deterministic coverage includes shared/legacy media, trash, restore hashes/traversal, drafts, live-PID protection, corrupt-DB quarantine, time gaps/overlap, resampling, two-source mixing/drift/failure, transcript corrections, local HTTP cancellation, action evidence, review state, compact layout and Unicode/long-table export.
- Final Linux suite: **122 passed**, 0 failed, 34.32 seconds (`final-linux.xml`), including slow-stop UI responsiveness and final-decoder cancellation cleanup. New Windows build results will be recorded after execution; a configured workflow is not itself evidence of a successful build.

The Windows workflow checks x64 architecture, dependencies, Qt scaling, source and packaged real recognition from synthetic spoken audio, packaged theme startup, a pre-0.4 schema migration, install/remove/reinstall and existing-data preservation. It saves JUnit XML, measurements, exact dependency versions, source SHA, checksums and signing status. These tests do not establish physical device reliability.

## E. Actual performance

[Linux measurement JSON](validation/performance-linux.json) is a single cloud run, not a device guarantee. The first run measured 0.598 seconds from script startup through first window, 86.8 MB idle RSS, 0.747 seconds to load/render 10,000 rows (116.4 MB loaded RSS), 0.527 seconds for quick notes, and 0.266 seconds to persist all rows. This run used an Intel Xeon Platinum 8573C cloud VM, 5 logical CPUs and 35.7 GB visible RAM. A synthetic 90-minute source stream retained 16,000 context frames and 256 timing samples, with 0.462 MB peak traced allocations. It used a fake recognizer and ran faster than real time; it measures buffer retention only, not speech processing speed or full-app/native-model memory.

The reproducible script reports OS, Python, architecture, CPU, RAM, timings and workload scope. Windows speech metrics separately report model readiness, first caption including model startup and decode/drain time for prequeued synthetic speech. These are not physical microphone end-to-end latency. No 8 GB laptop was available for this task.

## F. Remaining limits

- Physical mic/loopback quality, combined source alignment/drift, device disconnection and long recording behavior need the target-device acceptance checklist. Software loopback clock estimates are not hardware-exact. Sources already lost cannot be recovered; saved originals are retained for inspection.
- Real Ollama model quality and long semantic consistency remain unverified. English rules miss some commitments; source audits do not prove model correctness. Human review is required.
- Native model loading/decoding cancellation is cooperative. Low-memory/8 GB operation, real screen-reader use, complex-script/RTL exports and subjective note quality need independent tests.
- No diarization, translation, encrypted vault, automatic updates or cross-device syncing. The last three transcript revisions are retained in the database; a history-restore UI is not included.
- No legitimate signing certificate was available. Signing preparation supports a protected pre-provisioned certificate; it does not sign Inno's generated uninstaller or create a trusted publisher on its own.
- Full archives include owned media; imported recordings remain external links. DB snapshots alone do not contain audio. Files/backups/drafts are unencrypted.

See [Windows acceptance](WINDOWS_ACCEPTANCE.md) for reproducible physical-device and remote-update handoff checks.

## G. Release artifacts

The 0.4 installer, portable ZIP, validation artifacts, run URL and pull request will be listed with the executed Windows result. Downloads have 30-day Actions retention; no public release has been published.

## H. Engineering verdict

**Beta.** Substantial implementation and deterministic validation improve data safety, timing, workflow and maintainability. Hardware acceptance, 8 GB measurements, signing and independent semantic/accessibility review remain release gates. Passing unit tests or building an installer does not justify a production-ready claim.
