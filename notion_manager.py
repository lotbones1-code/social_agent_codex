"""
Notion Manager - Mission Control Dashboard for X Bot (@k_shamil57907)

Integrates bot activity with Notion Tasks Tracker database for real-time status monitoring.
Uses notion-client library for reliable API interaction.
"""

import os
import json
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

# Load environment variables from .env file (same as main bot)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required, will use system env vars

# Store import error for debugging (if import fails)
_notion_import_error = None

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError as e:
    NOTION_AVAILABLE = False
    _notion_import_error = e
    # Don't print here - let init_notion_manager() handle messaging
    pass
except Exception as e:
    # Catch any other import-related errors
    NOTION_AVAILABLE = False
    _notion_import_error = e
    pass


class NotionManager:
    """
    Manages all Notion integrations for bot activity tracking.
    
    Features:
    - Update task status (In Progress, Done, Blocked)
    - Log activities (POST, REPLY, VIDEO, ERROR, STATUS_CHANGE)
    - Track dashboard metrics (followers, posts, replies, views)
    - Daily summaries
    - Error handling with local backup
    """
    
    def __init__(self, api_token: str = None, database_id: str = None):
        """
        Initialize Notion manager.
        
        Args:
            api_token: Notion API token (or reads from env var NOTION_API_KEY)
            database_id: Notion database ID (or reads from env var NOTION_DATABASE_ID)
        """
        # Get credentials from args or environment (no hardcoded fallbacks)
        self.api_token = api_token or os.getenv("NOTION_API_KEY")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")
        
        self.client = None
        self.enabled = False
        self.backup_log_file = Path("notion_backup.log")
        self.task_cache = {}  # Cache task IDs by name
        self.retry_count = 3
        self.retry_delay = 2
        
        # Check if notion-client is installed
        if not NOTION_AVAILABLE:
            import sys
            # Get the import error from module-level variable
            error_msg = globals().get('_notion_import_error')
            if error_msg:
                print(f"[NOTION] ⚠️ notion-client import failed: {type(error_msg).__name__}: {error_msg}")
                print(f"[NOTION] Python executable: {sys.executable}")
                print("[NOTION] Make sure you're using venv311 Python: venv311/bin/python3")
            else:
                print("[NOTION] ⚠️ notion-client not installed. Run: pip install notion-client in your venv")
            print("[NOTION] Falling back to local logging only.")
            return
        
        # Check if API key is provided
        if not self.api_token or self.api_token.strip() == "":
            print("[NOTION] ⚠️ NOTION_API_KEY is missing. Set it in your environment.")
            print("[NOTION] Add to .env file: NOTION_API_KEY=your_token_here")
            return
        
        # Check if database ID is provided
        if not self.database_id or self.database_id.strip() == "":
            print("[NOTION] ⚠️ NOTION_DATABASE_ID is missing. Set it in your environment.")
            print("[NOTION] Add to .env file: NOTION_DATABASE_ID=your_database_id_here")
            return
        
        # Try to initialize client and verify connection
        try:
            self.client = Client(auth=self.api_token)
            # Test connection with a minimal API call
            try:
                self.client.databases.retrieve(database_id=self.database_id)
                self.enabled = True
                print("[NOTION] ✅ Connected to Notion API")
                # Warm up cache by fetching existing tasks
                self._refresh_task_cache()
            except Exception as test_error:
                error_str = str(test_error)
                error_type = type(test_error).__name__
                
                # Provide more specific error messages
                if "unauthorized" in error_str.lower() or "401" in error_str or "invalid" in error_str.lower():
                    print(f"[NOTION] ⚠️ Connection test failed: {error_type}")
                    print(f"[NOTION] Token format: {self.api_token[:10]}... (length: {len(self.api_token)})")
                    print("[NOTION] 🔧 TO FIX:")
                    print("[NOTION]   1. Go to: https://www.notion.so/my-integrations")
                    print("[NOTION]   2. Find 'X Bot Activity Logger' (or create it)")
                    print("[NOTION]   3. Copy the token (should start with 'secret_' for new integrations)")
                    print("[NOTION]   4. CRITICAL: Share integration with database:")
                    print("[NOTION]      - Open your Tasks database in Notion")
                    print("[NOTION]      - Click '...' menu (top right) → 'Connections'")
                    print("[NOTION]      - Click 'Add connections' → Select 'X Bot Activity Logger'")
                    print("[NOTION]   5. Update .env file with new token")
                    print("[NOTION]   6. Restart bot")
                elif "not found" in error_str.lower() or "404" in error_str:
                    print("[NOTION] ⚠️ Connection test failed: database not found")
                    print(f"[NOTION] Database ID: {self.database_id[:8]}...")
                    print("[NOTION] Check your NOTION_DATABASE_ID is correct")
                else:
                    print(f"[NOTION] ⚠️ Connection test failed: {error_type}: {error_str}")
                    print("[NOTION] Check your API token and database ID")
                    print(f"[NOTION] Token present: {'Yes' if self.api_token else 'No'} (length: {len(self.api_token) if self.api_token else 0})")
                    print(f"[NOTION] Database ID present: {'Yes' if self.database_id else 'No'}")
                self._log_backup(f"CONNECTION_TEST_ERROR: {error_type}: {error_str}")
        except Exception as e:
            print(f"[NOTION] ⚠️ Failed to initialize Notion client: {e}")
            print("[NOTION] Check your API token format and network connection")
            self._log_backup(f"INIT_ERROR: {e}")
    
    def _refresh_task_cache(self):
        """Refresh internal cache of task names to page IDs"""
        if not self.enabled:
            return
        
        try:
            # Use direct API request to query database
            response = self.client.request(
                path=f"databases/{self.database_id}/query",
                method="POST",
                body={}
            )
            for page in response.get("results", []):
                props = page.get("properties", {})
                title_prop = props.get("Task name") or props.get("Title") or props.get("Name") or props.get("Task")
                if title_prop:
                    # Extract title from Notion property
                    title_text = ""
                    if title_prop.get("title"):
                        title_text = "".join([t.get("plain_text", "") for t in title_prop["title"]])
                    elif title_prop.get("rich_text"):
                        title_text = "".join([t.get("plain_text", "") for t in title_prop["rich_text"]])
                    if title_text:
                        self.task_cache[title_text] = page["id"]
        except Exception as e:
            # Cache refresh is non-critical, just log and continue
            pass  # Silently skip cache refresh - tasks will be found on-demand
    
    def _log_backup(self, message: str):
        """Log to local file as backup if Notion API fails"""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            with open(self.backup_log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} | {message}\n")
        except Exception:
            pass  # Don't crash if backup logging fails
    
    def _retry_api_call(self, func, *args, **kwargs):
        """Execute API call with retry logic and 5-second timeout per attempt"""
        max_retries = 2  # Max 2 retries as per requirements
        timeout_seconds = 5  # 5 second timeout per attempt
        
        for attempt in range(max_retries):
            try:
                # Use threading to implement timeout
                result = [None]
                exception = [None]
                
                def call_func():
                    try:
                        result[0] = func(*args, **kwargs)
                    except Exception as e:
                        exception[0] = e
                
                thread = threading.Thread(target=call_func)
                thread.daemon = True
                thread.start()
                thread.join(timeout=timeout_seconds)
                
                if thread.is_alive():
                    # Thread is still running, timed out
                    error_msg = f"Notion API call timed out after {timeout_seconds} seconds"
                    print(f"[NOTION] ⚠️ {error_msg}")
                    self._log_backup(error_msg)
                    if attempt < max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                    return None
                
                if exception[0]:
                    raise exception[0]
                
                if result[0] is not None:
                    return result[0]
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                else:
                    error_msg = f"API call failed after {max_retries} attempts: {e}"
                    print(f"[NOTION] ✗ {error_msg}")
                    self._log_backup(error_msg)
                    return None
        
        return None
    
    def _find_task_by_name(self, task_name: str) -> Optional[str]:
        """
        Find task page ID by name.
        
        Args:
            task_name: Name of the task to find
        
        Returns:
            str: Page ID if found, None otherwise
        """
        if not self.enabled:
            return None
        
        # Check cache first
        if task_name in self.task_cache:
            return self.task_cache[task_name]
        
        # Search database using direct API request
        try:
            # Try Task name property first
            response = self.client.request(
                path=f"databases/{self.database_id}/query",
                method="POST",
                body={
                    "filter": {
                        "property": "Task name",
                        "title": {
                            "equals": task_name
                        }
                    }
                }
            )
            
            results = response.get("results", [])
            if results:
                page_id = results[0]["id"]
                self.task_cache[task_name] = page_id
                return page_id
            
            # Try alternative property names
            for prop_name in ["Title", "Name", "Task"]:
                try:
                    response = self.client.request(
                        path=f"databases/{self.database_id}/query",
                        method="POST",
                        body={
                            "filter": {
                                "property": prop_name,
                                "title": {
                                    "equals": task_name
                                }
                            }
                        }
                    )
                    results = response.get("results", [])
                    if results:
                        page_id = results[0]["id"]
                        self.task_cache[task_name] = page_id
                        return page_id
                except Exception:
                    continue
            
            return None
        except Exception as e:
            # Non-critical error, just return None (task will be created if needed)
            return None
    
    def update_task_status(self, task_name: str, status: str, result_data: Optional[str] = None) -> bool:
        """
        Update task status in Notion.
        
        Args:
            task_name: Name of the task (e.g., "Stage 10", "Stage 11B", "Bot Status")
            status: Status value ("In Progress", "Done", "Blocked", "Not started")
            result_data: Optional description/result data to add
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.enabled:
            self._log_backup(f"UPDATE_STATUS: {task_name} -> {status} | {result_data}")
            return False
        
        # Map status to emoji indicators
        status_emoji = {
            "In Progress": "🟢",
            "Done": "✅",
            "Blocked": "🔴",
            "Not started": "⚪",
            "Error": "🔴"
        }
        status_display = f"{status_emoji.get(status, '')} {status}"
        
        def _update():
            page_id = self._find_task_by_name(task_name)
            
            if not page_id:
                # Task doesn't exist, create it
                return self._create_task(task_name, status, result_data)
            
            # Build update properties
            # Map status values to valid Notion status options
            status_mapping = {
                "In Progress": "In progress",
                "In progress": "In progress",
                "Done": "Done",
                "Blocked": "Done",  # Map Blocked to Done if Blocked doesn't exist
                "Not started": "Not started",
                "Not Started": "Not started",
                "Error": "Done",  # Map Error to Done if Error doesn't exist
                "Sleeping": "In progress"  # Map Sleeping to In progress
            }
            mapped_status = status_mapping.get(status, "In progress")  # Default to "In progress"
            
            properties = {
                "Status": {
                    "status": {
                        "name": mapped_status
                    }
                }
            }
            
            # Add description/notes if provided
            if result_data:
                # Try to update Description or Notes property
                properties["Description"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": result_data
                            }
                        }
                    ]
                }
            
            self.client.pages.update(page_id=page_id, properties=properties)
            print(f"[NOTION] ✓ Updated task '{task_name}' to {status_display}")
            return True
        
        result = self._retry_api_call(_update)
        if result:
            return True
        else:
            self._log_backup(f"UPDATE_STATUS: {task_name} -> {status} | {result_data}")
            return False
    
    def _create_task(self, task_name: str, status: str, description: Optional[str] = None) -> bool:
        """Create a new task in Notion database"""
        try:
            # Map status values to valid Notion status options
            status_mapping = {
                "In Progress": "In progress",
                "In progress": "In progress",
                "Done": "Done",
                "Blocked": "Done",  # Map Blocked to Done if Blocked doesn't exist
                "Not started": "Not started",
                "Not Started": "Not started",
                "Error": "Done",  # Map Error to Done if Error doesn't exist
                "Sleeping": "In progress"  # Map Sleeping to In progress
            }
            mapped_status = status_mapping.get(status, "Not started")  # Default to "Not started" for new tasks
            
            properties = {
                "Task name": {
                    "title": [
                        {
                            "text": {
                                "content": task_name
                            }
                        }
                    ]
                },
                "Status": {
                    "status": {
                        "name": mapped_status
                    }
                }
            }
            
            if description:
                properties["Description"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": description
                            }
                        }
                    ]
                }
            
            page = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties
            )
            
            page_id = page["id"]
            self.task_cache[task_name] = page_id
            print(f"[NOTION] ✓ Created new task: {task_name}")
            return True
        except Exception as e:
            print(f"[NOTION] ✗ Failed to create task '{task_name}': {e}")
            self._log_backup(f"CREATE_TASK_ERROR: {task_name} - {e}")
            return False
    
    def log_activity(self, action_type: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Log an activity to Notion (creates new row in Tasks Tracker).
        
        Args:
            action_type: Type of action ("POST", "REPLY", "VIDEO", "ERROR", "STATUS_CHANGE")
            message: Activity message/description
            metadata: Optional dict with additional data (url, text, market, etc.)
        
        Returns:
            str: Page ID if successful, None otherwise
        """
        if not self.enabled:
            self._log_backup(f"LOG_ACTIVITY: {action_type} | {message} | {metadata}")
            return None
        
        def _log():
            # Build title from action type and message
            title = f"{action_type}: {message[:100]}"  # Truncate if too long
            
            # Build description from metadata
            description_parts = [message]
            if metadata:
                for key, value in metadata.items():
                    if value:
                        description_parts.append(f"{key}: {value}")
            description = "\n".join(description_parts)
            
            properties = {
                "Task name": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Status": {
                    "status": {
                        "name": "In progress"  # Activity logs default to "In progress"
                    }
                }
            }
            
            # Add Description if we have metadata
            if description:
                properties["Description"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": description[:2000]  # Notion limit
                            }
                        }
                    ]
                }
            
            # Add timestamp (try with Date first, retry without if it fails)
            properties_with_date = properties.copy()
            try:
                properties_with_date["Date"] = {
                    "date": {
                        "start": datetime.now(timezone.utc).isoformat()
                    }
                }
            except Exception:
                pass  # Date property might not exist
            
            # Try creating page with Date property first
            try:
                page = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties_with_date
                )
            except Exception as date_error:
                # If Date property doesn't exist, retry without it
                if "Date" in str(date_error) or "property" in str(date_error).lower():
                    print(f"[NOTION] Warning: Date property not found, retrying without Date field")
                    page = self.client.pages.create(
                        parent={"database_id": self.database_id},
                        properties=properties
                    )
                else:
                    # Re-raise if it's a different error
                    raise
            
            page_id = page["id"]
            print(f"[NOTION] ✓ Logged activity: {action_type} - {message[:50]}")
            return page_id
        
        result = self._retry_api_call(_log)
        if not result:
            self._log_backup(f"LOG_ACTIVITY: {action_type} | {message} | {metadata}")
        return result
    
    def update_dashboard_metrics(self, followers: int = None, posts_today: int = None, 
                                  replies_today: int = None, views_avg: float = None) -> bool:
        """
        Update dashboard metrics in Notion.
        
        Creates or updates a "Dashboard Metrics" task with current stats.
        
        Args:
            followers: Current follower count
            posts_today: Number of posts today
            replies_today: Number of replies today
            views_avg: Average views per post
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.enabled:
            metrics_str = f"Followers: {followers}, Posts: {posts_today}, Replies: {replies_today}, Views: {views_avg}"
            self._log_backup(f"METRICS: {metrics_str}")
            return False
        
        def _update():
            metrics_text = "📊 Dashboard Metrics\n\n"
            if followers is not None:
                metrics_text += f"👥 Followers: {followers}\n"
            if posts_today is not None:
                metrics_text += f"📝 Posts Today: {posts_today}\n"
            if replies_today is not None:
                metrics_text += f"💬 Replies Today: {replies_today}\n"
            if views_avg is not None:
                metrics_text += f"👀 Avg Views: {views_avg:.1f}\n"
            
            metrics_text += f"\n📅 Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            
            # Update or create dashboard metrics task
            return self.update_task_status("Dashboard Metrics", "In Progress", metrics_text)
        
        return self._retry_api_call(_update) or False
    
    def log_post_performance(self, post_id: str, views: int = None, clicks: int = None, 
                            likes: int = None, timestamp: Optional[datetime] = None) -> bool:
        """
        Log post performance metrics after 1 hour.
        
        Args:
            post_id: Post/tweet ID
            views: Number of views
            clicks: Number of link clicks (if applicable)
            likes: Number of likes
            timestamp: When the metrics were collected
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.enabled:
            self._log_backup(f"PERFORMANCE: {post_id} | Views: {views}, Clicks: {clicks}, Likes: {likes}")
            return False
        
        perf_text = f"Post ID: {post_id}\n"
        if views is not None:
            perf_text += f"Views: {views}\n"
        if clicks is not None:
            perf_text += f"Clicks: {clicks}\n"
            if views and views > 0:
                ctr = (clicks / views) * 100
                perf_text += f"CTR: {ctr:.2f}%\n"
        if likes is not None:
            perf_text += f"Likes: {likes}\n"
        if timestamp:
            perf_text += f"Collected: {timestamp.isoformat()}"
        
        metadata = {
            "post_id": post_id,
            "views": str(views) if views else "N/A",
            "clicks": str(clicks) if clicks else "N/A",
            "likes": str(likes) if likes else "N/A"
        }
        
        return self.log_activity("PERFORMANCE", f"Post {post_id} metrics", metadata) is not None
    
    def create_daily_summary(self, date: Optional[datetime] = None) -> bool:
        """
        Create a daily summary entry in Notion.
        
        Args:
            date: Date for summary (defaults to today)
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        if date is None:
            date = datetime.now(timezone.utc)
        
        summary_date = date.strftime("%Y-%m-%d")
        summary_title = f"Daily Summary - {summary_date}"
        
        # This would be called with actual metrics
        # For now, just create the entry
        return self.log_activity("STATUS_CHANGE", summary_title, {"date": summary_date}) is not None


# Global instance
NOTION_MANAGER = None

def init_notion_manager(api_token: str = None, database_id: str = None) -> NotionManager:
    """Initialize global Notion manager instance"""
    global NOTION_MANAGER
    NOTION_MANAGER = NotionManager(api_token=api_token, database_id=database_id)
    return NOTION_MANAGER

