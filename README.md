<div align="center">
  <img src="docs/assets/icon.svg" width="112" height="112" alt="Phone Link for Linux icon">

# Phone Link for Linux

**Your Android phone, connected to your Linux desktop.**

Calls · Contacts · Notifications · Clipboard · Wireless experiences

[![Linux](https://img.shields.io/badge/platform-Linux-2d6a8a?logo=linux&logoColor=white)](#requirements)
[![Python](https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white)](#development)
[![GTK](https://img.shields.io/badge/desktop-GTK_4_%2B_WebKit-5d8c44)](#architecture)
[![Status](https://img.shields.io/badge/status-experimental-e3a008)](#project-status)
[![Checks](https://github.com/slaveitgr/Phone-Link-for-Linux/actions/workflows/checks.yml/badge.svg)](https://github.com/slaveitgr/Phone-Link-for-Linux/actions/workflows/checks.yml)

[Features](#features) · [Installation](#installation) · [Verified tests](#verified-tests) · [Roadmap](#roadmap) · [Development](#development)

</div>

---

Phone Link for Linux is an independent desktop client connecting an Android phone running **Link to Windows** with Linux. It combines Microsoft account pairing and the phone's native relay with Linux Bluetooth telephony, a persistent background service, and a desktop interface based on the supplied Phone Link designs.

The goal is a useful, integrated Linux experience: answer calls with the laptop's microphone and speakers, browse real contacts, keep notifications and clipboard nearby, and bring wireless phone features into the desktop.

## Project status

**Active development — not a complete replacement for Microsoft's Windows client.**

The distinction below matters: **verified** means observed on the development devices; **implemented** means code exists but the complete user flow still needs testing; **in progress** means the feature is not ready to rely on.

## Features

| Feature | Status | What works today |
|:--|:--|:--|
| Microsoft sign-in and pairing | **Verified** | Real account authorization, device pairing and saved credentials in the system keyring. |
| Phone battery, charging, Wi-Fi and Bluetooth | **Verified** | Live phone-owned status rather than sample values. |
| Phone wallpaper preview | **Verified** | The phone's actual home wallpaper in the desktop UI. |
| Notifications | **Verified** | Real notifications received through the paired relay. |
| Text clipboard | **Verified** | Manual text transfer; received PC text was observed on the phone. |
| Bluetooth calls | **Verified** | Dial, answer and hang up through PipeWire telephony. Laptop speakers and microphone were tested. |
| Embedded dialer | **Implemented** | Calls stays inside Phone Link; a separate popup is reserved for incoming calls. |
| Contacts | **Verified** | **941 real contacts** imported from the development phone through Bluetooth PBAP. |
| Recent calls | **Verified** | **50 recent entries** returned by the phone, with real directions and timestamps. |
| Phone favorites | **Verified** | **1 real favorite** imported from the phone; matched to contacts by number. |
| Contact photos | **Implemented** | Real photo retrieval verified; lazy loading and bounded in-memory caching integrated into the contact UI. |
| Laptop status on the phone | **Verified** | Actual laptop battery and Wi-Fi appeared in Link to Windows. |
| Lock PC from the phone | **Verified** | The laptop locked and the phone displayed `Locked`. After reconnect, normal battery/Wi-Fi returned. |
| GNOME Applications companion | **Implemented** | Phone panel with wallpaper, status and shortcuts; validated in a private GNOME session. Installation requires a fresh GNOME session. |
| SMS messages | **In progress** | Read-only Bluetooth MAP helper exists; live message access has not yet succeeded. |
| Wireless photos and files | **In progress** | Native PhoneFiles metadata/thumbnail protocol identified; gallery and full file access are not yet complete. |
| Wireless screen mirroring | **In progress** | Wi-Fi connection and Linux receiver groundwork; native Microsoft streaming handshake remains incomplete. |
| Individual Android app streaming | **In progress** | Separate app-window streaming is a planned core feature, distinct from whole-screen mirroring. |
| Wireless Android webcam | **In progress** | Wi-Fi camera controller exists; virtual-camera activation and a real conferencing-app test remain outstanding. |

### Connection methods

- **Microsoft relay:** account pairing, notifications, device state and clipboard integration.
- **Bluetooth:** phone calls, contact book, recent calls and favorites.
- **Wi-Fi:** required operating transport for the planned photo/file access, screen/app streaming and webcam features. USB-only implementations do not satisfy those roadmap items.

The Linux scrcpy-based receiver work is separate from Microsoft's proprietary media transport. Initial Android debugging authorization may be needed for that receiver; it is not the same as Microsoft account pairing.

## Verified tests

Development snapshot: **8 November 2026**, Ubuntu/GNOME 51, POCO F8 Ultra.

### Observed on real devices

- Microsoft sign-in completed and pairing survived reopening the app.
- Actual wallpaper, phone status and notifications reached Linux.
- Text sent from the PC appeared in the phone's recent clipboard activity.
- A real Bluetooth call used the laptop's speakers **and** microphone.
- The phone's address book returned 941 contacts, 50 recent calls and 1 favorite.
- A real contact's JPEG photo was retrieved through PBAP.
- Phone-initiated PC locking worked. The stale Locked state was cleared, and laptop battery/Wi-Fi returned afterward.
- The application switched away from the embedded dialer after the cross-frame navigation fix.

### Automated and isolated checks

- **40 Python unit tests passed** in the development environment.
- A JavaScript regression test covers `Calls → Photos` and `Calls → Clipboard` across opaque local-file frame origins.
- The same regression test checks that incoming status/notification updates preserve the current dialer frame and typed input.
- JavaScript syntax and Python compilation checks passed.
- GNOME launcher checks covered Super, search/categories, Escape, outside-click closing, re-enable and destroyed-actor cleanup in a separate compositor.

**Still needs a real acceptance test:** the new incoming-call popup, automatic repeat lock/unlock cycles, the latest call-audio retry changes, and every wireless camera/streaming flow. Passing a protocol parser test is not proof that a phone feature works end to end.

## Installation

### Requirements

- A Linux desktop with Python 3, GTK 4 and WebKitGTK 6.
- Secret Service/keyring and systemd user services.
- PipeWire/WirePlumber with the Telephony D-Bus API, plus BlueZ/OBEX for calls and phonebook access.
- An Android phone with Link to Windows and the required permissions approved on the phone.
- NetworkManager's `nmcli` for the laptop network indicator.

The tested desktop is **Ubuntu with GNOME 51**. Older PipeWire builds may not expose the required telephony API. The optional GNOME companion is part of the accompanying Tahoe desktop integration.

```bash
sudo apt install python3-venv python3-gi gir1.2-gtk-4.0 \
  gir1.2-webkit-6.0 pipewire wireplumber bluez bluez-obexd

git clone https://github.com/slaveitgr/Phone-Link-for-Linux.git
cd Phone-Link-for-Linux
python3 install.py
```

The installer creates a **per-user** application and services. Launch **Phone Link for Linux** from Applications, sign in with Microsoft, and complete pairing in Link to Windows on the phone.

### Bluetooth configuration

Pair the phone in the Linux Bluetooth settings. Set its confirmed address in:

```text
~/.config/tahoe-phone-link/config.json
```

```json
{
  "bluetooth_address": "AA:BB:CC:DD:EE:FF"
}
```

The address is an example. Contact/message-sharing permissions are approved on the phone. No personal device address is shipped in the repository.

### Services

```bash
systemctl --user status tahoe-phone-link.service
systemctl --user status tahoe-phone-link-ui.service

tahoe-phone-link open
tahoe-phone-link calls
tahoe-phone-link clipboard
```

Closing the desktop window hides it while the user service remains available for incoming-call handling.

## Roadmap

### Reliability and release readiness

- [x] Persistent pairing and keyring-backed account storage.
- [x] Replace sample device data with real phone state and wallpaper.
- [x] Integrate the supplied Phone Link and dialer designs.
- [x] Fix navigation around the embedded dialer and preserve typed input during updates.
- [x] Read real contacts, recent calls and phone favorites.
- [x] Retrieve real contact photos and add lazy avatar loading.
- [ ] Validate the incoming-call popup with a real incoming call.
- [ ] Re-test call-audio retries and make Bluetooth media routing explicitly calls-only.
- [ ] Validate repeated lock/unlock reconnects and eliminate delayed laptop-status refreshes.
- [ ] Add reconnect controls, clearer permission states and broader distribution testing.

### Communication

- [ ] Complete real SMS reading and conversation UI.
- [ ] Add explicit user-initiated SMS replies after read access is working.
- [ ] Refresh call history reliably after completed calls.
- [ ] Improve favorite synchronization and multi-number contact selection.
- [ ] Add in-call controls and keypad tone support.

### Wireless media and desktop integration

- [ ] Receive native photo/file metadata and real thumbnails over Wi-Fi.
- [ ] Download/open original photos and transfer selected files.
- [ ] Expose the phone in the Linux file manager alongside other locations/drives.
- [ ] Make whole-screen mirroring work over Wi-Fi with explicit Start/Stop.
- [ ] Stream individual Android apps into separate desktop windows.
- [ ] Make the phone's Wi-Fi camera available as a real V4L2 webcam.
- [ ] Validate the webcam in a conferencing app and OBS.
- [ ] Complete the GNOME Applications companion integration in a fresh session.

## Architecture

```text
Link to Windows / Android
    ├── Microsoft DCG + SignalR ─── relay_service.py
    ├── Bluetooth HFP ───────────── phone_calls.py / PipeWire
    ├── Bluetooth PBAP ──────────── contacts, favorites, call history, photos
    └── Wireless media ──────────── receiver work in progress
                                      │
                         same-user private Unix socket
                                      │
                         GTK 4 + WebKit desktop UI
                         ├── embedded dialer
                         ├── incoming-call popup
                         └── optional GNOME companion
```

| Directory | Purpose |
|:--|:--|
| `src/` | Pairing, relay, desktop app, Bluetooth services and Linux integration. |
| `src/ui/` | Phone Link interface and embedded dialer. |
| `src/generated/` | Required protobuf bindings with generated notices. |
| `integration/gnome/` | Source for the Applications companion and Tahoe desktop integration. |
| `tests/` | Protocol, identity, pairing and navigation regression tests. |
| `docs/assets/` | Project branding assets. |

## Development

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src:src/generated python -m unittest discover -s tests
node tests/test_navigation.mjs
node --check src/ui/native.js
node --check src/ui/dialer/native.js
python -m compileall -q src install.py
```

GitHub Actions runs the source checks. Live-device tests are reported separately because they depend on phone permissions, Bluetooth capabilities and the desktop's audio stack.

## Data handling

- Account tokens and private keys stay in the operating system keyring.
- Contacts, messages, notification text, call records and contact photos stay in RAM.
- Temporary Bluetooth transfer files use private directories and are removed after decoding.
- The home wallpaper and nonsecret device-status cache are stored locally.
- Call audio routing is scoped to the selected phone and restores the previous microphone mute state.
- This repository excludes account exports, phone captures, private keys, device identifiers and personal phone data.

When reporting a problem, provide the relevant component and redacted error type. Keep message bodies, contact details, account tokens and personal captures out of public issues.

## Branding

The README uses the **same phone icon as the running desktop app in the dock**, supplied by the WhiteSur icon theme. [Icon attribution and license](docs/assets/ATTRIBUTION.md).

## Protocol provenance

The implementation is based on wire-format observations from user-supplied Phone Link / Link to Windows artifacts and public Linux APIs. Microsoft app packages and decompiled implementation source are not redistributed. Included generated protocol bindings retain their generated notices.

This is an **independent experimental project**, not an official Microsoft application and not a claim of complete Windows feature parity.
