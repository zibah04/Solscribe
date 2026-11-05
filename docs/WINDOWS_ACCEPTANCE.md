# Windows hardware acceptance before wider release

These checks are **pending** unless separately recorded with device details. Deterministic mocks, offscreen Qt and synthetic speech tests cannot establish physical device quality, perceptual accuracy or an 8 GB laptop memory budget.

Record the source SHA, installer checksum, Windows build, CPU, total RAM, audio drivers, selected devices, model, language, screen resolution/scaling and observed failures. Use a separate non-confidential test meeting; keep the originals until results are accepted.

## Install and existing work

1. Back up an existing 0.3 library, including external imported files. Close all older app windows.
2. Install 0.4, reopen old transcripts/notes, play old and imported audio, and verify speaker corrections. Review the automatic pre-migration DB snapshot.
3. Confirm a second instance cannot open the same library. Uninstall/reinstall and verify all previous data and audio remain.
4. Review Authenticode status and Windows Defender results. Keep normal Windows protections enabled; unsigned artifacts remain unsigned.

## Physical capture and live words

Test microphone only, playback only, and Both sources with internal, USB and intended Bluetooth devices. Check Windows microphone permissions and actual playback-output selection. Speak quiet/normal/loud test phrases; include silence, room noise, overlapping voices and an accent/language relevant to intended users.

For each source confirm the level meter, duration, audio playback, first caption before Stop, source timestamps, final short speech tail and completeness after Improve transcript. Record model startup/download separately from warm-caption delay. Measure wall-clock caption delay with a visible clock and an independent recording, not prequeued test audio.

For combined capture, play timed clicks through speakers and record them on the microphone at start and every ten minutes for at least 60 minutes. Inspect the saved original tracks and mixed WAV in an audio editor. Record initial offset and ending drift; a target of under 100 ms for clear conversation is a validation goal, not an established result. Repeat with headphones using a known dual-source timing fixture. Check attenuation/no clipping and source-start delays.

During a test disconnect/reconnect each device, switch Bluetooth profile, deny access and simulate a full recording disk using a disposable test volume. Confirm the unaffected source and already-written files remain, warnings are understandable, and no success message conceals missing samples. Close/reopen after an intentionally interrupted test process; verify complete frames already written can be recovered. Do not use valuable recordings for destructive tests.

## Practical performance

Use an actual 8 GB CPU-only Windows 10/11 laptop. Run the benchmark script and record total/available RAM, idle RSS and peak system commit in Task Manager. Exercise a 60–90 minute real meeting with tiny live captions, base final transcription and quick notes. Record cold/warm latency, recognition real-time factor, dropped-caption warnings, UI responsiveness and ending memory. Test a small optional Ollama model separately; do not assume it fits alongside the OS and speech models. A fake-model buffer run does not cover native model allocations or driver leaks.

## Interface, content and accessibility

At 1366×768 and a larger display, use Windows 100%, 125%, 150% and 200% scaling in both themes. Check sticky Record/Stop and input controls, compact Meetings/New/Add/Paste/Settings, scrolling, long titles, source-evidence and transcript-review dialogs. Navigate every workflow by keyboard; check focus, contrast and a real screen reader. Verify failed saves keep edits and prevent accidental closing/navigation.

Review transcripts before generating notes. Include explicit and tentative decisions, missing owners/deadlines, contradictory statements and non-English speech. Verify actions against source quotes; confirm participant identities manually. Test a real installed Ollama model, service restart, cancellation, long transcripts and instructions embedded in the spoken source. No AI audit proves correctness.

Export edited long documents and a multi-page action table in every supported format. Open DOCX in Word/LibreOffice, PDF in a normal viewer and SRT in a subtitle player. Check headings, page numbers, Unicode, scripts used by actual users, meaningful punctuation and very long paragraphs. Check the project JSON includes current edits. RTL/CJK/font coverage requires direct validation.

## Remote users and updates

Automatic updates are not implemented in 0.4. Distribute a versioned installer through a trusted HTTPS channel, with checksums, source identity, signing status and release notes. Users should close the app, create a full backup and install the newer version over the old one. Keep the prior installer and backups for recovery. An eventual updater needs signed metadata/packages, a protected signing pipeline, staged rollout, rollback and migration tests; do not silently add remote access to meeting files.
