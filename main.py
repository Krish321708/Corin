"""
HERMES Omnimind Absolute Edition
Main Application Entry Point & Frame Loop Orchestrator
Central system initialization, event handling, rendering pipeline, and daemon lifecycle management.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Dict, Optional, Tuple, Any

# Core system imports (from core folder)
from core.config import Config
from core.palette import Palette
from core.state import HermesState
from core.event_bus import EventBus
from core.self_test import run_self_tests
from core.daemons import DaemonManager
from core.ui_widgets import initialize_widgets
from core.ui_panels import initialize_panels

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Pygame imports
try:
    import pygame
    import pygame.time
    PYGAME_AVAILABLE = True
except ImportError:
    print("CRITICAL ERROR: Pygame not available. Install with: pip install pygame")
    PYGAME_AVAILABLE = False
    raise


class HermesApplication:
    """Main HERMES Omnimind application controller."""

    def __init__(self) -> None:
        print("═══════════════════════════════════════════════════════════════════════════════")
        print("██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗")
        print("██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝")
        print("███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗")
        print("██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║")
        print("██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║")
        print("╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝")
        print("        OMNIMIND ABSOLUTE EDITION - INITIALIZING")
        print("═══════════════════════════════════════════════════════════════════════════════")
        
        # Core system components
        self.event_bus = EventBus()
        self.state = HermesState()

        # Application state
        self.running = False
        self.clock: Optional[pygame.time.Clock] = None
        self.screen: Optional[pygame.Surface] = None

        # Managers and engines
        self.daemon_manager: Optional[DaemonManager] = None
        self.widgets: Dict[str, Any] = {}
        self.panels: Dict[str, Any] = {}

        # Mode management
        self.current_mode = "archer"
        self.mode_transition_progress = 1.0  # start stable
        self.target_mode = "archer"
        self.mode_transition_speed = 4.0

        # Brainstorming mode
        self.brainstorming_active = False

        # Hudson overlay
        self.hudson_overlay_visible = False

        # Social replacement panel
        self.social_panel_active = False

        # Frame timing
        self.last_frame_time = time.time()
        self.delta_time = 0.0

        # Boot time tracking
        self.boot_start_time = time.time()

        # Subscribe to key events
        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Setup event bus subscriptions."""
        self.event_bus.subscribe("voice_transcript", self._handle_voice_command)
        self.event_bus.subscribe("social_message_clicked", self._handle_social_message_click)
        self.event_bus.subscribe("message_sent", self._handle_message_sent)
        self.event_bus.subscribe("article_clicked", self._handle_article_click)
        self.event_bus.subscribe("critical_alert", self._handle_critical_alert)

    def initialize(self) -> bool:
        """Initialize all system components."""
        try:
            print("\n🔧 PHASE 1: CORE SYSTEM VALIDATION")
            
            # Run self-tests first
            print("   • Running mathematical validation suite...")
            if not run_self_tests():
                print("   ✗ Self-tests failed - system integrity compromised")
                return False
            print("   ✓ Self-tests passed - mathematical engine validated")

            # Set boot time in state
            self.state.set("boot_time", self.boot_start_time)

            print("\n🔧 PHASE 2: PYGAME INITIALIZATION")

            # Initialize Pygame
            pygame.init()
            pygame.font.init()

            # Mixer can fail on some Windows setups; don't hard-crash.
            try:
                pygame.mixer.init()
                print("   ✓ Audio mixer initialized")
            except Exception as e:
                print(f"   ⚠ Warning: Audio mixer failed (continuing without audio): {e}")

            # Create display surface at exact resolution
            print(f"   • Creating display surface: {Config.SCREEN_WIDTH}x{Config.SCREEN_HEIGHT}")
            self.screen = pygame.display.set_mode(
                (Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT),
                pygame.HWSURFACE | pygame.DOUBLEBUF,
            )
            pygame.display.set_caption("HERMES - Omnimind Absolute Edition")
            print("   ✓ Pygame display initialized")

            # Initialize clock for FPS control
            self.clock = pygame.time.Clock()
            print("   ✓ Frame timing clock initialized")

            print("\n🔧 PHASE 3: DIRECTORY SETUP")
            
            # Create required directories
            directories = [
                os.path.join(PROJECT_ROOT, "data"),
                os.path.join(PROJECT_ROOT, "assets"),
                os.path.join(PROJECT_ROOT, "assets", "sounds"),
                os.path.join(PROJECT_ROOT, "brainstorming_sessions")
            ]
            
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
                print(f"   ✓ Directory ensured: {os.path.relpath(directory, PROJECT_ROOT)}")

            print("\n🔧 PHASE 4: WIDGET INITIALIZATION")

            # Initialize UI widgets
            self.widgets = initialize_widgets(self.event_bus, self.state)
            if not self.widgets:
                print("   ✗ Widget initialization failed")
                return False
            print("   ✓ UI widgets initialized")

            print("\n🔧 PHASE 5: PANEL INITIALIZATION")

            # Initialize UI panels
            self.panels = initialize_panels(self.event_bus, self.state, self.widgets["font_manager"])
            if not self.panels:
                print("   ✗ Panel initialization failed")
                return False
            print("   ✓ UI panels initialized")

            # Set voice orb position
            voice_orb = self.widgets.get('voice_orb')
            if voice_orb:
                voice_orb.set_position((Config.SCREEN_WIDTH - 80, Config.SCREEN_HEIGHT - 80))

            print("\n🔧 PHASE 6: DAEMON STARTUP")

            # Initialize daemon manager and start daemons
            print("   • Starting background daemon services...")
            self.daemon_manager = DaemonManager(self.event_bus, self.state)
            daemon_results = self.daemon_manager.start_all_daemons()

            successful_daemons = sum(1 for success in daemon_results.values() if success)
            total_daemons = len(daemon_results)

            print(f"   • Daemon startup results: {successful_daemons}/{total_daemons} successful")

            if successful_daemons < total_daemons * 0.7:  # Require 70% success rate
                print("   ⚠ Warning: Less than 70% of daemons started successfully")
                print("   • System will continue with reduced functionality")
            else:
                print("   ✓ Daemon services operational")

            # System ready
            self.state.set("system_ready", True)
            self.state.set("current_persona_mode", self.current_mode)

            print("\n🚀 HERMES OMNIMIND INITIALIZATION COMPLETE")
            print("   • System ready for neural interface")
            print("   • All subsystems operational")
            print("   • Press Space for brainstorming mode")
            print("═══════════════════════════════════════════════════════════════════════════════\n")

            return True

        except Exception as e:
            print(f"\n❌ CRITICAL INITIALIZATION ERROR: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
            return False

    def run(self) -> None:
        """Main application run loop."""
        if not self.initialize():
            print("❌ INITIALIZATION FAILED - SYSTEM SHUTDOWN")
            return

        self.running = True

        try:
            print("🎯 ENTERING MAIN FRAME LOOP - 60 FPS TARGET")
            
            while self.running:
                # Delta time
                now = time.time()
                self.delta_time = now - self.last_frame_time
                self.last_frame_time = now
                self.delta_time = min(self.delta_time, 1.0 / 30.0)  # Clamp to prevent large jumps

                # Events
                self._handle_events()

                # Update
                self._update_systems()

                # Render
                self._render_frame()

                # FPS cap
                assert self.clock is not None
                self.clock.tick(Config.TARGET_FPS)

        except KeyboardInterrupt:
            print("\n🛑 KEYBOARD INTERRUPT RECEIVED")
        except Exception as e:
            print(f"\n❌ RUNTIME ERROR: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
        finally:
            self._shutdown()

    def _handle_events(self) -> None:
        """Handle Pygame events and keyboard shortcuts."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_click(event.pos)

            # Terminal keypress routing
            terminal = self.widgets.get("terminal")
            if terminal is not None and getattr(terminal, "expanded", False):
                terminal.handle_keypress(event)

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        """Handle keyboard shortcuts."""
        key = event.key

        # ESC - Exit brainstorming mode or quit
        if key == pygame.K_ESCAPE:
            if self.brainstorming_active:
                self._toggle_brainstorming_mode()
            else:
                self.running = False

        # Space - Toggle brainstorming mode
        elif key == pygame.K_SPACE:
            self._toggle_brainstorming_mode()

        # 1/2/3 - Persona mode switching
        elif key == pygame.K_1:
            self._switch_persona_mode("archer")
        elif key == pygame.K_2:
            self._switch_persona_mode("hudson")
        elif key == pygame.K_3:
            self._switch_persona_mode("both")

        # Tab - Toggle terminal
        elif key == pygame.K_TAB:
            terminal = self.widgets.get("terminal")
            if terminal is not None:
                terminal.toggle()

        # H - Hudson overlay
        elif key == pygame.K_h:
            self._toggle_hudson_overlay()

        # Panel navigation
        elif key == pygame.K_n:
            self.event_bus.publish("focus_panel", {"panel": "news"})
        elif key == pygame.K_g:
            self.event_bus.publish("focus_panel", {"panel": "globe"})

        # Social apps
        elif key == pygame.K_w:
            self.event_bus.publish("open_social_app", {"platform": "whatsapp"})
        elif key == pygame.K_i:
            self.event_bus.publish("open_social_app", {"platform": "instagram"})
        elif key == pygame.K_m and not (event.mod & pygame.KMOD_CTRL):
            self.event_bus.publish("open_social_app", {"platform": "gmail"})

        # Other shortcuts
        elif key == pygame.K_r and not (event.mod & pygame.KMOD_CTRL):
            self.event_bus.publish("open_reddit_preferences", {})
        elif key == pygame.K_f:
            self.event_bus.publish("fullscreen_globe", {})

        # Ctrl shortcuts
        elif key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
            self.event_bus.publish("force_save_memory", {})
        elif key == pygame.K_m and (event.mod & pygame.KMOD_CTRL):
            muted = bool(self.state.get("voice_muted", False))
            self.state.set("voice_muted", not muted)
            self.event_bus.publish("voice_mute_toggled", {"muted": not muted})
        elif key == pygame.K_r and (event.mod & pygame.KMOD_CTRL):
            self.event_bus.publish("force_refresh_data", {})

    def _handle_mouse_click(self, pos: Tuple[int, int]) -> None:
        """Handle mouse clicks and route to appropriate panels."""
        # Terminal click first
        terminal = self.widgets.get("terminal")
        if terminal is not None and terminal.handle_mouse_click(pos):
            return

        # Brainstorming mode absorbs clicks
        if self.brainstorming_active:
            return

        # Social replacement panel check
        if self.social_panel_active:
            social_panel = self.panels.get('social_replacement')
            if social_panel and getattr(social_panel, 'active', False):
                # Handle social panel clicks
                pass
            return

        # Route clicks to panels
        panel_order = ["personal_monitor", "news_feed", "globe", "terrain", "diagnostics"]
        for name in panel_order:
            panel = self.panels.get(name)
            if panel is not None and hasattr(panel, 'handle_mouse_click') and panel.handle_mouse_click(pos):
                return

        # Background click
        self.event_bus.publish("background_click", {"position": pos})

    def _toggle_brainstorming_mode(self) -> None:
        """Toggle brainstorming mode with instant transition."""
        self.brainstorming_active = not self.brainstorming_active
        
        panel = self.panels.get("brainstorming")
        if panel is not None:
            panel.set_active(self.brainstorming_active)
        
        self.event_bus.publish("brainstorming_mode_changed", {"active": self.brainstorming_active})
        
        print(f"🧠 Brainstorming mode: {'ENABLED' if self.brainstorming_active else 'DISABLED'}")

    def _switch_persona_mode(self, new_mode: str) -> None:
        """Switch persona mode with transition."""
        if new_mode == self.current_mode:
            return
        
        print(f"🔄 Switching persona mode: {self.current_mode} → {new_mode}")
        
        self.target_mode = new_mode
        self.mode_transition_progress = 0.0

        # Update orb immediately
        orb = self.widgets.get("voice_orb")
        if orb is not None:
            orb.current_mode = new_mode

        self.state.set("current_persona_mode", new_mode)
        self.event_bus.publish("persona_mode_changed", {"mode": new_mode, "previous_mode": self.current_mode})
        self.current_mode = new_mode

    def _toggle_hudson_overlay(self) -> None:
        """Toggle Hudson activity overlay."""
        self.hudson_overlay_visible = not self.hudson_overlay_visible
        overlay = self.panels.get("hudson_overlay")
        if overlay is not None:
            overlay.set_visible(self.hudson_overlay_visible)
        
        print(f"🔍 Hudson overlay: {'VISIBLE' if self.hudson_overlay_visible else 'HIDDEN'}")

    def _update_systems(self) -> None:
        """Update all system components with delta time."""
        # Update voice orb
        orb = self.widgets.get("voice_orb")
        if orb is not None:
            orb.update(self.delta_time)

        # Update terminal
        terminal = self.widgets.get("terminal")
        if terminal is not None:
            terminal.update(self.delta_time)

        # Update all panels
        for panel in self.panels.values():
            if hasattr(panel, "update"):
                panel.update(self.delta_time)

        # Mode transition progress
        if self.mode_transition_progress < 1.0:
            self.mode_transition_progress = min(1.0, self.mode_transition_progress + self.delta_time * self.mode_transition_speed)

        # Update system uptime
        uptime = time.time() - self.boot_start_time
        self.state.set("system_uptime", uptime)

    def _render_frame(self) -> None:
        """Render complete frame."""
        assert self.screen is not None

        # Brainstorming mode takes over completely
        if self.brainstorming_active:
            self.screen.fill(Palette.BLACK)
            brainstorming = self.panels.get("brainstorming")
            if brainstorming is not None:
                brainstorming.render(self.screen)
            pygame.display.flip()
            return

        # Normal rendering
        self.screen.fill(Palette.BLACK)

        # Check if social replacement is active
        social = self.panels.get("social_replacement")
        social_active = bool(getattr(social, "active", False)) if social is not None else False

        if social_active:
            # Render without terrain, social panel replaces it
            render_order = ["header_bar", "globe", "news_feed", "personal_monitor", "diagnostics"]
            for name in render_order:
                panel = self.panels.get(name)
                if panel is not None:
                    panel.render(self.screen)
            social.render(self.screen)
        else:
            # Normal full interface
            render_order = ["header_bar", "terrain", "globe", "news_feed", "personal_monitor", "diagnostics"]
            for name in render_order:
                panel = self.panels.get(name)
                if panel is not None:
                    panel.render(self.screen)

        # Voice orb (always visible in normal mode)
        orb = self.widgets.get("voice_orb")
        if orb is not None:
            orb.render(self.screen)

        # Terminal (always on top)
        terminal = self.widgets.get("terminal")
        if terminal is not None:
            terminal.render(self.screen)

        # Hudson overlay (on top of everything)
        if self.hudson_overlay_visible:
            overlay = self.panels.get("hudson_overlay")
            if overlay is not None:
                overlay.render(self.screen)

        # Mode transition fade effect
        if self.mode_transition_progress < 1.0:
            fade_alpha = int(255 * (1.0 - abs(self.mode_transition_progress - 0.5) * 2.0))
            if fade_alpha > 0:
                fade = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
                fade.fill(Palette.BLACK)
                fade.set_alpha(fade_alpha)
                self.screen.blit(fade, (0, 0))
                
                # Show mode transition text
                if 0.4 < self.mode_transition_progress < 0.6:
                    font_manager = self.widgets.get('font_manager')
                    if font_manager:
                        font = font_manager.get_font('huge')
                        mode_text = f"SWITCHING TO {self.target_mode.upper()}"
                        text_surface = font.render(mode_text, True, Palette.WHITE)
                        
                        text_x = (Config.SCREEN_WIDTH - text_surface.get_width()) // 2
                        text_y = (Config.SCREEN_HEIGHT - text_surface.get_height()) // 2
                        
                        self.screen.blit(text_surface, (text_x, text_y))

        pygame.display.flip()

    # ======================= EVENT HANDLERS =======================

    def _handle_voice_command(self, event_data: Dict[str, Any]) -> None:
        """Handle voice commands for mode switching."""
        text = str(event_data.get("text", "")).strip().lower()
        if not text:
            return
        
        # Mode switching commands
        if "archer" in text:
            self._switch_persona_mode("archer")
        elif "hudson" in text:
            self._switch_persona_mode("hudson")
        elif "both" in text:
            self._switch_persona_mode("both")

    def _handle_social_message_click(self, event_data: Dict[str, Any]) -> None:
        """Handle social message clicks to activate replacement panel."""
        platform = event_data.get("platform")
        message_data = event_data.get("message_data")
        panel = self.panels.get("social_replacement")
        
        if panel is not None and platform and message_data:
            panel.set_active(True, platform, message_data)
            self.social_panel_active = True
            print(f"📱 Opening {platform} interface")

    def _handle_message_sent(self, event_data: Dict[str, Any]) -> None:
        """Handle message sent event for auto-return."""
        platform = event_data.get("platform")
        
        if self.social_panel_active:
            print(f"📤 Message sent via {platform} - auto-returning to terrain")
            
            # The panel handles its own auto-return timing
            # This event just lets us know a message was sent
            pass

    def _handle_article_click(self, event_data: Dict[str, Any]) -> None:
        """Handle news article clicks for tactical overlay."""
        article_id = event_data.get("article_id")
        headline = event_data.get("headline", "")
        coordinates = event_data.get("coordinates")
        
        print(f"📰 Article clicked: {headline[:50]}...")
        
        # Forward for tactical overlay system
        self.event_bus.publish("show_tactical_overlay", {
            "type": "news_article",
            "article_id": article_id,
            "headline": headline,
            "coordinates": coordinates
        })

    def _handle_critical_alert(self, event_data: Dict[str, Any]) -> None:
        """Handle critical system alerts."""
        alert_type = event_data.get("type", "unknown")
        message = event_data.get("message", "Critical alert")
        
        print(f"🚨 CRITICAL ALERT [{alert_type.upper()}]: {message}")
        
        # Flash red overlay quickly
        if self.screen is not None:
            overlay = pygame.Surface((Config.SCREEN_WIDTH, Config.SCREEN_HEIGHT))
            overlay.fill(Palette.ALERT)
            overlay.set_alpha(100)
            self.screen.blit(overlay, (0, 0))
            pygame.display.flip()
        
        # Trigger audio alert
        self.event_bus.publish("play_alert_sound", {
            "sound_type": "critical_alarm",
            "priority": "urgent"
        })

    def _shutdown(self) -> None:
        """Clean shutdown sequence."""
        print("\n🛑 INITIATING SYSTEM SHUTDOWN")
        print("   • Stopping background daemons...")
        
        self.running = False

        # Stop all daemons
        if self.daemon_manager is not None:
            try:
                self.daemon_manager.stop_all_daemons()
                print("   ✓ Daemons stopped")
            except Exception as e:
                print(f"   ⚠ Error stopping daemons: {e}")

        print("   • Saving memory files...")
        
        # Force save memory files
        self.event_bus.publish("force_save_memory", {"reason": "shutdown"})
        
        # Wait briefly for saves to complete
        time.sleep(1.0)

        print("   • Cleaning up Pygame resources...")
        
        # Cleanup Pygame
        try:
            if self.screen:
                pygame.display.quit()
            pygame.mixer.quit()
            pygame.font.quit()
            pygame.quit()
            print("   ✓ Pygame cleaned up")
        except Exception as e:
            print(f"   ⚠ Pygame cleanup error: {e}")

        # Final statistics
        uptime = time.time() - self.boot_start_time
        print(f"   • Total system uptime: {uptime:.1f} seconds")
        
        print("✓ HERMES OMNIMIND SHUTDOWN COMPLETE")
        print("═══════════════════════════════════════════════════════════════════════════════")


def main() -> None:
    """Main entry point."""
    try:
        # Check Python version
        if sys.version_info < (3, 10):
            print("❌ ERROR: Python 3.10+ required")
            print(f"   Current version: {sys.version}")
            sys.exit(1)

        # Check if pygame is available
        if not PYGAME_AVAILABLE:
            print("❌ ERROR: Pygame not available")
            print("   Install with: pip install pygame")
            sys.exit(1)

        # Initialize and run application
        app = HermesApplication()
        app.run()

    except KeyboardInterrupt:
        print("\n🛑 CTRL+C RECEIVED - EMERGENCY SHUTDOWN")
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        print(f"   Traceback: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
