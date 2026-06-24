"""YouTube 新闻媒体视频评论提取工具。

用法示例:
    uv run main.py                                          # 不带参数运行，进入引导式输入
    uv run main.py --title "某新闻标题关键词" --count 250
    # 取 5 家头部媒体（默认），每家最多 3 个最热视频，各拉全部评论
    uv run main.py --title "某新闻标题关键词" --count 0
    # 取 3 家媒体，每家最多 2 个视频
    uv run main.py --title "某新闻标题关键词" --media-count 3 --videos-per-media 2
"""
import argparse
import csv
import json
import os
import sys

from dotenv import load_dotenv

from filters import DEFAULT_NEWS_KEYWORDS, find_duplicate_comments, is_ad_comment, is_news_channel, title_similarity
from summary import build_summary, print_summary, save_summary
from youtube_client import YouTubeClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="提取新闻媒体视频下的评论（自动过滤广告/推销内容）")
    parser.add_argument("--title", default=None, help="视频标题关键词；不提供时进入引导式输入")
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="每个视频目标提取评论数，默认 200（建议 200-300）；设为 0 表示拉取该视频全部评论",
    )
    parser.add_argument("--search-results", type=int, default=30, help="标题搜索返回的候选视频数，默认 30（需要足够候选池才能凑够多家媒体）")
    parser.add_argument(
        "--media-count",
        type=int,
        default=5,
        help="取多少家不同的新闻媒体（频道去重），按订阅数从高到低取头部媒体，默认 5（建议 3-10）；候选不足时按实际数量输出",
    )
    parser.add_argument(
        "--videos-per-media",
        type=int,
        default=3,
        help="同一家媒体最多取几个视频，按热度（播放量优先、评论数次之）从高到低取，默认 3",
    )
    parser.add_argument(
        "--no-category-filter",
        action="store_true",
        help="不限制搜索分类为「新闻和政治」(默认会限制以提高新闻媒体命中率)",
    )
    parser.add_argument(
        "--extra-keywords",
        default="",
        help="追加的新闻媒体频道关键词，逗号分隔，例如: BBC,CNN,联合早报",
    )
    parser.add_argument(
        "--min-subscribers",
        type=int,
        default=100_000,
        help="媒体频道最低订阅数门槛，低于此值的频道直接忽略，默认 100000（10万）",
    )
    parser.add_argument(
        "--min-video-comments",
        type=int,
        default=100,
        help="视频最低评论数门槛，低于此值的视频直接忽略，默认 100",
    )
    parser.add_argument(
        "--min-title-similarity",
        type=float,
        default=0.5,
        help="标题关键词与候选视频标题的最低相关度（0-1，按词级重合比例计算），低于此值的视频直接忽略，默认 0.5",
    )
    parser.add_argument(
        "--no-dedup-filter",
        action="store_true",
        help="不做跨视频重复评论（同作者同内容刷屏）去重，默认会去重",
    )
    parser.add_argument(
        "--sentiment",
        action="store_true",
        help="调用 DeepSeek API 对评论做情感分类（正面/负面/中性），需要 .env 中配置 DEEPSEEK_API_KEY",
    )
    parser.add_argument(
        "--whitelist",
        default="",
        help="频道白名单（频道名或频道ID，逗号分隔），命中直接视为新闻媒体",
    )
    parser.add_argument(
        "--blacklist",
        default="",
        help="频道黑名单（频道名或频道ID，逗号分隔），命中直接排除",
    )
    parser.add_argument(
        "--no-ad-filter",
        action="store_true",
        help="不过滤广告/推销类评论",
    )
    parser.add_argument(
        "--video-id",
        default="",
        help="直接指定视频ID，跳过标题搜索与媒体频道筛选",
    )
    parser.add_argument(
        "--order",
        default="time",
        choices=["relevance", "time"],
        help="评论排序方式，默认按时间。注意: order=relevance 时 YouTube API 会提前截断结果，"
        "拉取全部评论（--count 0）时必须用 time 才能保证完整，否则会有警告",
    )
    parser.add_argument("--output", default="output/comments.csv", help="输出文件路径 (.csv 或 .json)")
    return parser.parse_args()


def _prompt_str(prompt: str, default: str | None = None, required: bool = False) -> str:
    suffix = f" [默认: {default}]" if default is not None else ""
    while True:
        val = input(f"{prompt}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        if not required:
            return ""
        print("此项为必填，请输入。")


def _prompt_int(prompt: str, default: int) -> int:
    while True:
        val = input(f"{prompt} [默认: {default}]: ").strip()
        if not val:
            return default
        if val.isdigit():
            return int(val)
        print("请输入一个非负整数。")


def _prompt_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        val = input(f"{prompt} ({hint}): ").strip().lower()
        if not val:
            return default
        if val in ("y", "yes", "是"):
            return True
        if val in ("n", "no", "否"):
            return False
        print("请输入 y 或 n。")


def interactive_args(defaults: argparse.Namespace) -> argparse.Namespace:
    """引导式输入：逐项询问关键参数，最后二次确认；不确认则重新输入。"""
    while True:
        print("\n==== 引导式配置 ====")
        title = _prompt_str("请输入视频标题关键词", required=True)
        media_count = _prompt_int("要拉取几家媒体（建议 3-10）", defaults.media_count)
        videos_per_media = _prompt_int("每家媒体最多取几个视频", defaults.videos_per_media)
        min_subscribers = _prompt_int("媒体最低粉丝量门槛", defaults.min_subscribers)
        min_video_comments = _prompt_int("视频最低评论数门槛", defaults.min_video_comments)

        count_raw = _prompt_str(
            "每个视频拉取多少评论？输入「全部」或具体数字", default=str(defaults.count)
        )
        count = 0 if count_raw in ("全部", "all", "All", "0") else (int(count_raw) if count_raw.isdigit() else defaults.count)

        ad_filter = _prompt_yes_no("是否过滤广告/推销类评论？", default=True)
        output = _prompt_str("输出文件路径", default=defaults.output)

        print("\n==== 请确认以下配置 ====")
        print(f"  标题关键词:       {title}")
        print(f"  媒体家数:         {media_count}")
        print(f"  每家媒体视频数:   {videos_per_media}")
        print(f"  媒体最低粉丝量:   {min_subscribers:,}")
        print(f"  视频最低评论数:   {min_video_comments}")
        print(f"  每视频评论拉取数: {'全部' if count == 0 else count}")
        print(f"  过滤广告评论:     {'是' if ad_filter else '否'}")
        print(f"  输出路径:         {output}")

        if _prompt_yes_no("\n确认以上配置并开始执行？", default=True):
            args = argparse.Namespace(**vars(defaults))
            args.title = title
            args.media_count = media_count
            args.videos_per_media = videos_per_media
            args.min_subscribers = min_subscribers
            args.min_video_comments = min_video_comments
            args.count = count
            args.no_ad_filter = not ad_filter
            args.output = output
            return args

        print("\n好的，重新输入。")


def select_videos(client: YouTubeClient, args: argparse.Namespace) -> list[dict]:
    """搜索标题关键词，按媒体频道分组筛选视频。

    规则:
    1. 标题相关度 >= --min-title-similarity，过滤掉跑题的搜索结果
    2. 频道需满足「新闻媒体」判定（关键词/白名单），且订阅数 >= --min-subscribers
    3. 视频评论数 >= --min-video-comments，否则忽略
    4. 按频道订阅数从高到低，取 --media-count 家媒体（头部媒体），候选不足则按实际数量输出
    5. 每家媒体内部按热度（播放量优先、评论数次之）从高到低，取 --videos-per-media 个视频
    """
    candidates = client.search_videos(
        query=args.title,
        max_results=args.search_results,
        only_news_category=not args.no_category_filter,
        order="relevance",
    )
    if not candidates:
        print("未搜索到匹配的视频，请尝试更换关键词或加上 --no-category-filter")
        sys.exit(1)

    channel_info = client.get_channels_info([c["channel_id"] for c in candidates])
    video_stats = client.get_videos_info([c["video_id"] for c in candidates])

    keywords = list(DEFAULT_NEWS_KEYWORDS)
    if args.extra_keywords:
        keywords += [k.strip() for k in args.extra_keywords.split(",") if k.strip()]
    whitelist = {w.strip() for w in args.whitelist.split(",") if w.strip()}
    blacklist = {b.strip() for b in args.blacklist.split(",") if b.strip()}

    filtered = []
    for c in candidates:
        if title_similarity(args.title, c["title"]) < args.min_title_similarity:
            continue
        cinfo = channel_info.get(c["channel_id"], {})
        vinfo = video_stats.get(c["video_id"], {})
        if not is_news_channel(
            channel_title=cinfo.get("title", c["channel_title"]),
            custom_url=cinfo.get("custom_url", ""),
            description=cinfo.get("description", ""),
            subscriber_count=cinfo.get("subscriber_count", 0),
            keywords=keywords,
            min_subscribers=args.min_subscribers,
            whitelist=whitelist,
            blacklist=blacklist,
            channel_id=c["channel_id"],
        ):
            continue
        if vinfo.get("comment_count", 0) < args.min_video_comments:
            continue
        filtered.append(
            {
                **c,
                "view_count": vinfo.get("view_count", 0),
                "comment_count": vinfo.get("comment_count", 0),
                "subscriber_count": cinfo.get("subscriber_count", 0),
            }
        )

    if not filtered:
        print("候选视频中没有同时满足「标题相关度」「新闻媒体频道」与「最低评论数」规则的结果。")
        print("可尝试：降低 --min-title-similarity，放宽 --extra-keywords，降低 --min-subscribers / --min-video-comments，或用 --whitelist 指定频道。")
        sys.exit(1)

    by_channel: dict[str, list[dict]] = {}
    for v in filtered:
        by_channel.setdefault(v["channel_id"], []).append(v)

    # 按频道订阅数从高到低，取头部媒体
    ranked_channels = sorted(by_channel.items(), key=lambda kv: kv[1][0]["subscriber_count"], reverse=True)
    selected_channels = ranked_channels[: args.media_count]

    selected = []
    for _, vids in selected_channels:
        vids_sorted = sorted(vids, key=lambda v: (v["view_count"], v["comment_count"]), reverse=True)
        selected.extend(vids_sorted[: args.videos_per_media])

    print(f"共筛选出 {len(selected_channels)} 家媒体（目标 {args.media_count} 家），合计 {len(selected)} 个视频:")
    for _, vids in selected_channels:
        vids_sorted = sorted(vids, key=lambda v: (v["view_count"], v["comment_count"]), reverse=True)[: args.videos_per_media]
        print(f"  媒体: {vids_sorted[0]['channel_title']}  (订阅 {vids_sorted[0]['subscriber_count']:,})")
        for v in vids_sorted:
            print(f"    - {v['title']}  (播放 {v['view_count']:,}, 评论 {v['comment_count']:,})")

    return selected


def save_comments(comments: list[dict], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if output_path.endswith(".json"):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(comments, f, ensure_ascii=False, indent=2)
    else:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(comments[0].keys()) if comments else [])
            writer.writeheader()
            writer.writerows(comments)


def main() -> None:
    args = parse_args()  # 含 --help，提前解析以便不配置 .env 也能查看帮助

    load_dotenv()
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("未找到 YOUTUBE_API_KEY，请复制 .env.example 为 .env 并填入你的密钥")
        sys.exit(1)

    if not args.video_id and not args.title:
        args = interactive_args(args)

    client = YouTubeClient(api_key)
    target_count = None if args.count <= 0 else args.count

    if target_count is None and args.order == "relevance":
        print("警告: order=relevance 拉取全部评论会被 YouTube API 提前截断，自动切换为 order=time")
        args.order = "time"

    if args.video_id:
        video_id = args.video_id
        video_info = client.get_video_info(video_id)
        print(f"已指定视频: {video_info['title']}  —  {video_info['channel_title']}")
        videos = [{"video_id": video_id, "title": video_info["title"], "channel_title": video_info["channel_title"]}]
    else:
        videos = select_videos(client, args)

    all_comments = []
    for v in videos:
        label = "全部" if target_count is None else str(target_count)
        print(f"\n[{v['title']}] 开始拉取评论，目标数量: {label} ...")
        try:
            comments = client.get_comments(v["video_id"], target_count=target_count, order=args.order)
        except RuntimeError as e:
            print(f"跳过该视频: {e}")
            continue
        print(f"实际拉取到 {len(comments)} 条评论")

        if not args.no_ad_filter:
            before = len(comments)
            comments = [c for c in comments if not is_ad_comment(c["text"])]
            print(f"过滤广告/推销内容: 剔除 {before - len(comments)} 条，剩余 {len(comments)} 条")

        for c in comments:
            c["video_id"] = v["video_id"]
            c["video_title"] = v["title"]
            c["channel_title"] = v.get("channel_title", "")
        all_comments.extend(comments)

    if not args.no_dedup_filter and all_comments:
        before = len(all_comments)
        all_comments, removed = find_duplicate_comments(all_comments)
        if removed:
            print(f"\n跨视频去重: 剔除 {removed} 条同作者重复刷屏评论，剩余 {before - removed} 条")

    if args.sentiment and all_comments:
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        if not deepseek_key:
            print("\n未找到 DEEPSEEK_API_KEY，跳过情感分析（请检查 .env 文件）")
        else:
            from sentiment import classify_comments

            print(f"\n开始情感分析（DeepSeek），共 {len(all_comments)} 条评论 ...")
            classify_comments(all_comments, deepseek_key)
            print("情感分析完成")

    save_comments(all_comments, args.output)
    print(f"\n共 {len(all_comments)} 条评论，已保存至: {args.output}")

    if all_comments:
        summary = build_summary(all_comments)
        summary_path = save_summary(summary, args.output)
        print_summary(summary)
        print(f"摘要已保存至: {summary_path}")


if __name__ == "__main__":
    main()
