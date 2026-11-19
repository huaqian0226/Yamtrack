# hq 定制变更

## 工作约定

hq 于 2026-11-19 确定，简单功能直接在 `my-feature` 开发。只有多个功能并行开发时才拆分功能分支，分别测试通过后合入 `my-feature`。`hq/feature-store-links` 已快进合入 `my-feature`（`1f310216`）。

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
