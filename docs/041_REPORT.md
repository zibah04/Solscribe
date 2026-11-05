# SolScribe 0.4.1 beta verification

Implemented: safe user-controlled update checks/downloads/installer handoff, opt-in startup checks, a four-step interactive first-use guide with saved preferences and sample practice, replay controls, and the persistent `zibah@2026` footer. Application data schema and the existing recording/transcript/document workflow are retained.

Linux: **158 passed**, 0 failed, 25.35 seconds. New coverage exercises semantic release order, no downgrades/drafts/unrequested previews, untrusted addresses, invalid digests/sizes, partial or changed downloads, cancellation, preserved cached files, backup-before-install handoff, failed backup preservation, active-recording guards, update consent, guide replay/practice and compact footers. Existing regressions remain. Undefined-name checks and release-version consistency checks passed.

A real public HTTPS check selected the older published 0.4.0 beta, downloaded its 113,042,515-byte installer, and independently matched its recorded SHA256. It did not execute the downloaded installer. Metadata took 0.95 seconds; metadata plus verified download took 6.66 seconds on this cloud connection. This is not a client-network speed guarantee. Evidence: `docs/validation/041/update-source-linux.json`.

The long Linux startup test was traced to resetting the existing QApplication's Fusion style over closed test windows. Reusing the active style and disposing closed test windows removed the redundant work; the final full run completed without the earlier stall. Production and test applications now use the same style.

Windows build, packaged update/TLS checks and installer preservation results will be added after execution. A configured workflow does not establish a passing build. No new public release has been published by this 0.4.1 work yet; 0.4.0 remains available. See `docs/UPDATES.md` for client and owner steps.

Physical audio devices, 8 GB laptop performance, real Ollama writing quality, fresh consumer Windows, full screen-reader coverage and complex-script export remain acceptance limits from the 0.4 engineering report. This is still an unsigned beta; update hashes and HTTPS do not establish a verified publisher. Future code signing still needs legitimate credentials. Installation requires the user's explicit action.
