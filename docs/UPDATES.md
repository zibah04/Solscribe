# Sending SolScribe updates to remote users

Clients need to install 0.4.1 once. Earlier 0.4.0 builds cannot acquire update controls remotely. After that, they can use **Updates** in the footer or **Settings → Check for updates**. Optional startup checks can be enabled in the guide or Settings. An available version appears in the footer; nothing installs automatically.

The client checks the official public GitHub releases for this repository. It ignores drafts, older versions and malformed release files. Beta clients can receive newer beta or stable versions; stable builds skip preview versions. It requires the expected versioned Windows installer and its SHA256 digest from GitHub. It follows only HTTPS addresses on the official repository and GitHub asset hosts. No transcript, meeting title, recording or account token is sent.

A download is written to a temporary file under the profile's `updates` directory, bounded in memory, and verified before becoming installable. Cancelling, a broken connection, low disk space or a wrong checksum keeps the existing app. The user chooses **Install and close** when idle. The app saves pending edits, rechecks the installer and makes a database snapshot before opening the normal installer. Windows security prompts remain active. Current unsigned builds rely on the trusted GitHub HTTPS release channel and asset digest; the checksum does not replace publisher code signing.

Portable users can use the same check/download flow, but Install opens the normal installer. To remain portable, open the release page and replace the extracted application folder with the new portable ZIP. Both formats keep the meeting library outside the application folder.

## Owner's steps for a future release

1. Make and test the changes on a development branch. Update `solscribe/__init__.py` (`__version__` and `__release_tag__`), `SolScribe.iss`, and `assets/version_info.txt` consistently. Examples: version `0.4.2`, tag `v0.4.2-beta.1`. Use a new tag rather than replacing an older release.
2. Run `python scripts/release_version.py`. The Windows workflow also enforces matching versions and derives filenames automatically.
3. Push to a branch watched by the Windows workflow and wait for all tests, real speech/update checks, packaged startup and installer-preservation checks to pass. Download the successful `SolScribe-Windows` artifact.
4. On GitHub, create a **draft release** with the exact tag, targeting the tested source commit. Mark a beta as a prerelease. Add clear notes and the versioned `SolScribe-Setup-X.Y.Z.exe`, portable ZIP, SHA256SUMS, BUILD_INFO, signing status and license from that build. GitHub calculates the uploaded asset digest used by the app.
5. Review the draft and obtain publication approval. Publish only when the complete installer asset and notes are ready. The app never offers draft releases. A release missing its expected installer or digest is not installed.
6. Remote users receive the available-version notice on their next enabled startup check, or can click Updates immediately. They decide when to download and install. Users who keep the app open can check manually without restarting.

No new cloud backend, customer account or client API key is needed. Main-branch merging and public release publication remain separate review decisions. The original private-draft staging workflow intentionally refuses to modify the already published 0.4.0 release; a new version needs a new draft and verified build.

## First-use guide

The optional four-step guide appears on first normal launch, including an upgrade from 0.4.0 where the guide has not been seen. It explains privacy/appearance, microphone and computer sound, recording/review, then notes/saving/updates. The user can choose actual preferences, practise with a sample, or skip. The sample is saved text, not a microphone mode. The footer and Settings reopen the guide at any time while idle. Credit remains visible as `zibah@2026` in either theme and compact layouts.
