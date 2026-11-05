# Architecture and safety boundaries

The desktop remains PySide6/Qt Widgets. There is no web service or mandatory cloud dependency.

| Area | Modules and responsibilities |
| --- | --- |
| Presentation | `ui.py` coordinates workers and current meeting; `presentation/layout.py` constructs controls; recording, transcript, storage and action controllers handle their workflows |
| Persistence | `repository.py` owns transactions, schema migrations, explicit recording ownership and references, trash and drafts; `storage.py` preserves its public import path |
| Recovery | `filesystem.py` stages/fsyncs/replaces files; `backups.py` validates/stages archives and snapshots; `recovery.py` repairs known PCM WAV headers; `processes.py` checks active owners without signaling Windows processes |
| Capture | `recorder.py` keeps device callbacks short and writes via bounded queues; `combined.py` retains source tracks and a mix; `mixing.py` aligns source clocks with bounded buffers |
| Captions | `audio.py` defines capture packets and stateful FIR decimation; `pcm.py` chunks without repeated whole-buffer concatenation; `captioning.py` reconciles overlap and source time; `live.py` is its Qt worker adapter |
| Final recognition | `transcriber.py` owns one CPU int8 model; `speech_resources.py` limits CPU threads and releases model resources |
| Meeting intelligence | `intelligence.py` extracts conservative evidence records; `reports.py` drafts documents, chunks/condenses long source and audits output; `ollama.py` manages bounded local streaming and cancellation |
| Exports | `document_markup.py` parses CommonMark into shared blocks/runs; `exporters.py` renders DOCX/PDF/text and atomically replaces destinations |
| Verification | `diagnostics.py` and `scripts/` provide opt-in release checks; `tests/` contains deterministic domain, repository, worker and UI regressions |

## Storage contracts

Schema version 4 adds recording assets, session references, source offsets, deletion/recovery state, structured actions, review state and a short transcript history while retaining legacy session fields. Before migration a consistent database snapshot is preserved. Older schemas receive missing columns in a transaction. Legacy audio ownership is false, independent of its directory.

Meeting deletion changes metadata only. A permanent metadata purge needs a trashed meeting and confirmation. Audio purge separately requires explicit ownership, a managed path, no active or trashed references and confirmation. A durable purging intent blocks new references between the DB transaction and filesystem deletion and is retried after interruption.

Updates first write an independent atomic JSON draft, then commit SQLite with FULL synchronous writes. A failed commit retains the draft; newer drafts replay on startup. Damaged JSON is not substituted with empty content and autosaved over the original. Database lock waits are bounded to 250 ms for routine updates; pending UI edits remain if a save fails. A single-instance profile lock guards app access. Internal Store callers still use SQLite transactions.

Archive backups use a consistent DB snapshot, owned audio and checksums calculated over the archived bytes. Restore validates paths, file types, sizes, hashes, SQLite integrity and saved transcript structure before replacing the DB. The old DB is preserved. Imported audio is linked, not archived. Archives and draft files are sensitive and unencrypted.

## Time and worker contracts

AudioPacket positions use captured source frames. Queue overflow drops old live-caption packets while preserving their original absolute positions. Gaps reset overlap; timestamps do not shift subsequent speech earlier. Device capture queue loss is separately reported and represented by silence in the WAV timeline. Lost physical samples cannot be recreated.

The mic uses PortAudio ADC timing when available. Loopback uses a software monotonic estimate. The mixer maps source starts and subsequent clock observations onto a shared clock, resamples drift, bounds retained data, and records late samples. Both original tracks remain even if a source fails. This is implemented alignment, not a claim of hardware-perfect synchronization.

Capture disk writes, speech recognition, report requests, backup/restore and recording shutdown run outside the Qt event loop. Busy flags remain set until the UI has consumed queued completion signals. Caption appends avoid rescanning all rows unless edits need saving. Full final transcription is offered as a comparison; replacement is explicit and manual speaker names transfer only when timing is unambiguous. The previous three transcripts remain in the DB; a history-restore UI is not yet provided.

Speech model initialization/native decoding cannot be forcibly interrupted safely; cancellation is cooperative at available boundaries. Close keeps the window open while workers are active. No QThread termination or forced deletion of user recordings is used.

## Intelligence and security

Quick notes use explicit English commitments and verbatim evidence; attendee metadata never fills an unstated owner. Tentative/question/conditional statements do not become confirmed commitments. Action evidence is retained after user edits, with an edited status. Structured register edits and written prose are intentionally distinct.

Ollama is fixed to loopback, checks installed models, bounds responses/context/time, streams with cancellation and unloads the optional model after a job. Prompts label transcripts as untrusted data. Model-written facts still require review; date/assignment checks are warning aids, not semantic proof. No tools are executed from generated text, no HTML is rendered in exports, and Markdown links/images do not trigger external downloads.

No telemetry, credentials in source, custom cryptography or model duplication is introduced. Local encryption is deferred: OS disk encryption plus access control protects current files without adding a new unrecoverable key dependency. No signing credentials were available to this task. Optional signing preparation requires a legitimate certificate already provisioned on a protected build runner; it does not create trust or bypass Windows protections.
