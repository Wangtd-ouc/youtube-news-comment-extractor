"""YouTube Data API v3 调用封装。"""
import html

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

NEWS_POLITICS_CATEGORY_ID = "25"  # YouTube 内置分类：新闻和政治


def _build_http():
    """httplib2 不会自动读取 HTTP_PROXY/HTTPS_PROXY 环境变量，这里显式注入。"""
    proxy_info = httplib2.proxy_info_from_environment(method="https")
    return httplib2.Http(proxy_info=proxy_info, timeout=30)


class YouTubeClient:
    def __init__(self, api_key: str):
        self.youtube = build(
            "youtube", "v3", developerKey=api_key, http=_build_http()
        )

    def search_videos(
        self,
        query: str,
        max_results: int = 10,
        only_news_category: bool = True,
        order: str = "relevance",
    ) -> list[dict]:
        """按标题关键词搜索视频，返回 [{video_id, title, channel_id, channel_title}, ...]"""
        params = dict(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
            order=order,
        )
        if only_news_category:
            params["videoCategoryId"] = NEWS_POLITICS_CATEGORY_ID

        try:
            resp = self.youtube.search().list(**params).execute()
        except HttpError as e:
            raise RuntimeError(f"搜索视频失败: {e}") from e

        results = []
        for item in resp.get("items", []):
            results.append(
                {
                    "video_id": item["id"]["videoId"],
                    "title": html.unescape(item["snippet"]["title"]),
                    "channel_id": item["snippet"]["channelId"],
                    "channel_title": html.unescape(item["snippet"]["channelTitle"]),
                    "published_at": item["snippet"]["publishedAt"],
                }
            )
        return results

    def get_channels_info(self, channel_ids: list[str]) -> dict[str, dict]:
        """批量获取频道信息，返回 {channel_id: {title, custom_url, description, subscriber_count}}"""
        info = {}
        unique_ids = list(dict.fromkeys(channel_ids))
        for i in range(0, len(unique_ids), 50):  # channels.list 单次最多 50 个 id
            batch = unique_ids[i : i + 50]
            try:
                resp = (
                    self.youtube.channels()
                    .list(part="snippet,statistics", id=",".join(batch))
                    .execute()
                )
            except HttpError as e:
                raise RuntimeError(f"获取频道信息失败: {e}") from e

            for item in resp.get("items", []):
                snippet = item["snippet"]
                stats = item.get("statistics", {})
                info[item["id"]] = {
                    "title": html.unescape(snippet.get("title", "")),
                    "custom_url": snippet.get("customUrl", ""),
                    "description": snippet.get("description", ""),
                    "subscriber_count": int(stats.get("subscriberCount", 0)),
                }
        return info

    def get_videos_info(self, video_ids: list[str]) -> dict[str, dict]:
        """批量获取视频统计信息，返回 {video_id: {view_count, comment_count}}"""
        info = {}
        unique_ids = list(dict.fromkeys(video_ids))
        for i in range(0, len(unique_ids), 50):  # videos.list 单次最多 50 个 id
            batch = unique_ids[i : i + 50]
            try:
                resp = (
                    self.youtube.videos()
                    .list(part="statistics", id=",".join(batch))
                    .execute()
                )
            except HttpError as e:
                raise RuntimeError(f"获取视频统计信息失败: {e}") from e

            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                info[item["id"]] = {
                    "view_count": int(stats.get("viewCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                }
        return info

    def get_video_info(self, video_id: str) -> dict:
        """获取视频统计信息（标题、评论总数等）。"""
        try:
            resp = (
                self.youtube.videos()
                .list(part="snippet,statistics", id=video_id)
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"获取视频信息失败: {e}") from e

        items = resp.get("items", [])
        if not items:
            raise RuntimeError(f"视频不存在或不可访问: {video_id}")
        item = items[0]
        return {
            "title": html.unescape(item["snippet"]["title"]),
            "channel_title": html.unescape(item["snippet"]["channelTitle"]),
            "comment_count": int(item.get("statistics", {}).get("commentCount", 0)),
        }

    def get_comments(
        self,
        video_id: str,
        target_count: int | None = 200,
        order: str = "time",
    ) -> list[dict]:
        """拉取指定视频下的评论（不含逐条回复）。

        target_count=None 表示不设上限，拉取该视频下的全部评论。

        注意：YouTube API 的 order=relevance 会提前截断结果（实测远少于真实评论总数），
        要拉取「全部」评论时必须用 order=time，否则数据不完整。
        """
        comments = []
        page_token = None

        while target_count is None or len(comments) < target_count:
            page_size = 100 if target_count is None else min(100, target_count - len(comments))
            params = dict(
                part="snippet",
                videoId=video_id,
                maxResults=page_size,
                order=order,
                textFormat="plainText",
            )
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = self.youtube.commentThreads().list(**params).execute()
            except HttpError as e:
                if "commentsDisabled" in str(e):
                    raise RuntimeError("该视频已关闭评论功能") from e
                raise RuntimeError(f"获取评论失败: {e}") from e

            for item in resp.get("items", []):
                top = item["snippet"]["topLevelComment"]["snippet"]
                comments.append(
                    {
                        "comment_id": item["id"],
                        "author": top.get("authorDisplayName", ""),
                        "author_channel_id": top.get("authorChannelId", {}).get("value", ""),
                        "text": top.get("textDisplay", ""),
                        "like_count": top.get("likeCount", 0),
                        "published_at": top.get("publishedAt", ""),
                        "reply_count": item["snippet"].get("totalReplyCount", 0),
                    }
                )
                if target_count is not None and len(comments) >= target_count:
                    break

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return comments
