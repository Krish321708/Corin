# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: event_bus.py
# ROLE: Asynchronous publish/subscribe event system. Decouples background
#       daemons from the main rendering thread. Daemons publish events.
#       UI and persona engines subscribe to event types and react.
#       Zero pygame imports. Zero network calls. Pure threading primitives.
# =============================================================================

import threading
import time
import queue
from typing import Any, Callable, Dict, List, Optional, Tuple

# =============================================================================
# SECTION 1: EVENT TYPES REGISTRY
# =============================================================================

class EventType:
    """
    Central registry of all valid event type string constants.
    Using string constants prevents typo-based bugs in pub/sub wiring.
    Every event published on the bus must use one of these constants.
    """

    # --------------------------------------------------------------------------
    # HARDWARE & SYSTEM EVENTS
    # --------------------------------------------------------------------------
    HARDWARE_UPDATE:        str = "HARDWARE_UPDATE"
    TEMPERATURE_ALERT:      str = "TEMPERATURE_ALERT"
    RAM_ALERT:              str = "RAM_ALERT"
    STABILITY_ALERT:        str = "STABILITY_ALERT"
    THREAD_COUNT_UPDATE:    str = "THREAD_COUNT_UPDATE"
    DISK_ALERT:             str = "DISK_ALERT"

    # --------------------------------------------------------------------------
    # NETWORK EVENTS
    # --------------------------------------------------------------------------
    NETWORK_UPDATE:         str = "NETWORK_UPDATE"
    NETWORK_DOWN:           str = "NETWORK_DOWN"
    NETWORK_RESTORED:       str = "NETWORK_RESTORED"
    PING_SPIKE:             str = "PING_SPIKE"

    # --------------------------------------------------------------------------
    # AUDIO & VOICE EVENTS
    # --------------------------------------------------------------------------
    AUDIO_FFT_UPDATE:       str = "AUDIO_FFT_UPDATE"
    VOICE_TRANSCRIPT:       str = "VOICE_TRANSCRIPT"
    VOICE_LISTENING_START:  str = "VOICE_LISTENING_START"
    VOICE_LISTENING_STOP:   str = "VOICE_LISTENING_STOP"
    TTS_STARTED:            str = "TTS_STARTED"
    TTS_STOPPED:            str = "TTS_STOPPED"
    TTS_ENQUEUE:            str = "TTS_ENQUEUE"
    VOICE_MODE_COMMAND:     str = "VOICE_MODE_COMMAND"

    # --------------------------------------------------------------------------
    # LLM / PERSONA EVENTS
    # --------------------------------------------------------------------------
    ARCHER_TOKEN:           str = "ARCHER_TOKEN"
    ARCHER_RESPONSE_DONE:   str = "ARCHER_RESPONSE_DONE"
    HUDSON_TOKEN:           str = "HUDSON_TOKEN"
    HUDSON_RESPONSE_DONE:   str = "HUDSON_RESPONSE_DONE"
    LLM_REQUEST:            str = "LLM_REQUEST"
    LLM_ERROR:              str = "LLM_ERROR"
    SESSION_FLUSH:          str = "SESSION_FLUSH"
    MEMORY_SAVED:           str = "MEMORY_SAVED"

    # --------------------------------------------------------------------------
    # NEWS & GLOBE EVENTS
    # --------------------------------------------------------------------------
    NEWS_ARTICLES_UPDATED:  str = "NEWS_ARTICLES_UPDATED"
    NEWS_ARTICLE_SELECTED:  str = "NEWS_ARTICLE_SELECTED"
    NEWS_ARTICLE_DESELECTED:str = "NEWS_ARTICLE_DESELECTED"
    GLOBE_PIN_ADDED:        str = "GLOBE_PIN_ADDED"
    GLOBE_POINT_CLICKED:    str = "GLOBE_POINT_CLICKED"
    RSS_FETCH_STARTED:      str = "RSS_FETCH_STARTED"
    RSS_FETCH_COMPLETE:     str = "RSS_FETCH_COMPLETE"
    RSS_FETCH_ERROR:        str = "RSS_FETCH_ERROR"
    NLP_EXTRACTION_STARTED: str = "NLP_EXTRACTION_STARTED"
    NLP_EXTRACTION_DONE:    str = "NLP_EXTRACTION_DONE"

    # --------------------------------------------------------------------------
    # SOCIAL PLATFORM EVENTS
    # --------------------------------------------------------------------------
    WHATSAPP_MESSAGE:       str = "WHATSAPP_MESSAGE"
    WHATSAPP_SENT:          str = "WHATSAPP_SENT"
    WHATSAPP_DRAFT:         str = "WHATSAPP_DRAFT"
    INSTAGRAM_MESSAGE:      str = "INSTAGRAM_MESSAGE"
    INSTAGRAM_SENT:         str = "INSTAGRAM_SENT"
    GMAIL_MESSAGE:          str = "GMAIL_MESSAGE"
    GMAIL_SENT:             str = "GMAIL_SENT"
    REDDIT_POSTS_UPDATED:   str = "REDDIT_POSTS_UPDATED"
    SOCIAL_PANEL_OPEN:      str = "SOCIAL_PANEL_OPEN"
    SOCIAL_PANEL_CLOSE:     str = "SOCIAL_PANEL_CLOSE"
    SOCIAL_REPLY_REQUEST:   str = "SOCIAL_REPLY_REQUEST"
    SOCIAL_DRAFT_REQUEST:   str = "SOCIAL_DRAFT_REQUEST"
    SOCIAL_STYLE_REQUEST:   str = "SOCIAL_STYLE_REQUEST"

    # --------------------------------------------------------------------------
    # GITHUB EVENTS
    # --------------------------------------------------------------------------
    GITHUB_ALERT:           str = "GITHUB_ALERT"
    GITHUB_TASK_STARTED:    str = "GITHUB_TASK_STARTED"
    GITHUB_TASK_COMPLETE:   str = "GITHUB_TASK_COMPLETE"
    GITHUB_TASK_ESCALATED:  str = "GITHUB_TASK_ESCALATED"
    GITHUB_COMMIT_PUSHED:   str = "GITHUB_COMMIT_PUSHED"
    GITHUB_CONNECTED:       str = "GITHUB_CONNECTED"
    GITHUB_AUTH_FAILED:     str = "GITHUB_AUTH_FAILED"

    # --------------------------------------------------------------------------
    # UI STATE EVENTS
    # --------------------------------------------------------------------------
    UI_MODE_CHANGE:         str = "UI_MODE_CHANGE"
    BRAINSTORM_ENTER:       str = "BRAINSTORM_ENTER"
    BRAINSTORM_EXIT:        str = "BRAINSTORM_EXIT"
    BRAINSTORM_SAVED:       str = "BRAINSTORM_SAVED"
    TERMINAL_OPEN:          str = "TERMINAL_OPEN"
    TERMINAL_CLOSE:         str = "TERMINAL_CLOSE"
    TERMINAL_INPUT_SUBMIT:  str = "TERMINAL_INPUT_SUBMIT"
    HUDSON_OVERLAY_OPEN:    str = "HUDSON_OVERLAY_OPEN"
    HUDSON_OVERLAY_CLOSE:   str = "HUDSON_OVERLAY_CLOSE"
    FULLSCREEN_GLOBE_ENTER: str = "FULLSCREEN_GLOBE_ENTER"
    FULLSCREEN_GLOBE_EXIT:  str = "FULLSCREEN_GLOBE_EXIT"
    REDDIT_SETUP_OPEN:      str = "REDDIT_SETUP_OPEN"
    REDDIT_SETUP_CLOSE:     str = "REDDIT_SETUP_CLOSE"
    REDDIT_PREFS_SAVED:     str = "REDDIT_PREFS_SAVED"
    SHORTCUT_TRIGGERED:     str = "SHORTCUT_TRIGGERED"
    PERFORMANCE_TIER_SET:   str = "PERFORMANCE_TIER_SET"

    # --------------------------------------------------------------------------
    # ALERT & NOTIFICATION EVENTS
    # --------------------------------------------------------------------------
    SYSTEM_ALERT:           str = "SYSTEM_ALERT"
    ALERT_DISMISSED:        str = "ALERT_DISMISSED"
    SOUND_PLAY:             str = "SOUND_PLAY"
    PROACTIVE_OVERRIDE:     str = "PROACTIVE_OVERRIDE"

    # --------------------------------------------------------------------------
    # BOOT SEQUENCE EVENTS
    # --------------------------------------------------------------------------
    BOOT_SELF_TEST_PASS:    str = "BOOT_SELF_TEST_PASS"
    BOOT_SELF_TEST_FAIL:    str = "BOOT_SELF_TEST_FAIL"
    BOOT_COMPLETE:          str = "BOOT_COMPLETE"
    SHUTDOWN_INITIATED:     str = "SHUTDOWN_INITIATED"
    DAEMON_STARTED:         str = "DAEMON_STARTED"
    DAEMON_STOPPED:         str = "DAEMON_STOPPED"
    DAEMON_ERROR:           str = "DAEMON_ERROR"


# =============================================================================
# SECTION 2: EVENT OBJECT
# =============================================================================

class Event:
    """
    Immutable event container carrying a type, payload, source identifier,
    and creation timestamp.

    Events are created by publishers (daemons) and consumed by subscribers
    (UI panels, persona engine, audio engine).
    """

    __slots__ = ("event_type", "payload", "source", "timestamp", "event_id")

    _id_counter:  int              = 0
    _id_lock:     threading.Lock   = threading.Lock()

    def __init__(
        self,
        event_type: str,
        payload:    Any            = None,
        source:     str            = "UNKNOWN",
    ) -> None:
        """
        Args:
            event_type: One of the EventType string constants.
            payload:    Arbitrary data associated with the event.
                        Must be safe to read from multiple threads
                        (prefer plain dicts/primitives over shared objects).
            source:     String identifier of the publishing module
                        (e.g. "HardwareMonitor", "RssScraper", "PersonaEngine").
        """
        self.event_type: str   = event_type
        self.payload:    Any   = payload
        self.source:     str   = source
        self.timestamp:  float = time.time()

        # Atomic event ID generation
        with Event._id_lock:
            Event._id_counter += 1
            self.event_id: int = Event._id_counter

    def __repr__(self) -> str:
        return (
            f"Event(id={self.event_id}, "
            f"type={self.event_type}, "
            f"source={self.source}, "
            f"ts={self.timestamp:.3f})"
        )


# =============================================================================
# SECTION 3: SUBSCRIBER RECORD
# =============================================================================

class Subscription:
    """
    Internal record linking a subscriber callback to its event type filter,
    optional event source filter, and priority level.

    Higher priority subscribers receive events before lower priority ones
    within the same event type dispatch.
    """

    __slots__ = (
        "subscription_id", "event_type", "callback",
        "source_filter", "priority", "active",
    )

    def __init__(
        self,
        subscription_id: int,
        event_type:      str,
        callback:        Callable[["Event"], None],
        source_filter:   Optional[str] = None,
        priority:        int           = 0,
    ) -> None:
        """
        Args:
            subscription_id: Unique integer ID for this subscription.
            event_type:      EventType constant this subscription listens to.
            callback:        Callable invoked with the Event object on match.
                             Must be thread-safe (called from dispatcher thread).
            source_filter:   If set, only events from this source string trigger
                             the callback. None means accept from any source.
            priority:        Integer priority. Higher = dispatched first.
                             Default 0. UI callbacks typically use priority 10.
                             Critical system handlers use priority 50.
        """
        self.subscription_id: int                       = subscription_id
        self.event_type:      str                       = event_type
        self.callback:        Callable[["Event"], None] = callback
        self.source_filter:   Optional[str]             = source_filter
        self.priority:        int                       = priority
        self.active:          bool                      = True

    def matches(self, event: "Event") -> bool:
        """
        Determines if this subscription should receive the given event.

        Args:
            event: Event to test against this subscription's filters.

        Returns:
            True if the event matches all active filters.
        """
        if not self.active:
            return False
        if self.event_type != event.event_type:
            return False
        if self.source_filter is not None:
            if self.source_filter != event.source:
                return False
        return True

    def __repr__(self) -> str:
        return (
            f"Subscription(id={self.subscription_id}, "
            f"type={self.event_type}, "
            f"priority={self.priority}, "
            f"active={self.active})"
        )


# =============================================================================
# SECTION 4: EVENT BUS
# =============================================================================

class EventBus:
    """
    Asynchronous publish/subscribe event dispatcher for Project HERMES.

    Architecture:
        - Publishers (daemons) call publish() from background threads.
          publish() places the event into a thread-safe queue and returns
          immediately — never blocks the publishing thread.

        - A dedicated internal dispatcher thread drains the queue and
          invokes subscriber callbacks in priority order.

        - Subscribers register via subscribe() and receive a subscription_id
          for later unsubscription.

        - The main pygame rendering loop can also call poll() to retrieve
          a batch of pending events synchronously within the frame loop,
          for events that must be processed on the main thread
          (e.g. sound playback, UI state changes).

    Thread safety:
        - All public methods are protected by an internal RLock.
        - The dispatcher thread runs independently and never blocks publishers.
        - Callbacks are invoked from the dispatcher thread — they must be
          written to be thread-safe (write to HermesState via set/batch_set,
          never directly to pygame surfaces).
    """

    # Maximum events stored in the queue before oldest are dropped
    MAX_QUEUE_SIZE:     int = 2000

    # Maximum events returned per poll() call (prevents frame-time spikes)
    MAX_POLL_BATCH:     int = 50

    # Dispatcher thread sleep interval when queue is empty (seconds)
    DISPATCHER_SLEEP:   float = 0.002   # 2ms — very responsive

    def __init__(self) -> None:
        self._lock:              threading.RLock          = threading.RLock()
        self._queue:             queue.Queue              = queue.Queue(
                                                               maxsize=self.MAX_QUEUE_SIZE
                                                           )
        self._main_thread_queue: queue.Queue              = queue.Queue(
                                                               maxsize=self.MAX_QUEUE_SIZE
                                                           )
        self._subscriptions:     Dict[str, List[Subscription]] = {}
        self._sub_counter:       int                      = 0
        self._all_subs:          Dict[int, Subscription]  = {}

        # Dispatcher thread (background)
        self._running:           bool                     = False
        self._dispatcher_thread: Optional[threading.Thread] = None

        # Event history for debugging / Hudson overlay display
        self._history:           List[Event]              = []
        self._history_max:       int                      = 500

        # Statistics
        self._stats: Dict[str, int] = {
            "published":     0,
            "dispatched":    0,
            "dropped":       0,
            "errors":        0,
        }

    # ===========================================================================
    # SECTION 4.1: LIFECYCLE
    # ===========================================================================

    def start(self) -> None:
        """
        Starts the internal dispatcher thread.
        Must be called before any events are published.
        Safe to call multiple times (no-op if already running).
        """
        with self._lock:
            if self._running:
                return
            self._running = True

        self._dispatcher_thread = threading.Thread(
            target=self._dispatch_loop,
            name="EventBus-Dispatcher",
            daemon=True,
        )
        self._dispatcher_thread.start()

    def stop(self) -> None:
        """
        Signals the dispatcher thread to stop and waits for it to finish.
        Called during system shutdown sequence.
        Drains remaining queue events before stopping.
        """
        with self._lock:
            self._running = False

        if self._dispatcher_thread is not None:
            # Give the dispatcher a moment to drain remaining events
            self._dispatcher_thread.join(timeout=2.0)
            self._dispatcher_thread = None

    def is_running(self) -> bool:
        """Returns True if the dispatcher thread is active."""
        with self._lock:
            return self._running

    # ===========================================================================
    # SECTION 4.2: PUBLISH
    # ===========================================================================

    def publish(
        self,
        event_type: str,
        payload:    Any   = None,
        source:     str   = "UNKNOWN",
        main_thread_only: bool = False,
    ) -> int:
        """
        Publishes an event to the bus. Non-blocking — returns immediately.
        The event is placed in the appropriate queue and dispatched
        asynchronously by the dispatcher thread.

        Args:
            event_type:       EventType constant string.
            payload:          Any serializable data associated with the event.
            source:           String identifier of the publishing module.
            main_thread_only: If True, the event is placed in the main-thread
                              queue instead of the background dispatcher queue.
                              Use this for events that MUST be processed on the
                              pygame main thread (e.g. SOUND_PLAY, UI_MODE_CHANGE).

        Returns:
            event_id integer of the published event.
        """
        event = Event(event_type=event_type, payload=payload, source=source)

        with self._lock:
            self._stats["published"] += 1
            # Record in history
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history.pop(0)

        target_queue = (
            self._main_thread_queue if main_thread_only
            else self._queue
        )

        try:
            target_queue.put_nowait(event)
        except queue.Full:
            # Queue full: drop the oldest event to make room
            try:
                target_queue.get_nowait()
                target_queue.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass
            with self._lock:
                self._stats["dropped"] += 1

        return event.event_id

    def publish_event(self, event: "Event") -> None:
        """
        Publishes a pre-constructed Event object directly.
        Used internally and by modules that need to reuse event objects.

        Args:
            event: Pre-constructed Event instance.
        """
        with self._lock:
            self._stats["published"] += 1
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history.pop(0)

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass
            with self._lock:
                self._stats["dropped"] += 1

    # ===========================================================================
    # SECTION 4.3: SUBSCRIBE / UNSUBSCRIBE
    # ===========================================================================

    def subscribe(
        self,
        event_type:    str,
        callback:      Callable[["Event"], None],
        source_filter: Optional[str] = None,
        priority:      int           = 0,
    ) -> int:
        """
        Registers a callback to be invoked when a matching event is dispatched.

        Args:
            event_type:    EventType constant to listen for.
            callback:      Function accepting a single Event argument.
                           Called from the dispatcher thread — must be
                           thread-safe. Do not call pygame functions here.
            source_filter: If set, only events from this source trigger callback.
            priority:      Higher priority callbacks are called first.
                           Range: 0 (default) to 100 (maximum priority).

        Returns:
            Integer subscription_id for use with unsubscribe().
        """
        with self._lock:
            self._sub_counter += 1
            sub_id = self._sub_counter

            sub = Subscription(
                subscription_id=sub_id,
                event_type=event_type,
                callback=callback,
                source_filter=source_filter,
                priority=priority,
            )

            if event_type not in self._subscriptions:
                self._subscriptions[event_type] = []

            self._subscriptions[event_type].append(sub)
            # Keep sorted by priority descending (highest first)
            self._subscriptions[event_type].sort(
                key=lambda s: s.priority,
                reverse=True,
            )
            self._all_subs[sub_id] = sub

            return sub_id

    def unsubscribe(self, subscription_id: int) -> bool:
        """
        Deactivates and removes a subscription by its ID.

        Args:
            subscription_id: Integer ID returned by subscribe().

        Returns:
            True if the subscription was found and removed.
            False if the ID was not found.
        """
        with self._lock:
            if subscription_id not in self._all_subs:
                return False

            sub = self._all_subs.pop(subscription_id)
            sub.active = False

            event_type = sub.event_type
            if event_type in self._subscriptions:
                self._subscriptions[event_type] = [
                    s for s in self._subscriptions[event_type]
                    if s.subscription_id != subscription_id
                ]
                if not self._subscriptions[event_type]:
                    del self._subscriptions[event_type]

            return True

    def unsubscribe_all(self, event_type: str) -> int:
        """
        Removes all subscriptions for a given event type.

        Args:
            event_type: EventType constant string.

        Returns:
            Number of subscriptions removed.
        """
        with self._lock:
            if event_type not in self._subscriptions:
                return 0

            subs   = self._subscriptions.pop(event_type)
            count  = len(subs)
            for sub in subs:
                sub.active = False
                self._all_subs.pop(sub.subscription_id, None)
            return count

    def pause_subscription(self, subscription_id: int) -> bool:
        """
        Temporarily deactivates a subscription without removing it.
        The subscription can be resumed later via resume_subscription().

        Args:
            subscription_id: Integer ID returned by subscribe().

        Returns:
            True if found and paused.
        """
        with self._lock:
            if subscription_id not in self._all_subs:
                return False
            self._all_subs[subscription_id].active = False
            return True

    def resume_subscription(self, subscription_id: int) -> bool:
        """
        Re-activates a paused subscription.

        Args:
            subscription_id: Integer ID returned by subscribe().

        Returns:
            True if found and resumed.
        """
        with self._lock:
            if subscription_id not in self._all_subs:
                return False
            self._all_subs[subscription_id].active = True
            return True

    # ===========================================================================
    # SECTION 4.4: MAIN-THREAD POLL
    # ===========================================================================

    def poll(self, max_events: int = MAX_POLL_BATCH) -> List["Event"]:
        """
        Retrieves up to max_events from the main-thread event queue.
        Called once per frame from the pygame main loop to process events
        that require main-thread context (sound playback, UI transitions,
        palette mode switching).

        This method does NOT invoke subscriber callbacks — it returns raw
        events for the caller (main.py) to handle directly.

        Args:
            max_events: Maximum events to dequeue per call.

        Returns:
            List of Event objects (may be empty if queue is empty).
        """
        events: List[Event] = []
        for _ in range(max_events):
            try:
                event = self._main_thread_queue.get_nowait()
                events.append(event)
            except queue.Empty:
                break
        return events

    def poll_typed(
        self,
        event_type: str,
        max_events: int = MAX_POLL_BATCH,
    ) -> List["Event"]:
        """
        Retrieves and returns only events of a specific type from the
        main-thread queue. Non-matching events are re-queued.

        Args:
            event_type: EventType constant to filter for.
            max_events: Maximum events to check and return.

        Returns:
            List of matching Event objects.
        """
        all_events   = self.poll(max_events=max_events * 3)
        matched:     List[Event] = []
        not_matched: List[Event] = []

        for event in all_events:
            if event.event_type == event_type:
                matched.append(event)
            else:
                not_matched.append(event)

        # Re-queue non-matching events
        for event in not_matched:
            try:
                self._main_thread_queue.put_nowait(event)
            except queue.Full:
                pass

        return matched[:max_events]

    # ===========================================================================
    # SECTION 4.5: BACKGROUND DISPATCHER LOOP
    # ===========================================================================

    def _dispatch_loop(self) -> None:
        """
        Internal background dispatcher thread entry point.
        Continuously drains the background event queue and invokes
        matching subscriber callbacks in priority order.

        Runs until self._running is set to False.
        Handles callback exceptions gracefully without crashing the bus.
        """
        while self._running:
            try:
                # Block with timeout so we can check _running flag
                event = self._queue.get(timeout=self.DISPATCHER_SLEEP)
            except queue.Empty:
                continue

            self._dispatch_event(event)

        # Drain remaining events after stop() is called
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._dispatch_event(event)
            except queue.Empty:
                break

    def _dispatch_event(self, event: "Event") -> None:
        """
        Dispatches a single event to all matching subscribers.
        Subscribers are invoked in priority order (highest first).
        Exceptions in callbacks are caught and logged without crashing.

        Args:
            event: Event to dispatch.
        """
        with self._lock:
            subs = list(
                self._subscriptions.get(event.event_type, [])
            )

        dispatched = False
        for sub in subs:
            if sub.matches(event):
                try:
                    sub.callback(event)
                    dispatched = True
                except Exception as exc:
                    with self._lock:
                        self._stats["errors"] += 1
                    # Log error without crashing the dispatcher
                    print(
                        f"[EventBus] ERROR in callback "
                        f"(sub_id={sub.subscription_id}, "
                        f"event={event.event_type}): {exc}"
                    )

        with self._lock:
            if dispatched:
                self._stats["dispatched"] += 1

    # ===========================================================================
    # SECTION 4.6: CONVENIENCE PUBLISH METHODS
    # ===========================================================================

    def emit_hardware_update(self, payload: Dict[str, Any]) -> int:
        """Publishes a HARDWARE_UPDATE event from the hardware monitor daemon."""
        return self.publish(
            EventType.HARDWARE_UPDATE,
            payload=payload,
            source="HardwareMonitor",
        )

    def emit_network_update(
        self,
        ping_ms:     float,
        internet_up: bool,
    ) -> int:
        """Publishes a NETWORK_UPDATE event from the network monitor daemon."""
        return self.publish(
            EventType.NETWORK_UPDATE,
            payload={"ping_ms": ping_ms, "internet_up": internet_up},
            source="NetworkMonitor",
        )

    def emit_network_down(self) -> int:
        """Publishes a NETWORK_DOWN event and a main-thread SYSTEM_ALERT."""
        self.publish(
            EventType.NETWORK_DOWN,
            payload={"message": "NETWORK CONNECTION LOST"},
            source="NetworkMonitor",
            main_thread_only=False,
        )
        return self.publish(
            EventType.SYSTEM_ALERT,
            payload={
                "message":  "NETWORK CONNECTION LOST",
                "severity": "CRITICAL",
                "category": "NETWORK",
            },
            source="NetworkMonitor",
            main_thread_only=True,
        )

    def emit_network_restored(self) -> int:
        """Publishes a NETWORK_RESTORED event."""
        return self.publish(
            EventType.NETWORK_RESTORED,
            payload={"message": "NETWORK CONNECTION RESTORED"},
            source="NetworkMonitor",
        )

    def emit_fft_update(
        self,
        bands:   List[float],
        volume:  float,
        speaking: bool,
    ) -> int:
        """Publishes an AUDIO_FFT_UPDATE event from the AudioDSP daemon."""
        return self.publish(
            EventType.AUDIO_FFT_UPDATE,
            payload={
                "bands":    bands,
                "volume":   volume,
                "speaking": speaking,
            },
            source="AudioDSPEngine",
        )

    def emit_voice_transcript(self, text: str) -> int:
        """
        Publishes a VOICE_TRANSCRIPT event from the STT daemon.
        Also published to main-thread queue for immediate LLM routing.
        """
        self.publish(
            EventType.VOICE_TRANSCRIPT,
            payload={"text": text},
            source="VoiceReceiver",
        )
        return self.publish(
            EventType.VOICE_TRANSCRIPT,
            payload={"text": text},
            source="VoiceReceiver",
            main_thread_only=True,
        )

    def emit_tts_enqueue(self, text: str, persona: str = "ARCHER") -> int:
        """
        Publishes a TTS_ENQUEUE event to route text to the TTS daemon.

        Args:
            text:    Text string for the TTS engine to speak.
            persona: "ARCHER" or "HUDSON" — determines voice parameters.
        """
        return self.publish(
            EventType.TTS_ENQUEUE,
            payload={"text": text, "persona": persona},
            source="PersonaEngine",
        )

    def emit_archer_token(self, token: str) -> int:
        """Publishes an ARCHER_TOKEN streaming delta event."""
        return self.publish(
            EventType.ARCHER_TOKEN,
            payload={"token": token},
            source="ArcherPersona",
        )

    def emit_hudson_token(self, token: str) -> int:
        """Publishes a HUDSON_TOKEN streaming delta event."""
        return self.publish(
            EventType.HUDSON_TOKEN,
            payload={"token": token},
            source="HudsonPersona",
        )

    def emit_archer_done(self, full_response: str) -> int:
        """
        Publishes an ARCHER_RESPONSE_DONE event when streaming is complete.
        Routes to main thread for UI finalization.
        """
        return self.publish(
            EventType.ARCHER_RESPONSE_DONE,
            payload={"full_response": full_response},
            source="ArcherPersona",
            main_thread_only=True,
        )

    def emit_hudson_done(self, full_response: str) -> int:
        """
        Publishes a HUDSON_RESPONSE_DONE event when streaming is complete.
        Routes to main thread for UI finalization.
        """
        return self.publish(
            EventType.HUDSON_RESPONSE_DONE,
            payload={"full_response": full_response},
            source="HudsonPersona",
            main_thread_only=True,
        )

    def emit_news_updated(self, article_count: int) -> int:
        """Publishes a NEWS_ARTICLES_UPDATED event after RSS scrape cycle."""
        return self.publish(
            EventType.NEWS_ARTICLES_UPDATED,
            payload={"count": article_count},
            source="RssScraper",
            main_thread_only=True,
        )

    def emit_news_selected(self, article_id: str) -> int:
        """
        Publishes a NEWS_ARTICLE_SELECTED event when user clicks
        a news item or globe pin.
        Routes to main thread for tactical overlay rendering.
        """
        return self.publish(
            EventType.NEWS_ARTICLE_SELECTED,
            payload={"article_id": article_id},
            source="UIInteraction",
            main_thread_only=True,
        )

    def emit_globe_clicked(
        self,
        lat: float,
        lon: float,
        article_id: str,
    ) -> int:
        """
        Publishes a GLOBE_POINT_CLICKED event when user clicks a globe pin.
        Routes to main thread for tactical detail overlay.
        """
        return self.publish(
            EventType.GLOBE_POINT_CLICKED,
            payload={
                "lat":        lat,
                "lon":        lon,
                "article_id": article_id,
            },
            source="UIInteraction",
            main_thread_only=True,
        )

    def emit_whatsapp_message(self, sender: str, preview: str,
                               thread_id: str, full_body: str) -> int:
        """Publishes a WHATSAPP_MESSAGE event from the social integration daemon."""
        return self.publish(
            EventType.WHATSAPP_MESSAGE,
            payload={
                "sender":    sender,
                "preview":   preview,
                "thread_id": thread_id,
                "full_body": full_body,
            },
            source="WhatsAppIntegration",
            main_thread_only=True,
        )

    def emit_instagram_message(
        self,
        sender:      str,
        preview:     str,
        thread_id:   str,
        full_body:   str,
        account_idx: int,
    ) -> int:
        """Publishes an INSTAGRAM_MESSAGE event from the social integration daemon."""
        return self.publish(
            EventType.INSTAGRAM_MESSAGE,
            payload={
                "sender":      sender,
                "preview":     preview,
                "thread_id":   thread_id,
                "full_body":   full_body,
                "account_idx": account_idx,
            },
            source="InstagramIntegration",
            main_thread_only=True,
        )

    def emit_gmail_message(
        self,
        sender:    str,
        subject:   str,
        preview:   str,
        thread_id: str,
        full_body: str,
    ) -> int:
        """Publishes a GMAIL_MESSAGE event from the Gmail integration daemon."""
        return self.publish(
            EventType.GMAIL_MESSAGE,
            payload={
                "sender":    sender,
                "subject":   subject,
                "preview":   preview,
                "thread_id": thread_id,
                "full_body": full_body,
            },
            source="GmailIntegration",
            main_thread_only=True,
        )

    def emit_github_alert(
        self,
        repo:        str,
        issue_title: str,
        issue_url:   str,
        issue_body:  str,
        issue_number: int,
    ) -> int:
        """Publishes a GITHUB_ALERT event from the GitHub engine daemon."""
        return self.publish(
            EventType.GITHUB_ALERT,
            payload={
                "repo":         repo,
                "issue_title":  issue_title,
                "issue_url":    issue_url,
                "issue_body":   issue_body,
                "issue_number": issue_number,
            },
            source="GitHubEngine",
        )

    def emit_github_escalated(
        self,
        repo:         str,
        issue_title:  str,
        issue_number: int,
        reason:       str,
    ) -> int:
        """
        Publishes a GITHUB_TASK_ESCALATED event when Hudson determines
        an issue is too complex to auto-resolve.
        Routes to main thread for user notification.
        """
        return self.publish(
            EventType.GITHUB_TASK_ESCALATED,
            payload={
                "repo":         repo,
                "issue_title":  issue_title,
                "issue_number": issue_number,
                "reason":       reason,
            },
            source="GitHubEngine",
            main_thread_only=True,
        )

    def emit_system_alert(
        self,
        message:  str,
        severity: str,
        category: str,
    ) -> int:
        """
        Publishes a SYSTEM_ALERT event routed to the main thread.
        Triggers the alert sound and proactive overlay.

        Args:
            message:  Alert message string.
            severity: SystemAlert.SEVERITY_ constant.
            category: SystemAlert.CATEGORY_ constant.
        """
        return self.publish(
            EventType.SYSTEM_ALERT,
            payload={
                "message":  message,
                "severity": severity,
                "category": category,
            },
            source="ProactiveDaemon",
            main_thread_only=True,
        )

    def emit_sound_play(self, sound_category: int) -> int:
        """
        Publishes a SOUND_PLAY event routed to the main thread.
        The audio engine picks this up via poll() in the frame loop.

        Args:
            sound_category: Integer 1-4 mapping to sound file categories:
                1 = Access Granted Chirp
                2 = Thinking Machine Click
                3 = Deep Space Ping
                4 = Alert Alarm
        """
        return self.publish(
            EventType.SOUND_PLAY,
            payload={"category": sound_category},
            source="EventBus",
            main_thread_only=True,
        )

    def emit_ui_mode_change(self, mode: str) -> int:
        """
        Publishes a UI_MODE_CHANGE event routed to the main thread.
        Triggers palette transition and UI layout transformation.

        Args:
            mode: UIMode constant string ("ARCHER", "HUDSON", or "BOTH").
        """
        return self.publish(
            EventType.UI_MODE_CHANGE,
            payload={"mode": mode},
            source="VoiceReceiver",
            main_thread_only=True,
        )

    def emit_brainstorm_enter(self) -> int:
        """Publishes BRAINSTORM_ENTER to main thread (space bar trigger)."""
        return self.publish(
            EventType.BRAINSTORM_ENTER,
            payload={},
            source="ShortcutHandler",
            main_thread_only=True,
        )

    def emit_brainstorm_exit(self) -> int:
        """Publishes BRAINSTORM_EXIT to main thread (ESC key trigger)."""
        return self.publish(
            EventType.BRAINSTORM_EXIT,
            payload={},
            source="ShortcutHandler",
            main_thread_only=True,
        )

    def emit_terminal_submit(self, text: str) -> int:
        """
        Publishes TERMINAL_INPUT_SUBMIT when user presses Enter in terminal.
        Routed to main thread for LLM routing.

        Args:
            text: The multi-line terminal input text to submit.
        """
        return self.publish(
            EventType.TERMINAL_INPUT_SUBMIT,
            payload={"text": text},
            source="TerminalWidget",
            main_thread_only=True,
        )

    def emit_session_flush(self, persona: str) -> int:
        """
        Publishes SESSION_FLUSH when a persona's token limit is exceeded.
        Triggers memory_manager to save soul.md and users.md.

        Args:
            persona: "ARCHER" or "HUDSON".
        """
        return self.publish(
            EventType.SESSION_FLUSH,
            payload={"persona": persona},
            source="PersonaEngine",
        )

    def emit_daemon_started(self, daemon_name: str) -> int:
        """Published by each daemon when its thread begins execution."""
        return self.publish(
            EventType.DAEMON_STARTED,
            payload={"daemon": daemon_name},
            source=daemon_name,
        )

    def emit_daemon_stopped(self, daemon_name: str) -> int:
        """Published by each daemon when its thread terminates cleanly."""
        return self.publish(
            EventType.DAEMON_STOPPED,
            payload={"daemon": daemon_name},
            source=daemon_name,
        )

    def emit_daemon_error(self, daemon_name: str, error: str) -> int:
        """Published by a daemon when it encounters a non-fatal error."""
        return self.publish(
            EventType.DAEMON_ERROR,
            payload={"daemon": daemon_name, "error": error},
            source=daemon_name,
            main_thread_only=True,
        )

    def emit_performance_tier(self, tier: str) -> int:
        """
        Published by the boot screen when performance tier is selected.

        Args:
            tier: PerformanceTier constant string.
        """
        return self.publish(
            EventType.PERFORMANCE_TIER_SET,
            payload={"tier": tier},
            source="BootScreen",
            main_thread_only=True,
        )

    def emit_shutdown(self) -> int:
        """Published by main.py when the application exit sequence begins."""
        return self.publish(
            EventType.SHUTDOWN_INITIATED,
            payload={},
            source="Main",
            main_thread_only=True,
        )

    def emit_social_reply(
        self,
        msg_id:    str,
        platform:  str,
        thread_id: str,
        mode:      str,
    ) -> int:
        """
        Publishes a SOCIAL_REPLY_REQUEST event to route to Archer for
        crafting and sending a reply.

        Args:
            msg_id:    SocialMessage.msg_id string.
            platform:  SocialMessage.PLATFORM_ constant.
            thread_id: Platform conversation thread ID.
            mode:      "RESPOND", "DRAFT", or "STYLE_CHAT".
        """
        return self.publish(
            EventType.SOCIAL_REPLY_REQUEST,
            payload={
                "msg_id":    msg_id,
                "platform":  platform,
                "thread_id": thread_id,
                "mode":      mode,
            },
            source="UIInteraction",
            main_thread_only=False,
        )

    def emit_reddit_prefs_saved(self, preferences: Dict[str, bool]) -> int:
        """
        Publishes REDDIT_PREFS_SAVED after the user completes
        the Reddit preference setup screen.

        Args:
            preferences: Dict of {category_name: bool} checkbox states.
        """
        return self.publish(
            EventType.REDDIT_PREFS_SAVED,
            payload={"preferences": preferences},
            source="RedditSetupScreen",
        )

    # ===========================================================================
    # SECTION 4.7: DIAGNOSTICS & INTROSPECTION
    # ===========================================================================

    def get_stats(self) -> Dict[str, int]:
        """
        Returns a copy of the event bus statistics dictionary.

        Returns:
            Dict with keys: published, dispatched, dropped, errors.
        """
        with self._lock:
            return dict(self._stats)

    def get_subscriber_count(self, event_type: Optional[str] = None) -> int:
        """
        Returns the number of active subscribers for a given event type,
        or total across all event types if event_type is None.

        Args:
            event_type: Specific EventType string, or None for total count.

        Returns:
            Integer subscriber count.
        """
        with self._lock:
            if event_type is not None:
                return len(self._subscriptions.get(event_type, []))
            return sum(
                len(subs) for subs in self._subscriptions.values()
            )

    def get_queue_depth(self) -> Dict[str, int]:
        """
        Returns the current depth of both event queues.

        Returns:
            Dict with keys "background" and "main_thread" queue sizes.
        """
        return {
            "background":  self._queue.qsize(),
            "main_thread": self._main_thread_queue.qsize(),
        }

    def get_recent_history(self, count: int = 20) -> List["Event"]:
        """
        Returns the most recent N events from the history log.
        Used by the Hudson overlay panel for activity display.

        Args:
            count: Number of most-recent events to return.

        Returns:
            List of Event objects (newest last).
        """
        with self._lock:
            return list(self._history[-count:])

    def get_registered_types(self) -> List[str]:
        """
        Returns a sorted list of all event types that currently have
        at least one active subscriber.

        Returns:
            Sorted list of EventType strings.
        """
        with self._lock:
            return sorted(self._subscriptions.keys())

    def reset_stats(self) -> None:
        """Resets all statistics counters to zero."""
        with self._lock:
            self._stats = {
                "published":  0,
                "dispatched": 0,
                "dropped":    0,
                "errors":     0,
            }

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"EventBus("
                f"running={self._running}, "
                f"subscribers={self.get_subscriber_count()}, "
                f"published={self._stats['published']}, "
                f"dispatched={self._stats['dispatched']}, "
                f"dropped={self._stats['dropped']}, "
                f"queue_depth={self.get_queue_depth()})"
            )


# =============================================================================
# SECTION 5: MODULE-LEVEL EVENT BUS SINGLETON
# =============================================================================

# Single global instance shared across all modules.
# Import directly: from event_bus import event_bus, EventType
event_bus: EventBus = EventBus()


# =============================================================================
# END OF event_bus.py
# =============================================================================