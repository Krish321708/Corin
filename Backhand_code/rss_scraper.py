"""
HERMES Omnimind Absolute Edition
RSS News Scraper & Geographic Intelligence Engine
Real-time news aggregation with AI-powered coordinate extraction and global event mapping.
"""

import asyncio
import json
import logging
import re
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin, urlparse
import hashlib
import sqlite3
import os

# Core system imports
from Backhand_code.config import Config
from Backhand_code.state import HermesState
from Backhand_code.event_bus import EventBus

# External libraries
try:
    import feedparser
    import requests
    from bs4 import BeautifulSoup
    import xml.etree.ElementTree as ET
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: RSS scraper dependencies missing: {e}")
    DEPENDENCIES_AVAILABLE = False

class GeographicExtractor:
    """Advanced NLP coordinate extraction using Gemini Flash 1.5."""
    
    def __init__(self):
        self.api_key = Config.OPENROUTER_API_KEY
        self.model = "google/gemini-flash-1.5:free"
        self.api_base = "https://openrouter.ai/api/v1"
        self.session = requests.Session()
        self.cache_db = "data/coordinate_cache.db"
        self.setup_cache_db()
        
        # Geographic extraction prompt template
        self.extraction_prompt = """You are a precise geographic intelligence analyst. Extract location information from news articles with surgical accuracy.

TASK: Analyze this news article and extract the PRIMARY geographic location where the main event occurred.

ARTICLE:
---
HEADLINE: {headline}
CONTENT: {content}
SOURCE: {source}
---

EXTRACTION RULES:
1. Identify the MAIN EVENT location (not just mentioned places)
2. If multiple locations, choose where the PRIMARY action/event occurred
3. Provide precise coordinates (latitude, longitude) in decimal degrees
4. If no clear geographic location exists, respond with "GLOBAL"

RESPONSE FORMAT (JSON only, no other text):
{{
    "location_found": true/false,
    "primary_location": "City, Country" or "GLOBAL",
    "coordinates": [latitude, longitude] or null,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of location choice"
}}

EXAMPLES:
- "Tesla factory fire in Berlin" → Berlin, Germany coordinates
- "Meta announces new AI model" → GLOBAL (no specific event location)
- "Earthquake strikes Tokyo" → Tokyo, Japan coordinates
- "Study shows climate change effects" → GLOBAL (general topic)

Extract now:"""

    def setup_cache_db(self):
        """Initialize coordinate extraction cache database."""
        os.makedirs("data", exist_ok=True)
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS coordinate_cache (
                content_hash TEXT PRIMARY KEY,
                headline TEXT,
                extracted_data TEXT,
                coordinates_lat REAL,
                coordinates_lon REAL,
                location_name TEXT,
                confidence REAL,
                is_global INTEGER,
                extraction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()

    def extract_coordinates(self, headline: str, content: str, source: str) -> Dict[str, Any]:
        """Extract geographic coordinates from article using AI analysis."""
        
        # Create content hash for caching
        content_hash = hashlib.sha256(f"{headline}{content}".encode()).hexdigest()
        
        # Check cache first
        cached_result = self._get_cached_extraction(content_hash)
        if cached_result:
            return cached_result
        
        try:
            # Clean and prepare content for analysis
            cleaned_content = self._clean_article_content(content)
            
            # Format prompt with article data
            prompt = self.extraction_prompt.format(
                headline=headline,
                content=cleaned_content[:2000],  # Limit content length
                source=source
            )
            
            # Make API request to Gemini Flash 1.5
            response = self._query_gemini_api(prompt)
            
            if response:
                extraction_result = self._parse_extraction_response(response)
                
                # Cache the result
                self._cache_extraction(content_hash, headline, extraction_result)
                
                return extraction_result
            
        except Exception as e:
            print(f"Error extracting coordinates: {e}")
        
        # Fallback to global marking
        return self._create_global_result()

    def _get_cached_extraction(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached coordinate extraction if available."""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT extracted_data, coordinates_lat, coordinates_lon, 
                   location_name, confidence, is_global 
            FROM coordinate_cache 
            WHERE content_hash = ? AND extraction_time > ?
        """, (content_hash, datetime.now() - timedelta(days=7)))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "location_found": not bool(result[5]),  # is_global inverted
                "primary_location": result[3] or "GLOBAL",
                "coordinates": [result[1], result[2]] if result[1] is not None else None,
                "confidence": result[4],
                "is_global": bool(result[5]),
                "cached": True
            }
        
        return None

    def _cache_extraction(self, content_hash: str, headline: str, extraction_result: Dict):
        """Cache extraction result for future use."""
        conn = sqlite3.connect(self.cache_db)
        cursor = conn.cursor()
        
        coords = extraction_result.get("coordinates")
        lat, lon = (coords[0], coords[1]) if coords else (None, None)
        
        cursor.execute("""
            INSERT OR REPLACE INTO coordinate_cache 
            (content_hash, headline, extracted_data, coordinates_lat, coordinates_lon,
             location_name, confidence, is_global)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            content_hash,
            headline,
            json.dumps(extraction_result),
            lat, lon,
            extraction_result.get("primary_location", "GLOBAL"),
            extraction_result.get("confidence", 0.0),
            1 if extraction_result.get("is_global", False) else 0
        ))
        
        conn.commit()
        conn.close()

    def _clean_article_content(self, content: str) -> str:
        """Clean and prepare article content for analysis."""
        # Remove HTML tags if present
        if '<' in content and '>' in content:
            soup = BeautifulSoup(content, 'html.parser')
            content = soup.get_text()
        
        # Remove excessive whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        
        # Remove common article artifacts
        content = re.sub(r'(Read more|Continue reading|Click here).*$', '', content)
        content = re.sub(r'\[.*?\]', '', content)  # Remove bracketed text
        
        return content

    def _query_gemini_api(self, prompt: str) -> Optional[str]:
        """Query Gemini Flash 1.5 via OpenRouter API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/hermes-omnimind",
            "X-Title": "HERMES Omnimind Geographic Extractor",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise geographic intelligence analyst. Extract location coordinates from news articles. Respond only in valid JSON format."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 300,
            "top_p": 0.9
        }
        
        try:
            response = self.session.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                print(f"Gemini API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"Error querying Gemini API: {e}")
        
        return None

    def _parse_extraction_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from Gemini API."""
        try:
            # Clean response and extract JSON
            response = response.strip()
            
            # Find JSON object in response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                
                # Validate and normalize response
                if result.get("location_found") and result.get("coordinates"):
                    # Validate coordinate format
                    coords = result["coordinates"]
                    if len(coords) == 2 and all(isinstance(x, (int, float)) for x in coords):
                        lat, lon = coords
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            result["is_global"] = False
                            return result
                
                # Invalid or missing coordinates - mark as global
                result["location_found"] = False
                result["primary_location"] = "GLOBAL"
                result["coordinates"] = None
                result["is_global"] = True
                return result
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error parsing extraction response: {e}")
        
        return self._create_global_result()

    def _create_global_result(self) -> Dict[str, Any]:
        """Create global fallback result."""
        return {
            "location_found": False,
            "primary_location": "GLOBAL",
            "coordinates": None,
            "confidence": 0.0,
            "reasoning": "No specific geographic location identified",
            "is_global": True
        }

class NewsArticleProcessor:
    """Advanced article content extraction and summarization."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 KHTML/Gecko/20100101 Chrome/91.0.4472.124 Safari/537.36'
        })

    def extract_full_article(self, url: str, rss_content: str) -> Dict[str, str]:
        """Extract full article content from URL with fallback to RSS content."""
        try:
            # First attempt: extract from original URL
            full_content = self._scrape_article_content(url)
            if full_content and len(full_content) > len(rss_content) * 1.5:
                return {
                    "content": full_content,
                    "source_type": "scraped"
                }
        except Exception as e:
            print(f"Error scraping article {url}: {e}")
        
        # Fallback: use RSS content
        return {
            "content": self._clean_rss_content(rss_content),
            "source_type": "rss"
        }

    def _scrape_article_content(self, url: str) -> str:
        """Scrape full article content from URL."""
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        # Try common article content selectors
        content_selectors = [
            'article', '[data-testid="article-body"]', '.article-body',
            '.post-content', '.entry-content', '.content', '.story-body',
            'main', '[role="main"]'
        ]
        
        for selector in content_selectors:
            content_element = soup.select_one(selector)
            if content_element:
                # Extract text with paragraph separation
                paragraphs = content_element.find_all('p')
                if paragraphs:
                    content = '\n\n'.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
                    if len(content) > 200:  # Minimum content length
                        return content
        
        # Fallback: get all paragraph text
        paragraphs = soup.find_all('p')
        content = '\n\n'.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
        
        return content if len(content) > 100 else ""

    def _clean_rss_content(self, content: str) -> str:
        """Clean RSS feed content."""
        if not content:
            return ""
        
        # Remove HTML tags
        soup = BeautifulSoup(content, 'html.parser')
        cleaned = soup.get_text()
        
        # Remove common RSS artifacts
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

    def generate_main_points(self, headline: str, content: str) -> List[str]:
        """Extract main points from article content."""
        # Simple extraction of key sentences
        sentences = re.split(r'[.!?]+', content)
        
        # Filter for informative sentences
        main_points = []
        for sentence in sentences[:10]:  # First 10 sentences
            sentence = sentence.strip()
            if (len(sentence) > 30 and 
                not sentence.lower().startswith(('the', 'a', 'an', 'this', 'that')) and
                any(word in sentence.lower() for word in ['said', 'announced', 'reported', 'according', 'confirmed'])):
                main_points.append(sentence)
                if len(main_points) >= 3:  # Max 3 main points
                    break
        
        # If no good sentences found, use first few sentences
        if not main_points:
            main_points = [s.strip() for s in sentences[:3] if len(s.strip()) > 20]
        
        return main_points

class RSSFeedManager:
    """RSS feed aggregation and management system."""
    
    def __init__(self):
        # Diverse news sources for comprehensive coverage
        self.news_sources = {
            'google_news_world': {
                'url': 'https://news.google.com/rss?topic=w',
                'name': 'Google News World'
            },
            'google_news_tech': {
                'url': 'https://news.google.com/rss?topic=tc',
                'name': 'Google News Technology'
            },
            'bbc_world': {
                'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',
                'name': 'BBC World News'
            },
            'reuters_world': {
                'url': 'https://feeds.reuters.com/reuters/worldNews',
                'name': 'Reuters World News'
            },
            'ap_news': {
                'url': 'https://feeds.apnews.com/ApNews/WorldNews',
                'name': 'Associated Press World'
            },
            'wired': {
                'url': 'https://www.wired.com/feed',
                'name': 'Wired Technology'
            },
            'techcrunch': {
                'url': 'https://feeds.feedburner.com/TechCrunch/',
                'name': 'TechCrunch'
            },
            'ars_technica': {
                'url': 'https://feeds.arstechnica.com/arstechnica/index',
                'name': 'Ars Technica'
            }
        }
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'HERMES-Omnimind/1.0 (News Aggregator)',
            'Accept': 'application/rss+xml, application/xml, text/xml'
        })

    def fetch_feed(self, feed_url: str, source_name: str) -> List[Dict[str, Any]]:
        """Fetch and parse RSS feed from URL."""
        try:
            response = self.session.get(feed_url, timeout=10)
            response.raise_for_status()
            
            # Parse RSS feed
            feed = feedparser.parse(response.content)
            
            if feed.bozo and feed.bozo_exception:
                print(f"RSS parsing warning for {source_name}: {feed.bozo_exception}")
            
            articles = []
            for entry in feed.entries[:20]:  # Limit to 20 articles per source
                try:
                    article_data = self._parse_rss_entry(entry, source_name)
                    if article_data:
                        articles.append(article_data)
                except Exception as e:
                    print(f"Error parsing RSS entry from {source_name}: {e}")
                    continue
            
            return articles
            
        except Exception as e:
            print(f"Error fetching RSS feed {source_name}: {e}")
            return []

    def _parse_rss_entry(self, entry, source_name: str) -> Optional[Dict[str, Any]]:
        """Parse individual RSS entry into structured data."""
        try:
            # Extract basic information
            title = getattr(entry, 'title', 'No Title').strip()
            link = getattr(entry, 'link', '')
            
            # Get publication time
            pub_time = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_time = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_time = datetime(*entry.updated_parsed[:6])
            else:
                pub_time = datetime.now()
            
            # Extract content
            content = ""
            if hasattr(entry, 'content'):
                content = entry.content[0].value if entry.content else ""
            elif hasattr(entry, 'summary'):
                content = entry.summary
            elif hasattr(entry, 'description'):
                content = entry.description
            
            # Skip if content is too short
            if len(content) < 50 and len(title) < 20:
                return None
            
            # Create unique ID
            article_id = hashlib.md5(f"{title}{link}".encode()).hexdigest()
            
            return {
                'id': article_id,
                'title': title,
                'url': link,
                'content': content,
                'source': source_name,
                'published': pub_time.isoformat(),
                'timestamp': pub_time
            }
            
        except Exception as e:
            print(f"Error parsing RSS entry: {e}")
            return None

    def fetch_all_sources(self) -> List[Dict[str, Any]]:
        """Fetch articles from all configured RSS sources."""
        all_articles = []
        
        for source_id, source_config in self.news_sources.items():
            try:
                articles = self.fetch_feed(source_config['url'], source_config['name'])
                all_articles.extend(articles)
                time.sleep(1)  # Rate limiting between sources
            except Exception as e:
                print(f"Error fetching source {source_id}: {e}")
                continue
        
        # Remove duplicates based on title similarity
        unique_articles = self._deduplicate_articles(all_articles)
        
        # Sort by publication time (newest first)
        unique_articles.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return unique_articles[:50]  # Return top 50 articles

    def _deduplicate_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate articles based on title similarity."""
        unique_articles = []
        seen_titles = set()
        
        for article in articles:
            title = article['title'].lower()
            title_words = set(re.findall(r'\w+', title))
            
            # Check for similar titles
            is_duplicate = False
            for seen_title in seen_titles:
                seen_words = set(re.findall(r'\w+', seen_title))
                overlap = len(title_words & seen_words)
                
                # Consider duplicate if >70% word overlap
                if overlap > 0 and overlap / max(len(title_words), len(seen_words)) > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_articles.append(article)
                seen_titles.add(title)
        
        return unique_articles

class NewsDatabase:
    """Persistent storage for processed news articles with geographic data."""
    
    def __init__(self, db_path: str = "data/news_database.db"):
        self.db_path = db_path
        self.setup_database()

    def setup_database(self):
        """Initialize news database with required tables."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Main news articles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id TEXT PRIMARY KEY,
                headline TEXT NOT NULL,
                main_points TEXT,
                source TEXT,
                source_url TEXT,
                published_time TIMESTAMP,
                coordinates_lat REAL,
                coordinates_lon REAL,
                location_name TEXT,
                is_global INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                content TEXT,
                processed_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                clicks INTEGER DEFAULT 0,
                last_accessed TIMESTAMP
            )
        """)
        
        # Geographic events index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_coordinates 
            ON news_articles(coordinates_lat, coordinates_lon)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_published_time 
            ON news_articles(published_time)
        """)
        
        conn.commit()
        conn.close()

    def store_article(self, article_data: Dict[str, Any]) -> bool:
        """Store processed article in database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO news_articles 
                (id, headline, main_points, source, source_url, published_time,
                 coordinates_lat, coordinates_lon, location_name, is_global,
                 confidence, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article_data['id'],
                article_data['headline'],
                json.dumps(article_data.get('main_points', [])),
                article_data['source'],
                article_data.get('url', ''),
                article_data['time'],
                article_data.get('coordinates', [None, None])[0],
                article_data.get('coordinates', [None, None])[1],
                article_data.get('location', 'GLOBAL'),
                1 if article_data.get('is_global', False) else 0,
                article_data.get('confidence', 0.0),
                article_data.get('content', '')
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error storing article: {e}")
            return False

    def get_recent_articles(self, hours: int = 24, include_global: bool = True) -> List[Dict[str, Any]]:
        """Retrieve recent articles for UI display."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since_time = datetime.now() - timedelta(hours=hours)
        
        if include_global:
            cursor.execute("""
                SELECT id, headline, main_points, source, source_url, published_time,
                       coordinates_lat, coordinates_lon, location_name, is_global, confidence
                FROM news_articles 
                WHERE published_time > ?
                ORDER BY published_time DESC
                LIMIT 100
            """, (since_time,))
        else:
            cursor.execute("""
                SELECT id, headline, main_points, source, source_url, published_time,
                       coordinates_lat, coordinates_lon, location_name, is_global, confidence
                FROM news_articles 
                WHERE published_time > ? AND is_global = 0
                ORDER BY published_time DESC
                LIMIT 100
            """, (since_time,))
        
        articles = []
        for row in cursor.fetchall():
            article = {
                'id': row[0],
                'headline': row[1],
                'main_points': json.loads(row[2]) if row[2] else [],
                'source': row[3],
                'url': row[4],
                'time': row[5],
                'coordinates': [row[6], row[7]] if row[6] is not None else None,
                'location': row[8],
                'is_global': bool(row[9]),
                'confidence': row[10]
            }
            articles.append(article)
        
        conn.close()
        return articles

    def get_geographic_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get articles with valid coordinates for globe plotting."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since_time = datetime.now() - timedelta(hours=hours)
        
        cursor.execute("""
            SELECT id, headline, source, coordinates_lat, coordinates_lon, location_name, confidence
            FROM news_articles 
            WHERE published_time > ? 
            AND coordinates_lat IS NOT NULL 
            AND coordinates_lon IS NOT NULL
            AND is_global = 0
            ORDER BY confidence DESC, published_time DESC
        """, (since_time,))
        
        events = []
        for row in cursor.fetchall():
            events.append({
                'id': row[0],
                'headline': row[1],
                'source': row[2],
                'coordinates': [row[3], row[4]],
                'location': row[5],
                'confidence': row[6]
            })
        
        conn.close()
        return events

    def track_article_click(self, article_id: str):
        """Track user interaction with article for analytics."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE news_articles 
                SET clicks = clicks + 1, last_accessed = ?
                WHERE id = ?
            """, (datetime.now(), article_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error tracking article click: {e}")

class RSSScraperEngine:
    """Main RSS scraping and processing engine."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.running = False
        
        # Initialize components
        self.feed_manager = RSSFeedManager()
        self.article_processor = NewsArticleProcessor()
        self.geographic_extractor = GeographicExtractor()
        self.database = NewsDatabase()
        
        # Processing queue
        self.processing_queue = deque()
        self.last_update = datetime.min
        
        # Event subscriptions
        self.event_bus.subscribe("article_clicked", self._handle_article_click)

    def start(self):
        """Start the RSS scraping daemon."""
        if not DEPENDENCIES_AVAILABLE:
            self.event_bus.publish("rss_scraper_error", {
                "error": "Required dependencies not available"
            })
            return False
        
        try:
            self.running = True
            
            # Start background processing threads
            threading.Thread(target=self._scraping_loop, daemon=True).start()
            threading.Thread(target=self._processing_loop, daemon=True).start()
            
            self.event_bus.publish("rss_scraper_started", {"status": "success"})
            return True
            
        except Exception as e:
            self.event_bus.publish("rss_scraper_error", {"error": str(e)})
            return False

    def _scraping_loop(self):
        """Main RSS feed scraping loop."""
        while self.running:
            try:
                start_time = time.time()
                
                # Fetch articles from all sources
                raw_articles = self.feed_manager.fetch_all_sources()
                
                # Filter new articles (not processed in last 2 hours)
                new_articles = self._filter_new_articles(raw_articles)
                
                # Add to processing queue
                for article in new_articles:
                    self.processing_queue.append(article)
                
                # Update state with scraping statistics
                self.state.set("rss_last_scrape_time", datetime.now().isoformat())
                self.state.set("rss_articles_scraped", len(raw_articles))
                self.state.set("rss_new_articles", len(new_articles))
                self.state.set("rss_processing_queue", len(self.processing_queue))
                
                # Publish update event
                self.event_bus.publish("rss_scrape_completed", {
                    "articles_found": len(raw_articles),
                    "new_articles": len(new_articles),
                    "processing_time": time.time() - start_time
                })
                
                # Wait 60 seconds before next scrape
                time.sleep(60)
                
            except Exception as e:
                print(f"RSS scraping error: {e}")
                time.sleep(120)  # Wait 2 minutes on error

    def _processing_loop(self):
        """Process articles with coordinate extraction."""
        while self.running:
            try:
                if self.processing_queue:
                    article = self.processing_queue.popleft()
                    processed_article = self._process_article(article)
                    
                    if processed_article:
                        # Store in database
                        self.database.store_article(processed_article)
                        
                        # Update UI state
                        self._update_ui_state()
                    
                    # Rate limiting for API calls
                    time.sleep(2)
                else:
                    time.sleep(5)  # Wait when no articles to process
                    
            except Exception as e:
                print(f"Article processing error: {e}")
                time.sleep(10)

    def _filter_new_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out articles that were recently processed."""
        cutoff_time = datetime.now() - timedelta(hours=2)
        
        new_articles = []
        for article in articles:
            # Skip if too old
            if article['timestamp'] < cutoff_time:
                continue
            
            # Check if already processed
            existing = self.database.get_recent_articles(hours=48)
            if any(existing_article['id'] == article['id'] for existing_article in existing):
                continue
            
            new_articles.append(article)
        
        return new_articles

    def _process_article(self, article: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process single article with full extraction pipeline."""
        try:
            # Extract full article content
            content_data = self.article_processor.extract_full_article(
                article['url'], 
                article['content']
            )
            
            full_content = content_data['content']
            
            # Generate main points
            main_points = self.article_processor.generate_main_points(
                article['title'], 
                full_content
            )
            
            # Extract geographic coordinates
            geo_data = self.geographic_extractor.extract_coordinates(
                article['title'], 
                full_content, 
                article['source']
            )
            
            # Create processed article data structure
            processed_article = {
                'id': article['id'],
                'headline': article['title'],
                'main_points': main_points,
                'source': article['source'],
                'url': article['url'],
                'time': article['published'],
                'coordinates': geo_data.get('coordinates'),
                'location': geo_data.get('primary_location', 'GLOBAL'),
                'is_global': geo_data.get('is_global', True),
                'confidence': geo_data.get('confidence', 0.0),
                'content': full_content
            }
            
            return processed_article
            
        except Exception as e:
            print(f"Error processing article {article.get('id', 'unknown')}: {e}")
            return None

    def _update_ui_state(self):
        """Update UI state with latest processed articles."""
        try:
            # Get recent articles for news panel
            recent_articles = self.database.get_recent_articles(hours=12)
            self.state.set("news_articles", recent_articles)
            
            # Get geographic events for globe plotting
            geographic_events = self.database.get_geographic_events(hours=24)
            self.state.set("globe_coordinates", geographic_events)
            
            # Update statistics
            total_articles = len(recent_articles)
            global_articles = len([a for a in recent_articles if a['is_global']])
            geographic_articles = total_articles - global_articles
            
            self.state.set("news_stats", {
                "total_articles": total_articles,
                "global_articles": global_articles,
                "geographic_articles": geographic_articles,
                "last_update": datetime.now().isoformat()
            })
            
            # Publish update event
            self.event_bus.publish("news_data_updated", {
                "articles_count": total_articles,
                "geographic_events": len(geographic_events)
            })
            
        except Exception as e:
            print(f"Error updating UI state: {e}")

    def _handle_article_click(self, event_data: Dict[str, Any]):
        """Handle user clicking on news article."""
        article_id = event_data.get("article_id")
        if article_id:
            # Track click for analytics
            self.database.track_article_click(article_id)
            
            # Emit tactical overlay event
            self.event_bus.publish("show_tactical_overlay", {
                "type": "news_article",
                "article_id": article_id
            })

    def get_article_details(self, article_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed article information for tactical overlay."""
        try:
            conn = sqlite3.connect(self.database.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT headline, main_points, source, source_url, published_time,
                       coordinates_lat, coordinates_lon, location_name, 
                       confidence, content
                FROM news_articles 
                WHERE id = ?
            """, (article_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'headline': result[0],
                    'main_points': json.loads(result[1]) if result[1] else [],
                    'source': result[2],
                    'url': result[3],
                    'time': result[4],
                    'coordinates': [result[5], result[6]] if result[5] is not None else None,
                    'location': result[7],
                    'confidence': result[8],
                    'content': result[9]
                }
            
        except Exception as e:
            print(f"Error getting article details: {e}")
        
        return None

    def stop(self):
        """Stop RSS scraping engine."""
        self.running = False
        self.event_bus.publish("rss_scraper_stopped", {"status": "shutdown"})

# Export main engine class
__all__ = ['RSSScraperEngine']