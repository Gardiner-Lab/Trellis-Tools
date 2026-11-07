#!/usr/bin/env bash
# Copies Trellis Tools' look - design/trellis.css, the tool switcher (design/modules.js) and the
# icons - into each module checked out beside the suite (app/static/trellis/), so every module
# looks the same, also on its own.
# Run after changing design/trellis.css or the icons: ./design/sync.sh, then release the modules.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
parent="$(dirname "$here")"
# The suite's own pages (the sign-in service serves them at /account/trellis.css).
cp "$here/design/trellis.css" "$here/portal/pages/trellis.css"
for repo in moclo-library-tool plasmid-editor lab-notebook seed-bank lab-stocks lab-booking genome-browser; do
    # The Genome Browser keeps its assets in static/ at the top of the repository.
    if [ "$repo" = genome-browser ]; then base="$parent/$repo"; else base="$parent/$repo/app"; fi
    dir="$base/static/trellis"
    if [ ! -d "$base" ]; then echo "skipped $repo: not checked out beside the suite"; continue; fi
    mkdir -p "$dir"
    cp "$here/design/trellis.css" "$here/design/modules.js" "$here/portal/pages/trellis.svg" "$dir/"
    cp "$here"/portal/pages/icons/*.svg "$dir/"
    mkdir -p "$dir/glyphs" && cp "$here"/portal/pages/glyphs/*.svg "$dir/glyphs/"
    echo "synced $repo"
done
