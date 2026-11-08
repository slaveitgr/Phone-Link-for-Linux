# Original Windows Phone Link UI: reconstruction findings

Inspected 2026-11-08. Static inspection only; no Windows executable was run.

## Identity and evidence

The supplied `Microsoft.YourPhone_1.26101.114.0_neutral_~_8wekyb3d8bbwe.AppxBundle`
contains `YourPhone.Package_1.26101.114.0_x64.msix`. Its SHA-256 exactly matches
the existing local `PhoneLink-x64.msix`:
`a36dbac4826a713509cfe5a0eeacad545357bd3dfd0de53c4004c51f30d64f1b`.
The bundle also has an x64 stub, which is a different target.

REA inventory parent Evidence:
`ev_5cc4b56f653258e979cbb20eaeeacfe23ef1047187a423c60f8eb178b622471e`;
summary `ev_2022eefc6bf902601d5f2f367da724ff0ac9b478702b5160fa4bcb646be7bd79`.
The inventory covers 1,383 central-directory members, with zero integrity
contradictions. Python ZIP inventory independently counted 493 SVG, 471 PNG,
258 DLL and 53 PRI entries. There are no standalone HTML/CSS/JS/XAML/XBF
members in this x64 package.

`YourPhone.Shell.dll` is .NET 10 CIL plus ReadyToRun, assembly version
1.26101.114.0, SHA-256
`047fa9a794264ef252925a96e29c6ce435407a6723478bd585ecd786b2ea2a87`,
MVID `8e1d1292-ab12-48f3-a85f-803ec5bb839e`.
Managed artifact Evidence parent
`ev_5b9d5bf27569d70ad30c059496097e21c118dcb1961632eace0ffb7afc9176ae`.
Managed member Evidence parent
`ev_f467d53c781392911897147a94d983179533a7827951d653f982acddf61083ac`;
type inventory view `ev_456b2256aa3b7cc20981ccc0cf760d9fb0e499e60f2e4e4c7363bced1a24d46c`.
It contains MainWindow, DedicatedWindowShell, TopNavShellViewModel,
TopNavMenuViewModel and NavigationViewEx types. Thus this shipped build has
multiple shells; an old screenshot does not alone identify the selected one.

## What can already be recovered faithfully

The Start companion is directly described by parseable Adaptive Card 1.5 JSON:
`Assets/StartMenu/DeviceCardTemplate.json` and `DeviceCardTemplateL2.json`.
These are layouts, not screenshots or guessed labels. The normal card declares:

- Centered ImageSet with the actual `wallpaperUrl` underneath `deviceFrameUrl`;
  clipping margin/corner radius come from device data. The normal device frame
  has explicit height 54px. Device picture is clickable using a launch action.
- Centered bold device name, conditional on a real nonempty name.
- Separate connectivity, Bluetooth and battery indicators. Actionable variants
  and passive variants have distinct visibility conditions. Indicator glyphs
  are 16px; connectivity/Bluetooth cells are 32px square. Passive battery has
  16px icon width, 4px gap and a separate actual percentage string.
- A scrollable features area: 12px outer columns, 16px feature glyphs, 8px item
  spacing and 4px list corner radius. Labels and launch targets are data-bound.
- Recent activity entries use 32px images, 12px gap and a minimum 38px text
  column. Person imagery is conditionally circular. Empty-state wording is
  separately data-bound. Actions are not hardcoded in the template.

These exact layout rules are a strong reference for our Applications companion.
The L2 variant is a separate template and must not be blended into the normal
one without deciding which version is the target.

## Main desktop UI resources

`resources.pri` has `mrm_pri2` header and 263 embedded `XBF\0` header candidates.
The adjacent bounded payloads contain WinUI namespaces, resource keys and view
class names. The existing tooling does not decode XBF node streams into a full
XAML tree. String candidates therefore identify follow-up targets, not final
pixel dimensions or runtime behavior.

Useful candidate offsets in this exact PRI:

| Offset | Component anchors | What is established |
| --- | --- | --- |
| 1030148 | LiteDeviceView, Small, LargeCompact, DeviceImage, PhoneNameGrid, DeviceSelectorComboBox | Compact and expanded device representations have explicit separate visibility states. |
| 1044732 | DeviceStatusTitleBarView, Connected, ConnectedBluetooth, Connecting, Refreshing, Disconnected | Connection presentation has multiple states and themed status glyph brushes. |
| 1048488 | DeviceStatusIndicatorsView, BatteryUnknown, BatteryPercent, ItemsRepeater, StackLayout | Battery unknown is distinct from a reported percentage; indicators use a repeated layout. |
| 1161572 | CallingView, DialConfirmationState, MiniActiveState, MiniCompactState, ActiveState | Calls have distinct confirmation, expanded and compact states, contact visuals and independent action panels. |

Call resource anchors include ContactVisual, DialConfirmationContactVisual,
MiniCallContactVisual, ExpandedPrimaryPhoneCall, Mute, Keypad, Hold, Resume,
End and Transfer controls. These prove structured call-state views, not that all
actions are supported by our Linux backend. The UI must expose only actions
backed by actual protocol support.

Resource-name candidates also include ChatConversationView, ConversationListView,
ConversationHeaderView, MessageComposer, MessageContactPhoneNumberPicker,
ContactDetailsView, PhotosFullPermissionDialog, MainWindow, SingleNodeShell,
TopNavShell and DedicatedWindowShell. Names are saved locally in
`windows-ui-private/xbf-resource-names.json`; candidate strings and offsets in
`windows-ui-private/xbf-candidates.json`.

## Implementation path and limits

1. Keep the current real-data bridge and transport controllers; replace only
   presentation components. Do not replace working integration with static UI.
2. Recreate the Start companion from the normal card's semantic structure and
   explicit measurements, binding our own real device and recent activity data.
3. For the desktop shell, decode the relevant PRI/XBF resource tree or obtain
   same-version Windows runtime screenshots at controlled scale. Match the
   chosen shell, font metrics, spacing, states and responsiveness against those.
4. Reconstruct calls as explicit state views: selected contact, outgoing,
   incoming, active, held and disconnected. Preserve the product requirement
   that only incoming calls automatically create a popup.
5. Recreate icons/controls within our asset system. Extracted Microsoft resource
   files are private analysis material and are not copied into public source.

The package gives substantially better evidence than generic screenshots, but
it is not a ready-to-run Linux UI. GTK/WebKit cannot directly instantiate these
WinUI/Windows Runtime controls. A claim of 100% visual identity is not yet
supported: exact XBF tree decoding, font rendering, dynamic feature flags,
responsive breakpoints and same-version runtime comparison remain unresolved.

Selected original resources were copied only into `windows-ui-private/` for
local analysis. No app source, installed runtime or public repository was edited.
REA archive session was closed after inspection.
