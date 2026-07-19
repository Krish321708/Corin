"""
HERMES Omnimind Absolute Edition
Configuration Constants & System Parameters
All static configuration values, screen dimensions, and system constants.
"""

<<<<<<< HEAD
import os


# =============================================================================
# UI MODE CONSTANTS
# Used by palette.py and all rendering modules for mode-aware color selection.
# =============================================================================

class UIMode:
    """UI persona mode string constants."""
    ARCHER = "archer"
    HUDSON = "hudson"
    BOTH   = "both"


# =============================================================================
# MAIN CONFIGURATION CLASS
# =============================================================================

class Config:
    """Central configuration constants for HERMES Omnimind system."""

=======
class Config:
    """Central configuration constants for HERMES Omnimind system."""
    
>>>>>>> aa058ec8dcf1da9245722f5e51f4973e3b93b44f
    # ===================== DISPLAY & RESOLUTION =====================
    SCREEN_WIDTH = 1920
    SCREEN_HEIGHT = 810
    TARGET_FPS = 60
<<<<<<< HEAD

    # ===================== VIEWPORT GEOMETRY =====================
    HEADER_HEIGHT = 44

    LEFT_VIEWPORT_WIDTH = 1248
    LEFT_VIEWPORT_HEIGHT = 587  # 631 - 44 (header)

    RIGHT_TOP_VIEWPORT_X = 1248
    RIGHT_TOP_VIEWPORT_WIDTH = 672  # 1920 - 1248
    RIGHT_TOP_VIEWPORT_HEIGHT = 361  # 405 - 44 (header)

=======
    
    # ===================== VIEWPORT GEOMETRY =====================
    # Header bar
    HEADER_HEIGHT = 44
    
    # Left viewport (terrain)
    LEFT_VIEWPORT_WIDTH = 1248
    LEFT_VIEWPORT_HEIGHT = 587  # 631 - 44 (header)
    
    # Right viewports
    RIGHT_TOP_VIEWPORT_X = 1248
    RIGHT_TOP_VIEWPORT_WIDTH = 672  # 1920 - 1248
    RIGHT_TOP_VIEWPORT_HEIGHT = 361  # 405 - 44 (header)
    
>>>>>>> aa058ec8dcf1da9245722f5e51f4973e3b93b44f
    RIGHT_BOTTOM_VIEWPORT_X = 1248
    RIGHT_BOTTOM_VIEWPORT_Y = 405
    RIGHT_BOTTOM_VIEWPORT_WIDTH = 672
    RIGHT_BOTTOM_VIEWPORT_HEIGHT = 405  # 810 - 405
<<<<<<< HEAD

    BOTTOM_STATUS_Y = 631
    BOTTOM_STATUS_HEIGHT = 179  # 810 - 631

    GLOBE_HEIGHT = 196
    GLOBE_RADIUS = 80
    GLOBE_POINT_COUNT = 400
    GLOBE_ROTATION_SPEED = 0.3
    GLOBE_PITCH_TILT = 0.2

    TERRAIN_GRID_DENSITY = 40
    TERRAIN_CAMERA_PITCH = -0.3
    TERRAIN_CAMERA_DISTANCE = 350
    TERRAIN_FOCAL_LENGTH = 400
    TERRAIN_PERSISTENCE = 0.5
    TERRAIN_LACUNARITY = 2.0

    CORNER_BRACKET_LENGTH = 20

    TELEMETRY_LEFT_POS = (20, 80)
    TELEMETRY_RIGHT_X = 1100
    PREVIEW_GRAPH_POS = (20, 520)

=======
    
    # Bottom status row
    BOTTOM_STATUS_Y = 631
    BOTTOM_STATUS_HEIGHT = 179  # 810 - 631
    
    # Globe specific
    GLOBE_HEIGHT = 196  # Upper portion of right-top viewport
    GLOBE_RADIUS = 80
    GLOBE_POINT_COUNT = 400
    GLOBE_ROTATION_SPEED = 0.3  # radians per second
    GLOBE_PITCH_TILT = 0.2  # radians
    
    # ===================== TERRAIN PARAMETERS =====================
    TERRAIN_GRID_DENSITY = 40  # 40x40 grid
    TERRAIN_CAMERA_PITCH = -0.3  # radians
    TERRAIN_CAMERA_DISTANCE = 350  # units
    TERRAIN_FOCAL_LENGTH = 400
    TERRAIN_PERSISTENCE = 0.5  # Fractal persistence
    TERRAIN_LACUNARITY = 2.0   # Fractal lacunarity
    
    # ===================== UI POSITIONING =====================
    # Corner brackets
    CORNER_BRACKET_LENGTH = 20
    
    # Telemetry overlays
    TELEMETRY_LEFT_POS = (20, 80)
    TELEMETRY_RIGHT_X = 1100  # Right-aligned in left viewport
    PREVIEW_GRAPH_POS = (20, 520)
    
    # LLM stream overlay
>>>>>>> aa058ec8dcf1da9245722f5e51f4973e3b93b44f
    LLM_OVERLAY_X = 50
    LLM_OVERLAY_Y = 500
    LLM_OVERLAY_WIDTH = 1150
    LLM_OVERLAY_HEIGHT = 80
<<<<<<< HEAD

    AUDIO_SAMPLE_RATE = 44100
    AUDIO_CHUNK_SIZE = 1024
    AUDIO_FFT_BANDS = 64

    TTS_SPEECH_RATE = 180
    TTS_VOLUME = 0.8

    TEMPERATURE_WARNING = 75.0
    TEMPERATURE_CRITICAL = 85.0

    HARDWARE_UPDATE_INTERVAL = 1.0
    NETWORK_UPDATE_INTERVAL = 1.0
    RSS_UPDATE_INTERVAL = 60.0

    OPENROUTER_API_KEY = "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"
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

    MAIN_LLM_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
    COORDINATE_EXTRACTION_MODEL = "google/gemini-flash-1.5:free"

    INSTAGRAM_ACCOUNTS = [
        {"username": "your_username_1", "password": "your_password_1"},
        {"username": "your_username_2", "password": "your_password_2"},
        {"username": "your_username_3", "password": "your_password_3"},
    ]

    # Audio sound file paths
    SOUND_ACCESS_GRANTED = os.path.join("assets", "sounds", "access_granted.wav")
    SOUND_THINKING_MACHINE = os.path.join("assets", "sounds", "thinking_machine.wav")
    SOUND_DEEP_SPACE_PING = os.path.join("assets", "sounds", "deep_space_ping.wav")
    SOUND_ALERT_ALARM = os.path.join("assets", "sounds", "alert_alarm.wav")

=======
    
    # ===================== AUDIO SYSTEM =====================
    AUDIO_SAMPLE_RATE = 44100
    AUDIO_CHUNK_SIZE = 1024
    AUDIO_FFT_BANDS = 64
    
    # Text-to-speech settings
    TTS_SPEECH_RATE = 180  # Words per minute
    TTS_VOLUME = 0.8       # Volume level (0.0 to 1.0)
    
    # ===================== HARDWARE MONITORING =====================
    # Temperature thresholds (Celsius)
    TEMPERATURE_WARNING = 75.0
    TEMPERATURE_CRITICAL = 85.0
    
    # Update intervals (seconds)
    HARDWARE_UPDATE_INTERVAL = 1.0
    NETWORK_UPDATE_INTERVAL = 1.0
    RSS_UPDATE_INTERVAL = 60.0
    
    # ===================== API CONFIGURATION =====================
    # OpenRouter API
    OPENROUTER_API_KEY = "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"
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    
    # Models
    MAIN_LLM_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
    COORDINATE_EXTRACTION_MODEL = "google/gemini-flash-1.5:free"
    
    # ===================== SOCIAL INTEGRATION =====================
    # Instagram accounts (replace with actual credentials)
    INSTAGRAM_ACCOUNTS = [
        {"username": "your_username_1", "password": "your_password_1"},
        {"username": "your_username_2", "password": "your_password_2"},
        {"username": "your_username_3", "password": "your_password_3"}
    ]
    
    # Reddit API credentials (replace with actual values)
>>>>>>> aa058ec8dcf1da9245722f5e51f4973e3b93b44f
    REDDIT_CLIENT_ID = "your_reddit_client_id"
    REDDIT_CLIENT_SECRET = "your_reddit_client_secret"
    REDDIT_USERNAME = "your_reddit_username"
    REDDIT_PASSWORD = "your_reddit_password"
<<<<<<< HEAD

    GITHUB_TOKEN = "your_github_token"
    GITHUB_USERNAME = "your_github_username"

    MEMORY_TOKEN_LIMIT = 20000
    MEMORY_FILE_WORD_LIMIT = 400
    SESSION_TIMEOUT = 1800

    MAX_DAEMON_RESTART_ATTEMPTS = 3
    DAEMON_RESTART_DELAY = 5.0

    SYSTEM_HEALTH_UPDATE_INTERVAL = 5.0
    CRITICAL_HEALTH_THRESHOLD = 30.0

    VOICE_RECOGNITION_TIMEOUT = 5.0
    VOICE_PHRASE_TIME_LIMIT = 10.0

    DEBUG_MODE = False
    LOG_LEVEL = "INFO"
    PERFORMANCE_MONITORING = True

    DATA_DIRECTORY = "data"
    ASSETS_DIRECTORY = "assets"
    SOUNDS_DIRECTORY = os.path.join("assets", "sounds")
    SESSIONS_DIRECTORY = "brainstorming_sessions"

    # Audio sound file paths
    SOUND_ACCESS_GRANTED = os.path.join("assets", "sounds", "access_granted.wav")
    SOUND_THINKING_MACHINE = os.path.join("assets", "sounds", "thinking_machine.wav")
    SOUND_DEEP_SPACE_PING = os.path.join("assets", "sounds", "deep_space_ping.wav")
    SOUND_ALERT_ALARM = os.path.join("assets", "sounds", "alert_alarm.wav")

    ARCHER_SOUL_FILE = os.path.join("data", "archer_soul.md")
    HUDSON_SOUL_FILE = os.path.join("data", "hudson_soul.md")
    USERS_FILE = os.path.join("data", "users.md")

    NEWS_DATABASE = os.path.join("data", "news_database.db")
    SOCIAL_LEARNING_DATABASE = os.path.join("data", "social_learning.db")
    COORDINATE_CACHE_DATABASE = os.path.join("data", "coordinate_cache.db")

    MAX_TERRAIN_POINTS = 1600
    MAX_NEWS_ARTICLES = 100
    MAX_SOCIAL_MESSAGES = 50
    MAX_MEMORY_ENTRIES = 200

    HTTP_TIMEOUT = 10.0
    MAX_CONCURRENT_REQUESTS = 5
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1.0

    AUDIO_NOISE_THRESHOLD = 300
    VOICE_ACTIVITY_THRESHOLD = 0.1
    TTS_QUEUE_SIZE = 10

    TERRAIN_UPDATE_FPS = 60
    GLOBE_UPDATE_FPS = 60
    DIAGNOSTIC_UPDATE_FPS = 30
    NEWS_SCROLL_SPEED = 20.0

    UI_MODE_ARCHER = "archer"
    UI_MODE_HUDSON = "hudson"
    UI_MODE_BOTH = "both"

    @classmethod
    def validate(cls) -> bool:
        if cls.SCREEN_WIDTH <= 0 or cls.SCREEN_HEIGHT <= 0:
            print("Config validation failed: invalid screen dimensions")
            return False

        if cls.TARGET_FPS <= 0 or cls.TARGET_FPS > 240:
            print("Config validation failed: invalid FPS target")
            return False

        if cls.TEMPERATURE_WARNING >= cls.TEMPERATURE_CRITICAL:
            print("Config validation failed: temperature thresholds inverted")
            return False

        if cls.AUDIO_SAMPLE_RATE <= 0 or cls.AUDIO_CHUNK_SIZE <= 0:
            print("Config validation failed: invalid audio parameters")
            return False

        if not cls.OPENROUTER_API_KEY:
            print("Warning: OpenRouter API key is empty")

        return True


# =============================================================================
# TOP-LEVEL CONFIG EXPORTS
# =============================================================================

class ActiveConfig:
    github_token = Config.GITHUB_TOKEN
    performance_tier = Config.UI_MODE_BOTH

ARCHER_SOUL_PATH = Config.ARCHER_SOUL_FILE
HUDSON_SOUL_PATH = Config.HUDSON_SOUL_FILE
USERS_MD_PATH = Config.USERS_FILE
SESSION_TOKEN_LIMIT = Config.MEMORY_TOKEN_LIMIT
FFT_BANDS = Config.AUDIO_FFT_BANDS

# System information
SYSTEM_NAME = "HERMES"
SYSTEM_VERSION = "Omnimind Absolute Edition"
SYSTEM_CODENAME = "Jarvis-Integration:StarkCore"

# Build info
BUILD_VERSION = "1.0.0"
BUILD_DATE = "2024-12-19"
BUILD_AUTHOR = "Neural Architecture Division"

# Feature flags
ENABLE_TERRAIN_RENDERING = True
ENABLE_VOICE_INTERFACE = True
ENABLE_SOCIAL_INTEGRATION = True
ENABLE_GITHUB_AUTOMATION = True
ENABLE_NEWS_SCRAPING = True
ENABLE_BRAINSTORMING_MODE = True
ENABLE_AUDIO_PROCESSING = True
ENABLE_HARDWARE_MONITORING = True

# Advanced settings
MAX_TERRAIN_POINTS = 1600  # 40x40 grid
MAX_NEWS_ARTICLES = 100
MAX_SOCIAL_MESSAGES = 50
MAX_MEMORY_ENTRIES = 200

# Network settings
HTTP_TIMEOUT = 10.0  # seconds
MAX_CONCURRENT_REQUESTS = 5
RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.0  # seconds

# Audio processing
AUDIO_NOISE_THRESHOLD = 300
VOICE_ACTIVITY_THRESHOLD = 0.1
TTS_QUEUE_SIZE = 10

# UI refresh rates
TERRAIN_UPDATE_FPS = 60
GLOBE_UPDATE_FPS = 60
DIAGNOSTIC_UPDATE_FPS = 30
NEWS_SCROLL_SPEED = 20.0  # pixels per second
=======
    
    # GitHub credentials (replace with actual values)
    GITHUB_TOKEN = "your_github_token"
    GITHUB_USERNAME = "your_github_username"
    
    # ===================== MEMORY & PERSISTENCE =====================
    # Memory file settings
    MEMORY_TOKEN_LIMIT = 20000  # Context limit for session end
    MEMORY_FILE_WORD_LIMIT = 400  # Words per memory file
    
    # Session timeout (seconds)
    SESSION_TIMEOUT = 1800  # 30 minutes
    
    # ===================== SYSTEM BEHAVIOR =====================
    # Daemon settings
    MAX_DAEMON_RESTART_ATTEMPTS = 3
    DAEMON_RESTART_DELAY = 5.0  # seconds
    
    # Health monitoring
    SYSTEM_HEALTH_UPDATE_INTERVAL = 5.0  # seconds
    CRITICAL_HEALTH_THRESHOLD = 30.0     # percentage
    
    # Voice recognition
    VOICE_RECOGNITION_TIMEOUT = 5.0      # seconds
    VOICE_PHRASE_TIME_LIMIT = 10.0       # seconds
    
    # ===================== DEBUGGING & DEVELOPMENT =====================
    DEBUG_MODE = False
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    PERFORMANCE_MONITORING = True
    
    # ===================== FILE PATHS =====================
    DATA_DIRECTORY = "data"
    ASSETS_DIRECTORY = "assets"
    SOUNDS_DIRECTORY = "assets/sounds"
    SESSIONS_DIRECTORY = "brainstorming_sessions"
    
    # Memory files
    ARCHER_SOUL_FILE = "data/archer_soul.md"
    HUDSON_SOUL_FILE = "data/hudson_soul.md"
    USERS_FILE = "data/users.md"
    
    # Databases
    NEWS_DATABASE = "data/news_database.db"
    SOCIAL_LEARNING_DATABASE = "data/social_learning.db"
    COORDINATE_CACHE_DATABASE = "data/coordinate_cache.db"
    
    # ===================== VALIDATION =====================
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration parameters."""
        # Check screen dimensions
        if cls.SCREEN_WIDTH <= 0 or cls.SCREEN_HEIGHT <= 0:
            return False
        
        # Check FPS
        if cls.TARGET_FPS <= 0 or cls.TARGET_FPS > 240:
            return False
        
        # Check temperature thresholds
        if cls.TEMPERATURE_WARNING >= cls.TEMPERATURE_CRITICAL:
            return False
        
        # Check API key exists
        if not cls.OPENROUTER_API_KEY or cls.OPENROUTER_API_KEY == "your_api_key_here":
            print("Warning: OpenRouter API key not configured")
        
        # Check audio parameters
        if cls.AUDIO_SAMPLE_RATE <= 0 or cls.AUDIO_CHUNK_SIZE <= 0:
            return False
        
        return True
    
    # ===================== SYSTEM INFO =====================
    SYSTEM_NAME = "HERMES"
    SYSTEM_VERSION = "Omnimind Absolute Edition"
    SYSTEM_CODENAME = "Jarvis-Integration:StarkCore"
    
    # Build info
    BUILD_VERSION = "1.0.0"
    BUILD_DATE = "2024-12-19"
    BUILD_AUTHOR = "Neural Architecture Division"
    
    # ===================== FEATURE FLAGS =====================
    # Enable/disable major features
    ENABLE_TERRAIN_RENDERING = True
    ENABLE_VOICE_INTERFACE = True
    ENABLE_SOCIAL_INTEGRATION = True
    ENABLE_GITHUB_AUTOMATION = True
    ENABLE_NEWS_SCRAPING = True
    ENABLE_BRAINSTORMING_MODE = True
    ENABLE_AUDIO_PROCESSING = True
    ENABLE_HARDWARE_MONITORING = True
    
    # ===================== ADVANCED SETTINGS =====================
    # Performance tuning
    MAX_TERRAIN_POINTS = 1600  # 40x40 grid
    MAX_NEWS_ARTICLES = 100
    MAX_SOCIAL_MESSAGES = 50
    MAX_MEMORY_ENTRIES = 200
    
    # Network settings
    HTTP_TIMEOUT = 10.0  # seconds
    MAX_CONCURRENT_REQUESTS = 5
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 1.0  # seconds
    
    # Audio processing
    AUDIO_NOISE_THRESHOLD = 300
    VOICE_ACTIVITY_THRESHOLD = 0.1
    TTS_QUEUE_SIZE = 10
    
    # UI refresh rates
    TERRAIN_UPDATE_FPS = 60
    GLOBE_UPDATE_FPS = 60
    DIAGNOSTIC_UPDATE_FPS = 30
    NEWS_SCROLL_SPEED = 20.0  # pixels per second
>>>>>>> aa058ec8dcf1da9245722f5e51f4973e3b93b44f
