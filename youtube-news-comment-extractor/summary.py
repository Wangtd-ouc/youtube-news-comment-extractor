"""评论结果统计摘要：按媒体分布、关键词词频等。"""
import json
import re
from collections import Counter

_STOPWORDS = {
    "the", "and", "to", "of", "in", "is", "it", "this", "that", "for", "on",
    "with", "as", "was", "are", "be", "at", "by", "an", "not", "but", "have",
    "has", "had", "from", "or", "you", "your", "they", "them", "their", "he",
    "she", "his", "her", "its", "if", "so", "my", "me", "just", "like",
    "about", "what", "who", "when", "how", "all", "more", "can", "will",
    "would", "there", "do", "does", "did", "because", "than", "too", "very",
    "then", "also", "one", "no", "yes", "out", "up", "now", "get", "got",
    "we", "people", "im", "dont", "thats", "going", "even", "still",
}


def build_summary(comments: list[dict]) -> dict:
    """生成评论结果的统计摘要：媒体分布、平均点赞数、Top关键词。"""
    by_media: dict[str, dict] = {}
    for c in comments:
        media = c.get("channel_title") or "未知"
        stat = by_media.setdefault(media, {"comment_count": 0, "like_sum": 0})
        stat["comment_count"] += 1
        stat["like_sum"] += c.get("like_count", 0)

    media_stats = [
        {
            "channel_title": media,
            "comment_count": s["comment_count"],
            "avg_like_count": round(s["like_sum"] / s["comment_count"], 2) if s["comment_count"] else 0,
        }
        for media, s in by_media.items()
    ]
    media_stats.sort(key=lambda x: x["comment_count"], reverse=True)

    word_counter: Counter = Counter()
    for c in comments:
        words = re.findall(r"[a-zA-Z']{3,}", c.get("text", "").lower())
        word_counter.update(w for w in words if w not in _STOPWORDS)
    top_keywords = [{"word": w, "count": n} for w, n in word_counter.most_common(20)]

    return {
        "total_comments": len(comments),
        "by_media": media_stats,
        "top_keywords": top_keywords,
    }


def summary_output_path(output_path: str) -> str:
    base = output_path.rsplit(".", 1)[0] if "." in output_path else output_path
    return f"{base}.summary.json"


def save_summary(summary: dict, output_path: str) -> str:
    path = summary_output_path(output_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return path


def print_summary(summary: dict) -> None:
    print(f"\n==== 结果摘要 ====")
    print(f"总评论数: {summary['total_comments']}")
    print("按媒体分布:")
    for s in summary["by_media"]:
        print(f"  {s['channel_title']}: {s['comment_count']} 条，平均点赞 {s['avg_like_count']}")
    if summary["top_keywords"]:
        top = ", ".join(f"{k['word']}({k['count']})" for k in summary["top_keywords"][:10])
        print(f"高频词 Top10: {top}")
