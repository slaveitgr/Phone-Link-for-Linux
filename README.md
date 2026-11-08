# Phone Link for Linux

An experimental Linux desktop client for an Android phone running Link to Windows. Native GTK/WebKit desktop UI, Microsoft account pairing, a background relay, and Bluetooth HFP calling through PipeWire.

## Current implementation

- Microsoft sign-in and saved pairing, with credentials in the operating system keyring.
- Real phone battery, charging, Wi-Fi, Bluetooth and home wallpaper.
- Phone notifications and text clipboard transfer.
- Embedded Calls dialer based on the supplied HTML design. Outgoing calls stay inside the app; an incoming call opens a separate answer/reject popup.
- Real Bluetooth dial/answer/hangup and scoped routing to the laptop microphone and speakers. Speakers and microphone were verified on the development machine.
- Native contacts search, with paging and a permission-required state. Full address-book sync remains under development.
- PC battery/Wi-Fi display and phone-initiated PC lock were verified on the development machine. Automatic clearing of the phone's cached Locked indicator is being validated.
- Optional GNOME Applications companion source in `integration/gnome`.

SMS, photo sync, app remoting, full call-history sync and screen mirroring are not implemented. Incoming-call popup behavior still needs a real incoming-call acceptance test. This is independent software, not a Microsoft product.

## Install on Ubuntu/GNOME

Requires Python 3, GTK 4, WebKitGTK 6, PyGObject, Secret Service, systemd user services, PipeWire/WirePlumber, BlueZ, `wpctl`, `pw-loopback`, and NetworkManager's `nmcli`.

```sh
sudo apt install python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-webkit-6.0 pipewire wireplumber bluez
python3 install.py
```

Then launch **Phone Link for Linux** from Applications and sign in with Microsoft. Pair with Link to Windows on your phone. The phone must approve the required permissions.

For calling, pair the phone in Ubuntu Bluetooth settings and set its confirmed Bluetooth address in `~/.config/tahoe-phone-link/config.json`:

```json
{"bluetooth_address": "AA:BB:CC:DD:EE:FF"}
```

The address above is an example. There are no personal device identifiers or credentials in this repository. The PipeWire Telephony API must be available; older distributions may not provide it.

## Development

```sh
PYTHONPATH=src:src/generated python3 -m unittest discover -s tests
node --check src/ui/native.js
node --check src/ui/dialer/native.js
```

The runtime stores notifications, contacts and clipboard contents in RAM behind a same-user Unix socket. Only the received wallpaper and nonsecret device status are cached on disk. Do not commit state directories, crash logs, captures or account exports.

## Protocol provenance

The client implements wire formats observed in user-supplied Phone Link / Link to Windows artifacts. `src/generated` contains only the protobuf bindings needed by the client, including their generated notices. Microsoft application packages, decompiled implementation source, tokens, private keys and personal phone data are not distributed. Python application code and UI integration were developed for this project; the UI follows the user-supplied mockups.

GNOME integration is supplied as source because it depends on the accompanying Tahoe desktop extension. Installation of that integration is separate from the desktop client and may require a new GNOME session.
