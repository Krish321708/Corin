"""
HERMES Omnimind Absolute Edition
System Daemons & Background Monitoring
Lightweight daemon lifecycle management for hardware monitoring, network status, 
audio capture, voice I/O, and proactive system health orchestration.
"""

import json
import logging
import os
import platform
import queue
import subprocess
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import hashlib

# Core system imports
from config import Config
from state import HermesState
from event_bus import EventBus
from audio_engine import AudioEngine
from memory_manager import MemoryManager
from persona_engine import PersonaEngine
from github_engine import GitHubEngine
from social_integrations import SocialIntegrationsManager
from rss_scraper import RSSScraperEngine

# External dependencies
try:
    import psutil
    import pyaudio
    import speech_recognition as sr
    import pyttsx3
    import requests
    import numpy as np
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Daemon dependencies missing: {e}")
    DEPENDENCIES_AVAILABLE = False

class HardwareMonitor:
    """Real-time system hardware monitoring daemon."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.running = False
        
        # Monitoring history for trend analysis
        self.cpu_history = deque(maxlen=120)  # 2 minutes at 1Hz
        self.ram_history = deque(maxlen=120)
        self.temp_history = deque(maxlen=120)
        self.disk_io_history = deque(maxlen=60)  # 1 minute for I/O
        self.net_io_history = deque(maxlen=60)
        
        # Previous I/O counters for rate calculation
        self.prev_disk_io = None
        self.prev_net_io = None
        self.prev_io_time = time.time()
        
        # Temperature monitoring setup
        self.temp_sources = self._discover_temperature_sources()

    def _discover_temperature_sources(self) -> List[str]:
        """Discover available temperature monitoring sources."""
        sources = []
        
        try:
            # Try psutil sensors (Linux/macOS)
            if hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                if temps:
                    sources.append("psutil")
            
            # Try reading thermal zone directly (Linux)
            thermal_zone_path = "/sys/class/thermal/thermal_zone0/temp"
            if os.path.exists(thermal_zone_path):
                sources.append("thermal_zone")
            
            # Try reading CPU temperature via lm-sensors (Linux)
            if platform.system() == "Linux":
                try:
                    result = subprocess.run(['sensors'], capture_output=True, text=True, timeout=2)
                    if result.returncode == 0 and 'temp' in result.stdout.lower():
                        sources.append("lm_sensors")
                except:
                    pass
            
            # Try WMI for Windows temperature
            if platform.system() == "Windows":
                try:
                    import wmi
                    sources.append("wmi")
                except ImportError:
                    pass
        
        except Exception as e:
            print(f"Error discovering temperature sources: {e}")
        
        return sources if sources else ["fallback"]

    def start(self):
        """Start hardware monitoring daemon."""
        if not DEPENDENCIES_AVAILABLE:
            return False
        
        try:
            self.running = True
            threading.Thread(target=self._monitoring_loop, daemon=True).start()
            
            self.event_bus.publish("hardware_monitor_started", {
                "status": "success",
                "temp_sources": self.temp_sources
            })
            return True
            
        except Exception as e:
            self.event_bus.publish("hardware_monitor_error", {"error": str(e)})
            return False

    def _monitoring_loop(self):
        """Main hardware monitoring loop."""
        while self.running:
            try:
                start_time = time.time()
                
                # Collect all metrics
                metrics = self._collect_hardware_metrics()
                
                # Update state
                self._update_state_metrics(metrics)
                
                # Check for alerts
                self._check_hardware_alerts(metrics)
                
                # Maintain consistent 1Hz timing
                elapsed = time.time() - start_time
                sleep_time = max(0, 1.0 - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"Hardware monitoring error: {e}")
                time.sleep(5)

    def _collect_hardware_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive hardware metrics."""
        metrics = {}
        
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            cpu_freq = psutil.cpu_freq()
            
            metrics['cpu_usage'] = cpu_percent
            metrics['cpu_per_core'] = cpu_per_core
            metrics['cpu_frequency'] = cpu_freq.current if cpu_freq else 0
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            metrics['ram_usage'] = memory.percent
            metrics['ram_available'] = memory.available // (1024**3)  # GB
            metrics['ram_total'] = memory.total // (1024**3)  # GB
            metrics['swap_usage'] = swap.percent
            
            # Temperature
            metrics['cpu_temp'] = self._get_cpu_temperature()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io and self.prev_disk_io:
                time_delta = time.time() - self.prev_io_time
                read_rate = (disk_io.read_bytes - self.prev_disk_io.read_bytes) / time_delta / (1024**2)  # MB/s
                write_rate = (disk_io.write_bytes - self.prev_disk_io.write_bytes) / time_delta / (1024**2)  # MB/s
                
                metrics['disk_read_mb'] = max(0, read_rate)
                metrics['disk_write_mb'] = max(0, write_rate)
            else:
                metrics['disk_read_mb'] = 0.0
                metrics['disk_write_mb'] = 0.0
            
            self.prev_disk_io = disk_io
            
            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io and self.prev_net_io:
                time_delta = time.time() - self.prev_io_time
                sent_rate = (net_io.bytes_sent - self.prev_net_io.bytes_sent) / time_delta / (1024**2)  # MB/s
                recv_rate = (net_io.bytes_recv - self.prev_net_io.bytes_recv) / time_delta / (1024**2)  # MB/s
                
                metrics['net_sent_mb'] = max(0, sent_rate)
                metrics['net_recv_mb'] = max(0, recv_rate)
            else:
                metrics['net_sent_mb'] = 0.0
                metrics['net_recv_mb'] = 0.0
            
            self.prev_net_io = net_io
            self.prev_io_time = time.time()
            
            # System info
            metrics['active_threads'] = threading.active_count()
            metrics['boot_time'] = psutil.boot_time()
            
            # Load averages (Unix-like systems)
            if hasattr(os, 'getloadavg'):
                load_avg = os.getloadavg()
                metrics['load_1min'] = load_avg[0]
                metrics['load_5min'] = load_avg[1]
                metrics['load_15min'] = load_avg[2]
            
        except Exception as e:
            print(f"Error collecting hardware metrics: {e}")
            
        return metrics

    def _get_cpu_temperature(self) -> float:
        """Get CPU temperature from available sources."""
        
        # Try psutil sensors first
        if "psutil" in self.temp_sources:
            try:
                temps = psutil.sensors_temperatures()
                for name, entries in temps.items():
                    if any(keyword in name.lower() for keyword in ['cpu', 'core', 'processor']):
                        for entry in entries:
                            if entry.current:
                                return entry.current
                
                # Fallback to any temperature sensor
                for name, entries in temps.items():
                    for entry in entries:
                        if entry.current and 20 <= entry.current <= 100:  # Reasonable range
                            return entry.current
            except:
                pass
        
        # Try thermal zone file (Linux)
        if "thermal_zone" in self.temp_sources:
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp = int(f.read().strip()) / 1000.0  # Convert millidegrees to degrees
                    if 20 <= temp <= 100:
                        return temp
            except:
                pass
        
        # Try lm-sensors (Linux)
        if "lm_sensors" in self.temp_sources:
            try:
                result = subprocess.run(['sensors'], capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    # Parse sensors output for CPU temperature
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if any(keyword in line.lower() for keyword in ['cpu', 'core', 'processor']):
                            if '°C' in line or 'C' in line:
                                # Extract temperature value
                                import re
                                temp_match = re.search(r'(\d+\.?\d*)\s*°?C', line)
                                if temp_match:
                                    temp = float(temp_match.group(1))
                                    if 20 <= temp <= 100:
                                        return temp
            except:
                pass
        
        # Try WMI (Windows)
        if "wmi" in self.temp_sources:
            try:
                import wmi
                w = wmi.WMI(namespace="root\\wmi")
                temperature_info = w.MSAcpi_ThermalZoneTemperature()
                if temperature_info:
                    temp = float(temperature_info[0].CurrentTemperature) / 10.0 - 273.15  # Kelvin to Celsius
                    if 20 <= temp <= 100:
                        return temp
            except:
                pass
        
        # Fallback: correlated random walk based on CPU usage
        if hasattr(self, '_fallback_temp'):
            cpu_usage = self.state.get("cpu_usage", 30.0)
            # Temperature loosely correlated with CPU usage
            target_temp = 35.0 + (cpu_usage * 0.5)  # Base 35°C + usage factor
            current_temp = self._fallback_temp
            
            # Random walk towards target with some noise
            import random
            change = (target_temp - current_temp) * 0.1 + random.uniform(-1, 1)
            self._fallback_temp = max(25.0, min(85.0, current_temp + change))
            return round(self._fallback_temp, 1)
        else:
            self._fallback_temp = 40.0  # Initial temperature
            return 40.0

    def _update_state_metrics(self, metrics: Dict[str, Any]):
        """Update state with collected metrics and history."""
        
        # Update current values
        for key, value in metrics.items():
            self.state.set(key, value)
        
        # Update history buffers
        timestamp = time.time()
        
        if 'cpu_usage' in metrics:
            self.cpu_history.append((timestamp, metrics['cpu_usage']))
            self.state.set("cpu_history", list(self.cpu_history))
        
        if 'ram_usage' in metrics:
            self.ram_history.append((timestamp, metrics['ram_usage']))
            self.state.set("ram_history", list(self.ram_history))
        
        if 'cpu_temp' in metrics:
            self.temp_history.append((timestamp, metrics['cpu_temp']))
            self.state.set("temp_history", list(self.temp_history))
        
        if 'disk_read_mb' in metrics and 'disk_write_mb' in metrics:
            self.disk_io_history.append((timestamp, metrics['disk_read_mb'], metrics['disk_write_mb']))
            self.state.set("disk_io_history", list(self.disk_io_history))
        
        if 'net_sent_mb' in metrics and 'net_recv_mb' in metrics:
            self.net_io_history.append((timestamp, metrics['net_sent_mb'], metrics['net_recv_mb']))
            self.state.set("net_io_history", list(self.net_io_history))

    def _check_hardware_alerts(self, metrics: Dict[str, Any]):
        """Check for hardware threshold alerts."""
        
        alerts = []
        
        # Temperature alerts
        if 'cpu_temp' in metrics:
            temp = metrics['cpu_temp']
            if temp > Config.TEMPERATURE_CRITICAL:  # 85°C default
                alerts.append({
                    "type": "critical",
                    "category": "temperature",
                    "message": f"CRITICAL: CPU temperature {temp:.1f}°C exceeds safe limits",
                    "value": temp,
                    "threshold": Config.TEMPERATURE_CRITICAL
                })
            elif temp > Config.TEMPERATURE_WARNING:  # 75°C default
                alerts.append({
                    "type": "warning", 
                    "category": "temperature",
                    "message": f"WARNING: CPU temperature {temp:.1f}°C approaching critical",
                    "value": temp,
                    "threshold": Config.TEMPERATURE_WARNING
                })
        
        # RAM alerts
        if 'ram_usage' in metrics:
            ram_usage = metrics['ram_usage']
            if ram_usage > 90:
                alerts.append({
                    "type": "critical",
                    "category": "memory",
                    "message": f"CRITICAL: RAM usage {ram_usage:.1f}% critically high",
                    "value": ram_usage,
                    "threshold": 90
                })
            elif ram_usage > 80:
                alerts.append({
                    "type": "warning",
                    "category": "memory", 
                    "message": f"WARNING: RAM usage {ram_usage:.1f}% elevated",
                    "value": ram_usage,
                    "threshold": 80
                })
        
        # CPU alerts
        if 'cpu_usage' in metrics:
            cpu_usage = metrics['cpu_usage']
            if cpu_usage > 95:
                alerts.append({
                    "type": "warning",
                    "category": "cpu",
                    "message": f"WARNING: CPU usage {cpu_usage:.1f}% at maximum",
                    "value": cpu_usage,
                    "threshold": 95
                })
        
        # Publish alerts
        for alert in alerts:
            self.event_bus.publish("hardware_alert", alert)
            
        # Update state with current alert status
        self.state.set("hardware_alerts", alerts)

    def stop(self):
        """Stop hardware monitoring daemon."""
        self.running = False

class NetworkMonitor:
    """Network connectivity and latency monitoring daemon."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.running = False
        
        # Ping history for trend analysis
        self.ping_history = deque(maxlen=120)  # 2 minutes at 1Hz
        
        # Test endpoints for connectivity
        self.test_endpoints = [
            "1.1.1.1",  # Cloudflare DNS
            "8.8.8.8",  # Google DNS
            "9.9.9.9",  # Quad9 DNS
        ]
        
        self.session = requests.Session()
        self.session.timeout = 3

    def start(self):
        """Start network monitoring daemon."""
        try:
            self.running = True
            threading.Thread(target=self._monitoring_loop, daemon=True).start()
            
            self.event_bus.publish("network_monitor_started", {"status": "success"})
            return True
            
        except Exception as e:
            self.event_bus.publish("network_monitor_error", {"error": str(e)})
            return False

    def _monitoring_loop(self):
        """Main network monitoring loop."""
        while self.running:
            try:
                start_time = time.time()
                
                # Test connectivity and latency
                connectivity_results = self._test_connectivity()
                
                # Update state
                self._update_network_state(connectivity_results)
                
                # Check for alerts
                self._check_network_alerts(connectivity_results)
                
                # Maintain 1Hz timing
                elapsed = time.time() - start_time
                sleep_time = max(0, 1.0 - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"Network monitoring error: {e}")
                time.sleep(5)

    def _test_connectivity(self) -> Dict[str, Any]:
        """Test network connectivity and latency."""
        results = {
            "internet_up": False,
            "ping_ms": 999.0,
            "endpoint_results": [],
            "timestamp": time.time()
        }
        
        successful_pings = []
        
        for endpoint in self.test_endpoints:
            try:
                # HTTP connectivity test
                start_time = time.time()
                response = self.session.get(f"http://{endpoint}", timeout=3)
                latency = (time.time() - start_time) * 1000  # Convert to ms
                
                if response.status_code == 200 or 200 <= response.status_code < 400:
                    successful_pings.append(latency)
                    results["endpoint_results"].append({
                        "endpoint": endpoint,
                        "success": True,
                        "latency_ms": latency,
                        "status_code": response.status_code
                    })
                else:
                    results["endpoint_results"].append({
                        "endpoint": endpoint,
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                        "latency_ms": 999.0
                    })
                    
            except requests.exceptions.RequestException as e:
                # Try ping as fallback
                try:
                    ping_latency = self._ping_endpoint(endpoint)
                    if ping_latency < 999:
                        successful_pings.append(ping_latency)
                        results["endpoint_results"].append({
                            "endpoint": endpoint,
                            "success": True,
                            "latency_ms": ping_latency,
                            "method": "ping"
                        })
                    else:
                        results["endpoint_results"].append({
                            "endpoint": endpoint,
                            "success": False,
                            "error": str(e),
                            "latency_ms": 999.0
                        })
                except Exception as ping_error:
                    results["endpoint_results"].append({
                        "endpoint": endpoint,
                        "success": False,
                        "error": str(ping_error),
                        "latency_ms": 999.0
                    })
        
        # Calculate overall connectivity status
        if successful_pings:
            results["internet_up"] = True
            results["ping_ms"] = min(successful_pings)  # Best latency
        
        return results

    def _ping_endpoint(self, endpoint: str) -> float:
        """Ping endpoint using system ping command."""
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "1", "-w", "3000", endpoint]
            else:
                cmd = ["ping", "-c", "1", "-W", "3", endpoint]
            
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                # Parse ping time from output
                output = result.stdout
                
                if platform.system() == "Windows":
                    # Windows: "time=123ms" or "time<1ms"
                    import re
                    time_match = re.search(r'time[<=](\d+\.?\d*)ms', output)
                    if time_match:
                        return float(time_match.group(1))
                else:
                    # Unix: "time=123.456 ms"
                    import re
                    time_match = re.search(r'time=(\d+\.?\d*)\s*ms', output)
                    if time_match:
                        return float(time_match.group(1))
                
                # Fallback: calculate based on execution time
                return (time.time() - start_time) * 1000
            
        except Exception as e:
            print(f"Ping error for {endpoint}: {e}")
        
        return 999.0

    def _update_network_state(self, results: Dict[str, Any]):
        """Update network state and history."""
        
        # Update current values
        self.state.set("internet_up", results["internet_up"])
        self.state.set("ping_ms", results["ping_ms"])
        self.state.set("network_endpoints", results["endpoint_results"])
        
        # Update ping history
        timestamp = results["timestamp"]
        self.ping_history.append((timestamp, results["ping_ms"], results["internet_up"]))
        self.state.set("ping_history", list(self.ping_history))

    def _check_network_alerts(self, results: Dict[str, Any]):
        """Check for network connectivity alerts."""
        
        alerts = []
        
        # Internet connectivity alerts
        if not results["internet_up"]:
            alerts.append({
                "type": "critical",
                "category": "connectivity",
                "message": "CRITICAL: Internet connection lost",
                "details": "All network endpoints unreachable"
            })
        
        # High latency alerts
        elif results["ping_ms"] > 500:
            alerts.append({
                "type": "warning",
                "category": "latency",
                "message": f"WARNING: High network latency {results['ping_ms']:.0f}ms",
                "value": results["ping_ms"],
                "threshold": 500
            })
        
        # Publish alerts
        for alert in alerts:
            self.event_bus.publish("network_alert", alert)
        
        # Update state
        self.state.set("network_alerts", alerts)

    def stop(self):
        """Stop network monitoring daemon."""
        self.running = False

class AudioCaptureEngine:
    """Raw audio capture daemon for FFT processing."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, audio_engine):
        self.event_bus = event_bus
        self.state = state
        self.audio_engine = audio_engine
        self.running = False
        
        # Audio capture parameters
        self.sample_rate = Config.AUDIO_SAMPLE_RATE
        self.chunk_size = Config.AUDIO_CHUNK_SIZE
        self.channels = 1
        self.format = pyaudio.paInt16
        
        # PyAudio instance
        self.pyaudio = None
        self.stream = None
        
        # Audio processing queue
        self.audio_queue = queue.Queue(maxsize=10)

    def start(self):
        """Start audio capture daemon."""
        if not DEPENDENCIES_AVAILABLE:
            return False
        
        try:
            # Initialize PyAudio
            self.pyaudio = pyaudio.PyAudio()
            
            # Open input stream
            self.stream = self.pyaudio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback,
                start=True
            )
            
            self.running = True
            threading.Thread(target=self._processing_loop, daemon=True).start()
            
            self.event_bus.publish("audio_capture_started", {
                "sample_rate": self.sample_rate,
                "chunk_size": self.chunk_size
            })
            return True
            
        except Exception as e:
            self.event_bus.publish("audio_capture_error", {"error": str(e)})
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio stream callback for continuous capture."""
        try:
            # Convert bytes to numpy array
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            
            # Add to processing queue (non-blocking)
            try:
                self.audio_queue.put_nowait(audio_data)
            except queue.Full:
                # Drop old data if queue is full
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(audio_data)
                except queue.Empty:
                    pass
                    
        except Exception as e:
            print(f"Audio callback error: {e}")
        
        return (in_data, pyaudio.paContinue)

    def _processing_loop(self):
        """Process captured audio data."""
        while self.running:
            try:
                # Get audio data from queue
                audio_data = self.audio_queue.get(timeout=1.0)
                
                # Send to audio engine for FFT processing
                fft_result = self.audio_engine.process_audio_chunk(audio_data)
                
                if fft_result:
                    # Update state with FFT data
                    self.state.set("audio_fft", fft_result["fft_bands"])
                    self.state.set("audio_volume", fft_result["volume_rms"])
                    self.state.set("audio_peak_frequency", fft_result.get("peak_frequency", 0))
                    
                    # Publish audio data event
                    self.event_bus.publish("audio_data_updated", fft_result)
                
            except queue.Empty:
                # No audio data available
                continue
            except Exception as e:
                print(f"Audio processing error: {e}")
                time.sleep(0.1)

    def stop(self):
        """Stop audio capture daemon."""
        self.running = False
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        if self.pyaudio:
            self.pyaudio.terminate()

class VoiceIOEngine:
    """Voice input/output coordination daemon."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.running = False
        
        # Speech recognition
        self.recognizer = None
        self.microphone = None
        
        # Text-to-speech
        self.tts_engine = None
        self.tts_queue = queue.Queue()
        
        # Voice activity detection
        self.is_listening = False
        self.is_speaking = False
        
        # Calibration settings
        self.ambient_noise_level = None

    def start(self):
        """Start voice I/O daemon."""
        if not DEPENDENCIES_AVAILABLE:
            return False
        
        try:
            # Initialize speech recognition
            self.recognizer = sr.Recognizer()
            self.microphone = sr.Microphone()
            
            # Calibrate for ambient noise
            print("Calibrating microphone for ambient noise...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
                self.ambient_noise_level = self.recognizer.energy_threshold
            
            # Initialize text-to-speech
            self.tts_engine = pyttsx3.init()
            self._configure_tts()
            
            self.running = True
            
            # Start daemon threads
            threading.Thread(target=self._voice_recognition_loop, daemon=True).start()
            threading.Thread(target=self._tts_processing_loop, daemon=True).start()
            
            # Setup event handlers
            self.event_bus.subscribe("speak_text", self._handle_speak_request)
            self.event_bus.subscribe("voice_mode_changed", self._handle_voice_mode_change)
            
            self.event_bus.publish("voice_io_started", {
                "ambient_noise_level": self.ambient_noise_level
            })
            return True
            
        except Exception as e:
            self.event_bus.publish("voice_io_error", {"error": str(e)})
            return False

    def _configure_tts(self):
        """Configure text-to-speech settings."""
        try:
            voices = self.tts_engine.getProperty('voices')
            
            # Select voice (prefer female voice if available)
            selected_voice = voices[0].id  # Default
            for voice in voices:
                if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                    selected_voice = voice.id
                    break
            
            self.tts_engine.setProperty('voice', selected_voice)
            self.tts_engine.setProperty('rate', Config.TTS_SPEECH_RATE)  # Words per minute
            self.tts_engine.setProperty('volume', Config.TTS_VOLUME)  # Volume level
            
        except Exception as e:
            print(f"TTS configuration error: {e}")

    def _voice_recognition_loop(self):
        """Continuous voice recognition loop."""
        while self.running:
            try:
                # Check if voice recognition should be active
                voice_enabled = self.state.get("voice_recognition_enabled", True)
                if not voice_enabled or self.is_speaking:
                    time.sleep(0.1)
                    continue
                
                # Listen for voice input
                with self.microphone as source:
                    # Set dynamic energy threshold
                    self.recognizer.energy_threshold = max(
                        self.ambient_noise_level * 1.2,
                        300  # Minimum threshold
                    )
                    
                    # Listen with timeout
                    try:
                        self.is_listening = True
                        self.state.set("voice_listening", True)
                        
                        audio = self.recognizer.listen(
                            source, 
                            timeout=1,
                            phrase_time_limit=5
                        )
                        
                        self.is_listening = False
                        self.state.set("voice_listening", False)
                        
                        # Transcribe audio
                        self._transcribe_audio(audio)
                        
                    except sr.WaitTimeoutError:
                        # No speech detected
                        self.is_listening = False
                        self.state.set("voice_listening", False)
                        continue
                        
            except Exception as e:
                print(f"Voice recognition error: {e}")
                self.is_listening = False
                self.state.set("voice_listening", False)
                time.sleep(1)

    def _transcribe_audio(self, audio):
        """Transcribe captured audio to text."""
        try:
            # Try Google Speech Recognition (free tier)
            text = self.recognizer.recognize_google(audio)
            
            if text.strip():
                timestamp = datetime.now().isoformat()
                
                # Update state
                self.state.set("last_transcript", text)
                self.state.set("transcript_timestamp", timestamp)
                
                # Publish transcript event
                self.event_bus.publish("voice_transcript", {
                    "text": text,
                    "timestamp": timestamp,
                    "confidence": 1.0  # Google API doesn't provide confidence
                })
                
        except sr.UnknownValueError:
            # Speech was unintelligible
            pass
        except sr.RequestError as e:
            print(f"Speech recognition service error: {e}")
        except Exception as e:
            print(f"Transcription error: {e}")

    def _tts_processing_loop(self):
        """Process text-to-speech queue."""
        while self.running:
            try:
                # Get text from TTS queue
                tts_data = self.tts_queue.get(timeout=1.0)
                
                text = tts_data.get("text", "")
                if not text.strip():
                    continue
                
                # Set speaking state
                self.is_speaking = True
                self.state.set("voice_speaking", True)
                
                # Speak text
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
                
                # Clear speaking state
                self.is_speaking = False
                self.state.set("voice_speaking", False)
                
                # Publish completion event
                self.event_bus.publish("speech_completed", {
                    "text": text,
                    "timestamp": datetime.now().isoformat()
                })
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS processing error: {e}")
                self.is_speaking = False
                self.state.set("voice_speaking", False)
                time.sleep(0.5)

    def _handle_speak_request(self, event_data):
        """Handle request to speak text."""
        text = event_data.get("text", "")
        priority = event_data.get("priority", "normal")
        
        if text.strip():
            # Add to TTS queue
            try:
                if priority == "urgent":
                    # Clear queue for urgent messages
                    while not self.tts_queue.empty():
                        try:
                            self.tts_queue.get_nowait()
                        except queue.Empty:
                            break
                
                self.tts_queue.put({
                    "text": text,
                    "priority": priority,
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                print(f"Error queuing TTS: {e}")

    def _handle_voice_mode_change(self, event_data):
        """Handle voice mode changes (Archer/Hudson/Both)."""
        mode = event_data.get("mode", "archer")
        
        # Adjust TTS settings based on mode
        try:
            if mode == "hudson":
                # More robotic/mechanical voice settings
                self.tts_engine.setProperty('rate', Config.TTS_SPEECH_RATE + 20)
            elif mode == "archer":
                # More natural/conversational voice settings
                self.tts_engine.setProperty('rate', Config.TTS_SPEECH_RATE)
            else:  # both
                # Balanced voice settings
                self.tts_engine.setProperty('rate', Config.TTS_SPEECH_RATE + 10)
                
        except Exception as e:
            print(f"Voice mode change error: {e}")

    def stop(self):
        """Stop voice I/O daemon."""
        self.running = False
        self.is_speaking = False
        self.is_listening = False
        
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except:
                pass

class ProactiveOrchestrator:
    """Proactive system health and alerting orchestrator."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        self.running = False
        
        # Alert tracking
        self.active_alerts = {}
        self.alert_history = deque(maxlen=100)
        
        # Health scoring
        self.health_metrics = {
            "cpu": 100.0,
            "memory": 100.0, 
            "temperature": 100.0,
            "network": 100.0,
            "storage": 100.0
        }
        
        # Setup event subscriptions
        self.event_bus.subscribe("hardware_alert", self._handle_hardware_alert)
        self.event_bus.subscribe("network_alert", self._handle_network_alert)

    def start(self):
        """Start proactive orchestrator daemon."""
        try:
            self.running = True
            threading.Thread(target=self._orchestration_loop, daemon=True).start()
            
            self.event_bus.publish("proactive_orchestrator_started", {"status": "success"})
            return True
            
        except Exception as e:
            self.event_bus.publish("proactive_orchestrator_error", {"error": str(e)})
            return False

    def _orchestration_loop(self):
        """Main orchestration and health monitoring loop."""
        while self.running:
            try:
                # Calculate overall system health
                overall_health = self._calculate_system_health()
                
                # Update state
                self.state.set("system_health", overall_health)
                self.state.set("health_metrics", self.health_metrics.copy())
                
                # Check for proactive interventions needed
                self._check_proactive_interventions(overall_health)
                
                # Clean up old alerts
                self._cleanup_old_alerts()
                
                time.sleep(5)  # Run every 5 seconds
                
            except Exception as e:
                print(f"Proactive orchestrator error: {e}")
                time.sleep(10)

    def _calculate_system_health(self) -> Dict[str, float]:
        """Calculate comprehensive system health scores."""
        
        # CPU health (based on usage and temperature)
        cpu_usage = self.state.get("cpu_usage", 0)
        cpu_temp = self.state.get("cpu_temp", 40)
        
        cpu_health = 100.0
        if cpu_usage > 80:
            cpu_health -= (cpu_usage - 80) * 2
        if cpu_temp > 70:
            cpu_health -= (cpu_temp - 70) * 3
        
        self.health_metrics["cpu"] = max(0, cpu_health)
        
        # Memory health
        ram_usage = self.state.get("ram_usage", 0)
        memory_health = max(0, 100 - (max(0, ram_usage - 60) * 2))
        self.health_metrics["memory"] = memory_health
        
        # Temperature health
        temp_health = 100.0
        if cpu_temp > Config.TEMPERATURE_WARNING:
            temp_health = max(0, 100 - ((cpu_temp - Config.TEMPERATURE_WARNING) * 5))
        self.health_metrics["temperature"] = temp_health
        
        # Network health
        internet_up = self.state.get("internet_up", False)
        ping_ms = self.state.get("ping_ms", 999)
        
        if not internet_up:
            network_health = 0
        elif ping_ms > 500:
            network_health = max(0, 100 - ((ping_ms - 100) * 0.1))
        else:
            network_health = 100
        
        self.health_metrics["network"] = network_health
        
        # Overall stability score
        overall_stability = sum(self.health_metrics.values()) / len(self.health_metrics)
        
        return {
            "overall": overall_stability,
            "stability_score": overall_stability,
            "core_health": overall_stability,
            "individual_metrics": self.health_metrics.copy()
        }

    def _check_proactive_interventions(self, health_data: Dict[str, float]):
        """Check if proactive interventions are needed."""
        
        overall_health = health_data["overall"]
        
        # Critical system health
        if overall_health < 30:
            self._trigger_critical_alert("System health critically low", overall_health)
        
        # Individual metric interventions
        for metric, value in self.health_metrics.items():
            if value < 25:
                self._trigger_intervention_alert(metric, value)
        
        # Update daemon override if needed
        if overall_health < 50:
            self.state.set("daemon_override", True)
            self.state.set("daemon_msg", f"System health degraded: {overall_health:.1f}%")
        else:
            self.state.set("daemon_override", False)
            self.state.set("daemon_msg", "")

    def _trigger_critical_alert(self, message: str, health_score: float):
        """Trigger critical system alert."""
        alert_id = hashlib.md5(f"critical_{message}".encode()).hexdigest()
        
        if alert_id not in self.active_alerts:
            alert = {
                "id": alert_id,
                "type": "critical",
                "category": "system",
                "message": message,
                "health_score": health_score,
                "timestamp": datetime.now().isoformat(),
                "acknowledged": False
            }
            
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
            
            # Trigger audio alert
            self.event_bus.publish("speak_text", {
                "text": f"Critical system alert: {message}",
                "priority": "urgent"
            })
            
            # Trigger visual alert
            self.event_bus.publish("critical_alert", alert)

    def _trigger_intervention_alert(self, metric: str, value: float):
        """Trigger proactive intervention alert."""
        alert_id = hashlib.md5(f"intervention_{metric}".encode()).hexdigest()
        
        if alert_id not in self.active_alerts:
            message = f"{metric.title()} health critically low: {value:.1f}%"
            
            alert = {
                "id": alert_id,
                "type": "intervention",
                "category": metric,
                "message": message,
                "value": value,
                "timestamp": datetime.now().isoformat()
            }
            
            self.active_alerts[alert_id] = alert
            
            # Queue for voice notification
            self.event_bus.publish("speak_text", {
                "text": message,
                "priority": "normal"
            })

    def _handle_hardware_alert(self, alert_data):
        """Handle hardware alerts from monitoring daemon."""
        alert_id = f"hardware_{alert_data.get('category', 'unknown')}"
        self.active_alerts[alert_id] = alert_data
        self.alert_history.append(alert_data)

    def _handle_network_alert(self, alert_data):
        """Handle network alerts from monitoring daemon."""
        alert_id = f"network_{alert_data.get('category', 'unknown')}"
        self.active_alerts[alert_id] = alert_data
        self.alert_history.append(alert_data)

    def _cleanup_old_alerts(self):
        """Remove old resolved alerts."""
        current_time = datetime.now()
        expired_alerts = []
        
        for alert_id, alert in self.active_alerts.items():
            alert_time = datetime.fromisoformat(alert["timestamp"])
            if (current_time - alert_time).total_seconds() > 300:  # 5 minutes
                expired_alerts.append(alert_id)
        
        for alert_id in expired_alerts:
            del self.active_alerts[alert_id]

    def stop(self):
        """Stop proactive orchestrator daemon."""
        self.running = False

class DaemonManager:
    """Central daemon lifecycle manager."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        
        # Initialize audio engine first (required by other daemons)
        self.audio_engine = AudioEngine(event_bus, state)
        
        # Initialize all daemon instances
        self.hardware_monitor = HardwareMonitor(event_bus, state)
        self.network_monitor = NetworkMonitor(event_bus, state)
        self.audio_capture = AudioCaptureEngine(event_bus, state, self.audio_engine)
        self.voice_io = VoiceIOEngine(event_bus, state)
        self.proactive_orchestrator = ProactiveOrchestrator(event_bus, state)
        
        # Initialize higher-level engines
        self.memory_manager = MemoryManager(event_bus, state)
        self.persona_engine = PersonaEngine(event_bus, state)
        self.github_engine = GitHubEngine(event_bus, state)
        self.social_integrations = SocialIntegrationsManager(event_bus, state)
        self.rss_scraper = RSSScraperEngine(event_bus, state)
        
        # Track daemon states
        self.daemon_states = {}

    def start_all_daemons(self) -> Dict[str, bool]:
        """Start all daemon instances."""
        results = {}
        
        # Start in dependency order
        startup_sequence = [
            ("audio_engine", self.audio_engine),
            ("hardware_monitor", self.hardware_monitor),
            ("network_monitor", self.network_monitor),
            ("audio_capture", self.audio_capture),
            ("voice_io", self.voice_io),
            ("memory_manager", self.memory_manager),
            ("persona_engine", self.persona_engine),
            ("github_engine", self.github_engine),
            ("social_integrations", self.social_integrations),
            ("rss_scraper", self.rss_scraper),
            ("proactive_orchestrator", self.proactive_orchestrator)
        ]
        
        for daemon_name, daemon_instance in startup_sequence:
            try:
                if hasattr(daemon_instance, 'start'):
                    success = daemon_instance.start()
                elif hasattr(daemon_instance, 'start_all'):
                    success = daemon_instance.start_all()
                else:
                    success = True  # Assume success if no start method
                
                results[daemon_name] = success
                self.daemon_states[daemon_name] = "running" if success else "failed"
                
                if success:
                    print(f"✓ {daemon_name} started successfully")
                else:
                    print(f"✗ {daemon_name} failed to start")
                
                # Small delay between daemon starts
                time.sleep(0.5)
                
            except Exception as e:
                print(f"✗ Error starting {daemon_name}: {e}")
                results[daemon_name] = False
                self.daemon_states[daemon_name] = "error"
        
        # Update state with daemon status
        self.state.set("daemon_states", self.daemon_states.copy())
        
        # Publish startup completion event
        successful_daemons = sum(1 for success in results.values() if success)
        total_daemons = len(results)
        
        self.event_bus.publish("daemons_startup_complete", {
            "results": results,
            "successful": successful_daemons,
            "total": total_daemons,
            "success_rate": successful_daemons / total_daemons
        })
        
        return results

    def stop_all_daemons(self):
        """Stop all running daemons."""
        print("Stopping all daemons...")
        
        # Stop in reverse dependency order
        shutdown_sequence = [
            ("proactive_orchestrator", self.proactive_orchestrator),
            ("rss_scraper", self.rss_scraper),
            ("social_integrations", self.social_integrations),
            ("github_engine", self.github_engine),
            ("persona_engine", self.persona_engine),
            ("memory_manager", self.memory_manager),
            ("voice_io", self.voice_io),
            ("audio_capture", self.audio_capture),
            ("network_monitor", self.network_monitor),
            ("hardware_monitor", self.hardware_monitor),
            ("audio_engine", self.audio_engine)
        ]
        
        for daemon_name, daemon_instance in shutdown_sequence:
            try:
                if hasattr(daemon_instance, 'stop'):
                    daemon_instance.stop()
                    print(f"✓ {daemon_name} stopped")
                elif hasattr(daemon_instance, 'stop_all'):
                    daemon_instance.stop_all()
                    print(f"✓ {daemon_name} stopped")
                
                self.daemon_states[daemon_name] = "stopped"
                
            except Exception as e:
                print(f"✗ Error stopping {daemon_name}: {e}")
                self.daemon_states[daemon_name] = "error"
        
        self.event_bus.publish("daemons_shutdown_complete", {
            "status": "complete"
        })

    def get_daemon_status(self) -> Dict[str, str]:
        """Get current status of all daemons."""
        return self.daemon_states.copy()

    def restart_daemon(self, daemon_name: str) -> bool:
        """Restart specific daemon."""
        daemon_map = {
            "hardware_monitor": self.hardware_monitor,
            "network_monitor": self.network_monitor,
            "audio_capture": self.audio_capture,
            "voice_io": self.voice_io,
            "proactive_orchestrator": self.proactive_orchestrator,
            "memory_manager": self.memory_manager,
            "persona_engine": self.persona_engine,
            "github_engine": self.github_engine,
            "social_integrations": self.social_integrations,
            "rss_scraper": self.rss_scraper,
            "audio_engine": self.audio_engine
        }
        
        daemon_instance = daemon_map.get(daemon_name)
        if not daemon_instance:
            return False
        
        try:
            # Stop daemon
            if hasattr(daemon_instance, 'stop'):
                daemon_instance.stop()
            
            time.sleep(1)
            
            # Restart daemon
            if hasattr(daemon_instance, 'start'):
                success = daemon_instance.start()
            else:
                success = True
            
            self.daemon_states[daemon_name] = "running" if success else "failed"
            return success
            
        except Exception as e:
            print(f"Error restarting {daemon_name}: {e}")
            self.daemon_states[daemon_name] = "error"
            return False

# Export main manager class
__all__ = ['DaemonManager']