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
| Your chosen AI provider        | Only if you enter an API key in Chooser, or if you pick a local model (Apple Intelligence on macOS / iOS, or Ollama on the Mac), in which case nothing leaves your machine for chat |

No request carries any identifier we could use to recognise you;
the AI providers see whatever their own terms describe, which is
why we recommend a local model (Apple Intelligence on the
free tier, Ollama on the Mac) if you're privacy-sensitive.

## What stays on your device

- **API keys** — stored in the system Keychain.
- **Notes** — JSON files in your Application Support directory.
- **Scrapbook clips, Snake high score, Settings** — `UserDefaults`.
- **Paintings** — PNGs you save land in Application Support.
- **Era choice, current shopfront registration, content-filter
  toggle** — `UserDefaults`.

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
  picker, and the optional Save panel.

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
