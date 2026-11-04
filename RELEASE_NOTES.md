# SolScribe 0.3.0

## A calmer workspace

- Light and dark themes, with familiar purple accents. Change Appearance at the bottom left; your choice is remembered.
- A welcoming first-use screen, clearer next steps, quieter controls and more room for your words.
- Formatted, editable notes and familiar Word/PDF saving.
- Keyboard access, named controls, visible focus states and readable text contrast in both themes.
- The app returns to your last meeting. Meeting details and optional writing setup stay out of the main workflow.

## Reliability

- Failed exports leave existing destination files intact.
- Unsaved edits remain open if the meeting database cannot be written; starting another meeting or closing will not silently discard them.
- Microphone start/stop failures clean up streams and recording threads.
- Windows-safe export names and correctly numbered subtitle files.
- Quick notes remain available if the optional writing helper is missing or unavailable.

## Validation and package contents

The release workflow runs automated regressions, theme/layout checks at 100%, 150% and 200% scaling, real speech recognition, packaged-app startup in both themes, and installer launch/removal checks that preserve an existing meeting and recording.

The download includes the installer, portable ZIP, quick-start guide, license, dependency versions, test results and SHA256 checksums. The source commit and build number are recorded in BUILD_INFO.txt. Windows installer and file properties identify version 0.3.0.

## Practical limits

- This build is unsigned. Public distribution with a verified publisher name requires a code-signing certificate, which is not included.
- First use needs internet for a speech download; recorded speech is processed on your PC. Polished rewriting additionally needs the optional local writing helper.
- Live words arrive in short batches with processing delay. Always review transcripts and meeting notes for accuracy.
- Physical microphone quality and Windows playback capture depend on your hardware, drivers and permissions. A final check on the intended devices remains necessary before public release.
- Simultaneous microphone/playback mixing and automatic speaker identification are not included. Speaker labels can be edited.
- Keep a copy of the downloaded release; GitHub workflow downloads are retained for 30 days.
