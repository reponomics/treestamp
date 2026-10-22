# Bundled fonts

## IBM Plex

Unmodified complete WOFF2 files from [IBM/plex](https://github.com/IBM/plex/tree/763c36ef9117782905ae010056dfbe8fd2653a25), pinned to commit `763c36ef9117782905ae010056dfbe8fd2653a25`. IBM Plex Sans supplies the interface text; IBM Plex Mono supplies repository paths and tree output. Regular and SemiBold are the 400 and 600 weights.

The files are served locally; there is no runtime font service or build dependency. The bundled [SIL Open Font License 1.1](OFL.txt) is copied from the same upstream commit.

| File | Upstream source | Size (bytes) |
| --- | --- | ---: |
| `IBMPlexSans-Regular.woff2` | [packages/plex-sans/fonts/complete/woff2/IBMPlexSans-Regular.woff2](https://raw.githubusercontent.com/IBM/plex/763c36ef9117782905ae010056dfbe8fd2653a25/packages/plex-sans/fonts/complete/woff2/IBMPlexSans-Regular.woff2) | 63,020 |
| `IBMPlexSans-SemiBold.woff2` | [packages/plex-sans/fonts/complete/woff2/IBMPlexSans-SemiBold.woff2](https://raw.githubusercontent.com/IBM/plex/763c36ef9117782905ae010056dfbe8fd2653a25/packages/plex-sans/fonts/complete/woff2/IBMPlexSans-SemiBold.woff2) | 67,060 |
| `IBMPlexMono-Regular.woff2` | [packages/plex-mono/fonts/complete/woff2/IBMPlexMono-Regular.woff2](https://raw.githubusercontent.com/IBM/plex/763c36ef9117782905ae010056dfbe8fd2653a25/packages/plex-mono/fonts/complete/woff2/IBMPlexMono-Regular.woff2) | 49,248 |
| `IBMPlexMono-SemiBold.woff2` | [packages/plex-mono/fonts/complete/woff2/IBMPlexMono-SemiBold.woff2](https://raw.githubusercontent.com/IBM/plex/763c36ef9117782905ae010056dfbe8fd2653a25/packages/plex-mono/fonts/complete/woff2/IBMPlexMono-SemiBold.woff2) | 50,600 |

SHA-256 checksums:

```text
ba711a3085ff9f27440b6b9c4550cfc47c97bf36591d5da958b975bb3add8c1a  IBMPlexSans-Regular.woff2
f78048030eab62e860efa39a0df79e2e5581bf122eb95b9bc42c0b8a4988d205  IBMPlexSans-SemiBold.woff2
ba204497f16b6d334cee9d1e963a831b73e3a56e1d6300a8489d18df7214b350  IBMPlexMono-Regular.woff2
6a825b4824c01cbb401e829e5a066a1818411bcb3538b5a5792c5ca9b82343c3  IBMPlexMono-SemiBold.woff2
```

## Reponomics wordmark

`Inter-Black-wordmark.woff2` is a 1,996-byte Inter Black (900) subset containing only the characters in `reponomics.`. It follows the lowercase, tightly spaced mark in the [Reponomics brand styles](https://reponomics.org/colors_and_type.css). The rest of the interface continues to use IBM Plex.

The subset was supplied by [Google Fonts](https://fonts.googleapis.com/css2?family=Inter:wght@900&text=reponomics.&display=swap), from its [version 20 WOFF2 asset](https://fonts.gstatic.com/l/font?kit=UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuBWYMZ1rib2Ai-7mcx_ufO4nQQlPwlo&skey=c491285d6722e4fa&v=v20), and is served locally. [Inter-OFL.txt](Inter-OFL.txt) contains the SIL Open Font License from the [Google Fonts Inter distribution](https://github.com/google/fonts/tree/main/ofl/inter).

SHA-256: `685d6112a28c158135598c788e538e7b08be1b5a725fa4990feb423d217753be`.
