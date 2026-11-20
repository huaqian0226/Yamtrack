# Personal workbench customization

## Branch ownership

`main` 对应上游稳定分支 **release**，初始版本为 `v0.26.3`（`76856f9e053e7f59469d1eac0238727263e2adfd`）。上游默认分支为 **dev**。**my-feature** 保存去除个人配置后的界面和同步定制。生产仍使用锁定的官方镜像及本地覆盖文件，源码发布与生产部署分别执行。

### 工作约定

hq 于 2026-11-19 确定，简单功能直接在 `my-feature` 开发。只有多个功能并行开发时才拆分功能分支，分别测试通过后合入 `my-feature`。`hq/feature-store-links` 已快进合入 `my-feature`（`1f310216`）。

## What is included

- 游戏详情页在标题下方显示商店按钮。版本、文件清单和部署步骤见 [hq 定制变更](../HQ-CHANGES.md)。
- Workbench navigation and named external tabs; local COOP adjustment.
- Games title-row combined Steam/Nintendo sync button and separate result panel.
- Authenticated, CSRF-protected queue endpoints; Steam uses the native import task.
- Steam imports add successfully matched, tracked games to the owner’s `已有游戏` list, including unchanged games on retries. Other lists, notes and scores are preserved; no membership is removed. This applies to scheduled and manual imports.
- Nintendo Go v0.1.1 导出与授权工具、伦敦时间每日 08:00 补跑和测试。批准映射可选 `source`（默认 `manual`，也支持 `igdb`），同步以事务更新时长。Steam 和 Switch 同时持有的游戏使用独立的 Switch `manual` 条目，两端同步均保护既有记录。
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
