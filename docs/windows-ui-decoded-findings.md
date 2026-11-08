# Original Windows UI: decoded layout evidence

Static analysis of the supplied Phone Link x64 MSIX, 8 November 2026.

## Recovery result

The locally built upstream `chausner/XbfTools` converter successfully converted **262 of 263** bounded XBF payloads embedded in `resources.pri` to XAML-like trees. The single failed payload starts at PRI offset `416104`. The previous conclusion that the layout was available only as string candidates is superseded for the 262 successful files.

Files remain private local analysis material under `windows-ui-private/xaml/`. Full conversion results are in `windows-ui-private/decode-all-results.json`; the resource/style/class index is `windows-ui-private/decoded-resource-index.json`. Input hashes, decoder revision and selected facts are recorded in `original-ui-layout-tokens.json`.

## Directly recovered structure

`402932.xaml` is `YourPhone.Shell.TopNavShell`. It defines a left **device + notifications pane** and a **horizontal top feature navigation** over the main content. This differs structurally from the current Linux layout, which puts every feature in a left navigation list. The original SplitView style uses 360 logical pixels when open, 40 when compact. The top navigation uses a 36-pixel top margin in inline/overlay states. The content grid has zero padding; individual feature views own their padding. States include Hidden, Collapsed, Overlay, Inline and Takeover. This static resource does not prove every Windows instance currently selects this shell: feature flags and viewmodels determine runtime selection.

`1473232.xaml` supplies application typography and sizing:

| Resource | Recovered value |
| --- | --- |
| AppNavPaneMediumWidth | 320 |
| AppPrimaryPaneMinWidth | 380 |
| Secondary pane min / medium / XL | 320 / 400 / 600 |
| AppWindowSmallWidth | 820 |
| AppTitleTextBlockStyle | 28, SemiBold |
| AppTitleLargeTextBlockStyle | 40, inherits SemiBold |
| AppSubtitleTextBlockStyle | 20, SemiBold |
| AppBodyTextBlockStyle / Strong | 14 Normal / 14 SemiBold |
| AppCaptionTextBlockStyle | 12 Normal |
| AppDisplayTextBlockStyle | 68 SemiBold |

`1355108.xaml` is the dark theme resource dictionary. It gives navigation #3B3B3B, primary pane #2B2B2B, secondary pane #333333 and content background #242424. These are distinct surfaces, rather than one invented translucent panel color. Accent brushes reference the Windows system accent and should not be treated as a fixed hardcoded blue.

`1036136.xaml` DeviceView gives image max-height 90, wide max-width 214, compact image 28×52, and the text/status column padding 24 on its left. Status indicators in `1048488.xaml` use 16-pixel glyphs, 4 spacing, and a separate semibold percentage label. Device quick actions in `1062232.xaml` have height32, radius4, glyph16, 12-pixel grid gaps and top-margin24.

`423932.xaml` defines top navigation item styles: minimum height40 and icon-box margin12 horizontally. Selected/hover/pressed/disabled combinations have separate resources and selected indicator states.

## Calls and photos

`1161572.xaml` CallingView has explicit DialConfirmationState, MiniActiveState, MiniCompactState and ActiveState. Mini/confirmation panels are width500 with padding12; contact visuals are80×80; action buttons40×40 with radius20, spaced40; expanded call min-width476, compact min-width320. These states must not be collapsed into one fake call screen.

`1185604.xaml` Keypad has 8-pixel row/column gaps and a48×48 call button. The call icon is glyph U+E717; secondary letters use size9 (`1184236.xaml`). Other action glyphs reference either the bundled MMX font or Windows SymbolThemeFontFamily; mapping all symbols to generic SVGs will not be visually identical.

`581292.xaml` MediaGalleryView defines actual FlipView, previous/next buttons and command bar. The content margin for its empty/error content is40,80,40,40, and navigation arrows occupy width114. `567736.xaml` MediaView is a separate resource from the full viewer. The current Linux modal is an intermediate design and requires reconstruction against these resources.

## Verification boundaries

The XbfTools upstream README explicitly says its parser is research software and the converted XAML may differ from original source. Some converted aliases are visibly questionable, and resource references/data bindings remain runtime-dependent. Recovered numeric values and tree relationships provide much stronger evidence than string scans, but **do not establish pixel identity or user interaction parity**. Matching Windows runtime screenshots at the same scale and state are still needed for final visual acceptance.

No target Windows executable was run. No live Linux UI/runtime changes were made by this investigation. Proprietary converted trees/assets remain private and are not automatically suitable for redistribution.
