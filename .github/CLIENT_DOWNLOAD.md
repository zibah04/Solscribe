# Client download preparation

`stage-lecture-download.yml` copies the unchanged 0.5.0 installer and portable ZIP from successful Windows run **42057519632** into its **private beta draft**. It verifies source `53d08ba08860e09a4878ff31680e3d62297c0d76`, the successful validation result, release target/tag, binary SHA256 values and uploaded metadata. Application code is not rebuilt or changed.

The workflow requires repository-content write permission only to attach draft assets. It refuses to change a published release and contains no publication operation. Public publication still requires explicit user approval, as specified in the engineering brief. Main is not merged.

After separate approval and publication, the new direct installer URL will be:

`https://github.com/zibah04/Solscribe/releases/download/v0.5.0-beta.1/SolScribe-Setup-0.5.0.exe`

That URL is not public while 0.5.0 remains a draft. Release downloads do not have the 30-day Actions retention limit. All unsigned-beta and lecture-quality limitations remain; see `docs/050_REPORT.md`.

The old `stage-client-download.yml` still targets only the preserved private 0.4.1 draft/run 42035906513 and is not used for 0.5.0. The previously approved 0.4.0 public release remains unchanged.

Private staging run 42058974658 completed successfully. All nine attached files were verified; binary sizes and hashes are retained in `docs/validation/050/private-release.json`. Owner review: https://github.com/zibah04/Solscribe/releases/tag/untagged-7b5815763aea643f22cd .
