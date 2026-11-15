# Personal workbench customization

## Branch ownership

`main` is an unmodified mirror of upstream **release**, initially v0.26.3 / 76856f9e053e7f59469d1eac0238727263e2adfd. Upstream's default branch is **dev**, not main. Keep local changes only on **my-feature**. This branch contains the deployed UI and sync implementation, with personal configuration removed. The running installation still uses the pinned official image plus local mounts; publishing this branch does not deploy a newer image.

## What is included

- Workbench navigation and named external tabs; local COOP adjustment.
- Games title-row combined Steam/Nintendo sync button and separate result panel.
- Authenticated, CSRF-protected queue endpoints; Steam uses the native import task.
- Nintendo Go v0.1.1 export/auth helper; transactional minute-only import with stable platform/title mapping; daily London 08:00 catch-up runner and tests.
- Private online backups and a Steam-key input helper.

Set WORKBENCH_USER and STEAM_USER_ID in the private environment. Set optional navigation URLs. No account IDs, API keys, tokens, cookies, owned-game mappings, databases, knowledge-base content or actual machine paths are committed. Copy approved-games.example.json to approved-games.json and explicitly approve titles before importing. Preserve an existing custom ID when adopting an already tracked game.

## Runtime layout

The workbench compose example builds this branch. Populate private .env and existing database before using it. Keep Nintendo private/ on the host, mounting only private/bridge into Yamtrack. Build the Go helper for the host architecture into nintendo-export/bin/nintendo-export. Set up a local launchd job to invoke scheduled-sync.py every 30 seconds (RunAtLoad true): the runner checks London time and pending requests, and only calls Nintendo when due/requested. Use absolute paths appropriate to your machine; do not reuse another person's launch configuration. The native Steam daily import must be configured separately in Yamtrack. macOS, Docker and a running Yamtrack are prerequisites.

## Updating with GitHub

1. Open a PR in your fork: **base main**, compare **FuzzyGrim/Yamtrack:release**. Merge only upstream stable changes; do not merge personal changes into main.
2. Open a second PR in your fork: **base my-feature**, compare **main**. Resolve conflicts and run checks, then merge. Preserve history instead of force-pushing or resetting the feature branch.
3. Build/test the merged feature branch against a copy of the database, back up production, and only then deploy deliberately. GitHub merges do not restart the live workstation.

GitHub's default Sync fork may track dev; do not treat syncing dev as upgrading the stable workbench. Use these comparisons:

- [Upstream stable → main](https://github.com/huaqian0226/Yamtrack/compare/main...FuzzyGrim:Yamtrack:release)
- [main → my-feature](https://github.com/huaqian0226/Yamtrack/compare/my-feature...main)

Do not enable release/publishing workflows merely to sync code. Keep main as the default branch and use my-feature when browsing or building personal changes.
