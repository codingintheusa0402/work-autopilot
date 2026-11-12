# screenpipe — what we use, how it is installed, and its license

work-autopilot does **not** include or redistribute screenpipe. Step 1 (Observe) runs screenpipe's own npm package
(`npx --yes screenpipe@latest record …`), which downloads screenpipe's official CLI binary for your OS.
You can also install the desktop app from screenpipe's site instead.

Checked on 2026-11-12. Licenses and plans change — read the current pages yourself before using it at work.

## Install (from screenpipe's own README)
- Desktop app for macOS, Windows, Linux: <https://screenpipe.com/how-to-install>
- CLI: `npx screenpipe record` (npm package `screenpipe`, which pulls `@screenpipe/cli-<os>-<arch>`; version 0.4.58
  at the time of writing, about 170 MB for the macOS arm64 binary)
- Source: <https://github.com/screenpipe/screenpipe>

## License (summary — not legal advice)
- The repository is **source-available, not open source**: "Screenpipe Commercial License"
  (<https://github.com/screenpipe/screenpipe/blob/main/LICENSE.md>). GitHub shows the license as "Other/NOASSERTION".
- Free use (section 2): personal non-commercial use; non-profit, educational or research use; and evaluation,
  development and testing **for up to seven (7) days at any organization size**.
- Commercial use (section 4) of the source or self-built binaries requires a paid Enterprise plan and commercial license.
- Official prebuilt builds are governed by screenpipe's Terms of Service and your plan (section 3: Free / Basic /
  Business plans; one license per person; 5+ users in one company need a Team or Enterprise plan).
  Pricing: <https://screenpipe.com/pricing>.

**What this means for you:** a 3–7 day observation at work may fit the 7-day evaluation window or the Free plan, but
whether it does depends on the current terms and on how you install it. Check the license and your employer's policy
(screen recording at work usually needs your company's OK) before you start.

## Privacy facts from screenpipe's README
- Capture is stored locally by default. Cloud AI, cloud transcription (Deepgram), sync and integrations send data off
  the device — **work-autopilot never turns any of them on**.
- The desktop app enables product analytics (PostHog) and crash reports (Sentry) by default. You can turn them off in
  Settings → Privacy → Analytics. The CLI flag `--disable-telemetry` turns telemetry off; work-autopilot always passes it.
- The local API listens on `127.0.0.1` only unless `--listen-on-lan` is set (we never set it).

## The exact flags work-autopilot passes
See `./wa observe command`. In short:
`--data-dir workspace/raw/screenpipe` (its own folder, deleted after analysis) · `--port 3031` ·
`--disable-telemetry` · `--disable-audio` (unless you opt in; then local Whisper only) · `--disable-keyboard-capture` ·
`--disable-clipboard-capture` · `--use-pii-removal=true` · `--ignore-incognito-windows=true` · `--video-quality low` ·
`--retention-days 8 --retention-mode all` (backstop) · one `--ignored-windows` per excluded app/keyword ·
one `--url-block <domain>:subdomains` per excluded site.

After recording, `wa observe stop` exports only **time, app name, redacted window title and site domain** — no screen
text, no images — and `wa analyze` deletes the raw recordings.

Note: even with `--data-dir`, screenpipe 0.4.58 writes a tiny `~/.screenpipe/machine_id` file (an installation id,
no screen data). We leave `~/.screenpipe` alone because it may belong to your own screenpipe install; delete it yourself
if you don't use screenpipe otherwise.
