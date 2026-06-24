# YouTube 新闻媒体视频评论提取工具

提取指定标题的 YouTube 视频下的评论，**限定为新闻媒体频道发布的视频**（剔除个人博主发布的视频），并自动过滤广告/推销类评论。

## 功能特性

- 按标题关键词搜索视频，默认限定在 YouTube「新闻和政治」分类下搜索
- 自动判断视频发布频道是否为新闻媒体（基于频道名称/简介关键词、订阅数门槛、白名单/黑名单，均可自定义）
- **按媒体（频道）分组去重**，自动取订阅数最高的 N 家媒体（`--media-count`，默认 5，建议 3-10），候选不足时按实际数量输出
- 媒体频道订阅数 < 10万（`--min-subscribers`）或视频评论数 < 100（`--min-video-comments`）直接忽略
- **同一家媒体最多取 M 个视频**（`--videos-per-media`，默认 3），按热度（播放量优先、评论数次之）从高到低选取；媒体数与每家视频数互不冲突——可能某家媒体凑满 3 个，另一家只有 1 个
- **标题相关度过滤**（`--min-title-similarity`，默认 0.5）：剔除搜索结果中标题和关键词不相关的跑题视频
- 拉取指定数量评论（默认 200 条，可调，建议 200-300），`--count 0` 可拉取该视频全部评论
- 自动过滤广告/推销类评论（外链、联系方式、刷粉兼职等关键词），规则存于可编辑的 `ad_patterns.txt`，改规则不用改代码
- **跨视频去重**：同一作者在不同视频下发的完全相同评论（常见刷屏/广告号特征）只保留一条，默认开启（`--no-dedup-filter` 关闭）
- **情感分析**（`--sentiment`，可选）：调用 DeepSeek API 为每条评论标注「正面/负面/中性」
- 单个视频已关闭评论功能时自动跳过，不中断整体流程
- 结果导出为 CSV 或 JSON（多视频/多媒体合并为一个文件，含 `video_id`/`video_title`/`channel_title` 区分来源），同时生成统计摘要（按媒体分布、平均点赞数、高频词 Top20）
- 不带参数运行会进入**引导式输入**，逐项询问关键配置并二次确认，适合非命令行用户

## 目录结构

```
youtube-news-comment-extractor/
├── main.py             # 命令行入口
├── youtube_client.py   # YouTube Data API v3 调用封装
├── filters.py          # 新闻媒体频道判定、标题相关度、广告评论过滤、跨视频去重
├── sentiment.py        # DeepSeek 情感分析（可选功能）
├── summary.py          # 结果统计摘要（媒体分布、高频词）
├── ad_patterns.txt     # 广告评论过滤正则规则（可直接编辑，无需改代码）
├── requirements.txt
├── .env.example        # 环境变量模板，复制为 .env 并填入自己的 API Key
└── output/             # 默认结果输出目录（已加入 .gitignore，不会提交）
```

## 准备工作

1. 申请一个 **YouTube Data API v3** 密钥：[Google Cloud Console](https://console.cloud.google.com/) → 创建项目 → 启用 `YouTube Data API v3` → 创建 API 密钥
2. （可选）如需使用情感分析功能，申请一个 [DeepSeek](https://platform.deepseek.com/) API 密钥
3. 复制环境变量模板并填入自己的密钥：

```bash
cp .env.example .env
# 编辑 .env，填入 YOUTUBE_API_KEY（必填）和 DEEPSEEK_API_KEY（可选）
```

> `.env` 已加入 `.gitignore`，不会被提交到仓库，放心填写真实密钥。

## 快速开始

```bash
git clone <你的仓库地址>
cd youtube-news-comment-extractor

# 推荐用 uv（https://github.com/astral-sh/uv）
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 或者用普通 venv + pip
# python3 -m venv .venv && source .venv/bin/activate
# pip install -r requirements.txt

cp .env.example .env   # 填入你的 API Key

uv run main.py --title "某新闻视频标题关键词" --count 250
# 取 5 家头部媒体（默认），每家最多 3 个最热视频，各拉 250 条评论
```

> **注意：依赖装在 `.venv` 虚拟环境里，不在系统 Python 里。**
> 直接用系统 `python3 main.py` 运行会报 `ModuleNotFoundError`（找不到 `httplib2` 等依赖）。
> 之后每次运行，二选一即可：
> - 先 `source .venv/bin/activate` 激活环境，再 `python3 main.py`
> - 或直接用 `uv run main.py`（无需手动激活，自动用项目环境）

## 使用方式

### 引导式输入（推荐新手）

不带任何参数直接运行，会逐项询问关键配置，最后展示汇总并二次确认；输入「否」可重新输入：

```bash
uv run main.py
```

依次询问：标题关键词、媒体家数、每家媒体视频数、媒体最低粉丝量、视频最低评论数、每视频评论拉取数（全部/具体数字）、是否过滤广告、输出路径。其余高级参数（白名单/黑名单、关键词扩展、排序方式等）仍只能通过命令行参数指定，引导模式使用默认值。

### 命令行参数模式（适合脚本化/批量调用）

```bash
uv run main.py --title "关键词" --count 200
```

只要带上 `--title`（或 `--video-id`），就直接按参数执行，不会进入引导式输入。

### 常用参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--title` | 视频标题关键词（必填） | - |
| `--count` | 每个视频目标提取评论数，`0` 表示拉取全部 | 200 |
| `--search-results` | 标题搜索返回的候选视频数（候选池越大，越容易凑够多家媒体） | 30 |
| `--media-count` | 取多少家不同媒体（频道去重），按订阅数从高到低取头部媒体；候选不足时按实际数量输出 | 5 |
| `--videos-per-media` | 同一家媒体最多取几个视频，按热度（播放量优先、评论数次之）从高到低取 | 3 |
| `--no-category-filter` | 不限制搜索分类为「新闻和政治」 | 关闭（默认限制） |
| `--extra-keywords` | 追加新闻媒体频道关键词，逗号分隔，如 `BBC,CNN,联合早报` | 无 |
| `--min-subscribers` | 媒体频道最低订阅数门槛，低于此值的频道直接忽略 | 100000（10万） |
| `--min-video-comments` | 视频最低评论数门槛，低于此值的视频直接忽略 | 100 |
| `--min-title-similarity` | 标题关键词与候选视频标题的最低相关度（0-1，词级重合比例），低于此值直接忽略 | 0.5 |
| `--no-dedup-filter` | 不做跨视频重复评论去重 | 关闭（默认去重） |
| `--sentiment` | 调用 DeepSeek API 做情感分类，需 `.env` 配置 `DEEPSEEK_API_KEY` | 关闭 |
| `--whitelist` | 频道白名单（频道名或ID，逗号分隔），命中直接视为新闻媒体（绕过关键词/订阅数判定） | 无 |
| `--blacklist` | 频道黑名单（频道名或ID，逗号分隔），命中直接排除 | 无 |
| `--no-ad-filter` | 不过滤广告/推销类评论 | 关闭（默认过滤） |
| `--video-id` | 直接指定视频ID，跳过标题搜索与媒体频道筛选 | 无 |
| `--order` | 评论排序方式 `relevance` 或 `time` | time |
| `--output` | 输出文件路径，支持 `.csv` / `.json` | `output/comments.csv` |

> 注意：`order=relevance` 时 YouTube API 会提前截断评论列表（实测远少于真实总数），拉取「全部评论」（`--count 0`）时程序会自动强制改为 `order=time` 以保证完整性。

### 示例

取 3 家媒体，每家最多 3 个最热视频，各拉全部评论并合并导出：

```bash
uv run main.py --title "某新闻事件" --media-count 3 --videos-per-media 3 --count 0 --output output/result.json
```

只想要订阅数 50 万以上、评论数 500 以上的更头部内容：

```bash
uv run main.py --title "某新闻事件" --min-subscribers 500000 --min-video-comments 500
```

已知频道是新闻媒体但名称里没有命中默认关键词，用白名单强制放行：

```bash
uv run main.py --title "某新闻事件" --whitelist "频道名或频道ID"
```

已经知道视频 ID，跳过搜索和频道筛选直接拉评论：

```bash
uv run main.py --video-id "VIDEO_ID" --count 250
```

拉取评论并做情感分析：

```bash
uv run main.py --title "某新闻事件" --sentiment
```

## 新闻媒体频道判定逻辑

1. 默认优先在 YouTube「新闻和政治」分类（`videoCategoryId=25`）下搜索（可用 `--no-category-filter` 关闭）
2. 频道名称/customUrl/简介中包含新闻媒体关键词（内置中英文关键词列表，见 `filters.py` 的 `DEFAULT_NEWS_KEYWORDS`，可用 `--extra-keywords` 追加）
3. 可选订阅数门槛过滤小频道
4. 白名单/黑名单优先级最高，可强制放行或排除特定频道

注意：YouTube API 本身不提供"是否为媒体机构"的官方字段，以上为启发式规则组合判定，存在误判可能，可通过白名单/黑名单及关键词参数调整。

## 媒体与视频选取逻辑

1. 搜索候选池（`--search-results` 条）依次过滤：标题相关度达标 → 新闻媒体频道发布 → 评论数达标
2. 按频道（媒体）分组去重，按订阅数从高到低排序，取前 `--media-count` 家（候选媒体不足时按实际数量输出，不会报错）
3. 每家媒体内部，按热度（播放量优先、评论数次之）从高到低排序，取前 `--videos-per-media` 个视频
4. 媒体家数与每家视频数是两个独立维度：例如要 3 家媒体、每家最多 3 个视频，可能是「3 家各 3 个」，也可能是「1 家凑满 3 个 + 2 家各 1 个」，取决于候选池里每家媒体实际有多少个视频满足评论数门槛

## 广告评论过滤规则

剔除包含以下特征的评论，规则存于项目根目录的 `ad_patterns.txt`（每行一条正则表达式，`#` 开头为注释），可直接编辑该文件调整规则，无需改代码：
- 外部链接（http(s) 链接、短链、www 域名）
- 联系方式诱导（加微信/加群/Telegram 等）
- 推销关键词（代购、刷粉、兼职、私信我、招代理等）

## 跨视频去重

同一作者（`authorChannelId`）在不同视频下发完全相同文本的评论，只保留第一条出现的，其余剔除（保留的评论上会标注 `duplicate_count` 出现次数），默认开启，`--no-dedup-filter` 可关闭。这类评论常见于刷粉/广告号批量投放同一条文案。

## 情感分析（DeepSeek，可选）

`--sentiment` 会调用 [DeepSeek](https://api.deepseek.com) 的 `deepseek-chat` 模型，按 20 条一批，为每条评论标注 `sentiment` 字段（正面/负面/中性）。需要在 `.env` 配置 `DEEPSEEK_API_KEY`；不配置则该功能不生效，不影响其他功能正常使用。某一批请求失败时该批标记为「未知」，不会中断整体流程。注意：评论量大时会产生较多 API 调用，按实际计费。

## 结果摘要

每次运行结束会额外生成一份 `<输出文件名>.summary.json`（例如输出 `output/comments.json` 则摘要为 `output/comments.summary.json`），内容包括：
- 总评论数
- 按媒体（频道）分布的评论数与平均点赞数
- 评论文本高频词 Top20（仅对英文/拉丁字母词汇做词频统计，中文暂无分词，统计效果有限）

## 技术栈

- Python 3.11+
- `google-api-python-client`（YouTube Data API v3 官方客户端）
- `python-dotenv`（加载 `.env` 中的 API Key）
- `requests`（调用 DeepSeek API）

## 网络说明

如果本机通过代理（`HTTP_PROXY`/`HTTPS_PROXY` 环境变量）上网，`requirements.txt` 中已包含 `pysocks`，`youtube_client.py` 会自动读取代理环境变量并注入到底层 `httplib2` 客户端，无需额外配置。

## 配额说明

- 标题搜索（`search.list`）每次消耗 100 units（无论 `--search-results` 设多大都只调用一次）
- 频道信息（`channels.list`）、视频统计（`videos.list`）各消耗 1 unit（候选池 <= 50 时各只需一次调用）
- 评论拉取（`commentThreads.list`）每次消耗 1 unit（每次最多返回 100 条），每个视频按评论量分页拉取
- API Key 默认每日配额 10000 units，单次完整流程（默认 5 家媒体 x 3 视频）通常消耗约 120-150 units，主要取决于总评论量

## License

[MIT](LICENSE)
