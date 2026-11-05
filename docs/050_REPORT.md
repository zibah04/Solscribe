# 0.5.0 lecture-mode verification

Status: final Windows and Linux verification passed. The installer (113,083,533 bytes), portable ZIP (170,389,328 bytes) and seven supporting files are checksum-verified in the [private beta draft](https://github.com/zibah04/Solscribe/releases/tag/untagged-7b5815763aea643f22cd). [Private staging run 42058974658](https://github.com/zibah04/Solscribe/actions/runs/42058974658) passed. No public 0.5.0 release has been published or main merged.

Source: `53d08ba08860e09a4878ff31680e3d62297c0d76` on `codex/solscribe-050-lecture-mode`.

- [Draft review PR #3](https://github.com/zibah04/Solscribe/pull/3)
- [Final Windows build 42057519632](https://github.com/zibah04/Solscribe/actions/runs/42057519632)
- [Windows installer/portable artifact 13429369426](https://github.com/zibah04/Solscribe/actions/runs/42057519632/artifacts/13429369426)
- [Validation artifact 13430417019](https://github.com/zibah04/Solscribe/actions/runs/42057519632/artifacts/13430417019)

## Behavior

Dedicated lecture notes and source-backed revision practice retain all 0.4.1 guide/update/footer changes. Schema 5 migrates old libraries with a snapshot and keeps meeting and study documents separate. Newer unknown schemas are rejected instead of downgraded. Recording a lecture after using the sample creates a separate lecture and preserves the sample.

Automated cases cover split live captions, long-lecture tail coverage, formulas/negation, literal markup, source hashes, invalid AI sources/numbers, unavailable writing helper fallback, migration, future-schema rejection, mode/save failure guards, editable cards with immutable evidence, changed-transcript warnings, source navigation, guide choices, six exports and both themes at compact laptop sizes.

## Executed checks

- Linux: **193 passed**, 0 failures/errors/skips, 47.356 seconds. Actual app entry-point smoke passed through both themes, guide, lecture creation, answer reveal and source navigation. Dependency, undefined-name, version consistency and diff checks passed.
- Windows Python 3.11.9 x64: **193 passed**, 0 failures/errors/skips, 40.707 seconds at 150% Qt scaling. **87 additional layout cases** passed at 100/125/200% scaling.
- Real synthesized speech passed through source and packaged CPU/int8 recognition. This tests actual recognition of prerecorded speech, not a physical microphone or lecture comprehension.
- Real public HTTPS update checks/downloads passed in source and packaged builds with installer size/SHA256 verification and Windows internet-origin marking; the downloaded old installer was not executed by that smoke test.
- The packaged and installed apps passed both themes, guide/footer, study generation, revision reveal and source navigation without a writing helper.
- **Two install/uninstall cycles** passed with a real legacy database/WAV. Existing summary, words, speaker, conservative media ownership and audio survived; lecture notes, cards, source excerpts and source hashes also survived.
- A separate synthetic 1,000-segment lecture organized in 0.189 seconds on this Linux runner and retained the final topic in revision. This measures extraction behavior, not speech quality or learning outcomes.

Installer SHA256: `bed47c4f96f30d022e916eb76f4b2655169e51aac6e47f97a567b72b12d9f653`.

Portable ZIP SHA256: `75233e34df2c31624a1efa6599c3da011041001529259a44bfcbe671500bd5d1`.

Windows artifact bundle SHA256: `93851434261cff25fb655c4e4e64848dcca8b6398957d401d8722c956ec9c9b0`. Actions artifacts have a 30-day retention limit. Private release staging checks the exact successful run, source commit, release target, binary hashes and build identity, then verifies each attached asset. It has no publication operation.

Raw Linux XML, Windows annotations/metrics/checksums and both-theme screenshots are retained in [validation/050](validation/050). The earlier successful build 42056063720 is retained but is superseded by the final wording/recording-label build above.

## Limits and publication

See [LECTURE_MODE.md](LECTURE_MODE.md) for usage and limits. Real lecture accuracy, physical audio, 8 GB target hardware, actual Ollama quality and assistive technology are not certified by synthetic/offscreen tests. Quick category detection is English based, selected excerpts are limited and AI wording still needs review. This is an unsigned beta pending user acceptance.

The user's engineering brief explicitly requires approval before public publication or merging main. The published 0.4.0 download and earlier private 0.4.1 draft remain unchanged. A future public 0.5.0 direct link is not usable while its release remains private.
