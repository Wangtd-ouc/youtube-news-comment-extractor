"""调用 DeepSeek API 对评论做情感分类（正面/负面/中性）。"""
import json

import requests

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
LABELS = ("正面", "负面", "中性")


def _classify_batch(texts: list[str], api_key: str) -> list[str]:
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = (
        f"请判断下面这{len(texts)}条YouTube评论各自的情感倾向，只能是「正面」「负面」「中性」三者之一。"
        f"严格按输入顺序输出一个JSON对象：{{\"labels\": [\"正面\", \"负面\", ...]}}，"
        f"数组长度必须正好是{len(texts)}，不要输出任何其他内容。\n\n评论列表:\n{numbered}"
    )
    resp = requests.post(
        DEEPSEEK_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    labels = json.loads(content).get("labels", [])
    labels = [label if label in LABELS else "未知" for label in labels]
    if len(labels) < len(texts):
        labels += ["未知"] * (len(texts) - len(labels))
    return labels[: len(texts)]


def classify_comments(comments: list[dict], api_key: str, batch_size: int = 20) -> None:
    """原地为 comments 列表中每条记录添加 sentiment 字段。单批失败时该批标记为「未知」，不中断整体流程。"""
    for i in range(0, len(comments), batch_size):
        batch = comments[i : i + batch_size]
        texts = [c.get("text", "") for c in batch]
        try:
            labels = _classify_batch(texts, api_key)
        except Exception as e:
            print(f"情感分析第 {i // batch_size + 1} 批失败，标记为未知: {e}")
            labels = ["未知"] * len(batch)
        for c, label in zip(batch, labels):
            c["sentiment"] = label
