# SolScribe 0.5.0 beta

- Lecture mode adds an editable outline, key concepts, definitions, examples and revision practice. Each selected passage keeps timestamped original words and a jump to the transcript.
- Revision cards hide the answer until requested. Questions and answers are editable; the original evidence stays available separately.
- Quick study notes run locally without an extra writing service. English source cues identify definitions/examples. Long lectures select passages across the full transcript rather than only its beginning; this is a study aid, not an exhaustive textbook.
- Optional polished study notes use the existing local writing helper. Every source chunk is processed; invalid sources, unsupported numbers or unavailable helpers fall back to quick notes. AI wording still requires source review.
- Meeting and lecture notes are saved separately. Switching modes preserves both, as do upgrades, backups and project JSON. Transcript edits show when study notes refer to older words.
- The four-step guide now introduces Lecture and offers a sample lecture. Light/dark purple themes, updates and the zibah@2026 footer are included from 0.4.1.

This remains an unsigned beta. Real lecture speech accuracy, technical subjects, physical audio devices, target laptops and accessibility need user acceptance testing. No slide/PDF ingestion, automatic equation understanding or exam prediction is included. See docs/LECTURE_MODE.md and docs/050_REPORT.md.

---

## Previous version: SolScribe 0.4.1 beta

- A four-step first-use guide sets appearance, audio source and live words, explains recording/review/notes, and offers optional sample practice. Skip it or reopen Guide from the footer or Settings.
- Updates in the footer and Settings check the official GitHub releases. Startup checks are opt-in and throttled to once per day after a successful check. Recordings and notes are not part of the request.
- Updates download in the background, verify the official asset checksum, and wait for your choice to install. Active recordings/tasks block installation; current edits and a database backup are saved before the installer opens. Cancellation and failed checks keep the existing app.
- The footer now reads `zibah@2026`. Checkbox choices are clearly visible in both themes.
- Release version metadata is checked across the app, installer and Windows file properties. Build steps derive their filenames from the version automatically.

Users already on 0.4.0 must install 0.4.1 once to gain the update controls. Portable users can download the new portable folder or choose the normal installer; in-app Install uses the installer.

This remains an unsigned beta. The normal Windows installer prompts still apply. Updates need an internet connection; basic local use and the guide do not. Installation is not silent. See `docs/UPDATES.md` for how to deliver later releases and `docs/041_REPORT.md` for executed verification. Existing hardware, 8 GB, writing-quality and accessibility acceptance limits remain.

The Windows workflow checks source and packaged real HTTPS update downloads, source and packaged speech, both themes, scaling, legacy migration and two install/uninstall cycles. Each successful build includes the actual reports, checksums and source identity.

---

## Previous version: SolScribe 0.4.0 beta

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
