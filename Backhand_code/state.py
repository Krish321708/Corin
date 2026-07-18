# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: state.py
# ROLE: Thread-safe shared telemetry store. Every background daemon writes
#       here. The main rendering loop reads snapshots from here.
#       No rendering logic. No network calls. Pure data container.
# =============================================================================

import time
import threading
import collections
from typing import Any, Dict, List, Optional
from Backhand_code.config import (
    ActiveConfig, UIMode,
    ARCHER_SOUL_PATH, HUDSON_SOUL_PATH, USERS_MD_PATH,
    SESSION_TOKEN_LIMIT, FFT_BANDS,
)

# Attempt numpy import with fallback
try:
    import numpy as np
    NUMPY_AVAILABLE: bool = True
except ImportError:
    import array as arr
    NUMPY_AVAILABLE: bool = False

# =============================================================================
# SECTION 1: RING BUFFER
# =============================================================================

class RingBuffer:
    """
    Fixed-capacity circular buffer for storing streaming telemetry history.
    Thread-safe via an internal RLock.
    Used for CPU temperature history, ping latency history,
    CPU/RAM usage trends, and EKG sample history.

    FIFO semantics: oldest entry is evicted when capacity is exceeded.
    """

    def __init__(self, capacity: int) -> None:
        """
        Args:
            capacity: Maximum number of entries the buffer holds.
                      When full, the oldest entry is discarded on push().
        """
        if capacity < 1:
            raise ValueError(f"RingBuffer capacity must be >= 1, got {capacity}.")
        self._capacity: int                      = capacity
        self._buffer:   collections.deque        = collections.deque(maxlen=capacity)
        self._lock:     threading.RLock          = threading.RLock()

    def push(self, value: float) -> None:
        """
        Appends a new value to the buffer.
        If at capacity, the oldest value is automatically evicted.

        Args:
            value: Float telemetry value to store.
        """
        with self._lock:
            self._buffer.append(float(value))

    def data(self) -> List[float]:
        """
        Returns a snapshot copy of all current buffer contents,
        ordered oldest-first.

        Returns:
            List of floats (length <= capacity).
        """
        with self._lock:
            return list(self._buffer)

    def latest(self) -> float:
        """
        Returns the most recently pushed value without removing it.
        Returns 0.0 if the buffer is empty.

        Returns:
            Most recent float value, or 0.0 if empty.
        """
        with self._lock:
            if not self._buffer:
                return 0.0
            return self._buffer[-1]

    def average(self) -> float:
        """
        Returns the arithmetic mean of all values currently in the buffer.
        Returns 0.0 if the buffer is empty.

        Returns:
            Mean float value.
        """
        with self._lock:
            if not self._buffer:
                return 0.0
            return sum(self._buffer) / len(self._buffer)

    def minimum(self) -> float:
        """Returns the minimum value currently in the buffer. 0.0 if empty."""
        with self._lock:
            if not self._buffer:
                return 0.0
            return min(self._buffer)

    def maximum(self) -> float:
        """Returns the maximum value currently in the buffer. 0.0 if empty."""
        with self._lock:
            if not self._buffer:
                return 0.0
            return max(self._buffer)

    def is_full(self) -> bool:
        """Returns True if the buffer has reached its maximum capacity."""
        with self._lock:
            return len(self._buffer) == self._capacity

    def clear(self) -> None:
        """Removes all entries from the buffer."""
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def __repr__(self) -> str:
        with self._lock:
            return (f"RingBuffer(capacity={self._capacity}, "
                    f"size={len(self._buffer)}, "
                    f"latest={self.latest():.3f})")


# =============================================================================
# SECTION 2: HUDSON TASK ENTRY
# =============================================================================

class HudsonTask:
    """
    Represents a single background task performed by the Hudson daemon.
    Stored in the Hudson activity log displayed in the overlay panel (H key).
    """

    STATUS_PENDING:    str = "PENDING"
    STATUS_ANALYZING:  str = "ANALYZING"
    STATUS_RUNNING:    str = "RUNNING"
    STATUS_COMPLETE:   str = "COMPLETE"
    STATUS_FAILED:     str = "FAILED"
    STATUS_ESCALATED:  str = "ESCALATED"   # flagged to user (hard GitHub issue)

    def __init__(
        self,
        task_id:     str,
        task_type:   str,
        description: str,
        repo:        Optional[str] = None,
    ) -> None:
        """
        Args:
            task_id:     Unique identifier string (e.g. "TASK-0042").
            task_type:   Category string: "GITHUB", "NEWS", "MONITOR",
                         "CRON", "ALERT", "MEMORY", "SOCIAL".
            description: Human-readable task description.
            repo:        GitHub repo name if task_type == "GITHUB".
        """
        self.task_id:      str            = task_id
        self.task_type:    str            = task_type
        self.description:  str            = description
        self.repo:         Optional[str]  = repo
        self.status:       str            = HudsonTask.STATUS_PENDING
        self.created_at:   float          = time.time()
        self.updated_at:   float          = time.time()
        self.log_lines:    List[str]      = []
        self.result:       str            = ""

    def update_status(self, status: str, log_line: str = "") -> None:
        """
        Updates task status and optionally appends a log line.

        Args:
            status:   One of the STATUS_ class constants.
            log_line: Optional string to append to this task's log.
        """
        self.status     = status
        self.updated_at = time.time()
        if log_line:
            timestamp = time.strftime("%H:%M:%S", time.localtime(self.updated_at))
            self.log_lines.append(f"[{timestamp}] {log_line}")
            # Cap log lines to prevent unbounded growth
            if len(self.log_lines) > 50:
                self.log_lines = self.log_lines[-50:]

    def age_seconds(self) -> float:
        """Returns seconds since this task was created."""
        return time.time() - self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the task to a plain dictionary for JSON export."""
        return {
            "task_id":     self.task_id,
            "task_type":   self.task_type,
            "description": self.description,
            "repo":        self.repo,
            "status":      self.status,
            "created_at":  self.created_at,
            "updated_at":  self.updated_at,
            "log_lines":   self.log_lines,
            "result":      self.result,
        }

    def __repr__(self) -> str:
        return (f"HudsonTask(id={self.task_id}, type={self.task_type}, "
                f"status={self.status})")


# =============================================================================
# SECTION 3: NEWS ARTICLE ENTRY
# =============================================================================

class NewsArticle:
    """
    Structured container for a single scraped and NLP-processed news article.
    Matches the 5-column JSON schema defined in the specification:
        headline, main_points, source, time, coordinates
    """

    def __init__(
        self,
        headline:     str,
        main_points:  List[str],
        source:       str,
        pub_time:     str,
        latitude:     float,
        longitude:    float,
        raw_url:      str  = "",
        raw_text:     str  = "",
    ) -> None:
        """
        Args:
            headline:    Article headline string.
            main_points: List of extracted key point strings (3-5 points).
            source:      Publisher name string (e.g. "BBC News").
            pub_time:    ISO-format publication timestamp string.
            latitude:    Geographic latitude of event location [-90, 90].
            longitude:   Geographic longitude of event location [-180, 180].
            raw_url:     Original article URL.
            raw_text:    Full raw article text (used by NLP, not displayed).
        """
        self.headline:    str        = headline
        self.main_points: List[str]  = main_points
        self.source:      str        = source
        self.pub_time:    str        = pub_time
        self.latitude:    float      = float(latitude)
        self.longitude:   float      = float(longitude)
        self.raw_url:     str        = raw_url
        self.raw_text:    str        = raw_text
        self.fetched_at:  float      = time.time()
        self.article_id:  str        = (
            f"{source[:8].upper().replace(' ','_')}"
            f"_{int(self.fetched_at)}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes to the 5-column JSON schema."""
        return {
            "article_id":   self.article_id,
            "headline":     self.headline,
            "main_points":  self.main_points,
            "source":       self.source,
            "time":         self.pub_time,
            "coordinates":  {
                "latitude":  self.latitude,
                "longitude": self.longitude,
            },
            "raw_url":      self.raw_url,
            "fetched_at":   self.fetched_at,
        }

    def __repr__(self) -> str:
        return (f"NewsArticle(id={self.article_id}, "
                f"source={self.source}, "
                f"lat={self.latitude:.2f}, lon={self.longitude:.2f})")


# =============================================================================
# SECTION 4: SOCIAL MESSAGE ENTRY
# =============================================================================

class SocialMessage:
    """
    Represents a single incoming social notification from WhatsApp,
    Instagram DM, or Gmail.
    """

    PLATFORM_WHATSAPP:  str = "WHATSAPP"
    PLATFORM_INSTAGRAM: str = "INSTAGRAM"
    PLATFORM_GMAIL:     str = "GMAIL"
    PLATFORM_REDDIT:    str = "REDDIT"

    STATUS_UNREAD:  str = "UNREAD"
    STATUS_READ:    str = "READ"
    STATUS_REPLIED: str = "REPLIED"
    STATUS_DRAFTED: str = "DRAFTED"

    def __init__(
        self,
        platform:    str,
        sender:      str,
        preview:     str,
        full_body:   str  = "",
        thread_id:   str  = "",
        account_idx: int  = 0,
    ) -> None:
        """
        Args:
            platform:    One of the PLATFORM_ class constants.
            sender:      Display name or username of the sender.
            preview:     Short message preview (first ~60 chars).
            full_body:   Full message body text.
            thread_id:   Platform-specific thread/conversation ID.
            account_idx: Instagram account index (0, 1, or 2) for
                         multi-account Instagram support. 0 for others.
        """
        self.platform:    str   = platform
        self.sender:      str   = sender
        self.preview:     str   = preview
        self.full_body:   str   = full_body
        self.thread_id:   str   = thread_id
        self.account_idx: int   = account_idx
        self.status:      str   = SocialMessage.STATUS_UNREAD
        self.received_at: float = time.time()
        self.msg_id:      str   = f"{platform[:2]}_{int(self.received_at * 1000)}"

    def mark_read(self) -> None:
        """Marks this message as read."""
        self.status = SocialMessage.STATUS_READ

    def mark_replied(self) -> None:
        """Marks this message as replied."""
        self.status = SocialMessage.STATUS_REPLIED

    def to_dict(self) -> Dict[str, Any]:
        """Serializes to a plain dictionary."""
        return {
            "msg_id":      self.msg_id,
            "platform":    self.platform,
            "sender":      self.sender,
            "preview":     self.preview,
            "full_body":   self.full_body,
            "thread_id":   self.thread_id,
            "account_idx": self.account_idx,
            "status":      self.status,
            "received_at": self.received_at,
        }

    def __repr__(self) -> str:
        return (f"SocialMessage(platform={self.platform}, "
                f"sender={self.sender}, status={self.status})")


# =============================================================================
# SECTION 5: SYSTEM ALERT ENTRY
# =============================================================================

class SystemAlert:
    """
    Represents a critical system alert generated by the proactive daemon.
    Displayed in the notifications panel and triggers the alarm sound.
    """

    SEVERITY_INFO:     str = "INFO"
    SEVERITY_WARNING:  str = "WARNING"
    SEVERITY_CRITICAL: str = "CRITICAL"

    CATEGORY_THERMAL:  str = "THERMAL"
    CATEGORY_NETWORK:  str = "NETWORK"
    CATEGORY_SECURITY: str = "SECURITY"
    CATEGORY_GITHUB:   str = "GITHUB"
    CATEGORY_RESOURCE: str = "RESOURCE"
    CATEGORY_SYSTEM:   str = "SYSTEM"

    def __init__(
        self,
        message:   str,
        severity:  str,
        category:  str,
    ) -> None:
        self.message:    str   = message
        self.severity:   str   = severity
        self.category:   str   = category
        self.created_at: float = time.time()
        self.alert_id:   str   = f"ALT_{int(self.created_at * 1000)}"
        self.dismissed:  bool  = False

    def dismiss(self) -> None:
        """Marks the alert as dismissed (no longer shown in active panel)."""
        self.dismissed = True

    def age_seconds(self) -> float:
        """Returns how old this alert is in seconds."""
        return time.time() - self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id":   self.alert_id,
            "message":    self.message,
            "severity":   self.severity,
            "category":   self.category,
            "created_at": self.created_at,
            "dismissed":  self.dismissed,
        }

    def __repr__(self) -> str:
        return (f"SystemAlert(id={self.alert_id}, "
                f"severity={self.severity}, "
                f"category={self.category})")


# =============================================================================
# SECTION 6: SESSION TOKEN TRACKER
# =============================================================================

class SessionTokenTracker:
    """
    Tracks the running token count for the current conversation session.
    When the count exceeds SESSION_TOKEN_LIMIT, triggers a session flush
    which saves memory files and resets the context window.

    Token estimation uses a simple 4-characters-per-token approximation,
    which is accurate enough for session boundary detection without
    requiring a full tokenizer library.
    """

    CHARS_PER_TOKEN: float = 4.0

    def __init__(self, limit: int = SESSION_TOKEN_LIMIT) -> None:
        self._limit:    int            = limit
        self._count:    int            = 0
        self._lock:     threading.RLock = threading.RLock()
        self._flushed:  bool           = False

    def add_text(self, text: str) -> bool:
        """
        Adds text to the running token estimate.
        Returns True if the limit has been exceeded (session should flush).

        Args:
            text: String to estimate token count from.

        Returns:
            True if cumulative token count now exceeds SESSION_TOKEN_LIMIT.
        """
        estimated_tokens = max(1, int(len(text) / self.CHARS_PER_TOKEN))
        with self._lock:
            self._count += estimated_tokens
            if self._count >= self._limit and not self._flushed:
                self._flushed = True
                return True
            return False

    def reset(self) -> None:
        """Resets the counter after a successful session flush."""
        with self._lock:
            self._count   = 0
            self._flushed = False

    def current_count(self) -> int:
        """Returns the current estimated token count."""
        with self._lock:
            return self._count

    def remaining(self) -> int:
        """Returns estimated tokens remaining before session flush."""
        with self._lock:
            return max(0, self._limit - self._count)

    def percentage_used(self) -> float:
        """Returns percentage of token limit consumed [0.0, 100.0]."""
        with self._lock:
            return min(100.0, (self._count / self._limit) * 100.0)

    def __repr__(self) -> str:
        return (f"SessionTokenTracker("
                f"count={self._count}, "
                f"limit={self._limit}, "
                f"pct={self.percentage_used():.1f}%)")


# =============================================================================
# SECTION 7: HERMES STATE - CENTRAL THREAD-SAFE TELEMETRY STORE
# =============================================================================

class HermesState:
    """
    Central thread-safe telemetry and interface data store for Project HERMES.

    All background daemon threads write exclusively through set() / batch_set().
    The main rendering loop reads exclusively through snapshot() / get().
    The re-entrant lock (RLock) allows the same thread to acquire nested locks
    without deadlocking (e.g. a daemon calling multiple set() operations
    within a single logical update cycle).

    Data categories managed:
        - Hardware telemetry (CPU, RAM, disk, network, temperature)
        - Audio DSP state (FFT bands, volume RMS)
        - Voice I/O state (transcript, TTS queue)
        - LLM stream buffers (Archer, Hudson)
        - News articles (NewsArticle list)
        - Social messages (SocialMessage list per platform)
        - System alerts (SystemAlert list)
        - GitHub task activity (HudsonTask list)
        - UI state (active mode, brainstorm mode, terminal visibility)
        - Memory session state (token counts, flush flags)
        - Globe coordinate pins (from news NLP)
        - Reddit preference profile
    """

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()

        # Initialize FFT array
        if NUMPY_AVAILABLE:
            _fft_init = list(__import__('numpy').zeros(FFT_BANDS, dtype=float))
        else:
            _fft_init = [0.0] * FFT_BANDS

        # -----------------------------------------------------------------------
        # Core telemetry dictionary
        # All values are plain Python primitives or HERMES data objects.
        # -----------------------------------------------------------------------
        self._data: Dict[str, Any] = {

            # ------------------------------------------------------------------
            # HARDWARE TELEMETRY
            # ------------------------------------------------------------------
            "cpu_temp":           40.0,        # float: degrees Celsius
            "cpu_usage":          0.0,          # float: overall CPU percent [0,100]
            "cpu_per_core":       [],           # List[float]: per-core usage percent
            "ram_usage":          0.0,          # float: RAM usage percent [0,100]
            "ram_used_gb":        0.0,          # float: RAM used in GB
            "ram_total_gb":       0.0,          # float: total RAM in GB
            "disk_read_mb":       0.0,          # float: disk read rate MB/s
            "disk_write_mb":      0.0,          # float: disk write rate MB/s
            "disk_usage_pct":     0.0,          # float: disk usage percent
            "net_sent_mb":        0.0,          # float: network sent MB/s
            "net_recv_mb":        0.0,          # float: network received MB/s
            "ping_ms":            0.0,          # float: latest ping milliseconds
            "internet_up":        False,        # bool: connectivity confirmed
            "stability_score":    100.0,        # float: composite health [0,100]
            "core_health":        100.0,        # float: hardware health [0,100]
            "active_threads":     0,            # int: live Python thread count
            "system_uptime_secs": 0.0,          # float: seconds since boot

            # ------------------------------------------------------------------
            # AUDIO DSP
            # ------------------------------------------------------------------
            "audio_fft":          _fft_init,   # List[float]: 64-band FFT [0,1]
            "audio_volume":       0.0,          # float: RMS volume [0,1]
            "audio_speaking":     False,        # bool: voice actively detected
            "audio_ai_speaking":  False,        # bool: TTS currently playing

            # ------------------------------------------------------------------
            # VOICE I/O
            # ------------------------------------------------------------------
            "transcript":         "",           # str: latest STT result
            "last_transcript":    "",           # str: previous STT result
            "tts_queue":          [],           # List[str]: sentences queued for TTS
            "voice_muted":        False,        # bool: voice output muted flag

            # ------------------------------------------------------------------
            # LLM STREAMS
            # ------------------------------------------------------------------
            "archer_stream":      "",           # str: Archer live token stream
            "archer_full":        "",           # str: Archer complete last response
            "hudson_stream":      "",           # str: Hudson live token stream
            "hudson_full":        "",           # str: Hudson complete last response
            "active_persona":     UIMode.ARCHER, # str: which persona is responding
            "llm_thinking":       False,        # bool: API call in flight

            # ------------------------------------------------------------------
            # NEWS & GLOBE
            # ------------------------------------------------------------------
            "news_articles":      [],           # List[NewsArticle]
            "news_selected_idx":  -1,           # int: index of clicked article (-1=none)
            "globe_pins":         [],           # List[dict]: {lat, lon, article_id}
            "globe_yaw":          0.0,          # float: accumulated yaw angle (radians)

            # ------------------------------------------------------------------
            # SOCIAL MESSAGES
            # ------------------------------------------------------------------
            "whatsapp_messages":  [],           # List[SocialMessage]
            "instagram_messages": [],           # List[SocialMessage] (all accounts)
            "gmail_messages":     [],           # List[SocialMessage]
            "reddit_posts":       [],           # List[dict]: reddit post dicts
            "social_active_msg":  None,         # SocialMessage | None: open message
            "social_panel_open":  False,        # bool: social view replacing terrain
            "social_platform":    "",           # str: which platform is open

            # ------------------------------------------------------------------
            # SYSTEM ALERTS
            # ------------------------------------------------------------------
            "system_alerts":      [],           # List[SystemAlert]
            "alert_flash_state":  False,        # bool: toggled by proactive daemon

            # ------------------------------------------------------------------
            # GITHUB TASKS
            # ------------------------------------------------------------------
            "hudson_tasks":       [],           # List[HudsonTask]
            "github_connected":   False,        # bool: GitHub token validated
            "github_repos":       [],           # List[str]: repo full names
            "github_token":       ActiveConfig.github_token,  # str: PAT

            # ------------------------------------------------------------------
            # UI STATE
            # ------------------------------------------------------------------
            "ui_mode":            UIMode.ARCHER, # str: current UI mode
            "brainstorm_active":  False,         # bool: brainstorm mode fullscreen
            "terminal_open":      False,         # bool: terminal expanded
            "terminal_input":     "",            # str: current terminal input buffer
            "terminal_history":   [],            # List[str]: displayed terminal lines
            "hudson_overlay_open": False,        # bool: Hudson activity overlay
            "fullscreen_globe":   False,         # bool: globe tactical fullscreen
            "social_view_open":   False,         # bool: social panel active
            "news_tactical_open": False,         # bool: news tactical overlay open
            "reddit_setup_open":  False,         # bool: Reddit preference screen open

            # ------------------------------------------------------------------
            # MEMORY & SESSION
            # ------------------------------------------------------------------
            "session_flush_pending": False,     # bool: memory save triggered
            "archer_token_count":    0,         # int: Archer session token estimate
            "hudson_token_count":    0,         # int: Hudson session token estimate
            "boot_time":             time.time(), # float: epoch at system start

            # ------------------------------------------------------------------
            # REDDIT PREFERENCES
            # ------------------------------------------------------------------
            "reddit_preferences": {},           # dict: {category: bool}
            "reddit_learned_tags": [],          # List[str]: inferred tags

            # ------------------------------------------------------------------
            # BRAINSTORMING SESSION
            # ------------------------------------------------------------------
            "brainstorm_exchanges": [],         # List[dict]: {speaker, text, ts}
            "brainstorm_topic":     "",         # str: inferred topic for filename

            # ------------------------------------------------------------------
            # PERFORMANCE TIER
            # ------------------------------------------------------------------
            "performance_tier":   ActiveConfig.performance_tier,

        }

        # -----------------------------------------------------------------------
        # Ring buffers for time-series telemetry history
        # Stored separately from _data for direct RingBuffer method access.
        # -----------------------------------------------------------------------
        self.temp_history:    RingBuffer = RingBuffer(capacity=120)
        self.ping_history:    RingBuffer = RingBuffer(capacity=120)
        self.cpu_history:     RingBuffer = RingBuffer(capacity=120)
        self.ram_history:     RingBuffer = RingBuffer(capacity=120)
        self.volume_history:  RingBuffer = RingBuffer(capacity=64)
        self.ekg_history:     RingBuffer = RingBuffer(capacity=256)

        # -----------------------------------------------------------------------
        # Session token trackers (one per persona)
        # -----------------------------------------------------------------------
        self.archer_tracker: SessionTokenTracker = SessionTokenTracker()
        self.hudson_tracker: SessionTokenTracker = SessionTokenTracker()

        # -----------------------------------------------------------------------
        # Hudson task ID counter (atomic via lock)
        # -----------------------------------------------------------------------
        self._task_counter: int = 0

    # ===========================================================================
    # SECTION 7.1: ATOMIC READ / WRITE INTERFACE
    # ===========================================================================

    def get(self, key: str, default: Any = None) -> Any:
        """
        Thread-safe read of a single telemetry value.

        Args:
            key:     State dictionary key string.
            default: Value to return if key is not found.

        Returns:
            Current value stored at key, or default.
        """
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Thread-safe write of a single telemetry value.

        Args:
            key:   State dictionary key string.
            value: New value to store. Must be a plain Python primitive
                   or a HERMES data object (NewsArticle, SocialMessage, etc.).
        """
        with self._lock:
            self._data[key] = value

    def batch_set(self, updates: Dict[str, Any]) -> None:
        """
        Thread-safe atomic write of multiple telemetry values in one lock
        acquisition. Preferred over multiple individual set() calls when
        updating related fields that must be consistent with each other.

        Args:
            updates: Dictionary of {key: value} pairs to write atomically.
        """
        with self._lock:
            for key, value in updates.items():
                self._data[key] = value

    def snapshot(self) -> Dict[str, Any]:
        """
        Returns a shallow-copy snapshot of the entire state dictionary.
        Called once per frame by the main rendering loop.

        The shallow copy prevents the rendering loop from seeing mid-update
        state mutations while keeping copy overhead minimal.
        Mutable objects (lists, dicts) inside the snapshot are NOT deep-copied
        — renderers must treat them as read-only.

        Returns:
            Shallow dict copy of the current state.
        """
        with self._lock:
            return dict(self._data)

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Thread-safe read of multiple keys in a single lock acquisition.

        Args:
            keys: List of state dictionary key strings.

        Returns:
            Dictionary of {key: value} for all requested keys that exist.
        """
        with self._lock:
            return {k: self._data[k] for k in keys if k in self._data}

    # ===========================================================================
    # SECTION 7.2: LIST MUTATION HELPERS
    # ===========================================================================

    def append_to(self, key: str, item: Any, max_length: int = 0) -> None:
        """
        Thread-safe append to a list stored in the state dictionary.
        Optionally caps the list length by removing the oldest entry
        when max_length is exceeded (FIFO eviction).

        Args:
            key:        State key whose value is a list.
            item:       Item to append.
            max_length: If > 0, evict oldest items to maintain this length.
        """
        with self._lock:
            if key not in self._data:
                self._data[key] = []
            if not isinstance(self._data[key], list):
                self._data[key] = []
            self._data[key].append(item)
            if max_length > 0:
                while len(self._data[key]) > max_length:
                    self._data[key].pop(0)

    def prepend_to(self, key: str, item: Any, max_length: int = 0) -> None:
        """
        Thread-safe prepend (insert at index 0) to a list in the state.
        Newest items appear first. Used for notification feeds.

        Args:
            key:        State key whose value is a list.
            item:       Item to prepend.
            max_length: If > 0, evict oldest items from end of list.
        """
        with self._lock:
            if key not in self._data:
                self._data[key] = []
            if not isinstance(self._data[key], list):
                self._data[key] = []
            self._data[key].insert(0, item)
            if max_length > 0:
                while len(self._data[key]) > max_length:
                    self._data[key].pop()

    def remove_from(self, key: str, item: Any) -> bool:
        """
        Thread-safe removal of an item from a list in the state.

        Args:
            key:  State key whose value is a list.
            item: Item to remove (first occurrence).

        Returns:
            True if item was found and removed, False otherwise.
        """
        with self._lock:
            if key not in self._data:
                return False
            lst = self._data[key]
            if not isinstance(lst, list):
                return False
            try:
                lst.remove(item)
                return True
            except ValueError:
                return False

    def clear_list(self, key: str) -> None:
        """
        Thread-safe clearing of a list stored at the given key.

        Args:
            key: State key whose value is a list.
        """
        with self._lock:
            if key in self._data and isinstance(self._data[key], list):
                self._data[key].clear()

    # ===========================================================================
    # SECTION 7.3: DOMAIN-SPECIFIC HELPERS
    # ===========================================================================

    def add_news_article(self, article: "NewsArticle") -> None:
        """
        Adds a NewsArticle to the news feed and registers its coordinate pin
        on the globe. Keeps the newest 50 articles.

        Args:
            article: Fully constructed NewsArticle instance.
        """
        with self._lock:
            # Prepend (newest first)
            self._data["news_articles"].insert(0, article)
            while len(self._data["news_articles"]) > 50:
                self._data["news_articles"].pop()

            # Register globe pin
            pin = {
                "article_id": article.article_id,
                "lat":        article.latitude,
                "lon":        article.longitude,
                "headline":   article.headline[:40],
            }
            self._data["globe_pins"].insert(0, pin)
            while len(self._data["globe_pins"]) > 50:
                self._data["globe_pins"].pop()

    def add_social_message(self, message: "SocialMessage") -> None:
        """
        Adds a SocialMessage to the appropriate platform list.
        Keeps the newest 30 messages per platform.

        Args:
            message: Fully constructed SocialMessage instance.
        """
        with self._lock:
            platform = message.platform
            if platform == SocialMessage.PLATFORM_WHATSAPP:
                key = "whatsapp_messages"
            elif platform == SocialMessage.PLATFORM_INSTAGRAM:
                key = "instagram_messages"
            elif platform == SocialMessage.PLATFORM_GMAIL:
                key = "gmail_messages"
            elif platform == SocialMessage.PLATFORM_REDDIT:
                key = "reddit_posts"
            else:
                return

            self._data[key].insert(0, message)
            while len(self._data[key]) > 30:
                self._data[key].pop()

    def add_system_alert(self, alert: "SystemAlert") -> None:
        """
        Adds a SystemAlert to the active alerts list.
        Automatically dismisses alerts older than 5 minutes.
        Keeps maximum 10 active (non-dismissed) alerts.

        Args:
            alert: Fully constructed SystemAlert instance.
        """
        with self._lock:
            now = time.time()
            # Auto-dismiss stale alerts
            for existing in self._data["system_alerts"]:
                if existing.age_seconds() > 300.0:
                    existing.dismiss()
            # Remove dismissed alerts
            self._data["system_alerts"] = [
                a for a in self._data["system_alerts"] if not a.dismissed
            ]
            # Prepend new alert
            self._data["system_alerts"].insert(0, alert)
            # Cap at 10 active alerts
            while len(self._data["system_alerts"]) > 10:
                self._data["system_alerts"].pop()

    def create_hudson_task(
        self,
        task_type:   str,
        description: str,
        repo:        Optional[str] = None,
    ) -> "HudsonTask":
        """
        Creates a new HudsonTask, registers it in the task log,
        and returns it for the calling daemon to manage.

        Args:
            task_type:   HudsonTask.task_type category string.
            description: Human-readable task description.
            repo:        GitHub repo name (optional).

        Returns:
            The newly created and registered HudsonTask instance.
        """
        with self._lock:
            self._task_counter += 1
            task_id = f"TASK-{self._task_counter:04d}"
            task    = HudsonTask(
                task_id=task_id,
                task_type=task_type,
                description=description,
                repo=repo,
            )
            self._data["hudson_tasks"].insert(0, task)
            # Keep only the most recent 100 tasks
            while len(self._data["hudson_tasks"]) > 100:
                self._data["hudson_tasks"].pop()
            return task

    def update_hudson_task(
        self,
        task: "HudsonTask",
        status: str,
        log_line: str = "",
    ) -> None:
        """
        Updates a HudsonTask status and log.
        The task object is mutable and already in the list —
        this method exists for clarity and ensures lock safety.

        Args:
            task:     HudsonTask instance to update.
            status:   New status string.
            log_line: Optional log line to append.
        """
        with self._lock:
            task.update_status(status, log_line)

    def get_unread_count(self, platform: str) -> int:
        """
        Returns the count of unread messages for a given platform.

        Args:
            platform: SocialMessage.PLATFORM_ constant string.

        Returns:
            Integer count of unread messages.
        """
        with self._lock:
            if platform == SocialMessage.PLATFORM_WHATSAPP:
                msgs = self._data["whatsapp_messages"]
            elif platform == SocialMessage.PLATFORM_INSTAGRAM:
                msgs = self._data["instagram_messages"]
            elif platform == SocialMessage.PLATFORM_GMAIL:
                msgs = self._data["gmail_messages"]
            else:
                return 0
            return sum(
                1 for m in msgs
                if isinstance(m, SocialMessage)
                and m.status == SocialMessage.STATUS_UNREAD
            )

    def get_active_alerts(self) -> List["SystemAlert"]:
        """
        Returns a snapshot list of all non-dismissed system alerts.

        Returns:
            List of active SystemAlert instances (newest first).
        """
        with self._lock:
            return [
                a for a in self._data["system_alerts"]
                if not a.dismissed
            ]

    def dismiss_alert(self, alert_id: str) -> bool:
        """
        Dismisses a system alert by its ID string.

        Args:
            alert_id: The alert_id string of the alert to dismiss.

        Returns:
            True if the alert was found and dismissed, False otherwise.
        """
        with self._lock:
            for alert in self._data["system_alerts"]:
                if alert.alert_id == alert_id:
                    alert.dismiss()
                    return True
            return False

    def open_social_message(self, message: "SocialMessage") -> None:
        """
        Sets the given message as the currently active social message,
        opens the social panel (replaces terrain viewport), and marks
        the message as read.

        Args:
            message: SocialMessage to open.
        """
        with self._lock:
            message.mark_read()
            self._data["social_active_msg"]  = message
            self._data["social_panel_open"]  = True
            self._data["social_platform"]    = message.platform
            self._data["social_view_open"]   = True

    def close_social_panel(self) -> None:
        """
        Closes the social message panel and returns the terrain viewport.
        Called after a message is sent or the return button is pressed.
        """
        with self._lock:
            self._data["social_active_msg"]  = None
            self._data["social_panel_open"]  = False
            self._data["social_platform"]    = ""
            self._data["social_view_open"]   = False

    def append_archer_stream(self, token: str) -> bool:
        """
        Appends a token to Archer's live stream buffer and updates the
        session token tracker. Returns True if session limit exceeded.

        Args:
            token: Text token string from OpenRouter streaming delta.

        Returns:
            True if session token limit was just exceeded (flush needed).
        """
        with self._lock:
            self._data["archer_stream"] += token
            exceeded = self.archer_tracker.add_text(token)
            if exceeded:
                self._data["session_flush_pending"] = True
            return exceeded

    def append_hudson_stream(self, token: str) -> bool:
        """
        Appends a token to Hudson's live stream buffer and updates the
        session token tracker. Returns True if session limit exceeded.

        Args:
            token: Text token string from OpenRouter streaming delta.

        Returns:
            True if session token limit was just exceeded (flush needed).
        """
        with self._lock:
            self._data["hudson_stream"] += token
            exceeded = self.hudson_tracker.add_text(token)
            if exceeded:
                self._data["session_flush_pending"] = True
            return exceeded

    def flush_archer_stream(self) -> str:
        """
        Moves the current Archer stream buffer into archer_full
        and clears the stream. Returns the completed response text.

        Returns:
            Completed Archer response string.
        """
        with self._lock:
            completed = self._data["archer_stream"]
            self._data["archer_full"]   = completed
            self._data["archer_stream"] = ""
            return completed

    def flush_hudson_stream(self) -> str:
        """
        Moves the current Hudson stream buffer into hudson_full
        and clears the stream. Returns the completed response text.

        Returns:
            Completed Hudson response string.
        """
        with self._lock:
            completed = self._data["hudson_stream"]
            self._data["hudson_full"]   = completed
            self._data["hudson_stream"] = ""
            return completed

    def add_terminal_line(self, line: str) -> None:
        """
        Appends a line to the terminal display history buffer.
        Enforces the maximum terminal history cap.

        Args:
            line: Text line to append (speaker prefix included by caller).
        """
        from Backhand_code.config import TERMINAL_MAX_HISTORY
        with self._lock:
            self._data["terminal_history"].append(line)
            while len(self._data["terminal_history"]) > TERMINAL_MAX_HISTORY:
                self._data["terminal_history"].pop(0)

    def add_brainstorm_exchange(
        self,
        speaker: str,
        text:    str,
    ) -> None:
        """
        Records a brainstorming session exchange (user or AI utterance).
        Also updates the inferred topic from the first user utterance.

        Args:
            speaker: "YOU" or "ARCHER" or "HUDSON".
            text:    Utterance text string.
        """
        with self._lock:
            exchange = {
                "speaker":   speaker,
                "text":      text,
                "timestamp": time.time(),
            }
            self._data["brainstorm_exchanges"].append(exchange)

            # Infer topic from first user utterance (first 5 words)
            if (speaker == "YOU" and
                    not self._data["brainstorm_topic"] and
                    text.strip()):
                words = text.strip().split()
                topic_words = words[:min(5, len(words))]
                topic = "_".join(w.lower() for w in topic_words
                                 if w.isalpha())
                self._data["brainstorm_topic"] = topic or "session"

    def clear_brainstorm_session(self) -> None:
        """Clears all brainstorming exchanges and topic for a new session."""
        with self._lock:
            self._data["brainstorm_exchanges"].clear()
            self._data["brainstorm_topic"] = ""

    def update_fft(self, bands: List[float], volume: float) -> None:
        """
        Updates the audio FFT band array and volume RMS in one atomic write.
        Also pushes volume to the volume history ring buffer.

        Args:
            bands:  List of 64 normalized FFT amplitude values [0.0, 1.0].
            volume: Normalized RMS volume scalar [0.0, 1.0].
        """
        with self._lock:
            self._data["audio_fft"]    = bands
            self._data["audio_volume"] = volume
        self.volume_history.push(volume)

    def push_hardware_telemetry(
        self,
        cpu_temp:     float,
        cpu_usage:    float,
        cpu_per_core: List[float],
        ram_usage:    float,
        ram_used_gb:  float,
        ram_total_gb: float,
        disk_read:    float,
        disk_write:   float,
        disk_pct:     float,
        net_sent:     float,
        net_recv:     float,
        thread_count: int,
        uptime_secs:  float,
    ) -> None:
        """
        Atomic batch write of all hardware telemetry in a single lock.
        Called by the HardwareMonitor daemon every polling cycle.
        Also pushes values into their respective ring buffers.
        """
        from Backhand_code.math_engine import stability_score as compute_stability
        ping_ms    = self._data.get("ping_ms", 0.0)
        net_up     = self._data.get("internet_up", False)
        stability  = compute_stability(
            cpu_temp, cpu_usage, ram_usage, ping_ms, net_up
        )

        with self._lock:
            self._data["cpu_temp"]           = cpu_temp
            self._data["cpu_usage"]          = cpu_usage
            self._data["cpu_per_core"]       = cpu_per_core
            self._data["ram_usage"]          = ram_usage
            self._data["ram_used_gb"]        = ram_used_gb
            self._data["ram_total_gb"]       = ram_total_gb
            self._data["disk_read_mb"]       = disk_read
            self._data["disk_write_mb"]      = disk_write
            self._data["disk_usage_pct"]     = disk_pct
            self._data["net_sent_mb"]        = net_sent
            self._data["net_recv_mb"]        = net_recv
            self._data["active_threads"]     = thread_count
            self._data["system_uptime_secs"] = uptime_secs
            self._data["stability_score"]    = stability
            self._data["core_health"]        = min(100.0,
                stability * 0.6 + max(0.0, 100.0 - cpu_usage) * 0.4
            )

        # Push to ring buffers (outside lock — RingBuffer has its own lock)
        self.temp_history.push(cpu_temp)
        self.cpu_history.push(cpu_usage)
        self.ram_history.push(ram_usage)

    def push_network_telemetry(
        self,
        ping_ms:     float,
        internet_up: bool,
    ) -> None:
        """
        Atomic write of network telemetry and ring buffer push.
        Called by the NetworkMonitor daemon every polling cycle.

        Args:
            ping_ms:     Round-trip latency in milliseconds.
            internet_up: True if connectivity confirmed.
        """
        with self._lock:
            self._data["ping_ms"]     = ping_ms
            self._data["internet_up"] = internet_up
        self.ping_history.push(ping_ms)

    def set_ui_mode(self, mode: str) -> None:
        """
        Updates the active UI mode in state.
        Also triggers the palette transition via palette.set_mode().

        Args:
            mode: UIMode constant string ("ARCHER", "HUDSON", or "BOTH").
        """
        import Backhand_code.palette as palette
        with self._lock:
            self._data["ui_mode"] = mode
        palette.set_mode(mode)

    def get_uptime_string(self) -> str:
        """
        Computes and returns a formatted uptime string "UP: hh:mm:ss"
        based on the stored boot_time epoch value.

        Returns:
            Formatted string like "UP: 01:23:45".
        """
        with self._lock:
            boot_time = self._data["boot_time"]
        elapsed  = int(time.time() - boot_time)
        hours    = elapsed // 3600
        minutes  = (elapsed % 3600) // 60
        seconds  = elapsed % 60
        return f"UP: {hours:02d}:{minutes:02d}:{seconds:02d}"

    def get_session_progress(self, persona: str = "ARCHER") -> Dict[str, Any]:
        """
        Returns session token tracker statistics for the given persona.

        Args:
            persona: "ARCHER" or "HUDSON".

        Returns:
            Dict with keys: count, limit, remaining, percentage_used.
        """
        tracker = (self.archer_tracker
                   if persona == "ARCHER"
                   else self.hudson_tracker)
        return {
            "count":          tracker.current_count(),
            "limit":          SESSION_TOKEN_LIMIT,
            "remaining":      tracker.remaining(),
            "percentage_used": tracker.percentage_used(),
        }

    def reset_session(self, persona: str = "ARCHER") -> None:
        """
        Resets the session token tracker and clears the stream buffer
        for the given persona after a memory flush.

        Args:
            persona: "ARCHER" or "HUDSON".
        """
        with self._lock:
            self._data["session_flush_pending"] = False
            if persona == "ARCHER":
                self.archer_tracker.reset()
                self._data["archer_stream"] = ""
            else:
                self.hudson_tracker.reset()
                self._data["hudson_stream"] = ""

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"HermesState("
                f"cpu={self._data['cpu_usage']:.1f}%, "
                f"temp={self._data['cpu_temp']:.1f}C, "
                f"ram={self._data['ram_usage']:.1f}%, "
                f"ping={self._data['ping_ms']:.1f}ms, "
                f"mode={self._data['ui_mode']}, "
                f"alerts={len(self._data['system_alerts'])}, "
                f"news={len(self._data['news_articles'])})"
            )


# =============================================================================
# SECTION 8: MODULE-LEVEL STATE SINGLETON
# =============================================================================

# Single global instance shared across all modules.
# Import this directly: from state import hermes_state
hermes_state: HermesState = HermesState()


# =============================================================================
# END OF state.py
# =============================================================================