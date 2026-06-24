"""频道与评论过滤规则。"""
import re
from collections import Counter
from pathlib import Path

# 新闻媒体频道关键词（中英文混合，可通过 CLI --extra-keywords 追加）
DEFAULT_NEWS_KEYWORDS = [
    # 中文
    "新闻", "日报", "晚报", "早报", "时报", "电视台", "卫视", "广播",
    "通讯社", "传媒", "媒体", "资讯", "频道",
    # 英文/通用
    "news", "tv", "television", "broadcast", "broadcasting", "media",
    "network", "press", "journal", "times", "post", "gazette",
    "channel", "live",
]

# 广告/推销正则规则的默认值，仅在 ad_patterns.txt 缺失或为空时使用
_DEFAULT_AD_PATTERNS = [
    r"https?://\S+",
    r"t\.me/\S+",
    r"wa\.me/\S+",
    r"bit\.ly/\S+",
    r"加(我|微信|vx|VX|v信)",
    r"微信[:：]?\s*[\w\-]+",
    r"\b(telegram|tg)\b[:：]?\s*[\w\-]+",
    r"代购|刷粉|刷量|兼职|私信我|加群|进群|赚钱项目|招代理",
    r"www\.[\w\-]+\.\w+",
]

AD_PATTERNS_FILE = Path(__file__).parent / "ad_patterns.txt"


def _load_ad_patterns() -> list[str]:
    """从 ad_patterns.txt 加载广告正则规则（每行一条，# 开头为注释）；文件不存在或为空时回退默认规则。"""
    if AD_PATTERNS_FILE.exists():
        lines = AD_PATTERNS_FILE.read_text(encoding="utf-8").splitlines()
        patterns = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
        if patterns:
            return patterns
    return list(_DEFAULT_AD_PATTERNS)


AD_PATTERNS = _load_ad_patterns()
_AD_REGEXES = [re.compile(p, re.IGNORECASE) for p in AD_PATTERNS]


def is_ad_comment(text: str) -> bool:
    """判断评论是否为广告/推销内容。"""
    if not text:
        return False
    return any(r.search(text) for r in _AD_REGEXES)


def is_news_channel(
    channel_title: str,
    custom_url: str,
    description: str,
    subscriber_count: int,
    keywords: list[str],
    min_subscribers: int = 0,
    whitelist: set[str] | None = None,
    blacklist: set[str] | None = None,
    channel_id: str = "",
) -> bool:
    """根据频道名称/简介关键词与订阅数等规则，判断是否为新闻媒体频道。"""
    if blacklist and (channel_id in blacklist or channel_title in blacklist):
        return False
    if whitelist and (channel_id in whitelist or channel_title in whitelist):
        return True

    haystack = f"{channel_title} {custom_url} {description}".lower()
    keyword_hit = any(kw.lower() in haystack for kw in keywords)

    if not keyword_hit:
        return False
    if min_subscribers and subscriber_count < min_subscribers:
        return False
    return True


_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def title_similarity(query: str, title: str) -> float:
    """搜索关键词与候选视频标题的相关度：query 分词后有多大比例出现在 title 中（词级，不区分大小写）。"""
    query_words = {w for w in _WORD_RE.findall(query.lower()) if w}
    if not query_words:
        return 1.0
    title_words = set(_WORD_RE.findall(title.lower()))
    hit = sum(1 for w in query_words if w in title_words)
    return hit / len(query_words)


def find_duplicate_comments(comments: list[dict]) -> tuple[list[dict], int]:
    """跨视频识别同一作者发的完全相同评论（常见于刷屏/广告号），只保留首次出现，其余剔除。

    返回 (去重后的评论列表, 剔除数量)，每条保留的评论会附带 duplicate_count 字段。
    """
    keys = [
        (c.get("author_channel_id", ""), c.get("text", "").strip().lower())
        for c in comments
    ]
    counts = Counter(k for k in keys if k[0] and k[1])

    kept = []
    seen = set()
    removed = 0
    for c, key in zip(comments, keys):
        c["duplicate_count"] = counts.get(key, 1) if key[0] and key[1] else 1
        if key[0] and key[1] and counts[key] > 1:
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        kept.append(c)
    return kept, removed
