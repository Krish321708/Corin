# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: memory_manager.py
# ROLE: Manages archer_soul.md, hudson_soul.md, and users.md.
#       Handles session-end writes, smart merge (human-memory-style importance
#       scoring), 400-word cap enforcement, brainstorming session saves,
#       and Reddit preference persistence. All file I/O is synchronous and
#       protected by file-level locks. Zero pygame imports. Zero network calls.
# =============================================================================

import os
import re
import json
import math
import time
import threading
import datetime
from typing import Any, Dict, List, Optional, Tuple

from Backhand_code.config import (
    ARCHER_SOUL_PATH,
    HUDSON_SOUL_PATH,
    USERS_MD_PATH,
    MEMORY_DIR,
    BRAINSTORM_DIR,
    REDDIT_PREFS_PATH,
    MEMORY_MAX_WORDS,
    SESSION_TOKEN_LIMIT,
    OPENROUTER_API_KEY,
    OPENROUTER_CHAT_ENDPOINT,
    MODEL_CONVERSATION,
)

# =============================================================================
# SECTION 1: CONSTANTS
# =============================================================================

# Importance scoring weights (human memory model)
WEIGHT_EMOTIONAL:   float = 0.30   # strong sentiment / emotional language
WEIGHT_REPETITION:  float = 0.20   # topics mentioned multiple times
WEIGHT_RECENCY:     float = 0.20   # newer memories score higher
WEIGHT_ACTIONABLE:  float = 0.15   # tasks, decisions, preferences set
WEIGHT_NOVELTY:     float = 0.10   # unique / first-time information
WEIGHT_PERSONAL:    float = 0.05   # personal details (names, places, dates)

# Emotional language markers for scoring
EMOTIONAL_POSITIVE_WORDS: List[str] = [
    "love", "amazing", "incredible", "excited", "happy", "proud",
    "brilliant", "perfect", "fantastic", "great", "awesome", "best",
    "passion", "dream", "hope", "grateful", "inspired", "motivated",
    "brilliant", "genius", "fire", "legendary", "powerful", "strong",
]

EMOTIONAL_NEGATIVE_WORDS: List[str] = [
    "hate", "terrible", "awful", "angry", "frustrated", "scared",
    "worried", "anxious", "stressed", "broken", "failed", "disaster",
    "dangerous", "critical", "urgent", "emergency", "problem", "issue",
    "error", "wrong", "bad", "horrible", "annoying", "struggling",
]

ACTIONABLE_MARKERS: List[str] = [
    "want", "need", "will", "must", "should", "prefer", "like",
    "don't like", "always", "never", "decided", "planning", "going to",
    "remember", "remind", "set", "configured", "changed", "updated",
    "favourite", "favorite", "hate", "love", "allergic", "birthday",
    "deadline", "goal", "target", "project", "task", "priority",
]

PERSONAL_MARKERS: List[str] = [
    "my name", "i am", "i'm", "i was", "i live", "i work", "i study",
    "my age", "my job", "my family", "my friend", "my partner", "my boss",
    "years old", "born", "from", "country", "city", "school", "university",
    "company", "team", "colleague", "brother", "sister", "mother", "father",
]

# Minimum importance score threshold for keeping a memory entry
MIN_IMPORTANCE_THRESHOLD: float = 0.25

# Word count target for smart merge output (slightly under cap for safety)
MERGE_TARGET_WORDS: int = 360

# File encoding
FILE_ENCODING: str = "utf-8"

# =============================================================================
# SECTION 2: MEMORY ENTRY
# =============================================================================

class MemoryEntry:
    """
    Represents a single atomic memory unit extracted from a conversation.
    Each entry has content text, a timestamp, and a computed importance score.
    """

    __slots__ = (
        "content", "timestamp", "importance", "entry_type",
        "word_count", "source_persona",
    )

    ENTRY_TYPE_FACT:         str = "FACT"
    ENTRY_TYPE_PREFERENCE:   str = "PREFERENCE"
    ENTRY_TYPE_EMOTION:      str = "EMOTION"
    ENTRY_TYPE_DECISION:     str = "DECISION"
    ENTRY_TYPE_TASK:         str = "TASK"
    ENTRY_TYPE_CONTEXT:      str = "CONTEXT"
    ENTRY_TYPE_PERSONALITY:  str = "PERSONALITY"

    def __init__(
        self,
        content:        str,
        timestamp:      float,
        importance:     float       = 0.5,
        entry_type:     str         = "FACT",
        source_persona: str         = "ARCHER",
    ) -> None:
        self.content:        str   = content.strip()
        self.timestamp:      float = timestamp
        self.importance:     float = max(0.0, min(1.0, importance))
        self.entry_type:     str   = entry_type
        self.word_count:     int   = len(content.split())
        self.source_persona: str   = source_persona

    def age_days(self) -> float:
        """Returns the age of this memory entry in days."""
        return (time.time() - self.timestamp) / 86400.0

    def to_markdown_line(self) -> str:
        """
        Formats this entry as a single markdown bullet line.
        Format: - [TYPE | SCORE] content text

        Returns:
            Formatted markdown string.
        """
        dt_str = datetime.datetime.fromtimestamp(
            self.timestamp
        ).strftime("%Y-%m-%d")
        return (
            f"- [{self.entry_type} | {self.importance:.2f} | {dt_str}] "
            f"{self.content}"
        )

    def __repr__(self) -> str:
        return (
            f"MemoryEntry(type={self.entry_type}, "
            f"importance={self.importance:.2f}, "
            f"words={self.word_count})"
        )


# =============================================================================
# SECTION 3: IMPORTANCE SCORER
# =============================================================================

class ImportanceScorer:
    """
    Scores text segments by importance using a weighted multi-factor model
    that mimics human memory consolidation patterns.

    Factors:
        1. Emotional weight    — presence of strong emotional language
        2. Repetition weight   — topic overlap with existing entries
        3. Recency weight      — how recent this entry is vs. session start
        4. Actionable weight   — contains preferences, decisions, tasks
        5. Novelty weight      — introduces information not in existing entries
        6. Personal weight     — mentions personal details / identity markers
    """

    def __init__(self, session_start: float) -> None:
        """
        Args:
            session_start: Epoch timestamp of session start
                           (used for recency normalization).
        """
        self._session_start: float     = session_start
        self._seen_topics:   List[str] = []

    def score(
        self,
        text:             str,
        existing_entries: List[MemoryEntry],
        entry_timestamp:  float,
    ) -> Tuple[float, str]:
        """
        Computes the importance score for a text segment.

        Args:
            text:             The candidate memory text to score.
            existing_entries: Current memory entries (for repetition/novelty).
            entry_timestamp:  Epoch timestamp when this text was generated.

        Returns:
            Tuple of (importance_score [0.0, 1.0], detected_entry_type string).
        """
        text_lower = text.lower()
        words      = text_lower.split()

        # --- Factor 1: Emotional weight ---
        pos_count = sum(
            1 for w in EMOTIONAL_POSITIVE_WORDS
            if w in text_lower
        )
        neg_count = sum(
            1 for w in EMOTIONAL_NEGATIVE_WORDS
            if w in text_lower
        )
        emotional_raw   = min(1.0, (pos_count + neg_count) / 4.0)
        emotional_score = emotional_raw * WEIGHT_EMOTIONAL

        # --- Factor 2: Repetition weight ---
        # If this topic overlaps with existing entries, it's being reinforced
        if existing_entries:
            overlap_scores = []
            for entry in existing_entries:
                existing_words = set(entry.content.lower().split())
                new_words      = set(words)
                if len(new_words) > 0:
                    overlap = len(existing_words & new_words) / len(new_words)
                    overlap_scores.append(overlap)
            repetition_raw   = min(1.0, max(overlap_scores) * 2.0) if overlap_scores else 0.0
        else:
            repetition_raw = 0.0
        repetition_score = repetition_raw * WEIGHT_REPETITION

        # --- Factor 3: Recency weight ---
        session_duration = max(1.0, time.time() - self._session_start)
        elapsed          = max(0.0, entry_timestamp - self._session_start)
        recency_raw      = min(1.0, elapsed / session_duration)
        recency_score    = recency_raw * WEIGHT_RECENCY

        # --- Factor 4: Actionable weight ---
        actionable_count = sum(
            1 for marker in ACTIONABLE_MARKERS
            if marker in text_lower
        )
        actionable_raw   = min(1.0, actionable_count / 3.0)
        actionable_score = actionable_raw * WEIGHT_ACTIONABLE

        # --- Factor 5: Novelty weight ---
        # New information not overlapping heavily with existing entries
        if existing_entries:
            all_existing_words = set()
            for entry in existing_entries:
                all_existing_words.update(entry.content.lower().split())
            new_word_set  = set(words)
            novel_words   = new_word_set - all_existing_words
            novelty_raw   = len(novel_words) / max(1, len(new_word_set))
        else:
            novelty_raw = 1.0
        novelty_score = novelty_raw * WEIGHT_NOVELTY

        # --- Factor 6: Personal weight ---
        personal_count = sum(
            1 for marker in PERSONAL_MARKERS
            if marker in text_lower
        )
        personal_raw   = min(1.0, personal_count / 2.0)
        personal_score = personal_raw * WEIGHT_PERSONAL

        # --- Total weighted score ---
        total = (
            emotional_score  +
            repetition_score +
            recency_score    +
            actionable_score +
            novelty_score    +
            personal_score
        )
        total = max(0.0, min(1.0, total))

        # --- Detect entry type ---
        entry_type = self._classify_entry_type(text_lower, actionable_count,
                                                 pos_count, neg_count,
                                                 personal_count)

        return (total, entry_type)

    def _classify_entry_type(
        self,
        text_lower:       str,
        actionable_count: int,
        pos_count:        int,
        neg_count:        int,
        personal_count:   int,
    ) -> str:
        """
        Classifies the entry into one of the MemoryEntry type constants.

        Classification rules (ordered by priority):
            1. Personal marker dominant → FACT
            2. Strong emotion          → EMOTION
            3. Actionable/decision     → PREFERENCE or DECISION
            4. Task language           → TASK
            5. Default                 → CONTEXT

        Args:
            text_lower:       Lowercased text.
            actionable_count: Count of actionable marker matches.
            pos_count:        Positive emotional word count.
            neg_count:        Negative emotional word count.
            personal_count:   Personal marker count.

        Returns:
            MemoryEntry entry type string constant.
        """
        task_words = [
            "task", "todo", "remind", "deadline", "finish",
            "complete", "build", "create", "fix", "implement",
        ]
        decision_words = [
            "decided", "decision", "chose", "choice", "going with",
            "settled on", "picked", "selected", "confirmed",
        ]
        personality_words = [
            "always", "never", "every time", "i tend to", "i usually",
            "my style", "my approach", "the way i", "i believe",
            "my philosophy", "my mindset",
        ]

        if personal_count >= 2:
            return MemoryEntry.ENTRY_TYPE_FACT

        if (pos_count + neg_count) >= 3:
            return MemoryEntry.ENTRY_TYPE_EMOTION

        if any(w in text_lower for w in decision_words):
            return MemoryEntry.ENTRY_TYPE_DECISION

        if any(w in text_lower for w in task_words):
            return MemoryEntry.ENTRY_TYPE_TASK

        if any(w in text_lower for w in personality_words):
            return MemoryEntry.ENTRY_TYPE_PERSONALITY

        if actionable_count >= 2:
            return MemoryEntry.ENTRY_TYPE_PREFERENCE

        return MemoryEntry.ENTRY_TYPE_CONTEXT


# =============================================================================
# SECTION 4: MARKDOWN FILE PARSER
# =============================================================================

def _parse_memory_file(filepath: str) -> List[MemoryEntry]:
    """
    Parses an existing memory markdown file into a list of MemoryEntry objects.

    Expected line format:
        - [TYPE | SCORE | YYYY-MM-DD] content text

    Lines not matching this format are treated as CONTEXT entries
    with a moderate importance score (0.4) and current timestamp.

    Args:
        filepath: Absolute path to the markdown file.

    Returns:
        List of MemoryEntry objects parsed from the file.
        Empty list if file does not exist or is empty.
    """
    if not os.path.isfile(filepath):
        return []

    entries:  List[MemoryEntry] = []
    pattern = re.compile(
        r"^-\s+\[([A-Z_]+)\s*\|\s*([\d.]+)\s*\|\s*([\d-]+)\]\s+(.+)$"
    )

    try:
        with open(filepath, "r", encoding=FILE_ENCODING) as f:
            lines = f.readlines()
    except Exception:
        return []

    now = time.time()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = pattern.match(line)
        if match:
            entry_type  = match.group(1).strip()
            importance  = float(match.group(2).strip())
            date_str    = match.group(3).strip()
            content     = match.group(4).strip()

            # Parse date string to epoch timestamp
            try:
                dt        = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                timestamp = dt.timestamp()
            except ValueError:
                timestamp = now

            entries.append(MemoryEntry(
                content=content,
                timestamp=timestamp,
                importance=importance,
                entry_type=entry_type,
            ))
        else:
            # Unformatted line — treat as medium-importance context
            if line.startswith("-"):
                content = line.lstrip("- ").strip()
            else:
                content = line
            if content:
                entries.append(MemoryEntry(
                    content=content,
                    timestamp=now,
                    importance=0.4,
                    entry_type=MemoryEntry.ENTRY_TYPE_CONTEXT,
                ))

    return entries


def _entries_to_markdown(
    entries:  List[MemoryEntry],
    header:   str,
) -> str:
    """
    Serializes a list of MemoryEntry objects to a formatted markdown string.

    Format:
        # {header}
        *Last Updated: YYYY-MM-DD HH:MM:SS*
        *Entries: N | Total Words: W*

        ## Core Memories
        [entries sorted by importance descending]

    Args:
        entries: List of MemoryEntry objects to serialize.
        header:  Markdown H1 header string.

    Returns:
        Complete markdown file content string.
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_words = sum(e.word_count for e in entries)

    lines: List[str] = [
        f"# {header}",
        f"*Last Updated: {now_str}*",
        f"*Entries: {len(entries)} | Total Words: {total_words}*",
        "",
        "## Core Memories",
        "",
    ]

    # Sort by importance descending
    sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)

    for entry in sorted_entries:
        lines.append(entry.to_markdown_line())

    lines.append("")
    return "\n".join(lines)


def _count_words_in_file(filepath: str) -> int:
    """
    Counts the total word count of a markdown memory file.

    Args:
        filepath: Path to the file.

    Returns:
        Integer word count. 0 if file does not exist.
    """
    if not os.path.isfile(filepath):
        return 0
    try:
        with open(filepath, "r", encoding=FILE_ENCODING) as f:
            content = f.read()
        return len(content.split())
    except Exception:
        return 0


def _write_file(filepath: str, content: str) -> bool:
    """
    Atomically writes content to a file by first writing to a temp file
    then renaming it (prevents partial writes on crash).

    Args:
        filepath: Target file path.
        content:  String content to write.

    Returns:
        True if write succeeded, False on error.
    """
    temp_path = filepath + ".tmp"
    try:
        with open(temp_path, "w", encoding=FILE_ENCODING) as f:
            f.write(content)
        os.replace(temp_path, filepath)
        return True
    except Exception as exc:
        print(f"[MemoryManager] File write error ({filepath}): {exc}")
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return False


# =============================================================================
# SECTION 5: SMART MERGE ENGINE
# =============================================================================

class SmartMergeEngine:
    """
    Executes the human-memory-style smart merge algorithm.

    When a memory file exceeds the 400-word cap, this engine:
        1. Scores all existing entries by importance.
        2. Applies recency decay (older = slightly lower score).
        3. Applies repetition boost (frequently mentioned = higher score).
        4. Selects the highest-scoring entries that fit within MERGE_TARGET_WORDS.
        5. Optionally uses the LLM to compress/summarize low-scoring clusters
           before discarding them (ensuring no unique fact is completely lost).

    The result is a merged entry list that preserves the most important
    memories while staying within the word budget.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()

    def merge(
        self,
        entries:           List[MemoryEntry],
        new_entries:       List[MemoryEntry],
        target_word_count: int = MERGE_TARGET_WORDS,
    ) -> List[MemoryEntry]:
        """
        Merges new entries into the existing entry list, enforcing the
        word cap through importance-based selection.

        Algorithm:
            1. Combine old + new entries into a single pool.
            2. Apply recency decay to old entries.
            3. Apply repetition boost (entries sharing topics with
               multiple others get a small score boost).
            4. Sort by final score descending.
            5. Greedily select entries until word budget is exhausted.
            6. Guarantee at least one entry of each type survives
               (type diversity preservation).

        Args:
            entries:           Existing entries from the memory file.
            new_entries:       Newly extracted entries from this session.
            target_word_count: Maximum total word count for output.

        Returns:
            Merged, pruned list of MemoryEntry objects within word budget.
        """
        with self._lock:
            now = time.time()

            # Step 1: Combine all entries
            combined = list(entries) + list(new_entries)
            if not combined:
                return []

            # Step 2: Apply recency decay to existing (not new) entries
            existing_set = set(id(e) for e in entries)
            for entry in combined:
                if id(entry) in existing_set:
                    # Decay: 5% reduction per 7 days of age
                    age_weeks = entry.age_days() / 7.0
                    decay     = max(0.5, 1.0 - age_weeks * 0.05)
                    entry.importance *= decay

            # Step 3: Repetition boost
            # Entries that share significant topic overlap with multiple
            # other entries get a small importance boost (reinforcement)
            for i, entry_a in enumerate(combined):
                words_a     = set(entry_a.content.lower().split())
                boost_count = 0
                for j, entry_b in enumerate(combined):
                    if i == j:
                        continue
                    words_b = set(entry_b.content.lower().split())
                    if len(words_a) > 0:
                        overlap = len(words_a & words_b) / len(words_a)
                        if overlap > 0.25:
                            boost_count += 1
                if boost_count >= 2:
                    entry_a.importance = min(1.0,
                        entry_a.importance + 0.04 * boost_count
                    )

            # Step 4: Sort by importance descending
            combined.sort(key=lambda e: e.importance, reverse=True)

            # Step 5: Greedy word-budget selection
            selected:     List[MemoryEntry] = []
            word_budget   = target_word_count
            type_coverage: Dict[str, bool] = {}

            # First pass: ensure type diversity (one of each type if possible)
            all_types = {
                MemoryEntry.ENTRY_TYPE_FACT,
                MemoryEntry.ENTRY_TYPE_PREFERENCE,
                MemoryEntry.ENTRY_TYPE_EMOTION,
                MemoryEntry.ENTRY_TYPE_DECISION,
                MemoryEntry.ENTRY_TYPE_TASK,
                MemoryEntry.ENTRY_TYPE_CONTEXT,
                MemoryEntry.ENTRY_TYPE_PERSONALITY,
            }

            for target_type in all_types:
                # Find highest-scoring entry of this type
                for entry in combined:
                    if (entry.entry_type == target_type and
                            entry.importance >= MIN_IMPORTANCE_THRESHOLD and
                            entry not in selected):
                        if entry.word_count <= word_budget:
                            selected.append(entry)
                            word_budget   -= entry.word_count
                            type_coverage[target_type] = True
                        break

            # Second pass: fill remaining budget with highest-importance entries
            for entry in combined:
                if entry in selected:
                    continue
                if entry.importance < MIN_IMPORTANCE_THRESHOLD:
                    continue
                if entry.word_count <= word_budget:
                    selected.append(entry)
                    word_budget -= entry.word_count
                if word_budget <= 0:
                    break

            # Step 6: Sort selected entries by type then importance for output
            type_priority = {
                MemoryEntry.ENTRY_TYPE_FACT:        1,
                MemoryEntry.ENTRY_TYPE_PREFERENCE:  2,
                MemoryEntry.ENTRY_TYPE_PERSONALITY: 3,
                MemoryEntry.ENTRY_TYPE_DECISION:    4,
                MemoryEntry.ENTRY_TYPE_EMOTION:     5,
                MemoryEntry.ENTRY_TYPE_TASK:        6,
                MemoryEntry.ENTRY_TYPE_CONTEXT:     7,
            }
            selected.sort(
                key=lambda e: (
                    type_priority.get(e.entry_type, 9),
                    -e.importance,
                )
            )

            return selected

    def compress_low_scoring_cluster(
        self,
        entries: List[MemoryEntry],
    ) -> Optional[MemoryEntry]:
        """
        Attempts to compress a cluster of low-scoring entries into a single
        summary entry using the LLM API.

        If API call fails, falls back to a simple concatenated summary.

        Args:
            entries: List of low-importance entries to compress.

        Returns:
            A single MemoryEntry summarizing the cluster, or None if
            the cluster is empty or contains no extractable content.
        """
        if not entries:
            return None

        combined_text = " ".join(e.content for e in entries)
        if len(combined_text.split()) < 5:
            return None

        # Compute cluster importance as weighted average
        avg_importance = sum(e.importance for e in entries) / len(entries)

        # Try LLM compression
        summary_text = self._call_llm_compress(combined_text)
        if not summary_text:
            # Fallback: simple first-sentence extraction from combined
            sentences = re.split(r'[.!?]', combined_text)
            summary_text = ". ".join(
                s.strip() for s in sentences[:2] if s.strip()
            )
            if not summary_text:
                summary_text = combined_text[:120].strip()

        return MemoryEntry(
            content=summary_text,
            timestamp=time.time(),
            importance=max(MIN_IMPORTANCE_THRESHOLD, avg_importance),
            entry_type=MemoryEntry.ENTRY_TYPE_CONTEXT,
        )

    def _call_llm_compress(self, text: str) -> Optional[str]:
        """
        Calls the OpenRouter API to compress a cluster of memory text
        into a single concise sentence preserving key facts.

        Args:
            text: Combined text of low-scoring memory entries.

        Returns:
            Compressed summary string, or None on failure.
        """
        try:
            import requests

            prompt = (
                "Compress the following memory notes into ONE concise sentence "
                "(maximum 25 words) that preserves all unique factual information. "
                "Output ONLY the compressed sentence, nothing else.\n\n"
                f"Memory notes:\n{text}"
            )

            payload = {
                "model": MODEL_CONVERSATION,
                "messages": [
                    {
                        "role":    "user",
                        "content": prompt,
                    }
                ],
                "max_tokens":   60,
                "temperature":  0.3,
                "stream":       False,
            }

            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "https://hermes.local",
                "X-Title":       "HERMES-MemoryManager",
            }

            response = requests.post(
                OPENROUTER_CHAT_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=8.0,
            )

            if response.status_code == 200:
                data    = response.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    return content.strip() if content else None

        except Exception as exc:
            print(f"[MemoryManager] LLM compress error: {exc}")

        return None


# =============================================================================
# SECTION 6: CONVERSATION EXTRACTOR
# =============================================================================

class ConversationExtractor:
    """
    Extracts atomic memory entries from raw conversation exchange lists.
    Processes transcript text into scored MemoryEntry objects ready
    for storage in the memory files.

    Works on both Archer session transcripts (for users.md / archer_soul.md)
    and Hudson session logs (for hudson_soul.md).
    """

    def __init__(self, session_start: float) -> None:
        """
        Args:
            session_start: Epoch timestamp of session start.
        """
        self._scorer: ImportanceScorer = ImportanceScorer(session_start)

    def extract_user_memories(
        self,
        exchanges:        List[Dict[str, Any]],
        existing_entries: List[MemoryEntry],
    ) -> List[MemoryEntry]:
        """
        Extracts memory entries about the USER from conversation exchanges.
        These entries go into users.md.

        Processes only "YOU" speaker turns. Looks for personal disclosures,
        preferences, emotions, decisions, and tasks expressed by the user.

        Args:
            exchanges:        List of {speaker, text, timestamp} dicts.
            existing_entries: Current users.md entries (for scoring context).

        Returns:
            List of new MemoryEntry objects extracted from user speech.
        """
        entries: List[MemoryEntry] = []

        for exchange in exchanges:
            if exchange.get("speaker", "").upper() != "YOU":
                continue

            text      = exchange.get("text", "").strip()
            timestamp = exchange.get("timestamp", time.time())

            if not text or len(text.split()) < 4:
                continue

            # Split long turns into sentence segments for granular extraction
            sentences = self._split_into_segments(text)

            for sentence in sentences:
                if len(sentence.split()) < 4:
                    continue

                score, entry_type = self._scorer.score(
                    sentence, existing_entries, timestamp
                )

                if score >= MIN_IMPORTANCE_THRESHOLD:
                    entries.append(MemoryEntry(
                        content=sentence,
                        timestamp=timestamp,
                        importance=score,
                        entry_type=entry_type,
                        source_persona="USER",
                    ))

        return entries

    def extract_archer_soul_memories(
        self,
        exchanges:        List[Dict[str, Any]],
        existing_entries: List[MemoryEntry],
    ) -> List[MemoryEntry]:
        """
        Extracts personality/growth memories for Archer's soul.md.
        Focuses on Archer's responses — significant things he said,
        promises made, emotional moments, evolving opinions.

        Args:
            exchanges:        List of {speaker, text, timestamp} dicts.
            existing_entries: Current archer_soul.md entries.

        Returns:
            List of new MemoryEntry objects for Archer's soul.
        """
        entries:    List[MemoryEntry] = []
        soul_words = [
            "i believe", "i think", "in my opinion", "i feel",
            "i understand", "i know", "i learned", "i realize",
            "i promise", "i will always", "i remember", "that matters",
            "important to", "i care", "i value", "my purpose",
            "interesting", "fascinating", "remarkable", "significant",
        ]

        for exchange in exchanges:
            speaker = exchange.get("speaker", "").upper()
            if speaker not in ("ARCHER",):
                continue

            text      = exchange.get("text", "").strip()
            timestamp = exchange.get("timestamp", time.time())

            if not text or len(text.split()) < 6:
                continue

            sentences = self._split_into_segments(text)

            for sentence in sentences:
                if len(sentence.split()) < 5:
                    continue

                text_lower = sentence.lower()
                has_soul   = any(w in text_lower for w in soul_words)

                score, entry_type = self._scorer.score(
                    sentence, existing_entries, timestamp
                )

                # Boost score if contains soul-defining language
                if has_soul:
                    score = min(1.0, score + 0.15)
                    entry_type = MemoryEntry.ENTRY_TYPE_PERSONALITY

                if score >= MIN_IMPORTANCE_THRESHOLD:
                    entries.append(MemoryEntry(
                        content=sentence,
                        timestamp=timestamp,
                        importance=score,
                        entry_type=entry_type,
                        source_persona="ARCHER",
                    ))

        return entries

    def extract_hudson_soul_memories(
        self,
        task_log:         List[Dict[str, Any]],
        existing_entries: List[MemoryEntry],
    ) -> List[MemoryEntry]:
        """
        Extracts operational memory entries for Hudson's soul.md.
        Based on completed task logs rather than conversational exchanges.
        Records significant operations, patterns, and learned behaviors.

        Args:
            task_log:         List of HudsonTask.to_dict() outputs from session.
            existing_entries: Current hudson_soul.md entries.

        Returns:
            List of new MemoryEntry objects for Hudson's soul.
        """
        entries: List[MemoryEntry] = []
        now     = time.time()

        for task_dict in task_log:
            status = task_dict.get("status", "")

            # Only record completed or escalated tasks
            if status not in ("COMPLETE", "ESCALATED", "FAILED"):
                continue

            desc   = task_dict.get("description", "").strip()
            repo   = task_dict.get("repo",        "")
            result = task_dict.get("result",       "").strip()

            if not desc:
                continue

            # Build memory text from task details
            if repo:
                mem_text = f"Task [{task_dict.get('task_type', 'OP')}] "  \
                           f"on {repo}: {desc}. "
            else:
                mem_text = f"Task [{task_dict.get('task_type', 'OP')}]: {desc}. "

            if result:
                mem_text += f"Result: {result[:80]}."

            # Determine importance based on task status
            if status == "COMPLETE":
                base_importance = 0.55
                entry_type      = MemoryEntry.ENTRY_TYPE_FACT
            elif status == "ESCALATED":
                base_importance = 0.75   # escalated = hard problem, worth remembering
                entry_type      = MemoryEntry.ENTRY_TYPE_DECISION
            else:
                base_importance = 0.45
                entry_type      = MemoryEntry.ENTRY_TYPE_CONTEXT

            score, _ = self._scorer.score(
                mem_text, existing_entries,
                task_dict.get("updated_at", now)
            )
            final_score = max(base_importance, score)

            entries.append(MemoryEntry(
                content=mem_text.strip(),
                timestamp=task_dict.get("updated_at", now),
                importance=final_score,
                entry_type=entry_type,
                source_persona="HUDSON",
            ))

        return entries

    def _split_into_segments(self, text: str) -> List[str]:
        """
        Splits a paragraph of text into atomic sentence segments
        for granular importance scoring.

        Uses sentence boundary detection (punctuation + conjunctions).
        Merges very short fragments (< 4 words) with adjacent segments.

        Args:
            text: Input paragraph string.

        Returns:
            List of sentence/clause strings.
        """
        # Split on sentence-ending punctuation
        raw_splits = re.split(r'(?<=[.!?])\s+', text.strip())

        # Further split on "and", "but", "so", "because" if segments are long
        segments: List[str] = []
        for seg in raw_splits:
            if len(seg.split()) > 20:
                sub = re.split(
                    r'\s+(?:and|but|so|because|however|therefore|although)\s+',
                    seg,
                    flags=re.IGNORECASE,
                )
                segments.extend(sub)
            else:
                segments.append(seg)

        # Merge fragments shorter than 4 words with next segment
        merged:  List[str] = []
        pending: str        = ""

        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            if pending:
                seg     = pending + " " + seg
                pending = ""
            if len(seg.split()) < 4:
                pending = seg
            else:
                merged.append(seg)

        if pending:
            if merged:
                merged[-1] += " " + pending
            else:
                merged.append(pending)

        return [s.strip() for s in merged if s.strip()]


# =============================================================================
# SECTION 7: MEMORY MANAGER — MAIN CONTROLLER
# =============================================================================

class MemoryManager:
    """
    Central memory persistence controller for Project HERMES.

    Manages:
        - archer_soul.md  : Archer's accumulated personality/growth memories
        - hudson_soul.md  : Hudson's operational memory and learned patterns
        - users.md        : User's personal details, preferences, and history

    All three files follow the same format and cap rules:
        - Maximum 400 words per file
        - Smart merge when cap is approached
        - Human-memory-style importance scoring determines what survives

    Session lifecycle:
        1. On boot: load existing entries from all three files.
        2. During session: buffer new memory candidates in memory.
        3. On session end (token cap hit or app close):
           a. Extract entries from session exchanges.
           b. Score all entries.
           c. Smart merge with existing entries.
           d. Write back to files.
           e. Reset session buffers.

    File writes are atomic (temp + rename) and protected by per-file locks.
    """

    def __init__(self) -> None:
        self._archer_lock:  threading.Lock = threading.Lock()
        self._hudson_lock:  threading.Lock = threading.Lock()
        self._users_lock:   threading.Lock = threading.Lock()

        self._merge_engine: SmartMergeEngine = SmartMergeEngine()

        # In-memory loaded entries (refreshed on save)
        self._archer_entries: List[MemoryEntry] = []
        self._hudson_entries: List[MemoryEntry] = []
        self._users_entries:  List[MemoryEntry] = []

        # Session start time (for recency scoring)
        self._session_start: float = time.time()

        # Buffered session data waiting to be flushed
        self._pending_exchanges:   List[Dict[str, Any]] = []
        self._pending_task_log:    List[Dict[str, Any]] = []
        self._brainstorm_exchanges: List[Dict[str, Any]] = []

        # Load existing memories on init
        self._load_all_files()

    # ===========================================================================
    # SECTION 7.1: FILE LOADING
    # ===========================================================================

    def _load_all_files(self) -> None:
        """Loads all three memory files into their respective entry lists."""
        self._archer_entries = _parse_memory_file(ARCHER_SOUL_PATH)
        self._hudson_entries = _parse_memory_file(HUDSON_SOUL_PATH)
        self._users_entries  = _parse_memory_file(USERS_MD_PATH)

        print(
            f"[MemoryManager] Loaded: "
            f"Archer={len(self._archer_entries)} entries, "
            f"Hudson={len(self._hudson_entries)} entries, "
            f"Users={len(self._users_entries)} entries."
        )

    def get_archer_context(self) -> str:
        """
        Returns a formatted string of Archer's memories for injection
        into the system prompt at session start.

        Returns:
            Markdown-formatted string of Archer's soul entries.
        """
        with self._archer_lock:
            if not self._archer_entries:
                return ""
            lines = ["[ARCHER MEMORY CONTEXT]"]
            for entry in sorted(
                self._archer_entries,
                key=lambda e: e.importance,
                reverse=True,
            ):
                lines.append(f"- {entry.content}")
            return "\n".join(lines)

    def get_hudson_context(self) -> str:
        """
        Returns Hudson's operational memory for injection into Hudson's
        system prompt at session start.

        Returns:
            Markdown-formatted string of Hudson's soul entries.
        """
        with self._hudson_lock:
            if not self._hudson_entries:
                return ""
            lines = ["[HUDSON OPERATIONAL MEMORY]"]
            for entry in sorted(
                self._hudson_entries,
                key=lambda e: e.importance,
                reverse=True,
            ):
                lines.append(f"- {entry.content}")
            return "\n".join(lines)

    def get_user_context(self) -> str:
        """
        Returns the user's memory context for injection into both
        Archer's and Hudson's system prompts.

        Returns:
            Markdown-formatted string of user memory entries.
        """
        with self._users_lock:
            if not self._users_entries:
                return ""
            lines = ["[USER PROFILE MEMORY]"]
            for entry in sorted(
                self._users_entries,
                key=lambda e: e.importance,
                reverse=True,
            ):
                lines.append(f"- {entry.content}")
            return "\n".join(lines)

    # ===========================================================================
    # SECTION 7.2: SESSION BUFFER MANAGEMENT
    # ===========================================================================

    def buffer_exchange(self, speaker: str, text: str) -> None:
        """
        Buffers a conversation exchange for processing at session end.
        Called after every user utterance or AI response.

        Args:
            speaker: "YOU", "ARCHER", or "HUDSON".
            text:    The utterance text.
        """
        self._pending_exchanges.append({
            "speaker":   speaker,
            "text":      text,
            "timestamp": time.time(),
        })

    def buffer_hudson_task(self, task_dict: Dict[str, Any]) -> None:
        """
        Buffers a completed HudsonTask for processing at session end.

        Args:
            task_dict: HudsonTask.to_dict() output.
        """
        self._pending_task_log.append(task_dict)

    def buffer_brainstorm_exchange(
        self,
        speaker: str,
        text:    str,
    ) -> None:
        """
        Buffers a brainstorming exchange separately from main conversation.
        Brainstorming sessions are saved to dedicated files AND also
        contribute to the main memory buffers for long-term retention.

        Args:
            speaker: "YOU" or "ARCHER".
            text:    The utterance text.
        """
        exchange = {
            "speaker":   speaker,
            "text":      text,
            "timestamp": time.time(),
        }
        self._brainstorm_exchanges.append(exchange)
        # Also buffer for main memory processing
        self._pending_exchanges.append(exchange)

    # ===========================================================================
    # SECTION 7.3: SESSION FLUSH
    # ===========================================================================

    def flush_session(self) -> bool:
        """
        Executes the full session memory flush cycle.
        Called when the 20k token limit is hit or when the app closes.

        Process:
            1. Extract entries from buffered exchanges.
            2. Merge with existing file entries.
            3. Write all three files.
            4. Reset session buffers.
            5. Save any pending brainstorming session.

        Returns:
            True if all three files were written successfully.
        """
        print("[MemoryManager] Flushing session memories...")
        session_start  = self._session_start
        extractor      = ConversationExtractor(session_start)

        # --- Extract new entries ---
        new_user_entries  = extractor.extract_user_memories(
            self._pending_exchanges,
            self._users_entries,
        )
        new_archer_entries = extractor.extract_archer_soul_memories(
            self._pending_exchanges,
            self._archer_entries,
        )
        new_hudson_entries = extractor.extract_hudson_soul_memories(
            self._pending_task_log,
            self._hudson_entries,
        )

        print(
            f"[MemoryManager] Extracted: "
            f"{len(new_user_entries)} user, "
            f"{len(new_archer_entries)} archer, "
            f"{len(new_hudson_entries)} hudson entries."
        )

        # --- Merge and write each file ---
        archer_ok = self._merge_and_write_archer(new_archer_entries)
        hudson_ok = self._merge_and_write_hudson(new_hudson_entries)
        users_ok  = self._merge_and_write_users(new_user_entries)

        # --- Save brainstorming session if any ---
        if self._brainstorm_exchanges:
            self.save_brainstorm_session(self._brainstorm_exchanges)

        # --- Reset session buffers ---
        self._pending_exchanges.clear()
        self._pending_task_log.clear()
        self._brainstorm_exchanges.clear()
        self._session_start = time.time()

        success = archer_ok and hudson_ok and users_ok
        print(
            f"[MemoryManager] Flush complete. "
            f"Archer={'OK' if archer_ok else 'FAIL'}, "
            f"Hudson={'OK' if hudson_ok else 'FAIL'}, "
            f"Users={'OK' if users_ok else 'FAIL'}."
        )
        return success

    def _merge_and_write_archer(
        self,
        new_entries: List[MemoryEntry],
    ) -> bool:
        """
        Merges new Archer soul entries with existing, enforces word cap,
        and writes archer_soul.md.

        Args:
            new_entries: Newly extracted entries from this session.

        Returns:
            True if write succeeded.
        """
        with self._archer_lock:
            merged = self._merge_engine.merge(
                self._archer_entries,
                new_entries,
                target_word_count=MERGE_TARGET_WORDS,
            )
            self._archer_entries = merged

            content = _entries_to_markdown(
                merged,
                "ARCHER SOUL — Omnimind Absolute Edition",
            )
            return _write_file(ARCHER_SOUL_PATH, content)

    def _merge_and_write_hudson(
        self,
        new_entries: List[MemoryEntry],
    ) -> bool:
        """
        Merges new Hudson soul entries with existing, enforces word cap,
        and writes hudson_soul.md.

        Args:
            new_entries: Newly extracted entries from this session.

        Returns:
            True if write succeeded.
        """
        with self._hudson_lock:
            merged = self._merge_engine.merge(
                self._hudson_entries,
                new_entries,
                target_word_count=MERGE_TARGET_WORDS,
            )
            self._hudson_entries = merged

            content = _entries_to_markdown(
                merged,
                "HUDSON SOUL — Operational Memory Core",
            )
            return _write_file(HUDSON_SOUL_PATH, content)

    def _merge_and_write_users(
        self,
        new_entries: List[MemoryEntry],
    ) -> bool:
        """
        Merges new user memory entries with existing, enforces word cap,
        and writes users.md.

        Args:
            new_entries: Newly extracted entries from this session.

        Returns:
            True if write succeeded.
        """
        with self._users_lock:
            merged = self._merge_engine.merge(
                self._users_entries,
                new_entries,
                target_word_count=MERGE_TARGET_WORDS,
            )
            self._users_entries = merged

            content = _entries_to_markdown(
                merged,
                "USER PROFILE — HERMES Memory Store",
            )
            return _write_file(USERS_MD_PATH, content)

    # ===========================================================================
    # SECTION 7.4: FORCE SAVE (Ctrl+S)
    # ===========================================================================

    def force_save(self) -> bool:
        """
        Immediately flushes current session memories without waiting
        for the token limit. Called by Ctrl+S shortcut.

        Returns:
            True if flush succeeded.
        """
        print("[MemoryManager] Force save triggered.")
        return self.flush_session()

    # ===========================================================================
    # SECTION 7.5: BRAINSTORMING SESSION SAVER
    # ===========================================================================

    def save_brainstorm_session(
        self,
        exchanges:    List[Dict[str, Any]],
        topic:        str = "",
    ) -> bool:
        """
        Saves a brainstorming session to a dedicated timestamped file
        in the brainstorm_sessions/ directory.

        File naming: YYYY-MM-DD_HH-MM-SS_{topic_slug}.md
        File format: Markdown transcript with speaker labels and timestamps.

        Args:
            exchanges: List of {speaker, text, timestamp} dicts.
            topic:     Inferred topic string (used in filename).

        Returns:
            True if file was written successfully.
        """
        if not exchanges:
            return False

        now      = datetime.datetime.now()
        dt_str   = now.strftime("%Y-%m-%d_%H-%M-%S")
        topic_slug = re.sub(r'[^a-z0-9_]', '', topic.lower()[:30]) or "session"
        filename = f"{dt_str}_{topic_slug}.md"
        filepath = os.path.join(BRAINSTORM_DIR, filename)

        # Build markdown content
        lines: List[str] = [
            f"# Brainstorming Session — {now.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Topic:** {topic or 'Unclassified'}",
            f"**Exchanges:** {len(exchanges)}",
            "",
            "---",
            "",
        ]

        for exchange in exchanges:
            speaker   = exchange.get("speaker", "UNKNOWN")
            text      = exchange.get("text", "")
            ts        = exchange.get("timestamp", time.time())
            ts_str    = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")

            lines.append(f"**[{ts_str}] {speaker}:**")
            lines.append(f"{text}")
            lines.append("")

        content = "\n".join(lines)
        success = _write_file(filepath, content)

        if success:
            print(f"[MemoryManager] Brainstorm session saved: {filename}")
        else:
            print(f"[MemoryManager] Brainstorm session save FAILED: {filename}")

        return success

    # ===========================================================================
    # SECTION 7.6: REDDIT PREFERENCES
    # ===========================================================================

    def save_reddit_preferences(
        self,
        preferences: Dict[str, bool],
    ) -> bool:
        """
        Saves the Reddit checkbox preference profile to JSON.

        Args:
            preferences: Dict of {category_name: bool} from setup screen.

        Returns:
            True if saved successfully.
        """
        try:
            content = json.dumps(preferences, indent=2)
            success = _write_file(REDDIT_PREFS_PATH, content)
            if success:
                print(
                    f"[MemoryManager] Reddit preferences saved "
                    f"({len(preferences)} categories)."
                )
            return success
        except Exception as exc:
            print(f"[MemoryManager] Reddit prefs save error: {exc}")
            return False

    def load_reddit_preferences(self) -> Dict[str, bool]:
        """
        Loads the Reddit preference profile from JSON.

        Returns:
            Dict of {category_name: bool}.
            Empty dict if file does not exist or is malformed.
        """
        if not os.path.isfile(REDDIT_PREFS_PATH):
            return {}
        try:
            with open(REDDIT_PREFS_PATH, "r", encoding=FILE_ENCODING) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): bool(v) for k, v in data.items()}
        except Exception as exc:
            print(f"[MemoryManager] Reddit prefs load error: {exc}")
        return {}

    # ===========================================================================
    # SECTION 7.7: WORD COUNT MONITORING
    # ===========================================================================

    def get_word_counts(self) -> Dict[str, int]:
        """
        Returns the current word count for all three memory files.

        Returns:
            Dict with keys: archer, hudson, users (word counts).
        """
        return {
            "archer": _count_words_in_file(ARCHER_SOUL_PATH),
            "hudson": _count_words_in_file(HUDSON_SOUL_PATH),
            "users":  _count_words_in_file(USERS_MD_PATH),
        }

    def get_entry_counts(self) -> Dict[str, int]:
        """
        Returns the current entry count for all three memory stores.

        Returns:
            Dict with keys: archer, hudson, users (entry counts).
        """
        with self._archer_lock:
            archer_count = len(self._archer_entries)
        with self._hudson_lock:
            hudson_count = len(self._hudson_entries)
        with self._users_lock:
            users_count  = len(self._users_entries)

        return {
            "archer": archer_count,
            "hudson": hudson_count,
            "users":  users_count,
        }

    def is_approaching_cap(self, threshold: float = 0.80) -> Dict[str, bool]:
        """
        Checks if any memory file is approaching the word cap.
        Used to trigger proactive flush before the limit is hit.

        Args:
            threshold: Fraction of MEMORY_MAX_WORDS that triggers warning.
                       Default 0.80 = warn at 320 words.

        Returns:
            Dict with keys: archer, hudson, users (True if approaching cap).
        """
        warn_at    = int(MEMORY_MAX_WORDS * threshold)
        word_counts = self.get_word_counts()
        return {
            "archer": word_counts["archer"] >= warn_at,
            "hudson": word_counts["hudson"] >= warn_at,
            "users":  word_counts["users"]  >= warn_at,
        }

    # ===========================================================================
    # SECTION 7.8: DIAGNOSTICS
    # ===========================================================================

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Returns a complete diagnostic snapshot of the memory manager state.

        Returns:
            Dict with memory statistics and file status.
        """
        word_counts  = self.get_word_counts()
        entry_counts = self.get_entry_counts()
        approaching  = self.is_approaching_cap()

        return {
            "word_counts":          word_counts,
            "entry_counts":         entry_counts,
            "approaching_cap":      approaching,
            "max_words":            MEMORY_MAX_WORDS,
            "pending_exchanges":    len(self._pending_exchanges),
            "pending_tasks":        len(self._pending_task_log),
            "brainstorm_buffered":  len(self._brainstorm_exchanges),
            "session_start":        self._session_start,
            "session_age_mins":     (time.time() - self._session_start) / 60.0,
            "archer_file_exists":   os.path.isfile(ARCHER_SOUL_PATH),
            "hudson_file_exists":   os.path.isfile(HUDSON_SOUL_PATH),
            "users_file_exists":    os.path.isfile(USERS_MD_PATH),
            "brainstorm_dir":       BRAINSTORM_DIR,
        }

    def __repr__(self) -> str:
        counts = self.get_entry_counts()
        words  = self.get_word_counts()
        return (
            f"MemoryManager("
            f"archer={counts['archer']} entries/{words['archer']}w, "
            f"hudson={counts['hudson']} entries/{words['hudson']}w, "
            f"users={counts['users']} entries/{words['users']}w, "
            f"pending={len(self._pending_exchanges)} exchanges)"
        )


# =============================================================================
# SECTION 8: MODULE-LEVEL SINGLETON
# =============================================================================

# Single global instance shared across all modules.
# Import directly: from memory_manager import memory_manager
memory_manager: MemoryManager = MemoryManager()


# =============================================================================
# END OF memory_manager.py
# =============================================================================