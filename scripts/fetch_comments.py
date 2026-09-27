#!/usr/bin/env python3
"""Fetch public comments from CommentShark's unauthenticated read-only API."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
API_BASE = "https://www.commentshark.com/api/v1/public/videos"
API_DOCS = "https://www.commentshark.com/docs/api"


def extract_video_id(value: str) -> str:
    candidate = value.strip()
    if VIDEO_ID_RE.fullmatch(candidate):
        return candidate

    if "://" not in candidate:
        candidate = "https://" + candidate

    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host == "youtu.be":
        video_id = path_parts[0] if path_parts else ""
    elif host in YOUTUBE_HOSTS:
        if parsed.path.rstrip("/") == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            video_id = ""
            for marker in ("shorts", "live", "embed", "v"):
                if marker in path_parts:
                    marker_index = path_parts.index(marker)
                    if marker_index + 1 < len(path_parts):
                        video_id = path_parts[marker_index + 1]
                        break
    else:
        video_id = ""

    if not VIDEO_ID_RE.fullmatch(video_id):
        raise ValueError(
            "Could not find a valid 11-character YouTube video ID. "
            "Pass a YouTube watch, Shorts, live, embed, or youtu.be URL."
        )
    return video_id


def count_entries(comments: object) -> tuple[int, int]:
    """Count top-level rows and inline replies if the API includes them."""
    if not isinstance(comments, list):
        return 0, 0

    top_level = 0
    replies = 0
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        top_level += 1
        child_rows = comment.get("replies", [])
        if isinstance(child_rows, list):
            replies += len([row for row in child_rows if isinstance(row, dict)])
            _, nested_replies = count_entries(child_rows)
            replies += nested_replies
    return top_level, replies


def fetch_comments(
    video_id: str, max_comments: int, sort: str, include_replies: bool
) -> dict:
    query = urlencode(
        {
            "sort": sort,
            "maxComments": str(max_comments),
            "includeReplies": str(include_replies).lower(),
        }
    )
    url = f"{API_BASE}/{video_id}/comments?{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "youtube-comment-analyzer/1.0",
        },
        method="GET",
    )
    with urlopen(request, timeout=40) as response:
        raw = response.read()

    api_response = json.loads(raw.decode("utf-8"))
    if not isinstance(api_response, dict):
        raise ValueError("CommentShark returned an unexpected non-object JSON response.")

    comments = api_response.get("comments")
    top_level, replies = count_entries(comments)
    return {
        "_collector": {
            "name": "CommentShark public video comments API",
            "docs": API_DOCS,
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "videoId": video_id,
            "videoUrl": f"https://www.youtube.com/watch?v={video_id}",
            "sort": sort,
            "maxCommentsRequested": max_comments,
            "includeRepliesRequested": include_replies,
            "returnedTopLevelComments": top_level,
            "returnedInlineReplies": replies,
            "returnedCommentEntries": top_level + replies,
            "totalCommentsScanned": api_response.get("totalCommentsScanned"),
            "reachedCap": api_response.get("reachedCap"),
        },
        "apiResponse": api_response,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch public YouTube comments from CommentShark. No API key or "
            "third-party Python package is required."
        )
    )
    parser.add_argument("video", help="YouTube URL or 11-character video ID")
    parser.add_argument(
        "--max-comments",
        type=int,
        default=1000,
        help="requested scan cap (default: 1000; the service may impose its own cap)",
    )
    parser.add_argument(
        "--sort",
        choices=("random", "newest", "oldest"),
        default="random",
        help="sample order (default: random)",
    )
    parser.add_argument(
        "--no-replies",
        action="store_true",
        help="exclude inline replies",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write JSON to this path instead of stdout",
    )
    args = parser.parse_args()

    if args.max_comments < 1:
        parser.error("--max-comments must be a positive integer")

    try:
        video_id = extract_video_id(args.video)
        result = fetch_comments(
            video_id=video_id,
            max_comments=args.max_comments,
            sort=args.sort,
            include_replies=not args.no_replies,
        )
    except HTTPError as exc:
        retry_after = exc.headers.get("Retry-After")
        message = f"CommentShark returned HTTP {exc.code}."
        if exc.code == 429:
            message += " Rate limit reached; stop and use a fallback or try later."
            if retry_after:
                message += f" Retry-After: {retry_after}."
        elif exc.code in (403, 404):
            message += " The video may be unavailable or not publicly analyzable."
        else:
            message += f" See {API_DOCS}."
        print(message, file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"CommentShark returned invalid JSON: {exc}", file=sys.stderr)
        return 2
    except (URLError, TimeoutError, OSError) as exc:
        print(
            "Could not fetch or parse the CommentShark response "
            f"({exc}). Use the browser/export fallback if available.",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        print(f"Input or response error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"Could not write {args.out}: {exc}", file=sys.stderr)
            return 2
        meta = result["_collector"]
        print(
            "Fetched "
            f"{meta['returnedCommentEntries']} comment entries "
            f"({meta['returnedTopLevelComments']} top-level, "
            f"{meta['returnedInlineReplies']} replies); "
            f"server scanned {meta['totalCommentsScanned']!r}; "
            f"reached cap {meta['reachedCap']!r}. Saved {args.out}."
        )
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
