# Client download preparation

`stage-client-download.yml` copies the unchanged installer and portable ZIP from
the successful Windows run into the existing **private beta draft**. It verifies
the source SHA, successful validation, binary SHA256 values and uploaded metadata.
Application code is not rebuilt or changed.

The workflow requires repository-content write permission only to attach draft
assets. It refuses to change a published release and contains no publication
operation. Public release publication still requires explicit user approval, as
specified in the engineering brief. Main is not merged by this workflow.

After approval and publication, the installer can be downloaded without GitHub
sign-in from the stable release asset URL:

`https://github.com/zibah04/Solscribe/releases/download/v0.4.0-beta.1/SolScribe-Setup-0.4.0.exe`

That URL is not public while the release remains a draft. Release assets do not
have the 30-day retention limit of Actions artifacts. This remains an unsigned
beta; all hardware and quality limitations in the engineering report still apply.
