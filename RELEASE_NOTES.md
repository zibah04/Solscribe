# SolScribe 0.4.0 beta

This version improves the existing private Windows meeting app while retaining the purple palette, light/dark themes, editable transcripts, four note types and all six export formats.

## Changes

- Recoverable meeting trash; separate confirmed deletion of unused owned audio. Shared/imported/legacy recordings remain protected.
- Transactional schema migration, pre-upgrade/daily database snapshots, full backup ZIPs with checksums, staged restore, independent recovery drafts and interrupted PCM WAV recovery.
- Capture-clock live captions with overlapping context, FIR resampling, bounded queues and explicit skipped-caption warnings. Recorded timelines retain gaps instead of shifting later words earlier.
- Microphone, computer playback and combined capture. Combined mode preserves both source WAVs plus a mixed file, with software clock alignment and drift compensation.
- Compare an improved transcript before replacing manual words; retain speaker corrections where timing is clear and preserve existing documents. Bulk speaker renaming.
- Conservative source-grounded English action extraction, editable action register with evidence, review state and draft checks.
- Bounded/cancellable local writing requests, model availability checks, long-source condensation and transparent quick-note fallback.
- Smaller UI controllers, large-transcript rendering improvements, responsive recording shutdown and backup jobs. Compact navigation and a scrollable workspace support small scaled windows.
- Shared CommonMark parsing for rich exports preserves literal symbols, code, links and tables. Word/PDF page numbering, Unicode fonts and multi-page table support.
- Windows x64 build validation includes source and packaged speech recognition, 100/125/150/200% Qt scaling, legacy-data migration and install/remove/reinstall preservation. Optional signing preparation fails closed when configured.

## Verification evidence

See `docs/ENGINEERING_REPORT.md` for executed checks and limitations. Each successful workflow artifact records the source SHA, build number, exact dependencies, tests, measurements, SHA256 checksums and Authenticode status. Validation artifacts are retained even if a later packaging step fails. Downloads expire after 30 days.

## Known limits

Physical microphone/loopback synchronization, disconnection behavior and long-duration recording need target-device checks. The 8 GB CPU-only target is not certified by offscreen/cloud tests. System capture uses software timing; driver failures can lose samples, and warnings cannot reconstruct them.

Live captions are provisional two-second batches plus processing. First use downloads a speech model; native model initialization/decoding cancellation remains cooperative. AI notes and English heuristics need human review. A real Ollama model's report quality has not been independently established here.

No automatic speaker identification, translation, encrypted vault, syncing or automatic updater is included. Saved files and backups are unencrypted. The generated uninstaller is not covered by the optional signing preparation; no signing certificate is supplied. Complex-script/RTL export layout and real screen-reader testing remain pending. Use `docs/WINDOWS_ACCEPTANCE.md` before a public release.
