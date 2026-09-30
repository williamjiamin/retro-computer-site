# Retro Computer — Privacy Policy

**Effective: September 2026**

Retro Computer is a single-user desktop app. It does not have a
server, an account system, analytics, ads, or any first-party
tracking. The short version: **we don't see anything you do in
the app.**

## What leaves your device

The app connects only to public, opt-in endpoints:

| Endpoint                       | Why                                     |
|--------------------------------|-----------------------------------------|
| `history.muffinlabs.com`       | "On This Day" feed for the Today window |
| `hn.algolia.com`               | Hacker News front page for Tech Wire    |
| `ipapi.co`                     | Approximate city + coordinates for weather |
| `api.open-meteo.com`           | Current weather for those coordinates   |
| Your chosen AI provider        | Only if you enter an API key in Chooser. The default — a model built into the app — and the other local models (Apple Intelligence on macOS / iOS, Ollama on the Mac, any model you download) send nothing off your machine for chat |
| `huggingface.co` (and its CDN) | Never for the built-in model, which ships inside the app. Only when you tap Download on another model in Chooser ▸ Local Model: the weights themselves. The request carries no identifier and says nothing about you; once the file is on your device, chatting with it reaches no network at all |

No request carries any identifier we could use to recognise you;
the AI providers see whatever their own terms describe, which is
why we recommend a local model (Apple Intelligence on the
free tier, Ollama on the Mac) if you're privacy-sensitive.

## What stays on your device

- **API keys** — stored in the system Keychain.
- **The local model's free daily allowance** — a date and a number: how
  many replies the on-device model gave you today, so the free allowance can
  start again tomorrow. Never a question, never an answer, never a time of
  day. `UserDefaults`.
- **Notes** — JSON files in your Application Support directory.
- **Memos** — JSON files in your Application Support directory.
- **Journal** — one JSON file per day in your Application Support
  directory. It is read only on your device; nothing about it is sent
  anywhere, and nothing else in the app keeps a copy of what you wrote.
  The morning edition reads the same files to compute your streak and
  to unseal a time capsule from a past entry, all on the device.
- **Digitizer** — works only on a picture you hand it, and never stores
  that picture. The result leaves the app only when you copy it or save
  it to a place you choose. Its settings (mode, ink, dots) are in
  `UserDefaults`.
- **Scrapbook clips, Snake high score, Settings** — `UserDefaults`.
- **Paintings** — PNGs you save land in Application Support.
- **Downloaded models** — the weights of any local model you download sit in
  the app's Caches folder (`Library/Caches/models/…`), so the system may
  reclaim them if the device runs out of room, and Chooser ▸ Local Model
  deletes them on request. The conversation you have with one never leaves
  the device: there is no request to make.
- **The Adding Machine's paper tape** — one JSON file,
  `adding-machine.json`, in Application Support: the figures on the
  roll and the calculation in progress, so the roll is still there
  after a relaunch. TAPE tears it off and starts a fresh one.
- **Game saves** — the Puzzle's tray and best move count
  (`puzzle.save.v1`), and Sprocket's age: when its egg was laid, its
  stage, and how many keys have been pressed since — a count, never
  which keys (`sprocket.growth.v1`). Both `UserDefaults`.
- **Arcade hi-scores** — `UserDefaults` under `arcade.scores.v1`:
  four five-row tables keyed by game, plus the last
  initials the cabinet seeded. No network, no telemetry,
  no migration. Forgotten by hand-editing the key in
  Defaults, or by Control Panel's upcoming Forget button.
- **Sprocket's gift memory** — only the kind (byte, picture, link,
  text, file) and the date of what you give Sprocket, never the
  thing itself: dragged items are never opened. `UserDefaults`;
  Control Panel ▸ Companion ▸ Forget gifts clears it.
- **Era choice, current shopfront registration, content-filter
  toggle** — `UserDefaults`.
- **The morning edition's day counter** — `UserDefaults` under
  `todayRitual.edition.v1`: the issue numbers you've already seen, so
  the desk never re-delivers the same paper. Nothing about what you
  wrote is in this file.
- **Wallpaper Foundry** — the on/off flag (`wallpaper.foundry.onDesk`)
  and the cached pattern you cast, in `UserDefaults`. Patterns stay
  until you switch themes or use the Foundry's own erase.
- **The boot screen** — the lines you kept on or off and any text
  edits, `UserDefaults`. The default six lines ship with the app.
- **Alarm clock** — the next alarm time and the recurrence rule, in
  `UserDefaults`. The OS-level notification the alarm schedules is
  cleared when you remove it.
- **Trash** — the items currently in the trash and the auto-undelete
  countdown, in `UserDefaults`. Emptying Trash removes them.
- **Voice & push-to-talk toggles** — `UserDefaults`. The toggle state
  only; recorded audio and the transcription never touch the
  filesystem.

None of this is backed up to us because we don't have an "us". iCloud
backup happens or not based on your OS settings.

## Voice Mode & the microphone

Push-to-talk uses the microphone only while you hold the Talk
button, and the system asks for permission first. Speech is turned
into text **on your device** whenever your system supports it
(English does on modern Macs and iPhones). If on-device
recognition is not available for your locale, Apple's speech
service processes the audio under Apple's privacy terms — we
never receive it either way. Spoken replies use the system
speech synthesizer, entirely on-device.

## Sandbox & file access

The Mac app runs in the macOS App Sandbox. The three
entitlements it ships with are:

- `com.apple.security.app-sandbox` — required by App Review.
- `com.apple.security.network.client` — the news / weather
  feeds and any user-configured cloud AI provider.
- `com.apple.security.files.user-selected.read-write` —
  Paint's "Open…" panel, the Library "browse a folder"
  picker, the Digitizer's Open and Export panels, and the
  optional Save panel.

The app can read or write only to files and folders you
explicitly pick in a system Open / Save dialog. It cannot
touch anything you haven't selected. iOS is sandboxed by
the OS, with no extra entitlements.

## Kids

Retro Computer is rated 17+ (Infrequent/Mild Mature/Suggestive
Themes) to cover user-generated text flowing through any of
the AI providers the user can configure. The app contains no
advertising. There is no chat with strangers — the AI chat
only reaches the provider you configure with your own key
(or Apple's on-device model).

## Contact

Questions: `support@rippaxlabs.com`. Source:
`https://github.com/williamjiamin/retro-computer`.

This policy is the one that ships in the app's
`PrivacyInfo.xcprivacy` ("NSPrivacyTracking: false", no
collected data types, no tracking domains). If a future build
adds a new endpoint, the manifest and this file are updated
in the same change.
