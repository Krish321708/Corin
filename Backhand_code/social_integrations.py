"""
HERMES Omnimind Absolute Edition
Social Integrations Engine
Real-time WhatsApp, Instagram, Gmail, and Reddit integration with learning algorithms.
"""

import asyncio
import base64
import json
import logging
import os
import pickle
import re
import smtplib
import sqlite3
import threading
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.mime.text import MimeText
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any
import hashlib

# Core system imports
from Backhand_code.config import Config
from Backhand_code.state import HermesState
from Backhand_code.event_bus import EventBus

# External API libraries
try:
    import praw
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from instagrapi import Client as InstagramClient
    from playwright.sync_api import sync_playwright
    import requests
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Social integration dependencies missing: {e}")
    DEPENDENCIES_AVAILABLE = False

class PriorityLearningEngine:
    """Advanced machine learning system for sender/content priority scoring."""
    
    def __init__(self, db_path: str = "data/social_learning.db"):
        self.db_path = db_path
        self.ensure_database()
        
    def ensure_database(self):
        """Create SQLite database for learning data if it doesn't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Sender priority learning table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sender_scores (
                email TEXT PRIMARY KEY,
                opens INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                read_time REAL DEFAULT 0.0,
                stars INTEGER DEFAULT 0,
                last_interaction TIMESTAMP,
                calculated_priority REAL DEFAULT 0.0
            )
        """)
        
        # Reddit content learning table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reddit_scores (
                post_id TEXT PRIMARY KEY,
                subreddit TEXT,
                title TEXT,
                clicked INTEGER DEFAULT 0,
                upvoted INTEGER DEFAULT 0,
                read_time REAL DEFAULT 0.0,
                saved INTEGER DEFAULT 0,
                keywords TEXT,
                score REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Content preference patterns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_patterns (
                category TEXT PRIMARY KEY,
                weight REAL DEFAULT 0.0,
                interactions INTEGER DEFAULT 0,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    def update_sender_score(self, email: str, action: str, value: float = 1.0):
        """Update sender priority based on user actions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get existing record or create new
        cursor.execute("SELECT * FROM sender_scores WHERE email = ?", (email,))
        record = cursor.fetchone()
        
        if not record:
            cursor.execute("""
                INSERT INTO sender_scores (email, last_interaction) 
                VALUES (?, ?)
            """, (email, datetime.now()))
            record = (email, 0, 0, 0.0, 0, datetime.now(), 0.0)
        
        # Update based on action
        opens, replies, read_time, stars = record[1], record[2], record[3], record[4]
        
        if action == "open":
            opens += 1
        elif action == "reply":
            replies += 1
        elif action == "read_time":
            read_time += value
        elif action == "star":
            stars += 1
        
        # Calculate priority score (weighted algorithm)
        priority = (
            opens * 0.1 +           # Opening emails shows interest
            replies * 2.0 +         # Replying is strong engagement signal
            min(read_time / 30, 5) * 0.5 +  # Time spent reading (capped)
            stars * 3.0             # Starring is explicit priority marking
        )
        
        # Decay factor based on recency
        last_interaction = datetime.fromisoformat(record[5]) if isinstance(record[5], str) else record[5]
        days_since = (datetime.now() - last_interaction).days
        decay = max(0.1, 1.0 - (days_since * 0.01))  # 1% decay per day
        priority *= decay
        
        cursor.execute("""
            UPDATE sender_scores 
            SET opens=?, replies=?, read_time=?, stars=?, 
                last_interaction=?, calculated_priority=?
            WHERE email=?
        """, (opens, replies, read_time, stars, datetime.now(), priority, email))
        
        conn.commit()
        conn.close()
        return priority
    
    def get_sender_priority(self, email: str) -> float:
        """Get current priority score for sender."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT calculated_priority FROM sender_scores WHERE email = ?", (email,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0.0
    
    def update_reddit_score(self, post_id: str, subreddit: str, title: str, action: str, value: float = 1.0):
        """Update Reddit content scoring based on user interactions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Extract keywords from title for pattern learning
        keywords = re.findall(r'\b\w+\b', title.lower())
        keywords_str = ",".join(keywords)
        
        # Get or create record
        cursor.execute("SELECT * FROM reddit_scores WHERE post_id = ?", (post_id,))
        record = cursor.fetchone()
        
        if not record:
            cursor.execute("""
                INSERT INTO reddit_scores (post_id, subreddit, title, keywords) 
                VALUES (?, ?, ?, ?)
            """, (post_id, subreddit, title, keywords_str))
            clicked, upvoted, read_time, saved = 0, 0, 0.0, 0
        else:
            clicked, upvoted, read_time, saved = record[3], record[4], record[5], record[6]
        
        # Update based on action
        if action == "click":
            clicked = 1
        elif action == "upvote":
            upvoted = 1
        elif action == "read_time":
            read_time += value
        elif action == "save":
            saved = 1
        
        # Calculate content score
        score = clicked * 1.0 + upvoted * 2.0 + min(read_time / 60, 3) + saved * 3.0
        
        cursor.execute("""
            UPDATE reddit_scores 
            SET clicked=?, upvoted=?, read_time=?, saved=?, score=?
            WHERE post_id=?
        """, (clicked, upvoted, read_time, saved, score, post_id))
        
        # Update category patterns
        for keyword in keywords[:5]:  # Top 5 keywords
            self.update_content_pattern(keyword, score * 0.1)
        
        self.update_content_pattern(f"subreddit:{subreddit}", score * 0.2)
        
        conn.commit()
        conn.close()
        return score
    
    def update_content_pattern(self, category: str, score_delta: float):
        """Update content pattern weights for recommendation engine."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT weight, interactions FROM content_patterns WHERE category = ?", (category,))
        result = cursor.fetchone()
        
        if result:
            new_weight = result[0] + score_delta
            new_interactions = result[1] + 1
            cursor.execute("""
                UPDATE content_patterns 
                SET weight=?, interactions=?, last_update=?
                WHERE category=?
            """, (new_weight, new_interactions, datetime.now(), category))
        else:
            cursor.execute("""
                INSERT INTO content_patterns (category, weight, interactions) 
                VALUES (?, ?, 1)
            """, (category, score_delta))
        
        conn.commit()
        conn.close()
    
    def get_content_preferences(self) -> Dict[str, float]:
        """Get current content preference weights for recommendations."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT category, weight FROM content_patterns WHERE weight > 0.1")
        preferences = dict(cursor.fetchall())
        conn.close()
        return preferences

class WhatsAppIntegration:
    """WhatsApp Web automation via Playwright with screenshot streaming."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.browser = None
        self.page = None
        self.authenticated = False
        self.screenshot_buffer = BytesIO()
        self.running = False
        self.message_queue = deque()
        
    def start(self):
        """Initialize WhatsApp Web session."""
        if not DEPENDENCIES_AVAILABLE:
            return False
            
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=False)
            self.page = self.browser.new_page()
            
            # Navigate to WhatsApp Web
            self.page.goto("https://web.whatsapp.com")
            
            # Wait for QR code or authenticated session
            try:
                # Check if already authenticated
                self.page.wait_for_selector("[data-testid='chat-list']", timeout=5000)
                self.authenticated = True
                self.event_bus.publish("whatsapp_authenticated", {"status": "success"})
            except:
                # Need to scan QR code
                self.event_bus.publish("whatsapp_qr_ready", {"status": "scan_required"})
                # Wait for authentication after QR scan
                self.page.wait_for_selector("[data-testid='chat-list']", timeout=60000)
                self.authenticated = True
                self.event_bus.publish("whatsapp_authenticated", {"status": "success"})
            
            self.running = True
            threading.Thread(target=self._monitor_messages, daemon=True).start()
            threading.Thread(target=self._capture_screenshots, daemon=True).start()
            
            return True
            
        except Exception as e:
            self.event_bus.publish("whatsapp_error", {"error": str(e)})
            return False
    
    def _monitor_messages(self):
        """Monitor for new WhatsApp messages."""
        last_count = 0
        
        while self.running and self.authenticated:
            try:
                # Get unread message count
                unread_elements = self.page.query_selector_all("[data-testid='icon-unread-count']")
                current_count = len(unread_elements)
                
                if current_count > last_count:
                    # New message(s) detected
                    self._fetch_recent_messages()
                    last_count = current_count
                
                time.sleep(2)
                
            except Exception as e:
                print(f"WhatsApp monitoring error: {e}")
                time.sleep(5)
    
    def _fetch_recent_messages(self):
        """Fetch recent unread messages and notify UI."""
        try:
            # Get chat list
            chat_elements = self.page.query_selector_all("[data-testid='chat']")
            
            for chat in chat_elements[:5]:  # Check top 5 chats
                # Look for unread indicator
                unread = chat.query_selector("[data-testid='icon-unread-count']")
                if not unread:
                    continue
                
                # Get sender name and last message
                name_element = chat.query_selector("[data-testid='conversation-info-header-chat-title']")
                message_element = chat.query_selector("[data-testid='last-msg-text']")
                
                if name_element and message_element:
                    sender = name_element.inner_text()
                    preview = message_element.inner_text()[:100]
                    timestamp = datetime.now()
                    
                    message_data = {
                        "platform": "whatsapp",
                        "sender": sender,
                        "preview": preview,
                        "timestamp": timestamp.isoformat(),
                        "chat_element": chat
                    }
                    
                    # Add to UI notification queue
                    self.event_bus.publish("new_message", message_data)
                    
        except Exception as e:
            print(f"Error fetching WhatsApp messages: {e}")
    
    def _capture_screenshots(self):
        """Continuously capture screenshots for UI embedding."""
        while self.running and self.authenticated:
            try:
                screenshot = self.page.screenshot()
                self.screenshot_buffer = BytesIO(screenshot)
                
                # Update state for UI access
                self.state.set("whatsapp_screenshot", base64.b64encode(screenshot).decode())
                
                time.sleep(0.5)  # 2 FPS screenshot capture
                
            except Exception as e:
                print(f"Screenshot capture error: {e}")
                time.sleep(1)
    
    def open_chat(self, sender: str):
        """Open specific chat in WhatsApp Web."""
        try:
            # Search for contact
            search_box = self.page.query_selector("[data-testid='chat-list-search']")
            if search_box:
                search_box.clear()
                search_box.type(sender)
                time.sleep(1)
                
                # Click first result
                first_chat = self.page.query_selector("[data-testid='chat']")
                if first_chat:
                    first_chat.click()
                    return True
            
        except Exception as e:
            print(f"Error opening WhatsApp chat: {e}")
        return False
    
    def send_message(self, message: str):
        """Send message in currently open chat."""
        try:
            message_box = self.page.query_selector("[data-testid='conversation-compose-box-input']")
            if message_box:
                message_box.clear()
                message_box.type(message)
                
                # Send message
                send_button = self.page.query_selector("[data-testid='send']")
                if send_button:
                    send_button.click()
                    return True
                    
        except Exception as e:
            print(f"Error sending WhatsApp message: {e}")
        return False
    
    def stop(self):
        """Clean shutdown of WhatsApp integration."""
        self.running = False
        if self.browser:
            self.browser.close()
        if hasattr(self, 'playwright'):
            self.playwright.stop()

class InstagramIntegration:
    """Instagram DM integration using instagrapi."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.clients = {}
        self.running = False
        self.accounts = Config.INSTAGRAM_ACCOUNTS  # List of account credentials
        
    def start(self):
        """Initialize Instagram clients for configured accounts."""
        if not DEPENDENCIES_AVAILABLE:
            return False
            
        try:
            for i, account in enumerate(self.accounts):
                client = InstagramClient()
                
                # Load existing session if available
                session_file = f"data/instagram_session_{i}.json"
                if os.path.exists(session_file):
                    client.load_settings(session_file)
                
                # Login
                client.login(account["username"], account["password"])
                
                # Save session for future use
                os.makedirs("data", exist_ok=True)
                client.dump_settings(session_file)
                
                self.clients[account["username"]] = client
                
                self.event_bus.publish("instagram_authenticated", {
                    "account": account["username"], 
                    "status": "success"
                })
            
            self.running = True
            threading.Thread(target=self._monitor_dms, daemon=True).start()
            return True
            
        except Exception as e:
            self.event_bus.publish("instagram_error", {"error": str(e)})
            return False
    
    def _monitor_dms(self):
        """Monitor for new Instagram DMs across all accounts."""
        last_dm_counts = {username: 0 for username in self.clients.keys()}
        
        while self.running:
            try:
                for username, client in self.clients.items():
                    # Get direct message threads
                    threads = client.direct_threads(amount=20)
                    current_count = len([t for t in threads if t.read_state == 0])  # Unread count
                    
                    if current_count > last_dm_counts[username]:
                        # New DM detected
                        self._fetch_recent_dms(username, client, threads)
                        last_dm_counts[username] = current_count
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                print(f"Instagram DM monitoring error: {e}")
                time.sleep(30)  # Longer delay on error to avoid rate limits
    
    def _fetch_recent_dms(self, account: str, client: InstagramClient, threads: List):
        """Fetch recent unread DMs and notify UI."""
        try:
            for thread in threads[:5]:  # Top 5 threads
                if thread.read_state != 0:  # Skip read threads
                    continue
                
                # Get thread details
                thread_detail = client.direct_thread(thread.id, amount=5)
                if not thread_detail.messages:
                    continue
                
                latest_message = thread_detail.messages[0]
                sender = latest_message.user.username if latest_message.user else "Unknown"
                
                # Skip if message is from the account owner (our reply)
                if sender == account:
                    continue
                
                message_data = {
                    "platform": "instagram",
                    "account": account,
                    "sender": sender,
                    "preview": latest_message.text or "[Media]",
                    "timestamp": latest_message.timestamp.isoformat(),
                    "thread_id": thread.id,
                    "message_id": latest_message.id
                }
                
                self.event_bus.publish("new_message", message_data)
                
        except Exception as e:
            print(f"Error fetching Instagram DMs: {e}")
    
    def send_direct_message(self, account: str, thread_id: str, message: str):
        """Send DM reply via Instagram."""
        try:
            client = self.clients.get(account)
            if not client:
                return False
                
            client.direct_send(message, thread_ids=[thread_id])
            return True
            
        except Exception as e:
            print(f"Error sending Instagram DM: {e}")
            return False
    
    def mark_as_read(self, account: str, thread_id: str):
        """Mark Instagram thread as read."""
        try:
            client = self.clients.get(account)
            if client:
                client.direct_thread_mark_read(thread_id)
                return True
        except Exception as e:
            print(f"Error marking Instagram thread as read: {e}")
        return False
    
    def stop(self):
        """Clean shutdown of Instagram integration."""
        self.running = False

class GmailIntegration:
    """Gmail integration with OAuth2 and priority learning."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.service = None
        self.running = False
        self.priority_engine = PriorityLearningEngine()
        
        # OAuth2 scopes
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.modify'
        ]
    
    def start(self):
        """Initialize Gmail API with OAuth2 authentication."""
        if not DEPENDENCIES_AVAILABLE:
            return False
            
        try:
            creds = None
            token_path = "data/gmail_token.json"
            credentials_path = "credentials.json"
            
            # Load existing token
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, self.scopes)
            
            # If no valid credentials, initiate OAuth2 flow
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(credentials_path):
                        self.event_bus.publish("gmail_error", {
                            "error": "credentials.json file missing. Please download from Google Cloud Console."
                        })
                        return False
                        
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, self.scopes)
                    creds = flow.run_local_server(port=0)
                
                # Save credentials for future use
                os.makedirs("data", exist_ok=True)
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            
            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=creds)
            
            # Test connection
            profile = self.service.users().getProfile(userId='me').execute()
            self.event_bus.publish("gmail_authenticated", {
                "email": profile['emailAddress'],
                "status": "success"
            })
            
            self.running = True
            threading.Thread(target=self._monitor_emails, daemon=True).start()
            return True
            
        except Exception as e:
            self.event_bus.publish("gmail_error", {"error": str(e)})
            return False
    
    def _monitor_emails(self):
        """Monitor for new emails with priority filtering."""
        last_history_id = None
        
        while self.running:
            try:
                # Get current mailbox state
                mailbox = self.service.users().getProfile(userId='me').execute()
                current_history_id = mailbox.get('historyId')
                
                if last_history_id and current_history_id != last_history_id:
                    # Check for new emails since last check
                    self._process_new_emails(last_history_id)
                
                last_history_id = current_history_id
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                print(f"Gmail monitoring error: {e}")
                time.sleep(60)  # Longer delay on error
    
    def _process_new_emails(self, since_history_id: str):
        """Process new emails and apply priority filtering."""
        try:
            # Get email history since last check
            history = self.service.users().history().list(
                userId='me',
                startHistoryId=since_history_id,
                labelId='INBOX'
            ).execute()
            
            if not history.get('history'):
                return
            
            for record in history['history']:
                if 'messagesAdded' not in record:
                    continue
                
                for message_record in record['messagesAdded']:
                    message_id = message_record['message']['id']
                    self._process_email(message_id)
                    
        except Exception as e:
            print(f"Error processing new emails: {e}")
    
    def _process_email(self, message_id: str):
        """Process individual email and determine if notification is needed."""
        try:
            # Get message details
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            
            headers = {h['name']: h['value'] for h in message['payload']['headers']}
            sender = headers.get('From', 'Unknown')
            subject = headers.get('Subject', 'No Subject')
            
            # Extract email address from sender
            sender_email = re.findall(r'<([^>]+)>', sender)
            sender_email = sender_email[0] if sender_email else sender
            
            # Check if this is a priority sender based on learning
            priority_score = self.priority_engine.get_sender_priority(sender_email)
            
            # Apply filtering rules
            if self._should_notify(sender_email, subject, priority_score):
                message_data = {
                    "platform": "gmail",
                    "sender": sender,
                    "sender_email": sender_email,
                    "subject": subject,
                    "timestamp": datetime.now().isoformat(),
                    "message_id": message_id,
                    "priority_score": priority_score,
                    "snippet": message.get('snippet', '')[:100]
                }
                
                self.event_bus.publish("new_message", message_data)
                
        except Exception as e:
            print(f"Error processing email {message_id}: {e}")
    
    def _should_notify(self, sender_email: str, subject: str, priority_score: float) -> bool:
        """Determine if email should generate notification based on learned patterns."""
        
        # Always notify high-priority senders (learned behavior)
        if priority_score > 5.0:
            return True
        
        # Filter out common automated/marketing patterns
        spam_indicators = [
            'unsubscribe', 'newsletter', 'promotion', 'deal', 'offer',
            'marketing', 'noreply', 'no-reply', 'donotreply'
        ]
        
        sender_lower = sender_email.lower()
        subject_lower = subject.lower()
        
        # Skip obvious automated emails
        for indicator in spam_indicators:
            if indicator in sender_lower or indicator in subject_lower:
                if priority_score < 1.0:  # Unless learned as important
                    return False
        
        # Always notify if sender has any positive learning history
        if priority_score > 0.1:
            return True
        
        # For unknown senders, notify only non-promotional content
        if any(word in subject_lower for word in ['re:', 'fwd:', 'urgent', 'important']):
            return True
        
        return False  # Default to no notification for unknown low-priority emails
    
    def mark_as_read(self, message_id: str):
        """Mark email as read and update sender priority."""
        try:
            # Mark as read in Gmail
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            # Get sender for priority learning
            message = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='metadata'
            ).execute()
            
            headers = {h['name']: h['value'] for h in message['payload']['headers']}
            sender = headers.get('From', '')
            sender_email = re.findall(r'<([^>]+)>', sender)
            sender_email = sender_email[0] if sender_email else sender
            
            # Update learning model
            self.priority_engine.update_sender_score(sender_email, "open")
            return True
            
        except Exception as e:
            print(f"Error marking email as read: {e}")
            return False
    
    def send_reply(self, message_id: str, reply_text: str):
        """Send reply to email and update sender priority."""
        try:
            # Get original message for reply context
            original = self.service.users().messages().get(
                userId='me', 
                id=message_id,
                format='full'
            ).execute()
            
            headers = {h['name']: h['value'] for h in original['payload']['headers']}
            sender = headers.get('From', '')
            subject = headers.get('Subject', '')
            message_id_header = headers.get('Message-ID', '')
            
            # Create reply message
            reply_subject = f"Re: {subject}" if not subject.startswith('Re:') else subject
            
            reply = MimeText(reply_text)
            reply['to'] = sender
            reply['subject'] = reply_subject
            reply['In-Reply-To'] = message_id_header
            reply['References'] = message_id_header
            
            # Send reply
            raw_message = base64.urlsafe_b64encode(reply.as_bytes()).decode()
            send_result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            # Update learning model with strong engagement signal
            sender_email = re.findall(r'<([^>]+)>', sender)
            sender_email = sender_email[0] if sender_email else sender
            self.priority_engine.update_sender_score(sender_email, "reply")
            
            return True
            
        except Exception as e:
            print(f"Error sending email reply: {e}")
            return False
    
    def stop(self):
        """Clean shutdown of Gmail integration."""
        self.running = False

class RedditIntegration:
    """Reddit integration with preference learning and content curation."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.reddit = None
        self.running = False
        self.priority_engine = PriorityLearningEngine()
        self.initial_preferences = []
        
    def start(self):
        """Initialize Reddit API client."""
        if not DEPENDENCIES_AVAILABLE:
            return False
            
        try:
            self.reddit = praw.Reddit(
                client_id=Config.REDDIT_CLIENT_ID,
                client_secret=Config.REDDIT_CLIENT_SECRET,
                username=Config.REDDIT_USERNAME,
                password=Config.REDDIT_PASSWORD,
                user_agent='HermesOmnimind/1.0'
            )
            
            # Test authentication
            user = self.reddit.user.me()
            self.event_bus.publish("reddit_authenticated", {
                "username": str(user),
                "status": "success"
            })
            
            # Load initial preferences from setup
            self.load_preferences()
            
            self.running = True
            threading.Thread(target=self._curate_content, daemon=True).start()
            return True
            
        except Exception as e:
            self.event_bus.publish("reddit_error", {"error": str(e)})
            return False
    
    def load_preferences(self):
        """Load initial preference survey results."""
        prefs_file = "data/reddit_preferences.json"
        if os.path.exists(prefs_file):
            with open(prefs_file, 'r') as f:
                self.initial_preferences = json.load(f)
        else:
            # Default preferences if survey not completed
            self.initial_preferences = [
                "technology", "programming", "artificial intelligence", 
                "science", "news", "worldnews"
            ]
    
    def save_preferences(self, preferences: List[str]):
        """Save user preferences from setup survey."""
        os.makedirs("data", exist_ok=True)
        with open("data/reddit_preferences.json", 'w') as f:
            json.dump(preferences, f)
        self.initial_preferences = preferences
        
        # Seed learning engine with initial preferences
        for pref in preferences:
            self.priority_engine.update_content_pattern(f"category:{pref}", 2.0)
    
    def _curate_content(self):
        """Main content curation loop using learned preferences."""
        while self.running:
            try:
                curated_posts = []
                
                # Phase 1: Use initial preferences (first few weeks)
                if not self._has_sufficient_learning_data():
                    curated_posts.extend(self._get_initial_preference_posts())
                
                # Phase 2: Machine learning based curation
                learned_preferences = self.priority_engine.get_content_preferences()
                if learned_preferences:
                    curated_posts.extend(self._get_ml_curated_posts(learned_preferences))
                
                # Phase 3: Exploration (discover new content)
                curated_posts.extend(self._get_exploration_posts())
                
                # Remove duplicates and sort by relevance
                seen_ids = set()
                unique_posts = []
                for post in curated_posts:
                    if post['id'] not in seen_ids:
                        unique_posts.append(post)
                        seen_ids.add(post['id'])
                
                # Limit to top 20 posts
                unique_posts = unique_posts[:20]
                
                # Update state with curated content
                self.state.set("reddit_curated_posts", unique_posts)
                self.event_bus.publish("reddit_content_updated", {"posts": unique_posts})
                
                time.sleep(600)  # Update every 10 minutes
                
            except Exception as e:
                print(f"Reddit curation error: {e}")
                time.sleep(300)  # 5 minutes on error
    
    def _has_sufficient_learning_data(self) -> bool:
        """Check if we have enough user interaction data for ML curation."""
        conn = sqlite3.connect(self.priority_engine.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reddit_scores WHERE score > 0")
        interaction_count = cursor.fetchone()[0]
        conn.close()
        return interaction_count > 50  # Need 50+ interactions to rely on ML
    
    def _get_initial_preference_posts(self) -> List[Dict]:
        """Get posts based on initial preference survey."""
        posts = []
        
        for preference in self.initial_preferences[:5]:  # Top 5 preferences
            try:
                if preference.startswith("r/"):
                    # Specific subreddit
                    subreddit = self.reddit.subreddit(preference[2:])
                else:
                    # Search across all subreddits
                    search_results = list(self.reddit.subreddit("all").search(
                        preference, sort="relevance", time_filter="day", limit=10
                    ))
                    
                    for submission in search_results:
                        posts.append(self._format_post(submission, "search"))
                    continue
                
                # Get hot posts from subreddit
                for submission in subreddit.hot(limit=10):
                    posts.append(self._format_post(submission, "preference"))
                    
            except Exception as e:
                print(f"Error fetching posts for preference '{preference}': {e}")
        
        return posts
    
    def _get_ml_curated_posts(self, preferences: Dict[str, float]) -> List[Dict]:
        """Get posts based on machine learning preferences."""
        posts = []
        
        # Sort preferences by weight
        sorted_prefs = sorted(preferences.items(), key=lambda x: x[1], reverse=True)
        
        for category, weight in sorted_prefs[:10]:  # Top 10 learned preferences
            try:
                if category.startswith("subreddit:"):
                    # Specific subreddit preference
                    subreddit_name = category.replace("subreddit:", "")
                    subreddit = self.reddit.subreddit(subreddit_name)
                    
                    for submission in subreddit.hot(limit=max(5, int(weight))):
                        posts.append(self._format_post(submission, "ml_curated"))
                        
                elif category.startswith("category:"):
                    # Category-based search
                    search_term = category.replace("category:", "")
                    search_results = list(self.reddit.subreddit("all").search(
                        search_term, sort="relevance", time_filter="day", 
                        limit=max(3, int(weight))
                    ))
                    
                    for submission in search_results:
                        posts.append(self._format_post(submission, "ml_curated"))
                        
            except Exception as e:
                print(f"Error fetching ML curated posts for '{category}': {e}")
        
        return posts
    
    def _get_exploration_posts(self) -> List[Dict]:
        """Get exploration posts to discover new interests."""
        posts = []
        
        try:
            # Get trending posts from r/all
            for submission in self.reddit.subreddit("all").hot(limit=5):
                posts.append(self._format_post(submission, "exploration"))
            
            # Get posts from random interesting subreddits
            exploration_subreddits = [
                "todayilearned", "explainlikeimfive", "askreddit", 
                "showerthoughts", "mildlyinteresting"
            ]
            
            for sub_name in exploration_subreddits:
                try:
                    subreddit = self.reddit.subreddit(sub_name)
                    for submission in subreddit.hot(limit=2):
                        posts.append(self._format_post(submission, "exploration"))
                except:
                    continue
                    
        except Exception as e:
            print(f"Error fetching exploration posts: {e}")
        
        return posts
    
    def _format_post(self, submission, source: str) -> Dict:
        """Format Reddit submission into standardized post data."""
        return {
            "id": submission.id,
            "title": submission.title,
            "subreddit": str(submission.subreddit),
            "author": str(submission.author) if submission.author else "[deleted]",
            "score": submission.score,
            "url": submission.url,
            "permalink": f"https://reddit.com{submission.permalink}",
            "created_utc": submission.created_utc,
            "num_comments": submission.num_comments,
            "selftext": submission.selftext[:200] if submission.selftext else "",
            "source": source,
            "clicked": False,
            "saved": False
        }
    
    def track_interaction(self, post_id: str, action: str, value: float = 1.0):
        """Track user interaction with Reddit post for learning."""
        try:
            # Get post data from state
            posts = self.state.get("reddit_curated_posts", [])
            post_data = next((p for p in posts if p["id"] == post_id), None)
            
            if post_data:
                # Update learning engine
                self.priority_engine.update_reddit_score(
                    post_id=post_id,
                    subreddit=post_data["subreddit"],
                    title=post_data["title"],
                    action=action,
                    value=value
                )
                
                # Update post in current state
                post_data[action] = True
                self.state.set("reddit_curated_posts", posts)
                
        except Exception as e:
            print(f"Error tracking Reddit interaction: {e}")
    
    def stop(self):
        """Clean shutdown of Reddit integration."""
        self.running = False

class SocialIntegrationsManager:
    """Main coordinator for all social platform integrations."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        
        # Initialize platform integrations
        self.whatsapp = WhatsAppIntegration(event_bus, state)
        self.instagram = InstagramIntegration(event_bus, state)
        self.gmail = GmailIntegration(event_bus, state)
        self.reddit = RedditIntegration(event_bus, state)
        
        # Message queue for UI display
        self.message_queue = deque(maxlen=100)
        
        # Setup event handlers
        self.event_bus.subscribe("new_message", self._handle_new_message)
        self.event_bus.subscribe("orb_action", self._handle_orb_action)
        self.event_bus.subscribe("message_interaction", self._handle_message_interaction)
        
    def start_all(self):
        """Start all social integrations."""
        results = {
            "whatsapp": self.whatsapp.start(),
            "instagram": self.instagram.start(),
            "gmail": self.gmail.start(),
            "reddit": self.reddit.start()
        }
        
        self.event_bus.publish("social_integrations_started", results)
        return all(results.values())
    
    def _handle_new_message(self, data: Dict):
        """Handle new message notification from any platform."""
        # Add timestamp if not present
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        
        # Add to message queue for UI display
        self.message_queue.append(data)
        
        # Update state for UI access
        messages_list = list(self.message_queue)
        self.state.set("recent_messages", messages_list)
        
        # Trigger UI notification
        self.event_bus.publish("ui_show_notification", {
            "type": "message",
            "platform": data["platform"],
            "sender": data["sender"],
            "preview": data.get("preview", data.get("subject", "New message"))
        })
    
    def _handle_orb_action(self, data: Dict):
        """Handle orb menu actions (respond, draft, etc.)."""
        action = data.get("action")
        platform = data.get("platform")
        message_data = data.get("message_data")
        
        if action == "respond":
            self._auto_respond(platform, message_data)
        elif action == "draft":
            self._create_draft(platform, message_data)
        elif action == "chat_style":
            self._start_style_chat(platform, message_data)
    
    def _auto_respond(self, platform: str, message_data: Dict):
        """Generate and send automatic response in user's style."""
        try:
            # This would integrate with persona_engine.py for style generation
            # For now, placeholder implementation
            
            response_text = self._generate_response(message_data)
            
            if platform == "whatsapp":
                # Open chat and send response
                self.whatsapp.open_chat(message_data["sender"])
                success = self.whatsapp.send_message(response_text)
                
            elif platform == "instagram":
                success = self.instagram.send_direct_message(
                    message_data["account"],
                    message_data["thread_id"],
                    response_text
                )
                
            elif platform == "gmail":
                success = self.gmail.send_reply(
                    message_data["message_id"],
                    response_text
                )
            else:
                success = False
            
            if success:
                self.event_bus.publish("message_sent", {
                    "platform": platform,
                    "response": response_text[:100]
                })
            
        except Exception as e:
            print(f"Error auto-responding: {e}")
    
    def _generate_response(self, message_data: Dict) -> str:
        """Generate contextual response (placeholder - would integrate with AI personas)."""
        # This would call into persona_engine.py for actual response generation
        # For now, return a simple acknowledgment
        return "Thanks for your message! I'll get back to you soon."
    
    def _create_draft(self, platform: str, message_data: Dict):
        """Create draft response for user review."""
        try:
            draft_text = self._generate_response(message_data)
            
            # Store draft in state for UI display
            draft_data = {
                "platform": platform,
                "message_data": message_data,
                "draft_text": draft_text,
                "created_at": datetime.now().isoformat()
            }
            
            drafts = self.state.get("message_drafts", [])
            drafts.append(draft_data)
            self.state.set("message_drafts", drafts)
            
            self.event_bus.publish("draft_created", draft_data)
            
        except Exception as e:
            print(f"Error creating draft: {e}")
    
    def _start_style_chat(self, platform: str, message_data: Dict):
        """Start autonomous chat in user's style."""
        # This would enable autonomous conversation mode
        # Implementation would depend on persona_engine.py capabilities
        pass
    
    def _handle_message_interaction(self, data: Dict):
        """Handle user interactions with messages for learning."""
        platform = data.get("platform")
        action = data.get("action")  # open, reply, star, etc.
        message_data = data.get("message_data")
        
        if platform == "gmail":
            self.gmail.priority_engine.update_sender_score(
                message_data.get("sender_email", ""),
                action,
                data.get("value", 1.0)
            )
        elif platform == "reddit":
            self.reddit.track_interaction(
                message_data.get("id", ""),
                action,
                data.get("value", 1.0)
            )
    
    def get_recent_messages(self, limit: int = 20) -> List[Dict]:
        """Get recent messages across all platforms."""
        return list(self.message_queue)[-limit:]
    
    def stop_all(self):
        """Shutdown all social integrations."""
        self.whatsapp.stop()
        self.instagram.stop()
        self.gmail.stop()
        self.reddit.stop()

# Export main manager class
__all__ = ['SocialIntegrationsManager']