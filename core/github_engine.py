# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: github_engine.py
# ROLE: Hudson's autonomous GitHub monitoring and issue resolution engine.
#       Watches all repositories for new issues, evaluates complexity,
#       applies fixes for minor issues, commits and pushes directly to
#       main branch, escalates hard issues to the user with full context.
#       Zero pygame imports. Pure GitHub API + git operations.
# =============================================================================

import os
import re
import sys
import json
import time
import shutil
import tempfile
import threading
import subprocess
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
    REQUESTS_AVAILABLE: bool = True
except ImportError:
    REQUESTS_AVAILABLE: bool = False

from core.config import (
    GITHUB_API_BASE,
    GITHUB_TOKEN_PLACEHOLDER,
    GITHUB_MIN_ANALYSIS_SECONDS,
    GITHUB_COMMIT_MESSAGE_PREFIX,
    GITHUB_MINOR_KEYWORDS,
    GITHUB_HARD_KEYWORDS,
    GITHUB_POLL_RATE,
    ActiveConfig,
)

# =============================================================================
# SECTION 1: CONSTANTS
# =============================================================================

# GitHub API endpoints
GITHUB_REPOS_ENDPOINT:    str = f"{GITHUB_API_BASE}/user/repos"
GITHUB_ISSUES_ENDPOINT:   str = f"{GITHUB_API_BASE}/repos/{{owner}}/{{repo}}/issues"
GITHUB_ISSUE_ENDPOINT:    str = f"{GITHUB_API_BASE}/repos/{{owner}}/{{repo}}/issues/{{number}}"
GITHUB_CONTENTS_ENDPOINT: str = f"{GITHUB_API_BASE}/repos/{{owner}}/{{repo}}/contents/{{path}}"
GITHUB_COMMITS_ENDPOINT:  str = f"{GITHUB_API_BASE}/repos/{{owner}}/{{repo}}/git/commits"
GITHUB_REFS_ENDPOINT:     str = f"{GITHUB_API_BASE}/repos/{{owner}}/{{repo}}/git/refs/heads/{{branch}}"
GITHUB_PULLS_ENDPOINT:    str = f"{GITHUB_API_BASE}/repos/{{owner}}/{{repo}}/pulls"
GITHUB_RATE_LIMIT:        str = f"{GITHUB_API_BASE}/rate_limit"

# HTTP request settings
REQUEST_TIMEOUT:       float = 20.0
MAX_RETRIES:           int   = 3
RETRY_DELAY:           float = 2.0
MIN_REQUEST_GAP:       float = 0.5   # 500ms between GitHub API calls

# Issue tracking
MAX_ISSUE_AGE_DAYS:    float = 7.0   # ignore issues older than 7 days
MAX_ISSUES_PER_REPO:   int   = 10    # max issues to process per poll cycle

# Clone settings
CLONE_TIMEOUT:         float = 60.0  # max seconds for git clone
GIT_OPERATION_TIMEOUT: float = 30.0  # max seconds for git operations

# Label for Hudson-processed issues
HUDSON_LABEL:          str   = "hudson-processed"
HUDSON_ESCALATE_LABEL: str   = "needs-human-review"

# Issue states
ISSUE_STATE_OPEN:      str   = "open"
ISSUE_STATE_CLOSED:    str   = "closed"

# =============================================================================
# SECTION 2: GITHUB ISSUE DATA CLASS
# =============================================================================

class GitHubIssue:
    """
    Structured container for a single GitHub issue fetched from the API.
    Tracks processing state across the evaluation lifecycle.
    """

    STATE_NEW:        str = "NEW"
    STATE_ANALYZING:  str = "ANALYZING"
    STATE_FIXING:     str = "FIXING"
    STATE_FIXED:      str = "FIXED"
    STATE_ESCALATED:  str = "ESCALATED"
    STATE_SKIPPED:    str = "SKIPPED"
    STATE_FAILED:     str = "FAILED"

    def __init__(
        self,
        number:       int,
        title:        str,
        body:         str,
        repo_full:    str,
        url:          str,
        created_at:   str,
        labels:       List[str],
        author:       str,
    ) -> None:
        self.number:       int        = number
        self.title:        str        = title
        self.body:         str        = body if body else ""
        self.repo_full:    str        = repo_full   # "owner/repo"
        self.url:          str        = url
        self.created_at:   str        = created_at
        self.labels:       List[str]  = labels
        self.author:       str        = author
        self.state:        str        = GitHubIssue.STATE_NEW
        self.classification: str      = ""
        self.reasoning:    str        = ""
        self.suggested_fix: str       = ""
        self.fix_applied:  bool       = False
        self.commit_sha:   str        = ""
        self.analysis_start: float    = 0.0
        self.analysis_end:   float    = 0.0

    def owner(self) -> str:
        """Returns the repository owner (first part of repo_full)."""
        parts = self.repo_full.split("/")
        return parts[0] if len(parts) >= 2 else ""

    def repo_name(self) -> str:
        """Returns the repository name (second part of repo_full)."""
        parts = self.repo_full.split("/")
        return parts[1] if len(parts) >= 2 else self.repo_full

    def age_days(self) -> float:
        """
        Returns the age of this issue in days from creation to now.

        Returns:
            Float days since issue creation.
        """
        try:
            import datetime
            dt  = datetime.datetime.strptime(
                self.created_at, "%Y-%m-%dT%H:%M:%SZ"
            )
            now = datetime.datetime.utcnow()
            return (now - dt).total_seconds() / 86400.0
        except Exception:
            return 0.0

    def is_already_processed(self) -> bool:
        """
        Checks if this issue already has the Hudson-processed label.

        Returns:
            True if the issue was previously handled by Hudson.
        """
        return (
            HUDSON_LABEL in self.labels or
            HUDSON_ESCALATE_LABEL in self.labels
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes to a plain dictionary for HudsonTask logging."""
        return {
            "number":         self.number,
            "title":          self.title,
            "body_preview":   self.body[:200],
            "repo_full":      self.repo_full,
            "url":            self.url,
            "state":          self.state,
            "classification": self.classification,
            "fix_applied":    self.fix_applied,
            "commit_sha":     self.commit_sha,
        }

    def __repr__(self) -> str:
        return (
            f"GitHubIssue(#{self.number}, "
            f"repo={self.repo_full}, "
            f"state={self.state}, "
            f"class={self.classification})"
        )


# =============================================================================
# SECTION 3: GITHUB API CLIENT
# =============================================================================

class GitHubAPIClient:
    """
    Authenticated GitHub REST API v3 client.
    Handles pagination, rate limiting, retry logic, and all
    repository/issue/content operations required by Hudson.
    """

    def __init__(self, token: str) -> None:
        """
        Args:
            token: GitHub Personal Access Token string.
        """
        self._token:          str   = token
        self._last_call_time: float = 0.0
        self._rate_remaining: int   = 5000
        self._rate_reset:     float = 0.0

    def _headers(self) -> Dict[str, str]:
        """Returns authenticated request headers."""
        return {
            "Authorization": f"token {self._token}",
            "Accept":        "application/vnd.github.v3+json",
            "Content-Type":  "application/json",
            "User-Agent":    "HERMES-Hudson/1.0",
        }

    def _enforce_rate_limit(self) -> None:
        """
        Enforces minimum gap between API calls and waits
        if the GitHub rate limit has been reached.
        """
        now     = time.time()
        elapsed = now - self._last_call_time
        if elapsed < MIN_REQUEST_GAP:
            time.sleep(MIN_REQUEST_GAP - elapsed)

        # Check if rate limit is exhausted
        if self._rate_remaining <= 5 and self._rate_reset > now:
            wait_time = self._rate_reset - now + 1.0
            print(
                f"[GitHubAPI] Rate limit reached. "
                f"Waiting {wait_time:.0f}s until reset..."
            )
            time.sleep(wait_time)

    def _request(
        self,
        method:  str,
        url:     str,
        payload: Optional[Dict] = None,
        params:  Optional[Dict] = None,
    ) -> Optional[Any]:
        """
        Executes an authenticated HTTP request with retry logic.

        Args:
            method:  HTTP method string ("GET", "POST", "PATCH", etc.).
            url:     Full URL string.
            payload: JSON request body dict (for POST/PATCH).
            params:  URL query parameters dict.

        Returns:
            Parsed JSON response (dict or list), or None on failure.
        """
        if not REQUESTS_AVAILABLE:
            return None

        self._enforce_rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self._headers(),
                    json=payload,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )

                # Update rate limit tracking from response headers
                remaining = response.headers.get("X-RateLimit-Remaining")
                reset_ts  = response.headers.get("X-RateLimit-Reset")
                if remaining is not None:
                    self._rate_remaining = int(remaining)
                if reset_ts is not None:
                    self._rate_reset = float(reset_ts)

                self._last_call_time = time.time()

                if response.status_code in (200, 201, 204):
                    if response.status_code == 204:
                        return {}
                    return response.json()

                if response.status_code == 403:
                    # Rate limit or forbidden
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        time.sleep(float(retry_after))
                    elif "rate limit" in response.text.lower():
                        time.sleep(60.0)
                    continue

                if response.status_code == 404:
                    # Resource not found — not a retry-able error
                    return None

                if response.status_code in (500, 502, 503):
                    # Server error — retry
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue

                print(
                    f"[GitHubAPI] HTTP {response.status_code} on "
                    f"{method} {url}: {response.text[:100]}"
                )
                return None

            except requests.exceptions.Timeout:
                print(
                    f"[GitHubAPI] Timeout on {method} {url} "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(RETRY_DELAY)
            except requests.exceptions.ConnectionError:
                print(
                    f"[GitHubAPI] Connection error on {method} {url} "
                    f"(attempt {attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(RETRY_DELAY)
            except Exception as exc:
                print(f"[GitHubAPI] Request error: {exc}")
                return None

        return None

    def validate_token(self) -> Tuple[bool, str]:
        """
        Validates the GitHub token by fetching the authenticated user.

        Returns:
            Tuple of (is_valid: bool, username: str).
        """
        data = self._request("GET", f"{GITHUB_API_BASE}/user")
        if data and isinstance(data, dict):
            return (True, data.get("login", "unknown"))
        return (False, "")

    def get_all_repos(self) -> List[Dict[str, Any]]:
        """
        Fetches all repositories accessible to the authenticated user.
        Handles pagination to retrieve all repos (not just first 30).

        Returns:
            List of repository data dicts.
        """
        repos: List[Dict] = []
        page   = 1
        per_page = 100

        while True:
            data = self._request(
                "GET",
                GITHUB_REPOS_ENDPOINT,
                params={
                    "per_page": per_page,
                    "page":     page,
                    "sort":     "updated",
                    "direction": "desc",
                },
            )

            if not data or not isinstance(data, list):
                break

            repos.extend(data)

            if len(data) < per_page:
                # Last page reached
                break

            page += 1

            # Safety cap: never fetch more than 1000 repos
            if len(repos) >= 1000:
                break

        return repos

    def get_open_issues(
        self,
        owner:  str,
        repo:   str,
        limit:  int = MAX_ISSUES_PER_REPO,
    ) -> List[Dict[str, Any]]:
        """
        Fetches open issues for a repository.
        Filters out pull requests (GitHub returns PRs as issues).

        Args:
            owner: Repository owner username.
            repo:  Repository name.
            limit: Maximum number of issues to return.

        Returns:
            List of issue data dicts (no pull requests).
        """
        url  = GITHUB_ISSUES_ENDPOINT.format(owner=owner, repo=repo)
        data = self._request(
            "GET",
            url,
            params={
                "state":    ISSUE_STATE_OPEN,
                "per_page": limit,
                "sort":     "created",
                "direction": "desc",
            },
        )

        if not data or not isinstance(data, list):
            return []

        # Filter out pull requests
        issues = [
            item for item in data
            if "pull_request" not in item
        ]

        return issues[:limit]

    def get_issue_details(
        self,
        owner:        str,
        repo:         str,
        issue_number: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches full details for a specific issue.

        Args:
            owner:        Repository owner.
            repo:         Repository name.
            issue_number: Issue number integer.

        Returns:
            Issue data dict or None if not found.
        """
        url = GITHUB_ISSUE_ENDPOINT.format(
            owner=owner,
            repo=repo,
            number=issue_number,
        )
        return self._request("GET", url)

    def get_file_content(
        self,
        owner:    str,
        repo:     str,
        path:     str,
        branch:   str = "main",
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetches the content and SHA of a file from the repository.
        Returns decoded content (base64 decoded) and the file's blob SHA.

        Args:
            owner:  Repository owner.
            repo:   Repository name.
            path:   File path within the repository.
            branch: Branch name. Default "main".

        Returns:
            Tuple of (decoded_content: str | None, blob_sha: str | None).
        """
        import base64

        url  = GITHUB_CONTENTS_ENDPOINT.format(
            owner=owner,
            repo=repo,
            path=path,
        )
        data = self._request(
            "GET",
            url,
            params={"ref": branch},
        )

        if not data or not isinstance(data, dict):
            return (None, None)

        content_b64 = data.get("content", "")
        blob_sha    = data.get("sha", "")

        try:
            # GitHub returns content with newlines embedded in base64
            clean_b64 = content_b64.replace("\n", "")
            decoded   = base64.b64decode(clean_b64).decode("utf-8", errors="replace")
            return (decoded, blob_sha)
        except Exception as exc:
            print(f"[GitHubAPI] Base64 decode error for {path}: {exc}")
            return (None, blob_sha)

    def update_file_content(
        self,
        owner:          str,
        repo:           str,
        path:           str,
        new_content:    str,
        blob_sha:       str,
        commit_message: str,
        branch:         str = "main",
    ) -> Optional[str]:
        """
        Updates a file in the repository via the Contents API.
        Commits the change directly to the specified branch.

        Args:
            owner:          Repository owner.
            repo:           Repository name.
            path:           File path within the repository.
            new_content:    New file content string (will be base64 encoded).
            blob_sha:       Current file blob SHA (required by GitHub API).
            commit_message: Commit message string.
            branch:         Target branch. Default "main".

        Returns:
            Commit SHA string on success, None on failure.
        """
        import base64

        url         = GITHUB_CONTENTS_ENDPOINT.format(
            owner=owner,
            repo=repo,
            path=path,
        )
        encoded     = base64.b64encode(
            new_content.encode("utf-8")
        ).decode("utf-8")

        payload = {
            "message": commit_message,
            "content": encoded,
            "sha":     blob_sha,
            "branch":  branch,
        }

        data = self._request("PUT", url, payload=payload)

        if data and isinstance(data, dict):
            commit_data = data.get("commit", {})
            return commit_data.get("sha", "")

        return None

    def add_issue_label(
        self,
        owner:        str,
        repo:         str,
        issue_number: int,
        labels:       List[str],
    ) -> bool:
        """
        Adds labels to a GitHub issue.
        Creates labels if they don't exist on the repo.

        Args:
            owner:        Repository owner.
            repo:         Repository name.
            issue_number: Issue number.
            labels:       List of label name strings to add.

        Returns:
            True if labels were added successfully.
        """
        url     = (f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
                   f"/issues/{issue_number}/labels")
        payload = {"labels": labels}
        data    = self._request("POST", url, payload=payload)
        return data is not None

    def create_issue_comment(
        self,
        owner:        str,
        repo:         str,
        issue_number: int,
        body:         str,
    ) -> bool:
        """
        Posts a comment on a GitHub issue.
        Used by Hudson to report fix status or escalation reasoning.

        Args:
            owner:        Repository owner.
            repo:         Repository name.
            issue_number: Issue number.
            body:         Comment body markdown text.

        Returns:
            True if comment was created successfully.
        """
        url     = (f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
                   f"/issues/{issue_number}/comments")
        payload = {"body": body}
        data    = self._request("POST", url, payload=payload)
        return data is not None

    def close_issue(
        self,
        owner:        str,
        repo:         str,
        issue_number: int,
    ) -> bool:
        """
        Closes a GitHub issue.
        Called after Hudson successfully applies a fix.

        Args:
            owner:        Repository owner.
            repo:         Repository name.
            issue_number: Issue number.

        Returns:
            True if issue was closed successfully.
        """
        url     = GITHUB_ISSUE_ENDPOINT.format(
            owner=owner,
            repo=repo,
            number=issue_number,
        )
        payload = {"state": ISSUE_STATE_CLOSED}
        data    = self._request("PATCH", url, payload=payload)
        return data is not None

    def get_repo_default_branch(
        self,
        owner: str,
        repo:  str,
    ) -> str:
        """
        Returns the default branch name for a repository.

        Args:
            owner: Repository owner.
            repo:  Repository name.

        Returns:
            Default branch name string. Falls back to "main".
        """
        url  = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        data = self._request("GET", url)
        if data and isinstance(data, dict):
            return data.get("default_branch", "main")
        return "main"

    def get_repo_tree(
        self,
        owner:  str,
        repo:   str,
        branch: str = "main",
        depth:  int = 2,
    ) -> List[str]:
        """
        Returns a flat list of file paths in the repository tree
        up to the specified depth.

        Used to identify affected files when an issue doesn't explicitly
        mention file paths.

        Args:
            owner:  Repository owner.
            repo:   Repository name.
            branch: Branch name.
            depth:  Maximum directory depth to include.

        Returns:
            List of file path strings.
        """
        url  = (f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
                f"/git/trees/{branch}?recursive=1")
        data = self._request("GET", url)

        if not data or not isinstance(data, dict):
            return []

        tree  = data.get("tree", [])
        paths = []

        for item in tree:
            if item.get("type") == "blob":
                path       = item.get("path", "")
                path_depth = path.count("/")
                if path_depth < depth:
                    paths.append(path)

        return paths

    def get_rate_limit_status(self) -> Dict[str, int]:
        """
        Returns current GitHub API rate limit status.

        Returns:
            Dict with keys: remaining, limit, reset_timestamp.
        """
        data = self._request("GET", GITHUB_RATE_LIMIT)
        if data and isinstance(data, dict):
            core = data.get("resources", {}).get("core", {})
            return {
                "remaining":       core.get("remaining", 0),
                "limit":           core.get("limit", 5000),
                "reset_timestamp": core.get("reset", 0),
            }
        return {"remaining": self._rate_remaining, "limit": 5000, "reset_timestamp": 0}


# =============================================================================
# SECTION 4: CODE FIX APPLICATOR
# =============================================================================

class CodeFixApplicator:
    """
    Applies Hudson's generated code fixes to repository files.
    Uses the GitHub Contents API for simple single-file fixes.
    Falls back to git clone → edit → push for multi-file operations.
    """

    def __init__(self, api_client: GitHubAPIClient) -> None:
        """
        Args:
            api_client: Authenticated GitHubAPIClient instance.
        """
        self._api: GitHubAPIClient = api_client

    def apply_fix(
        self,
        issue:          GitHubIssue,
        suggested_fix:  str,
        github_token:   str,
    ) -> Tuple[bool, str]:
        """
        Applies a fix for a MINOR GitHub issue.
        Routes to the appropriate fix strategy based on the fix description.

        Strategies:
            1. API-based single-file update (preferred — no local clone needed)
            2. Git clone → patch → push (fallback for complex edits)

        Args:
            issue:         The GitHubIssue being fixed.
            suggested_fix: Hudson's suggested fix description from the evaluator.
            github_token:  GitHub PAT for authenticated git operations.

        Returns:
            Tuple of (success: bool, commit_sha: str).
        """
        owner  = issue.owner()
        repo   = issue.repo_name()
        branch = self._api.get_repo_default_branch(owner, repo)

        # Try to identify the target file from the suggested fix
        target_file = self._extract_target_file(
            issue.body, issue.title, suggested_fix
        )

        if target_file:
            # Strategy 1: API-based single-file fix
            return self._apply_api_fix(
                issue, target_file, suggested_fix, branch
            )
        else:
            # Strategy 2: Clone-based fix
            return self._apply_clone_fix(
                issue, suggested_fix, branch, github_token
            )

    def _extract_target_file(
        self,
        issue_body:    str,
        issue_title:   str,
        suggested_fix: str,
    ) -> Optional[str]:
        """
        Extracts the most likely target file path from issue text
        and the suggested fix description.

        Uses regex patterns to find file paths mentioned in the text.

        Args:
            issue_body:    Issue body text.
            issue_title:   Issue title.
            suggested_fix: Hudson's suggested fix text.

        Returns:
            File path string, or None if no clear target identified.
        """
        combined = f"{issue_title} {issue_body} {suggested_fix}"

        # Pattern: file paths with extensions
        file_patterns = [
            r'`([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]{1,6})`',  # backtick-quoted
            r'"([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]{1,6})"',  # double-quoted
            r"'([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]{1,6})'",  # single-quoted
            r'\b([a-zA-Z0-9_/\-]+\.(?:py|js|ts|html|css|md|json|yaml|yml|txt|sh|go|rs|java|cpp|c|h))\b',
        ]

        for pattern in file_patterns:
            matches = re.findall(pattern, combined)
            if matches:
                # Return the first plausible file path
                for match in matches:
                    # Skip if it looks like a URL or library name
                    if ("://" not in match and
                            not match.startswith("www.") and
                            "." in match):
                        return match

        return None

    def _apply_api_fix(
        self,
        issue:         GitHubIssue,
        target_file:   str,
        suggested_fix: str,
        branch:        str,
    ) -> Tuple[bool, str]:
        """
        Applies a fix to a single file using the GitHub Contents API.
        Fetches current content, applies the fix, and commits.

        Args:
            issue:        The GitHubIssue being fixed.
            target_file:  Target file path in the repository.
            suggested_fix: Hudson's fix description.
            branch:       Target branch name.

        Returns:
            Tuple of (success: bool, commit_sha: str).
        """
        owner = issue.owner()
        repo  = issue.repo_name()

        # Fetch current file content and SHA
        current_content, blob_sha = self._api.get_file_content(
            owner, repo, target_file, branch
        )

        if current_content is None or blob_sha is None:
            print(
                f"[CodeFixApplicator] Cannot fetch {target_file} "
                f"from {owner}/{repo}"
            )
            return (False, "")

        # Apply the fix to the content
        fixed_content = self._apply_text_fix(
            current_content, suggested_fix, target_file
        )

        if fixed_content == current_content:
            print(
                f"[CodeFixApplicator] No changes detected after "
                f"applying fix to {target_file}"
            )
            return (False, "")

        # Build commit message
        commit_message = (
            f"{GITHUB_COMMIT_MESSAGE_PREFIX} Fix #{issue.number}: "
            f"{issue.title[:60]}\n\n"
            f"Automated fix applied by Hudson (HERMES Operational AI).\n"
            f"Issue: {issue.url}\n"
            f"Fix applied: {suggested_fix[:200]}"
        )

        # Commit the fix
        commit_sha = self._api.update_file_content(
            owner=owner,
            repo=repo,
            path=target_file,
            new_content=fixed_content,
            blob_sha=blob_sha,
            commit_message=commit_message,
            branch=branch,
        )

        if commit_sha:
            print(
                f"[CodeFixApplicator] Committed fix to {target_file} "
                f"on {owner}/{repo}:{branch} — SHA: {commit_sha[:8]}"
            )
            return (True, commit_sha)

        return (False, "")

    def _apply_text_fix(
        self,
        content:       str,
        suggested_fix: str,
        filename:      str,
    ) -> str:
        """
        Applies text-level corrections to file content based on
        the suggested fix description.

        Handles common MINOR fix types:
            - Typo corrections (searches for misspelled word, replaces)
            - Trailing whitespace removal
            - Consistent indentation normalization
            - Unused import removal
            - Simple comment additions

        Args:
            content:       Current file content string.
            suggested_fix: Hudson's fix description text.
            filename:      File name (used to determine fix approach).

        Returns:
            Fixed content string.
        """
        fix_lower = suggested_fix.lower()
        result    = content

        # Trailing whitespace removal
        if any(kw in fix_lower for kw in [
            "trailing whitespace", "trailing spaces", "whitespace"
        ]):
            lines  = result.split("\n")
            result = "\n".join(line.rstrip() for line in lines)
            return result

        # Consistent indentation (Python files)
        if (any(kw in fix_lower for kw in [
                "indentation", "indent", "tabs to spaces"
            ]) and filename.endswith(".py")):
            lines  = result.split("\n")
            fixed  = []
            for line in lines:
                # Convert leading tabs to 4 spaces
                stripped = line.lstrip("\t")
                tabs     = len(line) - len(stripped)
                fixed.append("    " * tabs + stripped)
            result = "\n".join(fixed)
            return result

        # Remove unused imports in Python files
        if (any(kw in fix_lower for kw in [
                "unused import", "remove import"
            ]) and filename.endswith(".py")):
            # Extract the specific import to remove from suggested fix
            import_match = re.search(
                r'(?:remove|delete)\s+(?:import\s+)?[`"]?([a-zA-Z0-9_.]+)[`"]?',
                suggested_fix,
                re.IGNORECASE,
            )
            if import_match:
                import_name = import_match.group(1)
                lines       = result.split("\n")
                filtered    = [
                    line for line in lines
                    if not (
                        re.match(
                            rf'^\s*import\s+{re.escape(import_name)}\s*$',
                            line
                        ) or
                        re.match(
                            rf'^\s*from\s+\S+\s+import\s+.*{re.escape(import_name)}',
                            line
                        )
                    )
                ]
                result = "\n".join(filtered)
                return result

        # Typo corrections
        if any(kw in fix_lower for kw in ["typo", "spelling", "misspell"]):
            # Pattern: "change X to Y" or "replace X with Y"
            change_patterns = [
                r'(?:change|replace|fix)\s+[`"]([^`"]+)[`"]\s+(?:to|with)\s+[`"]([^`"]+)[`"]',
                r'[`"]([^`"]+)[`"]\s+should\s+be\s+[`"]([^`"]+)[`"]',
                r'(?:typo|misspelling):\s+[`"]([^`"]+)[`"]\s+→\s+[`"]([^`"]+)[`"]',
            ]
            for pattern in change_patterns:
                match = re.search(pattern, suggested_fix, re.IGNORECASE)
                if match:
                    wrong   = match.group(1)
                    correct = match.group(2)
                    result  = result.replace(wrong, correct)
                    return result

        # Ensure file ends with single newline
        if any(kw in fix_lower for kw in [
            "newline", "end of file", "missing newline", "eof"
        ]):
            result = result.rstrip("\n") + "\n"
            return result

        # Remove duplicate blank lines
        if any(kw in fix_lower for kw in [
            "blank lines", "empty lines", "multiple blank"
        ]):
            result = re.sub(r'\n{3,}', '\n\n', result)
            return result

        # Default: return content unchanged if no fix pattern matched
        return result

    def _apply_clone_fix(
        self,
        issue:         GitHubIssue,
        suggested_fix: str,
        branch:        str,
        github_token:  str,
    ) -> Tuple[bool, str]:
        """
        Applies a fix by cloning the repository locally, making changes,
        and force-pushing. Used when the API-based approach cannot
        identify a specific file target.

        This method:
            1. Creates a temporary directory.
            2. Clones the repository with credentials.
            3. Configures git user identity.
            4. Applies text-level fixes to detected files.
            5. Stages, commits, and pushes.
            6. Cleans up the temp directory.

        Args:
            issue:        The GitHubIssue being fixed.
            suggested_fix: Hudson's fix description.
            branch:       Target branch name.
            github_token: GitHub PAT for authenticated push.

        Returns:
            Tuple of (success: bool, commit_sha: str).
        """
        owner        = issue.owner()
        repo_name    = issue.repo_name()
        clone_url    = (
            f"https://{github_token}@github.com/{owner}/{repo_name}.git"
        )
        commit_sha   = ""
        temp_dir     = None

        try:
            # Create temp directory for clone
            temp_dir = tempfile.mkdtemp(prefix="hudson_fix_")

            # Step 1: Clone repository
            print(
                f"[CodeFixApplicator] Cloning {owner}/{repo_name} "
                f"into temp dir..."
            )
            clone_result = subprocess.run(
                ["git", "clone", "--depth", "1",
                 "--branch", branch, clone_url, temp_dir],
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT,
            )

            if clone_result.returncode != 0:
                print(
                    f"[CodeFixApplicator] Clone failed: "
                    f"{clone_result.stderr[:200]}"
                )
                return (False, "")

            repo_dir = temp_dir

            # Step 2: Configure git identity for this repo
            subprocess.run(
                ["git", "config", "user.email", "hudson@hermes.local"],
                cwd=repo_dir, capture_output=True, timeout=GIT_OPERATION_TIMEOUT
            )
            subprocess.run(
                ["git", "config", "user.name", "Hudson (HERMES)"],
                cwd=repo_dir, capture_output=True, timeout=GIT_OPERATION_TIMEOUT
            )

            # Step 3: Find and fix files
            fixed_files = self._scan_and_fix_directory(
                repo_dir, suggested_fix
            )

            if not fixed_files:
                print(
                    "[CodeFixApplicator] No files were modified during "
                    "clone-based fix."
                )
                return (False, "")

            # Step 4: Stage all changes
            add_result = subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=GIT_OPERATION_TIMEOUT,
            )

            if add_result.returncode != 0:
                print(
                    f"[CodeFixApplicator] git add failed: "
                    f"{add_result.stderr[:200]}"
                )
                return (False, "")

            # Step 5: Commit
            commit_message = (
                f"{GITHUB_COMMIT_MESSAGE_PREFIX} Fix #{issue.number}: "
                f"{issue.title[:60]}\n\n"
                f"Files modified: {', '.join(fixed_files)}\n"
                f"Automated fix by Hudson (HERMES Operational AI).\n"
                f"Issue: {issue.url}"
            )

            commit_result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=GIT_OPERATION_TIMEOUT,
            )

            if commit_result.returncode != 0:
                if "nothing to commit" in commit_result.stdout.lower():
                    print("[CodeFixApplicator] Nothing to commit.")
                    return (False, "")
                print(
                    f"[CodeFixApplicator] Commit failed: "
                    f"{commit_result.stderr[:200]}"
                )
                return (False, "")

            # Extract commit SHA from output
            sha_match = re.search(
                r'\[.*?([a-f0-9]{7,40})\]',
                commit_result.stdout
            )
            commit_sha = sha_match.group(1) if sha_match else "unknown"

            # Step 6: Push to remote
            push_result = subprocess.run(
                ["git", "push", "origin", branch],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=GIT_OPERATION_TIMEOUT,
            )

            if push_result.returncode != 0:
                print(
                    f"[CodeFixApplicator] Push failed: "
                    f"{push_result.stderr[:200]}"
                )
                return (False, "")

            print(
                f"[CodeFixApplicator] Clone-fix pushed successfully. "
                f"Files: {fixed_files}. SHA: {commit_sha}"
            )
            return (True, commit_sha)

        except subprocess.TimeoutExpired:
            print("[CodeFixApplicator] Git operation timed out.")
            return (False, "")
        except Exception as exc:
            print(f"[CodeFixApplicator] Clone-fix error: {exc}")
            return (False, "")
        finally:
            # Always clean up temp directory
            if temp_dir and os.path.isdir(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    def _scan_and_fix_directory(
        self,
        repo_dir:      str,
        suggested_fix: str,
    ) -> List[str]:
        """
        Scans the cloned repository directory for files to fix.
        Applies text-level corrections to all eligible files.

        Eligible file extensions: .py, .js, .ts, .html, .css, .md,
        .json, .yaml, .yml, .txt, .sh, .go, .rs, .java, .cpp, .c

        Skips: .git directory, node_modules, __pycache__, .env files.

        Args:
            repo_dir:      Path to the cloned repository directory.
            suggested_fix: Hudson's fix description.

        Returns:
            List of relative file paths that were modified.
        """
        eligible_extensions = {
            ".py", ".js", ".ts", ".html", ".css", ".md",
            ".json", ".yaml", ".yml", ".txt", ".sh",
            ".go", ".rs", ".java", ".cpp", ".c", ".h",
        }

        skip_dirs = {
            ".git", "node_modules", "__pycache__",
            ".venv", "venv", "dist", "build", ".next",
        }

        modified_files: List[str] = []

        for root, dirs, files in os.walk(repo_dir):
            # Prune skip directories in-place
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() not in eligible_extensions:
                    continue

                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, repo_dir)

                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        original = f.read()

                    fixed = self._apply_text_fix(original, suggested_fix, filename)

                    if fixed != original:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(fixed)
                        modified_files.append(rel_path)

                except Exception as exc:
                    print(
                        f"[CodeFixApplicator] Error processing {rel_path}: {exc}"
                    )

        return modified_files


# =============================================================================
# SECTION 5: GITHUB ENGINE — MAIN CONTROLLER
# =============================================================================

class GitHubEngine:
    """
    Hudson's complete GitHub monitoring and autonomous issue resolution engine.

    Lifecycle:
        1. Validates GitHub token on startup.
        2. Fetches all repository names.
        3. Polls all repos for new open issues every GITHUB_POLL_RATE seconds.
        4. For each new unprocessed issue:
           a. Creates a HudsonTask in HermesState.
           b. Delegates to PersonaEngine for complexity evaluation (min 60s).
           c. If MINOR: apply fix → commit → push → close issue → comment.
           d. If HARD: post escalation comment → label issue → alert user.
        5. Reports all activity through EventBus.

    Runs as a daemon thread managed by daemons.py.
    All state writes go through HermesState.
    All alerts go through EventBus.
    """

    def __init__(self) -> None:
        self._api_client:   Optional[GitHubAPIClient]  = None
        self._fix_applicator: Optional[CodeFixApplicator] = None
        self._running:      bool                        = False
        self._thread:       Optional[threading.Thread]  = None
        self._token:        str                         = ""
        self._username:     str                         = ""

        # Track processed issue numbers to avoid reprocessing
        self._processed_issues: Dict[str, set] = {}   # repo_full → set of issue numbers

        # Lock for processed issues tracking
        self._processed_lock: threading.Lock = threading.Lock()

    def initialize(self, token: str) -> bool:
        """
        Initializes the GitHub engine with the provided personal access token.
        Validates the token and fetches initial repository list.

        Args:
            token: GitHub Personal Access Token string.

        Returns:
            True if initialization succeeded and token is valid.
        """
        if not token or token == GITHUB_TOKEN_PLACEHOLDER:
            print("[GitHubEngine] No valid GitHub token provided. Engine disabled.")
            return False

        self._token      = token
        self._api_client = GitHubAPIClient(token)

        # Validate token
        is_valid, username = self._api_client.validate_token()
        if not is_valid:
            print("[GitHubEngine] GitHub token validation failed. Engine disabled.")
            return False

        self._username       = username
        self._fix_applicator = CodeFixApplicator(self._api_client)

        print(
            f"[GitHubEngine] Initialized. Authenticated as: {username}"
        )

        # Update state
        try:
            from Backhand_code.state import hermes_state
            hermes_state.batch_set({
                "github_connected": True,
                "github_token":     token,
            })
        except Exception:
            pass

        # Publish connection event
        try:
            from Backhand_code.event_bus import event_bus, EventType
            event_bus.publish(
                EventType.GITHUB_CONNECTED,
                payload={"username": username},
                source="GitHubEngine",
            )
        except Exception:
            pass

        return True

    def start(self) -> None:
        """
        Starts the GitHub monitoring daemon thread.
        No-op if already running or not initialized.
        """
        if self._running or self._api_client is None:
            return

        self._running = True
        self._thread  = threading.Thread(
            target=self._monitor_loop,
            name="GitHubEngine-Monitor",
            daemon=True,
        )
        self._thread.start()
        print("[GitHubEngine] Monitor thread started.")

    def stop(self) -> None:
        """
        Signals the monitor thread to stop and waits for clean exit.
        Called during application shutdown.
        """
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        print("[GitHubEngine] Monitor thread stopped.")

    def _monitor_loop(self) -> None:
        """
        Main monitoring loop. Runs until self._running is False.
        Polls all repositories for new issues every GITHUB_POLL_RATE seconds.
        """
        try:
            from Backhand_code.event_bus import event_bus, EventType
            event_bus.emit_daemon_started("GitHubEngine")
        except Exception:
            pass

        while self._running:
            try:
                self._poll_all_repositories()
            except Exception as exc:
                print(f"[GitHubEngine] Poll error: {exc}")
                try:
                    from Backhand_code.event_bus import event_bus
                    event_bus.emit_daemon_error("GitHubEngine", str(exc))
                except Exception:
                    pass

            # Wait for next poll cycle (interruptible)
            wait_start = time.time()
            while self._running and (time.time() - wait_start) < GITHUB_POLL_RATE:
                time.sleep(1.0)

        try:
            from Backhand_code.event_bus import event_bus
            event_bus.emit_daemon_stopped("GitHubEngine")
        except Exception:
            pass

    def _poll_all_repositories(self) -> None:
        """
        Fetches all repositories and polls each one for new issues.
        Updates HermesState with current repo list.
        """
        if self._api_client is None:
            return

        repos = self._api_client.get_all_repos()
        if not repos:
            return

        repo_names = [r.get("full_name", "") for r in repos if r.get("full_name")]

        # Update state with current repo list
        try:
            from Backhand_code.state import hermes_state
            hermes_state.set("github_repos", repo_names)
        except Exception:
            pass

        print(
            f"[GitHubEngine] Polling {len(repo_names)} repositories "
            f"for new issues..."
        )

        # Poll each repository
        for repo_full in repo_names:
            if not self._running:
                break
            try:
                self._poll_repository(repo_full)
            except Exception as exc:
                print(f"[GitHubEngine] Error polling {repo_full}: {exc}")

    def _poll_repository(self, repo_full: str) -> None:
        """
        Polls a single repository for new open issues.
        Skips issues that are too old, already processed, or are PRs.

        Args:
            repo_full: Full repository name "owner/repo".
        """
        if self._api_client is None:
            return

        parts = repo_full.split("/")
        if len(parts) != 2:
            return

        owner, repo = parts[0], parts[1]

        # Fetch open issues
        raw_issues = self._api_client.get_open_issues(
            owner, repo, limit=MAX_ISSUES_PER_REPO
        )

        if not raw_issues:
            return

        for raw in raw_issues:
            if not self._running:
                break

            issue_number = raw.get("number", 0)

            # Skip if already processed in this session
            with self._processed_lock:
                if repo_full not in self._processed_issues:
                    self._processed_issues[repo_full] = set()
                if issue_number in self._processed_issues[repo_full]:
                    continue

            # Build GitHubIssue object
            issue = GitHubIssue(
                number=issue_number,
                title=raw.get("title", ""),
                body=raw.get("body", "") or "",
                repo_full=repo_full,
                url=raw.get("html_url", ""),
                created_at=raw.get("created_at", ""),
                labels=[
                    lbl.get("name", "")
                    for lbl in raw.get("labels", [])
                ],
                author=raw.get("user", {}).get("login", "unknown"),
            )

            # Skip already-processed issues (has Hudson labels)
            if issue.is_already_processed():
                with self._processed_lock:
                    self._processed_issues[repo_full].add(issue_number)
                continue

            # Skip issues older than MAX_ISSUE_AGE_DAYS
            if issue.age_days() > MAX_ISSUE_AGE_DAYS:
                with self._processed_lock:
                    self._processed_issues[repo_full].add(issue_number)
                continue

            # Mark as seen before processing to prevent double-processing
            with self._processed_lock:
                self._processed_issues[repo_full].add(issue_number)

            # Process the issue in a separate thread so one slow issue
            # doesn't block the rest of the repository poll cycle
            threading.Thread(
                target=self._process_issue,
                args=(issue,),
                daemon=True,
                name=f"Hudson-Issue-{issue_number}",
            ).start()

    def _process_issue(self, issue: GitHubIssue) -> None:
        """
        Full issue processing pipeline for a single GitHubIssue.
        Runs in its own daemon thread.

        Pipeline:
            1. Publish GITHUB_ALERT event.
            2. Create HudsonTask.
            3. Evaluate complexity (min 60s).
            4. If MINOR: apply fix, commit, push, close, comment.
            5. If HARD: escalate to user, post comment, add label.

        Args:
            issue: The GitHubIssue to process.
        """
        print(
            f"[GitHubEngine] Processing issue #{issue.number} "
            f"in {issue.repo_full}: {issue.title[:60]}"
        )

        # Step 1: Publish alert event
        try:
            from Backhand_code.event_bus import event_bus
            event_bus.emit_github_alert(
                repo=issue.repo_full,
                issue_title=issue.title,
                issue_url=issue.url,
                issue_body=issue.body,
                issue_number=issue.number,
            )
        except Exception:
            pass

        # Step 2: Create HudsonTask
        try:
            from Backhand_code.state import hermes_state
            task = hermes_state.create_hudson_task(
                task_type="GITHUB",
                description=f"Issue #{issue.number}: {issue.title}",
                repo=issue.repo_full,
            )
            hermes_state.update_hudson_task(
                task, "ANALYZING",
                f"Evaluating complexity of issue #{issue.number}..."
            )
        except Exception as task_err:
            print(f"[GitHubEngine] HudsonTask creation error: {task_err}")
            task = None

        # Step 3: Evaluate complexity
        issue.state          = GitHubIssue.STATE_ANALYZING
        issue.analysis_start = time.time()

        # Get affected files from repo tree for context
        affected_files = self._get_affected_files_for_issue(issue)

        try:
            from Backhand_code.persona_engine import persona_engine
            classification, reasoning, suggested_fix = (
                persona_engine.evaluate_github_issue(
                    repo=issue.repo_full,
                    issue_title=issue.title,
                    issue_body=issue.body,
                    issue_number=issue.number,
                    affected_files=affected_files,
                )
            )
        except Exception as eval_err:
            print(f"[GitHubEngine] Evaluation error: {eval_err}")
            classification = "HARD"
            reasoning      = f"Evaluation failed: {eval_err}. Defaulting to HARD."
            suggested_fix  = ""

        issue.analysis_end    = time.time()
        issue.classification  = classification
        issue.reasoning       = reasoning
        issue.suggested_fix   = suggested_fix

        analysis_time = issue.analysis_end - issue.analysis_start
        print(
            f"[GitHubEngine] Issue #{issue.number} classified as "
            f"{classification} (analysis: {analysis_time:.1f}s)."
        )

        # Step 4a: MINOR — apply fix
        if classification == "MINOR":
            self._handle_minor_issue(issue, task)
        # Step 4b: HARD — escalate
        else:
            self._handle_hard_issue(issue, task)

    def _handle_minor_issue(
        self,
        issue: GitHubIssue,
        task:  Optional[Any],
    ) -> None:
        """
        Handles a MINOR GitHub issue: applies fix, commits, pushes,
        closes the issue, and posts a success comment.

        Args:
            issue: The classified MINOR GitHubIssue.
            task:  Associated HudsonTask (may be None on error).
        """
        if self._fix_applicator is None:
            return

        issue.state = GitHubIssue.STATE_FIXING

        if task:
            try:
                from Backhand_code.state import hermes_state
                hermes_state.update_hudson_task(
                    task, "RUNNING",
                    f"Applying fix to issue #{issue.number}..."
                )
            except Exception:
                pass

        # Apply the fix
        success, commit_sha = self._fix_applicator.apply_fix(
            issue=issue,
            suggested_fix=issue.suggested_fix,
            github_token=self._token,
        )

        if success:
            issue.state      = GitHubIssue.STATE_FIXED
            issue.fix_applied = True
            issue.commit_sha = commit_sha

            # Post success comment on the issue
            comment = (
                f"## ✅ Hudson Auto-Fix Applied\n\n"
                f"**HERMES Operational AI** has automatically resolved this issue.\n\n"
                f"**Classification:** MINOR\n"
                f"**Commit:** `{commit_sha[:8] if commit_sha else 'N/A'}`\n\n"
                f"**Analysis:**\n{issue.reasoning}\n\n"
                f"**Fix Applied:**\n{issue.suggested_fix}\n\n"
                f"---\n"
                f"*Automated resolution by Hudson (HERMES Omnimind Absolute Edition)*"
            )
            self._api_client.create_issue_comment(
                issue.owner(), issue.repo_name(), issue.number, comment
            )

            # Add Hudson-processed label
            self._api_client.add_issue_label(
                issue.owner(), issue.repo_name(), issue.number,
                [HUDSON_LABEL],
            )

            # Close the issue
            self._api_client.close_issue(
                issue.owner(), issue.repo_name(), issue.number
            )

            # Update task
            if task:
                try:
                    from Backhand_code.state import hermes_state
                    task.result = f"Fixed and committed. SHA: {commit_sha[:8]}"
                    hermes_state.update_hudson_task(
                        task, "COMPLETE",
                        f"Issue #{issue.number} resolved. "
                        f"Commit: {commit_sha[:8] if commit_sha else 'N/A'}"
                    )
                except Exception:
                    pass

            # Publish success event
            try:
                from Backhand_code.event_bus import event_bus, EventType
                event_bus.publish(
                    EventType.GITHUB_COMMIT_PUSHED,
                    payload={
                        "repo":         issue.repo_full,
                        "issue_number": issue.number,
                        "commit_sha":   commit_sha,
                        "issue_title":  issue.title,
                    },
                    source="GitHubEngine",
                    main_thread_only=True,
                )
            except Exception:
                pass

            # Buffer for Hudson memory
            try:
                from Backhand_code.memory_manager import memory_manager
                memory_manager.buffer_hudson_task({
                    "task_type":    "GITHUB",
                    "description":  f"Fixed #{issue.number}: {issue.title}",
                    "repo":         issue.repo_full,
                    "status":       "COMPLETE",
                    "result":       f"Commit {commit_sha[:8] if commit_sha else 'N/A'}",
                    "updated_at":   time.time(),
                })
            except Exception:
                pass

            print(
                f"[GitHubEngine] Issue #{issue.number} fixed and closed. "
                f"Commit: {commit_sha[:8] if commit_sha else 'N/A'}"
            )

        else:
            # Fix application failed — escalate instead
            issue.state = GitHubIssue.STATE_FAILED
            print(
                f"[GitHubEngine] Fix application failed for "
                f"issue #{issue.number}. Escalating."
            )
            issue.classification = "HARD"
            issue.reasoning = (
                f"Originally classified as MINOR but fix application failed. "
                f"Original reasoning: {issue.reasoning}"
            )
            self._handle_hard_issue(issue, task)

    def _handle_hard_issue(
        self,
        issue: GitHubIssue,
        task:  Optional[Any],
    ) -> None:
        """
        Handles a HARD GitHub issue: posts escalation comment,
        adds escalation label, alerts the user via EventBus.

        Args:
            issue: The classified HARD GitHubIssue.
            task:  Associated HudsonTask (may be None on error).
        """
        issue.state = GitHubIssue.STATE_ESCALATED

        # Post escalation comment
        comment = (
            f"## ⚠️ Hudson Escalation — Human Review Required\n\n"
            f"**HERMES Operational AI** has analyzed this issue and "
            f"determined it requires human review.\n\n"
            f"**Classification:** HARD — Cannot auto-resolve\n\n"
            f"**Analysis:**\n{issue.reasoning}\n\n"
            f"**Why this cannot be auto-fixed:**\n"
            f"This issue involves changes beyond safe automated resolution "
            f"(architecture, security, complex logic, or new features).\n\n"
            f"**Recommended action:** Manual review and resolution required.\n\n"
            f"---\n"
            f"*Escalated by Hudson (HERMES Omnimind Absolute Edition)*"
        )

        if self._api_client:
            self._api_client.create_issue_comment(
                issue.owner(), issue.repo_name(), issue.number, comment
            )
            self._api_client.add_issue_label(
                issue.owner(), issue.repo_name(), issue.number,
                [HUDSON_ESCALATE_LABEL, HUDSON_LABEL],
            )

        # Update task
        if task:
            try:
                from Backhand_code.state import hermes_state
                task.result = f"Escalated: {issue.reasoning[:100]}"
                hermes_state.update_hudson_task(
                    task, "ESCALATED",
                    f"Issue #{issue.number} requires manual review."
                )
            except Exception:
                pass

        # Publish escalation event (routes to main thread for user alert)
        try:
            from Backhand_code.event_bus import event_bus
            event_bus.emit_github_escalated(
                repo=issue.repo_full,
                issue_title=issue.title,
                issue_number=issue.number,
                reason=issue.reasoning[:200],
            )
        except Exception:
            pass

        # Buffer for Hudson memory
        try:
            from Backhand_code.memory_manager import memory_manager
            memory_manager.buffer_hudson_task({
                "task_type":   "GITHUB",
                "description": f"Escalated #{issue.number}: {issue.title}",
                "repo":        issue.repo_full,
                "status":      "ESCALATED",
                "result":      issue.reasoning[:200],
                "updated_at":  time.time(),
            })
        except Exception:
            pass

        print(
            f"[GitHubEngine] Issue #{issue.number} escalated "
            f"to user for review."
        )

    def _get_affected_files_for_issue(
        self,
        issue: GitHubIssue,
    ) -> List[str]:
        """
        Extracts or infers the list of files affected by the issue.
        First checks the issue body for explicit file mentions,
        then falls back to fetching the repository's top-level tree.

        Args:
            issue: The GitHubIssue to analyze.

        Returns:
            List of file path strings.
        """
        combined = f"{issue.title} {issue.body}"

        # Look for explicit file path mentions
        file_patterns = [
            r'`([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]{1,6})`',
            r'"([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]{1,6})"',
            r"'([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]{1,6})'",
        ]

        found_files: List[str] = []
        for pattern in file_patterns:
            matches = re.findall(pattern, combined)
            for match in matches:
                if ("://" not in match and
                        "." in match and
                        match not in found_files):
                    found_files.append(match)

        if found_files:
            return found_files[:10]

        # Fallback: get repo tree (top 2 levels)
        if self._api_client:
            owner  = issue.owner()
            repo   = issue.repo_name()
            branch = self._api_client.get_repo_default_branch(owner, repo)
            tree   = self._api_client.get_repo_tree(owner, repo, branch, depth=2)
            return tree[:20]

        return []

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Returns a diagnostic snapshot of the GitHub engine state.

        Returns:
            Dict with engine health and activity metrics.
        """
        total_processed = sum(
            len(s) for s in self._processed_issues.values()
        )

        return {
            "running":          self._running,
            "authenticated":    bool(self._username),
            "username":         self._username,
            "repos_tracked":    len(self._processed_issues),
            "issues_processed": total_processed,
            "token_set":        bool(self._token) and
                                self._token != GITHUB_TOKEN_PLACEHOLDER,
        }

    def set_github_token(self, token: str) -> bool:
        """
        Updates the GitHub token at runtime (e.g. after user configuration).
        Re-initializes the engine with the new token.

        Args:
            token: New GitHub Personal Access Token.

        Returns:
            True if new token is valid and engine re-initialized.
        """
        was_running = self._running
        if was_running:
            self.stop()

        success = self.initialize(token)

        if success and was_running:
            self.start()

        return success

    def __repr__(self) -> str:
        return (
            f"GitHubEngine("
            f"running={self._running}, "
            f"user={self._username}, "
            f"repos={len(self._processed_issues)})"
        )


# =============================================================================
# SECTION 6: MODULE-LEVEL SINGLETON
# =============================================================================

# Single global instance shared across all modules.
# Import directly: from github_engine import github_engine
github_engine: GitHubEngine = GitHubEngine()


# =============================================================================
# END OF github_engine.py
# =============================================================================