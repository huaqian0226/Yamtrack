# hq 定制变更

## 工作约定

hq 于 2026-11-19 确定，简单功能直接在 `my-feature` 开发。只有多个功能并行开发时才拆分功能分支，分别测试通过后合入 `my-feature`。`hq/feature-store-links` 已快进合入 `my-feature`（`1f310216`）。

## v0.26.3-hq.3 · 2026-11-20

hq 于 2026-11-20 要求为 Switch 游戏补充 IGDB 资料。Nintendo 同步按 `source`、`media_type` 和 `media_id` 匹配条目，省略 `source` 时沿用 `manual`。新建 IGDB 条目优先使用 IGDB 标题和封面，查询失败时使用 Nintendo 导出资料。现有 Switch 条目由操作员原地迁移至 IGDB，保留 `Item.id` 和关联的 `Game` 行，并更新批准映射。双平台持有同一游戏时，Switch 记录保留为独立的 `manual` 条目。

Nintendo 同步遇到已有非 Nintendo 管理记录的 IGDB 条目时会回滚整批，并在命令行指出冲突游戏。Steam 覆盖同步识别到 Nintendo 同步历史时会跳过该游戏的时长和状态更新，显示警告并继续处理其他游戏。

**部署状态：** 2026-11-20 已上线。迁移前做 SQLite 在线备份并核对；14 个 Nintendo Item 在一个事务里原地改为 IGDB 来源（item.id 不变，Game 与列表关系逐字段核对一致），删除一个无关联的空 manual 条目。生产更新已挂载的 `overrides/steam.py`（sha256 `81996087…`）和宿主 `nintendo-export/` 两个脚本，compose 未改；重建应用容器、清 `igdb_game_*` 缓存。之后 Nintendo 同步 dry-run 和正式运行都是 0 新增、14 款无变化。旧 `/details/manual/game/...` 网址不做跳转（hq 确认不需要）。

| 变更文件 | 用途 |
|---|---|
| `workbench/nintendo-export/sync-yamtrack.py`、`workbench/nintendo-export/yamtrack_import.py` | 传递并验证批准映射的来源，支持 IGDB 资料及跨平台冲突保护。 |
| `src/integrations/imports/steam.py` | 覆盖同步时保护 Nintendo 管理的记录，提示将 Switch 记录保留为独立条目。 |
| `src/integrations/tests/imports/test_nintendo.py`、`src/integrations/tests/test_steam_update.py` | 用模拟数据验收两种来源、事务回滚、预览及 Steam 覆盖保护。 |
| `HQ-CHANGES.md`、`workbench/README.md`、`workbench/nintendo-export/approved-games.example.json` | 记录版本、部署步骤和可选的 `source` 字段。 |

### 部署到锁定镜像

1. 将 `workbench/nintendo-export/yamtrack_import.py` 和 `workbench/nintendo-export/sync-yamtrack.py` 复制到 `<PROJECT>/工作台/nintendo-export/`。
2. 将 `src/integrations/imports/steam.py` 复制到 `<PROJECT>/工作台/yamtrack/overrides/steam.py`，复用现有只读挂载。
3. 在 `<PROJECT>/工作台/yamtrack/` 重建 Yamtrack 应用容器。

   ```sh
   docker compose up -d --no-deps --force-recreate yamtrack
   ```

4. 操作员将可迁移的 Switch 条目原地改为 `source=igdb` 和对应的 IGDB `media_id`，并同步更新 `approved-games.json`；双平台重叠的 Switch 条目保留独立的 `manual` 映射。运行 Nintendo 预览核对映射和冲突提示后，再执行正式同步。

## v0.26.3-hq.2 · 2026-11-19

游戏详情页将商店按钮放在页面顶部的游戏标题正下方、海报上方。Steam、Nintendo eShop、Epic Games Store 和 GOG 按钮按已有链接显示，在新标签页打开。仅有 `Item` 的条目也适用，原有 `Details → Links` 保留。

**部署状态：** 2026-11-19 已上线。生产新增只读覆盖 `overrides/media_details.html`（sha256 `d1d6d002…`），重建应用容器后验证：Loftia 显示 Steam、Epic Games Store，马力欧惊奇显示 Nintendo eShop，电影和剧集页无按钮。起因：hq.1 的链接只出现在左栏 Details 卡片底部的 Links 小字行，hq 在浏览器里没注意到。

| 变更文件 | 用途 |
|---|---|
| `src/templates/app/media_details.html` | 游戏标题下方新增可换行的商店按钮，沿用已编译的样式。 |
| `src/app/tests/views/test_media_details.py` | 验证已有追踪记录和仅有 `Item` 的游戏，以及 TMDB 电影和剧集的链接渲染。 |
| `HQ-CHANGES.md`、`workbench/README.md` | 记录版本、部署方式和分支工作约定。 |

### 部署到锁定镜像

在 `v0.26.3-hq.1` 已部署的基础上，将此版本的 `src/templates/app/media_details.html` 复制到生产 Compose 目录下的 `overrides/media_details.html`，在 `services.yamtrack.volumes` 中追加只读挂载。

```yaml
- ./overrides/media_details.html:/yamtrack/templates/app/media_details.html:ro
```

重建 Yamtrack 应用容器使挂载生效。复用 `v0.26.3-hq.1` 的商店链接数据和镜像内已编译的 CSS。

## v0.26.3-hq.1 · 2026-11-19

基线为上游 `v0.26.3` 加 `my-feature` 的既有定制（`76a4e99f`）。开发分支为 `hq/feature-store-links`。这是源码定制版本，运行镜像仍为锁定的上游 `v0.26.3`。

**部署状态：** 2026-11-19 已上线。生产以只读覆盖 `overrides/igdb.py` 挂载本版本的 `src/app/providers/igdb.py`（sha256 `85abef9d…`），重建应用容器并清除 `igdb_game_*` 缓存后验证通过。

游戏详情页的 `Links` 区块展示 IGDB 提供的 Steam、Nintendo eShop、Epic Games Store 和 GOG 商品链接。每个商店优先使用 IGDB `websites` 中首个可识别的地址。没有 Steam 商店地址时，用 `external_games` 中 Steam 来源的数字 `uid` 生成 Steam 商品地址。只有 `Item` 的待买、待问条目也可显示这些链接。现有 `Provider` 区块仍显示 IGDB 链接，电影和剧集沿用原有 TMDB 链接。

| `src/` 下的变更文件 | 用途 |
|---|---|
| `src/app/providers/igdb.py` | 查询、解析并缓存游戏商店链接。部署时新增这一项覆盖。 |
| `src/app/tests/mock_data/metadata_game_igdb.json` | 模拟游戏元数据及商店链接。 |
| `src/app/tests/providers/test_metadata.py` | 验证网站优先、Steam 回退、无链接及缓存命中。 |
| `src/app/tests/providers/test_search.py` | 现有 IGDB 搜索测试改用模拟响应。 |
| `src/app/tests/views/test_media_details.py` | 验证仅有 `Item` 的游戏详情页及现有 TMDB 外链渲染。 |

### 部署到锁定镜像

1. 在生产 Compose 目录 `<PROJECT>/工作台/yamtrack` 下，将该版本的 `src/app/providers/igdb.py` 复制成 `overrides/igdb.py`。在 `docker-compose.yml` 的 `services.yamtrack.volumes` 中补一条只读挂载。

   ```yaml
   - ./overrides/igdb.py:/yamtrack/app/providers/igdb.py:ro
   ```

2. 在同一目录执行以下命令。第一条仅重建应用容器。第二条只删除 Django 的 IGDB 游戏详情缓存键，使下次打开详情时重新获取商店链接。也可以等旧条目按配置自然过期，默认最长 24 小时。

   ```sh
   docker compose up -d --no-deps --force-recreate yamtrack
   docker compose exec -T yamtrack python manage.py shell -c 'from django.core.cache import cache; print(cache.delete_pattern("igdb_game_*"))'
   ```

3. 打开已有游戏和仅有 `Item` 的待买或待问条目，核对 `Links` 中有来源数据的商店链接及 `Provider` 中的 IGDB 链接。升级上游镜像时重新核对覆盖文件和对应测试。
