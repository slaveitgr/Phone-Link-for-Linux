# Original Windows UI analysis

The initial package inventory has been superseded by [decoded XBF findings](windows-ui-decoded-findings.md). We recovered 262 of 263 compiled layouts. [Measured layout tokens](original-ui-layout-tokens.json) record exact source coordinates and known limits.

The reconstructed TopNavShell uses a 360px device/notification pane, horizontal navigation, actual device wallpaper, 90px maximum phone image, Segoe UI typography and the decoded dark theme palette. This is a measured reconstruction; it is not yet a claim of pixel identity with a running Windows client.

Original fonts from the developer’s supplied Windows media are installed locally for comparison. They and the extracted Microsoft XAML/font assets are not distributed in this repository.
