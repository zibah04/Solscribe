# SolScribe

Private meeting recording, transcripts and useful notes for Windows 10/11 x64. SolScribe 0.4.0 is a **beta**: light and dark themes retain the familiar purple palette, with a simpler workspace that adapts to smaller displays.

The validated 0.4.1 beta build adds verified in-app updates, an optional four-step first-use guide, and the `zibah@2026` footer. See [update delivery and setup](docs/UPDATES.md) and [0.4.1 verification](docs/041_REPORT.md). The published installer below remains 0.4.0 until the new beta is approved for public publication. Its Windows and Linux tests have passed.

## Get started

[Download the Windows installer](https://github.com/zibah04/Solscribe/releases/download/v0.4.0-beta.1/SolScribe-Setup-0.4.0.exe) (113 MB) and run it. No GitHub sign-in or ZIP extraction is needed. A [portable ZIP](https://github.com/zibah04/Solscribe/releases/download/v0.4.0-beta.1/SolScribe-Portable-Windows.zip) (170 MB) is also available; extract and keep its whole `SolScribe` folder together. Python is bundled. [Release notes, checksums and build identity](https://github.com/zibah04/Solscribe/releases/tag/v0.4.0-beta.1) accompany the unsigned beta. These release downloads do not have the 30-day expiry of Actions artifacts.

1. Choose **Microphone**, **Computer audio**, or **Both sources** at the bottom. Choose the microphone there; the computer playback device is in Settings.
2. Click **Record meeting**. With **Show words while I speak** enabled, captions arrive in roughly two-second audio batches plus model processing time. First use downloads a speech model. Your audio continues saving while it loads.
3. Click **Stop recording**, then review the words. **Improve transcript** rereads the full recording and lets you compare before accepting changes. Existing notes stay saved.
4. Click **Create notes**. Review the summary, minutes, memo and action items; edit them before sharing.
5. Choose **Save a copy** for Word, PDF or text. Export also supports Markdown, SRT and project JSON.

For an existing file, use **Add a recording**, then **Create transcript**. **Paste text** starts from existing words. **Example meeting** shows saved sample text and does not listen to the microphone.

## Everyday features

- CPU-only, int8 speech recognition with faster-whisper. `tiny` is the default for live captions; `base` offers a practical final-transcript starting point. Larger models use more memory and time.
- Capture-clock timestamps, overlapping caption context, bounded queues and explicit warnings if live words fall behind. A final short speech fragment is processed after Stop.
- Combined microphone and Windows playback capture keeps both original source WAVs and a mixed recording. Software clock alignment compensates measured clock changes; physical-device synchronization still needs validation on target hardware.
- Editable transcript words and speaker names, timestamp playback, transcript search and bulk speaker renaming. Speaker names are manual; automatic speaker identification is not included.
- Conservative quick notes work immediately. They quote source words, separate conditional decisions and keep missing owners/deadlines as **Unspecified**. English-language action extraction is heuristic.
- An editable action register includes task, owner, due date, status and source evidence. Double-click its source time to inspect the quote or navigate to the transcript. The register and written action notes remain separately editable.
- Draft review checkboxes clear after edits. Source checks help review AI output but cannot prove its factual accuracy.
- Automatic saving, recoverable meeting trash, explicit audio ownership, backup/restore and recovery drafts protect existing work.
- The sidebar gives way to a compact navigation bar on small windows. The main workspace scrolls; recording controls remain visible. Appearance is available in Settings in either layout.

## Optional polished writing

Quick notes need no additional service. Polished notes use [Ollama](https://ollama.com/) on this computer at `127.0.0.1:11434`. Install and run Ollama separately, install a suitable small model, then enter its name under **Settings → Advanced writing setup**. SolScribe checks that the model is available; it never downloads an Ollama model automatically. Avoid large writing models on an 8 GB PC.

The client supports bounded streaming responses, cancellation, context limits and hierarchical condensation of long transcripts. A missing service or malformed response transparently falls back to quick notes. Cancel keeps existing documents. Transcript content is treated as untrusted source data in prompts. AI can still invent or misinterpret details: verify names, decisions, dates and assignments against the original words.

## Your files and recovery

The installed and portable apps share `%LOCALAPPDATA%\SolScribe` for this Windows account:

| Location | Contents |
| --- | --- |
| `solscribe.db` | Meetings, transcripts, notes, actions and recording references |
| `recordings` | Audio newly recorded by SolScribe, including separate combined-capture tracks |
| `models` | Speech model cache |
| `backups` | Automatic database snapshots and preserved databases from restores |
| `drafts` | Independent recovery files retained if a database write fails |

Imported files are linked in place. Keep the original files. Legacy recordings have conservative ownership even if located inside `recordings`; upgrading never automatically claims or deletes them.

**Delete meeting** moves it to trash without deleting audio. Settings provides trash recovery, permanently removing trashed metadata, and a separate confirmed operation for unused SolScribe-owned audio. Audio referenced by any active or trashed meeting is protected. Uninstall removes the application, not the meeting library.

Use **Settings → Back up meetings** for a ZIP containing a consistent database snapshot and owned audio with checksums. Imported audio stays linked and is not copied into that archive. Automatic snapshots preserve the latest five database copies; they do not copy audio. Keep periodic full archives on another drive.

Restore accepts a backup ZIP or database snapshot (`.db`) and preserves the previous database. DB-only restores require the original audio paths to remain accessible. Invalid archives and damaged transcript structures are rejected before replacement. If startup fails because the database is damaged, the startup dialog offers backup recovery. Failed writes keep edits open and retain a draft when disk space permits. Interrupted, known-owned PCM recordings can recover complete frames already written; audio never written to disk cannot be reconstructed.

Only one application instance may open a meeting library at a time. Close older versions before upgrading or restoring.

## Privacy and limits

Audio and transcript processing is local by default. Speech models require a first-use download from the model provider; subsequent use can be offline. Optional Ollama traffic is local-only. There is no telemetry, automatic upload, cloud account or mandatory API key.

The database, WAVs, backups and drafts are **not encrypted by SolScribe**. Anyone with access to the Windows profile can read them. Use Windows account protection and BitLocker/device encryption where available; secure exported copies too. An in-app encrypted vault is deferred until key recovery and migration can be designed without locking people out of existing files.

The build is unsigned unless `SIGNING_STATUS.txt` verifies otherwise. No signing certificate is supplied. Keep Windows security protections enabled. Combined capture has no acoustic echo cancellation; headphones help avoid duplicate playback through the microphone. Physical audio reliability, mixed-source drift, multilingual accuracy, screen-reader behavior and 8 GB laptop performance need the checks in [Windows acceptance](docs/WINDOWS_ACCEPTANCE.md) before a wider release. Live captions are provisional; driver/device failures can cause missing audio, with warnings where detected. No automatic updates, syncing, translation or diarization are included.

## Keyboard access

Ctrl+N new meeting · Ctrl+O add recording · Ctrl+R record/stop · Ctrl+S save · Ctrl+E save a copy · Ctrl+, settings. Tab navigates controls; focus outlines are visible in both themes. Some complex-script and right-to-left exports need additional font/layout validation.

## Develop and verify

Use Python **3.11 x64** on Windows:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip check
.venv\Scripts\python -m pytest -q --junitxml=windows-tests.xml
.venv\Scripts\ruff check --select F821,F822,F823 solscribe scripts app.py
.venv\Scripts\python app.py
```

`run_windows.bat` sets up a source installation; `build_windows.bat` creates the executable. The Actions workflow uses the same x64 virtual environment for tests and packaging, checks 100/125/150/200% Qt scaling, runs real speech recognition from synthetic spoken test audio in both source and packaged builds, then exercises migration, installation, removal and reinstallation. It uploads tests, measurements, dependencies, checksums and build identity. Qt scaling tests are not physical Windows display testing.

For reproducible measurements, run `python scripts/benchmark.py --output performance.json`. It isolates temporary data and measures startup, RSS, 10,000-row loading, note generation and a synthetic 90-minute stream. It uses a fake recognizer for buffer retention; it is not a speech-speed benchmark. `python scripts/smoke_live.py live-smoke.wav` measures actual recognition on a 16 kHz mono PCM16 test file containing “meeting” and “report”. Its prequeued input timings are not physical microphone latency.

Optional Authenticode preparation uses `scripts/sign_windows.ps1`. A legitimate certificate and protected private key must already be provisioned in the runner's CurrentUser certificate store; set repository variable `WINDOWS_SIGNING_THUMBPRINT`. Configured signing failures fail the build. A future signing runner/service must protect that key; no secrets belong in source. Inno's generated uninstaller is not signed by this preparation.

See [architecture](docs/ARCHITECTURE.md), [release notes](RELEASE_NOTES.md) and [engineering evidence](docs/ENGINEERING_REPORT.md). Changes are prepared on `codex/solscribe-040-remediation`; the functional `codex/windows-build-v0.2` history is preserved. Review and merge the PR before making `main` the release source. The [public beta download](https://github.com/zibah04/Solscribe/releases/tag/v0.4.0-beta.1) was published with explicit user approval on 5 November 2026. Main has not been merged.

## Troubleshooting

- **No words yet:** wait for the speech download and initialization, check the level meter and device selection, use `tiny` for live captions. Imported-file transcription uses Create transcript instead.
- **No microphone:** allow desktop microphone access in Windows Privacy settings and check device drivers. Refresh by reopening the app after connecting a device.
- **No remote participants:** choose Computer audio or Both sources and select the actual playback output in Settings. Bluetooth profile changes may change the available device.
- **Writing helper unavailable:** quick notes remain usable. Confirm Ollama and the chosen model are installed and running for polished writing.
- **Save fails:** free disk space/check folder access; keep the window open. Recovery drafts are retained where possible.
- **A file will not decode:** use a trusted converter to make WAV, MP3 or M4A, then add it again. Codec support depends on PyAV/FFmpeg.

MIT licensed; see [LICENSE](LICENSE).
