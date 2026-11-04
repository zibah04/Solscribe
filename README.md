# SolScribe · Meeting Intelligence Studio (Windows)

**Private, offline-first LIVE speech-to-text and meeting documentation.** A native Windows 10/11 desktop app, not a website. Converts recorded conversations, meetings, lectures, voice notes and audio/video files into editable transcripts, minutes, memos, action lists and exportable documents.

## Features · version 0.3.0

- Record from a Windows microphone into local 16 kHz WAV, with elapsed time and audio-level indicator. **Live transcription** runs in a separate worker and adds timestamped captions as the recording continues. **Live captions appear while recording**, generally in ~2-second audio chunks plus CPU processing time. Also includes experimental Windows PC-playback capture (WASAPI loopback) for online-meeting audio.
- Import WAV, MP3, M4A, AAC, OGG, FLAC, WEBM, MP4 and several other media formats (decode support depends on PyAV / FFmpeg).
- Transcribe offline using **faster-whisper** (CPU int8): automatically detect language, or pick a supported language. Timestamps are kept for each transcript segment.
- Review or edit transcript text and **manually correct speaker labels**. Click a timestamp to jump in the source recording.
- **Summary, minutes, memo and action register** created on demand. The instant offline mode uses direct transcript excerpts and explicitly labels possible decisions/actions for verification.
- Optional more natural, context-aware summaries and documents using **Ollama** running locally (no remote API key required). Long transcripts are condensed in chunks.
- Edit generated documents, add meeting metadata, and automatically save changes in a private SQLite database.
- Export **PDF, Word DOCX, TXT, Markdown, SRT subtitles, and full project JSON**.
- Search the local project library, drag and drop recordings, or paste text. Built-in example project.

## Fastest start on Windows

**Option A – Windows installer (when built with GitHub Actions):** download `SolScribe-Setup-0.3.0.exe` from a successful workflow artifact and install normally.

**Option B – from this source ZIP:**

1. Install **Python 3.11 (64-bit)** from https://www.python.org/downloads/ (select *Add Python to PATH* during installation).
2. Extract this ZIP to a folder (for example `Documents\SolScribe`).
3. Double-click **`run_windows.bat`**. It will set up a private Python environment, install the libraries once, and open the native desktop window.
4. For a live meeting, ensure **Show words while I speak** is ticked, select your microphone and click **Record meeting**. Caption lines appear in the Transcript tab in chunks. Click Stop to finish. For a saved recording or voice memo, choose **Import audio / video** and then **Create transcript**.
5. For a more accurate final transcript, click **Create transcript** after stopping (you will be asked before replacing live captions).
6. Enter meeting details and click **Create notes**. Review your Summary, Minutes, Memo and Action items tabs, edit as needed, and export using the top-right menu.

The initial dependency installation and **first download of each Whisper model** require internet access. The live and full-transcription buttons may each use a selected Whisper model; choose `tiny`/`base` for responsive live captions. After the model has downloaded, live captions and standard transcription are completely local. No paid API keys are required. A computer with 8 GB RAM should start with `tiny`, `base` or `small`; `medium` / `large-v3` can be very slow or run out of memory on CPU.

### Optional: better local AI minutes

Install Ollama from https://ollama.com/ and in Windows Terminal run:

```powershell
ollama pull llama3.2
```

Keep Ollama running. Inside SolScribe open **Settings**, select **Polished notes**, then expand **Advanced writing setup**. Leave the model field as `llama3.2` (or use another installed model), and click Create notes. Minutes, memo and actions are produced with a fact-preserving prompt and remain editable. For very long meetings, the transcript is condensed in chunks. Even AI-generated notes must be reviewed against source audio.

### Make a portable Windows EXE

With Python 3.11 installed, double-click **`build_windows.bat`**. When it finishes, run:

`dist\SolScribe\SolScribe.exe`

Keep **all files in `dist\SolScribe`** together; it is a bundled directory, not a single stand-alone EXE. The EXE is built **on Windows**, not cross-compiled from Linux.

### Get a one-click installer automatically using GitHub

Upload this project to a new GitHub repository, **including the hidden `.github` directory**. Select the **Actions → Build SolScribe for Windows → Run workflow**. After the workflow completes, open its run and download the **SolScribe-Windows** artifact, which contains a portable app ZIP and an installer `.exe`. GitHub workflow artifacts expire after the retention period, so store a copy for distribution.

## Release 0.3.0

Switch between Light and Dark with **Appearance** at the bottom left. Both keep SolScribe's purple palette and your preference is saved. The workspace fits laptop screens, starts with helpful guidance and returns to your last meeting.

Record or add a recording, review the transcript, create notes, then save a copy. Quick notes work immediately; polished notes use an optional helper. If that helper is unavailable, SolScribe makes quick notes instead and explains what happened.

See [START_HERE.txt](START_HERE.txt) for the user guide and [RELEASE_NOTES.md](RELEASE_NOTES.md) for validation and public-release limits. Source builds and the installer are unsigned.

## Layout and live captions

- The transcript has its own large workspace. Meeting metadata is in **Meeting details**; final-transcription model and language are in **Settings**.
- **Fast captions** in Settings uses the `tiny` speech model for responsiveness. Captions update after roughly two seconds of audio plus recognition time; this is not instant word-by-word dictation.
- Loading/download, recognition, and failure messages stay visible above the transcript. First use needs an internet connection to download the selected model. The recording is still saved during loading.
- **Example meeting** opens saved sample text; it does not listen to your microphone. To see your own speech, select the correct input and click **Record meeting** with the checkbox enabled. Watch the input-level meter.
- The final short audio tail is processed on Stop. Wait for queued captions to finish. Use **Create transcript** after recording to improve accuracy with the final model.

## Privacy and important limitations

- By default SolScribe never sends audio or transcripts to cloud AI providers. The model downloads once; local Ollama requests go to `127.0.0.1`.
- Imported recordings are **linked in place**, not copied, so keep the original file. Microphone recordings are stored at `%LOCALAPPDATA%\SolScribe\recordings`.
- All session records, notes and transcripts reside in `%LOCALAPPDATA%\SolScribe\solscribe.db`; Whisper models are cached under `%LOCALAPPDATA%\SolScribe\models`.
- PC audio (loopback) and microphone are separate capture choices; **simultaneous microphone + system-audio mixing is not implemented**. Recording online meetings with a headset can therefore omit your own voice when you select PC audio.
- The app does **not automatically identify speakers**. Editable generic speaker labels are intentional, to avoid falsely claiming diarization.
- **Live transcription is implemented**: it produces provisional captions in short audio chunks while recording. It is *near-live*, not instant word-by-word captions; actual delay depends on processor and model. On a slow CPU, captions may lag or omit audio when the queue fills. The **full original recording remains intact**; use **Improve transcript** after recording for completeness and better word boundaries.
- Audio quality, background noise, overlapping speakers and accents can reduce accuracy. Live captions are not a substitute for independently verified official minutes.
- The simple offline drafting mode is an **extractive draft** (verbatim excerpts), not deep semantic understanding. For polished contextual reports, choose Ollama.
- The app is **not** a certified confidential-records management system: anyone with access to your Windows profile or database files may read them; protect your PC and secure your backups.
- Obtain consent and follow applicable privacy/recording laws before recording a meeting.

## Keyboard shortcuts

Ctrl+N: new session · Ctrl+O: import audio · Ctrl+S: save · Ctrl+E: export · Ctrl+R: start/stop recording (uses the live-caption checkbox).

## Developer commands

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest -q
```

## Troubleshooting

**App does not start**: confirm 64-bit Python 3.11 and re-run `run_windows.bat` with an internet connection. If you installed another major Python version, run the above developer commands with Python 3.11.

**First transcription stuck on model loading**: the chosen model may still be downloading; test with `tiny` or `base`. A firewall may block access to Hugging Face models. If the model is already cached, internet is no longer required.

**Live captions do not show up**: wait for the first speech-model download/initialization and about two seconds of audio plus processing. Try `tiny` for faster results on older laptops, or `base` for better accuracy. Live captions require a functioning microphone/PC-audio input and will not show during imported-file transcription, which uses the **Create transcript** button.

**Mic not available**: enable Windows *Settings → Privacy & security → Microphone* and *Let desktop apps access your microphone*. Change the mic in SolScribe's bottom-right dropdown. For capturing other participants in a Teams/Zoom meeting, choose the experimental **PC audio: ...** device from that same dropdown; this captures computer playback only.

**Video/audio cannot be decoded**: convert it to WAV, MP3 or M4A using a trusted converter, then import the resulting file.

**Ollama can't connect**: check that the Ollama application is running and the selected model has been pulled. The default service listens on `http://127.0.0.1:11434`.

**Windows SmartScreen warning**: unsigned custom EXEs can trigger SmartScreen. Builds are not code-signed; source is provided for inspection. Don't disable antivirus protections globally.

## Roadmap (not implemented in this version)

Automatic speaker diarization, combined microphone+system-audio mixing, multilingual translation, calendar integration, cross-device syncing, encrypted local vault, user-managed cloud-provider transcription, and installer code signing.

## License

MIT. See `LICENSE`.
