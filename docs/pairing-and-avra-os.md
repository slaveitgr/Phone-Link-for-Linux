# Pairing bootstrap and Avra OS integration

## Missing step in the earlier repository

The earlier `phone_app.py` rendered an existing `pairing_session.pairingLink`
and polled it, but stopped after CreateIdentity on a fresh installation.
Enrollment and session creation had been run from local development scripts
(`enroll_live.py` and `create_pairing_live.py`) which were not shipped.
An already-paired development machine concealed this missing first-run path.
`src/pairing_bootstrap.py` now connects these steps to first sign-in and to
restoration of an authorized account without a pairing session.

## Complete sequence

1. `msa_oauth.MsaLogin`: interactive Microsoft authorization and callback exchange.
2. `DeviceIdentity` and `IdentityService.create_identity`: nonce, certificate proof,
   then a device access token. The MSA and device tokens are distinct.
3. `DeviceService.enroll`: POST `/DeviceAuthProxy/EnrollDevice?api-version=1.5.0`.
   Save the response and the separate trust certificate/private key in Secret Service.
4. `PairingService.create_session`: POST
   `/DevicePairingProxy/PairingSessions?Api-Version=3.0.0`, MSA authorization,
   JSON `{"flow":"QRLINK_CHALLENGEPIN_SIGNIN","optionalPermission":["ALL"]}`.
5. Save the server response, including `pairingSessionId` and `pairingLink`.
   **Encode the server-issued pairingLink verbatim**, using `qrcode` and
   `SvgPathFillImage`. Do not construct a link from a hostname, MAC or device ID.
   `PhoneApp.show_pairing` writes a user-private `pairing-qr.svg` and displays it.
6. Scan with Android Link to Windows; approve account/device permissions.
7. `PhoneApp.poll_pairing` polls GET of the session every three seconds;
   on `READY_FOR_COMPLETE`, POST `<session-id>/Complete`;
   only `DEVICE_PAIRED` means successful pairing. Show challenge PIN if returned.
8. Save completion, remove the QR SVG, and allow `relay_service` to connect.
   Displaying a QR, Microsoft sign-in, and an active relay are separate states.

## Avra OS requirements

Package Python dependencies from requirements.txt (including qrcode), GTK4,
WebKitGTK6, a running Secret Service with an unlocked user keyring, a user
D-Bus session and the relay/UI user services from install.py. Never bake the
development machine's keyring, tokens, certificates, QR or pairing session into
an OS image. Each user must sign in and authorize their own phone.

An Avra frontend can call `prepare_pairing(account, identity, persist, ...)`
in a worker thread after interactive authorization. `persist` must securely
save the supplied account and report success. Render the returned pairingLink;
port the polling/completion behavior from phone_app.py. Pass `display_name`
for Avra branding. Region is optional; do not assume the user's country is GR.
The existing installer remains per-user, not a distro packaging recipe.

## Validation and limits

The existing development phone was paired using the local scripts. The new
bootstrap wiring has offline regression coverage; a fresh-account end-to-end
pairing on Avra OS still needs validation. Microsoft private service acceptance
and token expiry are external dependencies. Restored expired credentials need
authorization/refresh before calling the bootstrap. A process failure between
a server POST and secure persistence can leave an orphaned server registration;
this helper does not promise transactional or exactly-once remote operations.
Do not reset an existing working phone pairing just to test installation.
