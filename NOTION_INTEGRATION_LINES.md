# Exact Lines Added for Notion Integration in social_agent.py

## 1. IMPORT STATEMENT (Lines 87-94)

```python
try:
    from notion_manager import NOTION_MANAGER, init_notion_manager, log_task_to_notion
    # Initialize Notion manager (will use env vars or defaults)
    init_notion_manager()
except ImportError:
    NOTION_MANAGER = None
    log_task_to_notion = None
    print("⚠️ Notion manager not available (install: pip install notion-client)")
```

## 2. LOG ACTIVITY AFTER SUCCESSFUL POST (Lines 5683-5699)

Located in `post_original_content()` function, after successful post:

```python
        # [NOTION] Log post activity to Notion
        if NOTION_MANAGER:
            try:
                url = f"https://x.com/k_shamil57907/status/{post_id}" if post_id.startswith("post_") else None
                NOTION_MANAGER.log_activity(
                    "POST",
                    f"Original post: {tweet_text[:50]}...",
                    metadata={
                        "url": url or "Pending",
                        "text": tweet_text[:200],
                        "has_link": str(include_link),
                        "post_id": post_id,
                        "time": current_time
                    }
                )
            except Exception as e:
                log(f"[NOTION] Failed to log post: {e}")
```

## 3. LOG ACTIVITY AFTER SUCCESSFUL REPLY (Lines 3579-3602)

Located in `reply_to_card()` function, after successful reply:

```python
            # [NOTION] Log reply activity to Notion
            if NOTION_MANAGER:
                try:
                    url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None
                    # Extract username from card if available
                    username = "unknown"
                    try:
                        if card and hasattr(card, 'get'):
                            username = card.get('username', 'unknown')
                    except Exception:
                        pass
                    NOTION_MANAGER.log_activity(
                        "REPLY",
                        f"Replied to @{username}",
                        metadata={
                            "url": url or "Pending",
                            "text": text[:200],
                            "has_link": str(has_link_in_reply),
                            "tweet_id": str(tweet_id),
                            "topic": topic or "unknown"
                        }
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log reply: {e}")
```

## 4. LOG ERROR ACTIVITY (Lines 3872-3882)

Located in `force_original_post_immediately()` function, in exception handler:

```python
        # [NOTION] Log error to Notion
        if NOTION_MANAGER:
            try:
                NOTION_MANAGER.log_activity(
                    "ERROR",
                    f"Force post failed from {source_stage}: {str(e)[:100]}",
                    metadata={"error": str(e)[:500], "stage": source_stage}
                )
                NOTION_MANAGER.update_task_status(source_stage, "Blocked", f"Error: {str(e)[:200]}")
            except Exception:
                pass  # Don't fail on Notion errors
```

## 5. UPDATE TASK STATUS ON SLEEP (Lines 6923-6934)

Located in `bot_loop()` function, when bot enters sleep mode:

```python
            # [NOTION] Log sleep status
            if NOTION_MANAGER:
                try:
                    wake_time = datetime.now(timezone.utc).timestamp() + sleep_duration
                    wake_time_str = datetime.fromtimestamp(wake_time, tz=timezone.utc).strftime('%H:%M:%S UTC')
                    NOTION_MANAGER.update_task_status(
                        "Bot Status",
                        "Not started",
                        f"Sleeping until {wake_time_str} (UTC hours 3-6)"
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log sleep: {e}")
```

## 6. LOG VIDEO POST ACTIVITY (Lines 612-627)

Located in `post_video_with_context()` function, after successful video post:

```python
            # [NOTION] Log video post activity
            if NOTION_MANAGER:
                try:
                    video_name = os.path.basename(video_path) if video_path else "unknown"
                    NOTION_MANAGER.log_activity(
                        "VIDEO",
                        f"Video posted: {video_name}",
                        metadata={
                            "video_path": video_name,
                            "caption": context_text[:200],
                            "bypass_rate_limit": str(bypass_rate_limit),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log video: {e}")
```

## 7. LOG FORCE POST ACTIVITY (Lines 3849-3865)

Located in `force_original_post_immediately()` function, after successful force post (for Stage 11B):

```python
        # [NOTION] Log force post activity (especially for Stage 11B videos)
        if NOTION_MANAGER:
            try:
                is_video = source_stage == "11B_BREAKING_NEWS_VIDEO"
                activity_type = "VIDEO" if is_video else "POST"
                NOTION_MANAGER.log_activity(
                    activity_type,
                    f"Force post from {source_stage}: {text[:50]}...",
                    metadata={
                        "stage": source_stage,
                        "text": text[:200],
                        "is_video": str(is_video),
                        "time": current_time
                    }
                )
            except Exception as e:
                log(f"[NOTION] Failed to log force post: {e}")
```

## Summary

All Notion integration points are wrapped in:
- `if NOTION_MANAGER:` check (prevents crashes if module not available)
- `try/except Exception:` blocks (prevents crashes if Notion API fails)
- Proper error logging with `log(f"[NOTION] Failed to...")` for debugging

The bot will continue to function normally even if:
- `notion-client` is not installed
- Notion API is down
- Network issues occur
- Database permissions are incorrect

All errors are logged to console but never crash the bot.

