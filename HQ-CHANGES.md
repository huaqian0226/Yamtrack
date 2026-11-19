# hq 定制变更

## v0.26.3-hq.1 · 2026-11-19

基线为上游 `v0.26.3` 加 `my-feature` 的既有定制（`76a4e99f`）。分支为 `hq/feature-store-links`。这是源码定制版本，生产部署待执行，目标镜像仍为锁定的上游 `v0.26.3`。

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
