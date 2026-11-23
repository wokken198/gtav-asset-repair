# Notice

`gtatools` / `gtav-asset-repair` — Copyright (c) 2026 wokken198
<https://github.com/wokken198/gtav-asset-repair>

The code is MIT licensed (see `LICENSE`). In practice that means:

- **You may build on it.** A GUI, a desktop app, a fork, a wrapper that shells out
  to the CLI, or just the normal-map maths inside your own tool — all fine, no
  permission needed.
- **Keep the notice.** If you redistribute the code or a derivative, keep the
  copyright line and the MIT text. That is the only condition the license sets.
- **Link back if you can.** A one-line credit such as

  > Badge handling based on [gtav-asset-repair](https://github.com/wokken198/gtav-asset-repair)
  > by wokken198, MIT licensed.

  is not required by MIT, but it is how people find the original when they need the
  unmodified CLI, the changelog, or the known-pitfalls notes.
- **Do not imply endorsement.** Do not present a fork as an official release of this
  project, and do not ship it under the same name.
- **No game assets.** No `.dds`, `.ytd`, `.ydd`, `.ymt`, brand artwork, or Rockstar
  content is included here, and none of it is covered by this license. If you
  distribute such files, that is your own arrangement with their rights holders.

The bundled CodeWalker interop (`resources/pack_ytd.ps1`) loads `CodeWalker.Core.dll`
from the user's own CodeWalker installation; CodeWalker itself is not distributed
here and is not part of this project. `texconv` (DirectXTex, MIT) is likewise
expected to be supplied by the user.
