<p align="center">
  <img src="assets/cover.png" alt="YouTube comments becoming grouped insights and video ideas" width="100%">
</p>

# YouTube Comment Analyzer

**Turn recurring viewer questions into evidence-backed video ideas.**

A Codex skill that analyzes public YouTube comments, surfaces up to three audience needs, and packages the findings into a concise report with practical video angles.

## Install

```bash
git clone https://github.com/gregcolun/youtube-comment-analyzer.git ~/.codex/skills/youtube-comment-analyzer
```

Start a new Codex task, then use:

```text
$youtube-comment-analyzer https://www.youtube.com/watch?v=VIDEO_ID
```

You can also provide a CommentShark export or paste comments directly.

## What it does

- Groups repeated questions and practical pain points while filtering generic reactions and spam.
- Grounds up to three video opportunities in comment evidence and a bounded check of related videos.
- Creates a compact interactive HTML report with title directions and clear collection notes.

## Requirements

The included CommentShark fetcher uses Python 3’s standard library and needs no API key. It requires outbound access to CommentShark and may be subject to its rate limits. If fetching is unavailable, provide a CSV/XLSX export or copied comments. The market check requires web search or browser access.
