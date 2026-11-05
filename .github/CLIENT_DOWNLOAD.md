# Client download preparation

`stage-client-download.yml` copies the unchanged installer and portable ZIP from
the successful Windows run into the existing **private beta draft**. It verifies
the source SHA, successful validation, binary SHA256 values and uploaded metadata.
Application code is not rebuilt or changed.

The workflow requires repository-content write permission only to attach draft
assets. It refuses to change a published release and contains no publication
operation. Public release publication still requires explicit user approval, as
specified in the engineering brief. Main is not merged by this workflow.

The 0.4.1 beta is now prepared in a private draft using the successful Windows
run 42035906513. The previously approved 0.4.0 public release remains unchanged.
After separate approval and publication, the new direct installer URL will be:

`https://github.com/zibah04/Solscribe/releases/download/v0.4.1-beta.1/SolScribe-Setup-0.4.1.exe`

That new URL is not public while 0.4.1 remains a draft. The staging workflow cannot
publish it and refuses changes to any published release. Release downloads do not
have the 30-day Actions retention limit. All unsigned-beta limitations remain.
