# Client download preparation

`stage-client-download.yml` copies the unchanged installer and portable ZIP from
the successful Windows run into the existing **private beta draft**. It verifies
the source SHA, successful validation, binary SHA256 values and uploaded metadata.
Application code is not rebuilt or changed.

The workflow requires repository-content write permission only to attach draft
assets. It refuses to change a published release and contains no publication
operation. Public release publication still requires explicit user approval, as
specified in the engineering brief. Main is not merged by this workflow.

The beta was published with explicit user approval on 5 November 2026. The
installer is now available without GitHub sign-in from the stable release URL:

`https://github.com/zibah04/Solscribe/releases/download/v0.4.0-beta.1/SolScribe-Setup-0.4.0.exe`

The public installer URL was verified with an unauthenticated HTTP request
(returned 200 and the expected 113,042,515-byte installer). The staging workflow
now refuses to modify this published release; future versions need a new draft. Release assets do not
have the 30-day retention limit of Actions artifacts. This remains an unsigned
beta; all hardware and quality limitations in the engineering report still apply.
