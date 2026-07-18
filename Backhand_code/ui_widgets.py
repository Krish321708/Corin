"""
HERMES Omnimind Absolute Edition
UI Widgets & Drawing Primitives
Abstract visual components, terminal interface, voice orb, and tactical drawing primitives.
"""

import math
import random
import time
from typing import Dict, List, Optional, Tuple, Any, Union
import threading

# Core system imports
from config import Config
from palette import Palette
from state import HermesState
from event_bus import EventBus

# Pygame imports
try:
    import pygame
    import pygame.font
    import pygame.gfxdraw
    PYGAME_AVAILABLE = True
except ImportError:
    print("Warning: Pygame not available for UI widgets")
    PYGAME_AVAILABLE = False

class FontManager:
    """Centralized font management for the tactical interface."""
    
    def __init__(self):
        if not PYGAME_AVAILABLE:
            return
            
        pygame.font.init()
        
        # Load tactical monospace fonts
        self.fonts = {}
        self._load_tactical_fonts()
    
    def _load_tactical_fonts(self):
        """Load tactical monospace font family."""
        # Try to load preferred tactical fonts
        font_candidates = [
            "Consolas",
            "Monaco", 
            "Menlo",
            "DejaVu Sans Mono",
            "Liberation Mono",
            "Courier New"
        ]
        
        # Font sizes for different UI elements
        font_sizes = {
            'micro': 10,      # Small status text
            'small': 12,      # Secondary information
            'normal': 14,     # Standard UI text
            'medium': 16,     # Headers and important text
            'large': 18,      # Major headers
            'huge': 24,       # Title text
            'terminal': 13    # Terminal text
        }
        
        for size_name, size in font_sizes.items():
            font_loaded = False
            
            # Try each font candidate
            for font_name in font_candidates:
                try:
                    font = pygame.font.SysFont(font_name, size)
                    if font:
                        self.fonts[size_name] = font
                        font_loaded = True
                        break
                except:
                    continue
            
            # Fallback to default font
            if not font_loaded:
                try:
                    self.fonts[size_name] = pygame.font.Font(None, size)
                except:
                    # Ultimate fallback
                    self.fonts[size_name] = pygame.font.Font(pygame.font.get_default_font(), size)
    
    def get_font(self, size: str = 'normal') -> pygame.font.Font:
        """Get font by size name."""
        return self.fonts.get(size, self.fonts.get('normal'))
    
    def measure_text(self, text: str, size: str = 'normal') -> Tuple[int, int]:
        """Measure text dimensions."""
        font = self.get_font(size)
        return font.size(text)
    
    def render_text(self, text: str, color: Tuple[int, int, int], 
                   size: str = 'normal', antialias: bool = True) -> pygame.Surface:
        """Render text to surface."""
        font = self.get_font(size)
        return font.render(text, antialias, color)

class TextRenderer:
    """Advanced text rendering with wrapping, alignment, and tactical styling."""
    
    def __init__(self, font_manager: FontManager):
        self.font_manager = font_manager
    
    def wrap_text(self, text: str, max_width: int, font_size: str = 'normal') -> List[str]:
        """Wrap text to fit within specified width."""
        font = self.font_manager.get_font(font_size)
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            text_width, _ = font.size(test_line)
            
            if text_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    # Word is too long, break it
                    lines.append(word)
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def render_multiline_text(self, surface: pygame.Surface, text: str, 
                            pos: Tuple[int, int], max_width: int,
                            color: Tuple[int, int, int], font_size: str = 'normal',
                            line_spacing: int = 2, alignment: str = 'left') -> int:
        """Render multi-line text with wrapping and return total height."""
        lines = self.wrap_text(text, max_width, font_size)
        font = self.font_manager.get_font(font_size)
        line_height = font.get_height() + line_spacing
        
        x, y = pos
        total_height = 0
        
        for i, line in enumerate(lines):
            if not line.strip():
                y += line_height
                total_height += line_height
                continue
                
            text_surface = font.render(line, True, color)
            text_width = text_surface.get_width()
            
            # Apply alignment
            render_x = x
            if alignment == 'center':
                render_x = x + (max_width - text_width) // 2
            elif alignment == 'right':
                render_x = x + max_width - text_width
            
            surface.blit(text_surface, (render_x, y))
            y += line_height
            total_height += line_height
        
        return total_height
    
    def render_tactical_text(self, surface: pygame.Surface, text: str,
                           pos: Tuple[int, int], color: Tuple[int, int, int],
                           font_size: str = 'normal', glow: bool = False) -> pygame.Rect:
        """Render text with tactical styling and optional glow effect."""
        font = self.font_manager.get_font(font_size)
        
        if glow:
            # Render glow effect
            glow_color = tuple(min(255, c + 30) for c in color)
            for offset_x in [-1, 0, 1]:
                for offset_y in [-1, 0, 1]:
                    if offset_x == 0 and offset_y == 0:
                        continue
                    glow_surface = font.render(text, True, glow_color)
                    glow_surface.set_alpha(50)
                    surface.blit(glow_surface, (pos[0] + offset_x, pos[1] + offset_y))
        
        # Render main text
        text_surface = font.render(text, True, color)
        surface.blit(text_surface, pos)
        
        return pygame.Rect(pos[0], pos[1], text_surface.get_width(), text_surface.get_height())

class GeometricPrimitives:
    """Tactical geometric drawing primitives."""
    
    @staticmethod
    def draw_tactical_line(surface: pygame.Surface, start: Tuple[int, int], 
                          end: Tuple[int, int], color: Tuple[int, int, int], 
                          width: int = 1, dash_pattern: Optional[List[int]] = None):
        """Draw line with optional tactical dashing."""
        if dash_pattern is None:
            pygame.draw.line(surface, color, start, end, width)
        else:
            # Draw dashed line
            total_length = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
            if total_length == 0:
                return
                
            unit_x = (end[0] - start[0]) / total_length
            unit_y = (end[1] - start[1]) / total_length
            
            current_pos = 0
            dash_index = 0
            drawing = True
            
            while current_pos < total_length:
                dash_length = min(dash_pattern[dash_index % len(dash_pattern)], 
                                total_length - current_pos)
                
                if drawing:
                    seg_start = (
                        int(start[0] + unit_x * current_pos),
                        int(start[1] + unit_y * current_pos)
                    )
                    seg_end = (
                        int(start[0] + unit_x * (current_pos + dash_length)),
                        int(start[1] + unit_y * (current_pos + dash_length))
                    )
                    pygame.draw.line(surface, color, seg_start, seg_end, width)
                
                current_pos += dash_length
                dash_index += 1
                drawing = not drawing
    
    @staticmethod
    def draw_corner_brackets(surface: pygame.Surface, rect: pygame.Rect,
                           color: Tuple[int, int, int], bracket_length: int = 20,
                           thickness: int = 2):
        """Draw tactical corner brackets around a rectangle."""
        x, y, w, h = rect.x, rect.y, rect.width, rect.height
        
        # Top-left bracket
        pygame.draw.line(surface, color, (x, y), (x + bracket_length, y), thickness)
        pygame.draw.line(surface, color, (x, y), (x, y + bracket_length), thickness)
        
        # Top-right bracket
        pygame.draw.line(surface, color, (x + w - bracket_length, y), (x + w, y), thickness)
        pygame.draw.line(surface, color, (x + w, y), (x + w, y + bracket_length), thickness)
        
        # Bottom-left bracket
        pygame.draw.line(surface, color, (x, y + h - bracket_length), (x, y + h), thickness)
        pygame.draw.line(surface, color, (x, y + h), (x + bracket_length, y + h), thickness)
        
        # Bottom-right bracket
        pygame.draw.line(surface, color, (x + w, y + h - bracket_length), (x + w, y + h), thickness)
        pygame.draw.line(surface, color, (x + w - bracket_length, y + h), (x + w, y + h), thickness)
    
    @staticmethod
    def draw_radar_sweep(surface: pygame.Surface, center: Tuple[int, int],
                        radius: int, angle: float, color: Tuple[int, int, int],
                        sweep_width: float = 0.5):
        """Draw rotating radar sweep effect."""
        # Calculate sweep arc points
        start_angle = angle - sweep_width
        end_angle = angle + sweep_width
        
        points = [center]
        for a in [start_angle, end_angle]:
            x = center[0] + int(radius * math.cos(a))
            y = center[1] + int(radius * math.sin(a))
            points.append((x, y))
        
        # Draw filled sweep with alpha gradient
        temp_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.polygon(temp_surface, (*color, 100), 
                          [(p[0] - center[0] + radius, p[1] - center[1] + radius) for p in points])
        
        surface.blit(temp_surface, (center[0] - radius, center[1] - radius))
    
    @staticmethod
    def draw_hexagon(surface: pygame.Surface, center: Tuple[int, int],
                    radius: int, color: Tuple[int, int, int], width: int = 1):
        """Draw tactical hexagon."""
        points = []
        for i in range(6):
            angle = math.pi / 3 * i
            x = center[0] + radius * math.cos(angle)
            y = center[1] + radius * math.sin(angle)
            points.append((int(x), int(y)))
        
        pygame.draw.polygon(surface, color, points, width)
    
    @staticmethod
    def draw_crosshair(surface: pygame.Surface, center: Tuple[int, int],
                      size: int, color: Tuple[int, int, int], thickness: int = 1):
        """Draw tactical crosshair."""
        x, y = center
        # Horizontal line
        pygame.draw.line(surface, color, (x - size, y), (x + size, y), thickness)
        # Vertical line  
        pygame.draw.line(surface, color, (x, y - size), (x, y + size), thickness)

class ParticleSystem:
    """Advanced particle system for voice orb and effects."""
    
    def __init__(self):
        self.particles = []
        self.time_offset = random.random() * 1000
    
    def update(self, delta_time: float, mode: str = "archer"):
        """Update particle system based on current mode."""
        current_time = time.time() + self.time_offset
        
        # Mode-specific particle behaviors
        if mode == "archer":
            self._update_archer_mode(delta_time, current_time)
        elif mode == "hudson":
            self._update_hudson_mode(delta_time, current_time)
        elif mode == "both":
            self._update_both_mode(delta_time, current_time)
    
    def _update_archer_mode(self, delta_time: float, current_time: float):
        """Smooth, organic particle movement for Archer."""
        target_count = 24
        self._adjust_particle_count(target_count)
        
        for i, particle in enumerate(self.particles):
            # Smooth orbital motion
            base_angle = (current_time * 0.5) + (i * 2 * math.pi / len(self.particles))
            radius_variation = 1.0 + 0.15 * math.sin(current_time * 0.3 + i)
            
            particle['angle'] = base_angle
            particle['radius_mult'] = radius_variation
            particle['size'] = 2.5 + 0.5 * math.sin(current_time * 0.4 + i)
            particle['alpha'] = 180 + 50 * math.sin(current_time * 0.6 + i * 0.5)
            particle['color'] = Palette.CYAN  # Blue for Archer
    
    def _update_hudson_mode(self, delta_time: float, current_time: float):
        """Mechanical, rigid particle movement for Hudson."""
        target_count = 18
        self._adjust_particle_count(target_count)
        
        for i, particle in enumerate(self.particles):
            # Mechanical stepped rotation
            base_angle = int(current_time * 1.2) + (i * 2 * math.pi / len(self.particles))
            radius_variation = 1.0 + 0.05 * (1 if int(current_time * 2) % 2 == 0 else -1)
            
            particle['angle'] = base_angle
            particle['radius_mult'] = radius_variation
            particle['size'] = 2.0 + 0.3 * (i % 2)  # Alternating sizes
            particle['alpha'] = 160 + 60 * (1 if int(current_time * 3 + i) % 2 == 0 else 0)
            particle['color'] = Palette.AMBER  # Green for Hudson
    
    def _update_both_mode(self, delta_time: float, current_time: float):
        """Chaotic mixed particle movement for Both mode."""
        target_count = 36
        self._adjust_particle_count(target_count)
        
        for i, particle in enumerate(self.particles):
            # Mixed behaviors - some smooth, some mechanical
            if i % 2 == 0:
                # Archer-like particles
                base_angle = (current_time * 0.7) + (i * 2 * math.pi / len(self.particles))
                radius_variation = 1.0 + 0.2 * math.sin(current_time * 0.5 + i)
                particle['color'] = Palette.CYAN
            else:
                # Hudson-like particles
                base_angle = int(current_time * 0.9) + (i * 2 * math.pi / len(self.particles))
                radius_variation = 1.0 + 0.1 * (1 if int(current_time * 1.5) % 2 == 0 else -1)
                particle['color'] = Palette.AMBER
            
            particle['angle'] = base_angle
            particle['radius_mult'] = radius_variation
            particle['size'] = 1.8 + 0.8 * math.sin(current_time * 0.8 + i * 0.3)
            particle['alpha'] = 140 + 80 * math.sin(current_time * 0.7 + i)
    
    def _adjust_particle_count(self, target_count: int):
        """Adjust particle count to match target."""
        while len(self.particles) < target_count:
            self.particles.append({
                'angle': 0,
                'radius_mult': 1.0,
                'size': 2.0,
                'alpha': 255,
                'color': Palette.WHITE
            })
        
        while len(self.particles) > target_count:
            self.particles.pop()
    
    def render(self, surface: pygame.Surface, center: Tuple[int, int], base_radius: int):
        """Render all particles in the system."""
        for particle in self.particles:
            # Calculate particle position
            angle = particle['angle']
            radius = base_radius * particle['radius_mult']
            
            x = center[0] + int(radius * math.cos(angle))
            y = center[1] + int(radius * math.sin(angle))
            
            # Create particle surface with alpha
            particle_size = int(particle['size'])
            if particle_size < 1:
                continue
                
            particle_surface = pygame.Surface((particle_size * 2, particle_size * 2), pygame.SRCALPHA)
            
            # Draw particle with glow effect
            color = (*particle['color'], int(particle['alpha']))
            pygame.draw.circle(particle_surface, color, 
                             (particle_size, particle_size), particle_size)
            
            # Add glow
            glow_color = (*particle['color'], int(particle['alpha'] * 0.3))
            pygame.draw.circle(particle_surface, glow_color,
                             (particle_size, particle_size), particle_size + 2)
            
            surface.blit(particle_surface, (x - particle_size, y - particle_size))

class VoiceOrb:
    """Advanced voice interface orb with particle effects and mode switching."""
    
    def __init__(self, event_bus: EventBus, state: HermesState):
        self.event_bus = event_bus
        self.state = state
        
        # Orb properties
        self.position = (100, 100)  # Will be set by UI manager
        self.base_radius = 35
        self.current_mode = "archer"
        
        # Visual state
        self.is_listening = False
        self.is_speaking = False
        self.voice_activity = 0.0
        
        # Particle system
        self.particle_system = ParticleSystem()
        
        # Animation state
        self.pulse_time = 0.0
        self.rotation_angle = 0.0
        
        # Event subscriptions
        self.event_bus.subscribe("voice_listening", self._on_voice_listening)
        self.event_bus.subscribe("voice_speaking", self._on_voice_speaking)
        self.event_bus.subscribe("audio_data_updated", self._on_audio_data)
        self.event_bus.subscribe("persona_mode_changed", self._on_mode_changed)
    
    def set_position(self, position: Tuple[int, int]):
        """Set orb position on screen."""
        self.position = position
    
    def update(self, delta_time: float):
        """Update orb animations and particle system."""
        self.pulse_time += delta_time
        self.rotation_angle += delta_time * 0.5
        
        # Update particle system
        self.particle_system.update(delta_time, self.current_mode)
        
        # Update voice activity level
        audio_volume = self.state.get("audio_volume", 0.0)
        target_activity = min(1.0, audio_volume * 2.0) if self.is_listening or self.is_speaking else 0.0
        
        # Smooth activity level changes
        activity_speed = 10.0 if target_activity > self.voice_activity else 5.0
        self.voice_activity += (target_activity - self.voice_activity) * delta_time * activity_speed
        self.voice_activity = max(0.0, min(1.0, self.voice_activity))
    
    def render(self, surface: pygame.Surface):
        """Render the complete voice orb."""
        # Calculate dynamic radius based on voice activity
        activity_radius_bonus = self.voice_activity * 8
        current_radius = self.base_radius + activity_radius_bonus
        
        # Render outer glow ring
        self._render_glow_ring(surface, current_radius)
        
        # Render particle system
        self.particle_system.render(surface, self.position, current_radius * 0.8)
        
        # Render center core
        self._render_center_core(surface, current_radius)
        
        # Render status indicators
        self._render_status_indicators(surface)
    
    def _render_glow_ring(self, surface: pygame.Surface, radius: float):
        """Render outer glow ring."""
        # Get mode-specific color
        if self.current_mode == "archer":
            ring_color = Palette.CYAN
        elif self.current_mode == "hudson":
            ring_color = Palette.AMBER
        else:  # both
            # Alternating colors
            ring_color = Palette.CYAN if int(self.pulse_time * 2) % 2 == 0 else Palette.AMBER
        
        # Pulsing alpha based on voice activity and time
        base_alpha = 40 + 20 * math.sin(self.pulse_time * 3)
        activity_alpha = self.voice_activity * 60
        total_alpha = int(base_alpha + activity_alpha)
        
        # Create ring surface
        ring_surface = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        ring_center = (radius * 2, radius * 2)
        
        # Draw multiple concentric rings for glow effect
        for i in range(3):
            ring_radius = radius + i * 3
            alpha = total_alpha // (i + 1)
            color = (*ring_color, alpha)
            
            pygame.draw.circle(ring_surface, color, ring_center, int(ring_radius), 2)
        
        surface.blit(ring_surface, (self.position[0] - radius * 2, self.position[1] - radius * 2))
    
    def _render_center_core(self, surface: pygame.Surface, radius: float):
        """Render central orb core."""
        # Core size varies with voice activity
        core_radius = int(radius * 0.3 + self.voice_activity * 5)
        
        # Core color based on mode
        if self.current_mode == "archer":
            core_color = Palette.CYAN
        elif self.current_mode == "hudson":
            core_color = Palette.AMBER
        else:  # both
            # Gradient between colors
            mix_factor = (math.sin(self.pulse_time * 4) + 1) / 2
            core_color = Palette.mix(Palette.CYAN, Palette.AMBER, mix_factor)
        
        # Draw core with intensity based on activity
        intensity = int(120 + self.voice_activity * 100)
        core_color_intense = tuple(min(255, int(c * intensity / 255)) for c in core_color)
        
        pygame.draw.circle(surface, core_color_intense, self.position, core_radius)
        
        # Add inner highlight
        highlight_radius = max(1, core_radius - 2)
        highlight_color = tuple(min(255, c + 40) for c in core_color_intense)
        pygame.draw.circle(surface, highlight_color, self.position, highlight_radius)
    
    def _render_status_indicators(self, surface: pygame.Surface):
        """Render listening/speaking status indicators."""
        indicator_y = self.position[1] + self.base_radius + 15
        
        if self.is_listening:
            # Listening indicator - pulsing microphone symbol
            mic_alpha = int(180 + 75 * math.sin(self.pulse_time * 8))
            mic_color = (*Palette.WHITE, mic_alpha)
            
            # Simple microphone representation
            mic_rect = pygame.Rect(self.position[0] - 3, indicator_y, 6, 8)
            pygame.draw.ellipse(surface, mic_color, mic_rect)
            pygame.draw.line(surface, mic_color, 
                           (self.position[0], indicator_y + 8),
                           (self.position[0], indicator_y + 12), 2)
        
        elif self.is_speaking:
            # Speaking indicator - sound waves
            wave_alpha = int(150 + 100 * math.sin(self.pulse_time * 6))
            wave_color = (*Palette.WHITE, wave_alpha)
            
            for i in range(3):
                wave_radius = 5 + i * 3 + int(self.voice_activity * 4)
                pygame.draw.circle(surface, wave_color,
                                 (self.position[0], indicator_y + 5), wave_radius, 1)
    
    def _on_voice_listening(self, event_data):
        """Handle voice listening state change."""
        self.is_listening = event_data.get("listening", False)
    
    def _on_voice_speaking(self, event_data):
        """Handle voice speaking state change.""" 
        self.is_speaking = event_data.get("speaking", False)
    
    def _on_audio_data(self, event_data):
        """Handle audio data updates."""
        # Voice activity is handled in update() method
        pass
    
    def _on_mode_changed(self, event_data):
        """Handle persona mode changes."""
        new_mode = event_data.get("mode", "archer")
        if new_mode != self.current_mode:
            self.current_mode = new_mode
            # Trigger mode transition animation
            self.pulse_time = 0.0

class TerminalWidget:
    """Expandable terminal interface widget."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        self.event_bus = event_bus
        self.state = state
        self.font_manager = font_manager
        
        # Terminal state
        self.expanded = False
        self.expansion_progress = 0.0  # 0.0 = collapsed, 1.0 = fully expanded
        self.target_progress = 0.0
        
        # Geometry
        self.collapsed_height = 20
        self.expanded_height = Config.SCREEN_HEIGHT - Config.BOTTOM_STATUS_Y  # Cover bottom status row
        self.full_width = Config.SCREEN_WIDTH
        self.arrow_rect = pygame.Rect(Config.SCREEN_WIDTH // 2 - 10, 0, 20, self.collapsed_height)
        
        # Text input
        self.input_text = ""
        self.cursor_position = 0
        self.cursor_blink_time = 0.0
        self.text_lines = ["HERMES Terminal Interface Initialized", "Ready for input..."]
        self.max_lines = 25
        
        # Scrolling
        self.scroll_offset = 0
        
        # Event subscriptions
        self.event_bus.subscribe("terminal_toggle", self._on_toggle)
        self.event_bus.subscribe("terminal_input", self._on_input)
    
    def set_expanded(self, expanded: bool):
        """Set terminal expansion state."""
        self.expanded = expanded
        self.target_progress = 1.0 if expanded else 0.0
    
    def toggle(self):
        """Toggle terminal expansion state."""
        self.set_expanded(not self.expanded)
    
    def update(self, delta_time: float):
        """Update terminal animation and cursor."""
        # Smooth expansion animation
        if self.expansion_progress != self.target_progress:
            animation_speed = 8.0  # Animation speed
            progress_delta = (self.target_progress - self.expansion_progress) * delta_time * animation_speed
            self.expansion_progress += progress_delta
            
            # Clamp to target when very close
            if abs(self.expansion_progress - self.target_progress) < 0.01:
                self.expansion_progress = self.target_progress
        
        # Update cursor blink
        self.cursor_blink_time += delta_time
    
    def handle_keypress(self, event):
        """Handle keyboard input for terminal."""
        if not self.expanded:
            return
            
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                # Submit current input
                self._submit_input()
            elif event.key == pygame.K_BACKSPACE:
                # Remove character
                if self.cursor_position > 0:
                    self.input_text = (self.input_text[:self.cursor_position-1] + 
                                     self.input_text[self.cursor_position:])
                    self.cursor_position -= 1
            elif event.key == pygame.K_LEFT:
                # Move cursor left
                self.cursor_position = max(0, self.cursor_position - 1)
            elif event.key == pygame.K_RIGHT:
                # Move cursor right
                self.cursor_position = min(len(self.input_text), self.cursor_position + 1)
            elif event.key == pygame.K_HOME:
                # Move cursor to start
                self.cursor_position = 0
            elif event.key == pygame.K_END:
                # Move cursor to end
                self.cursor_position = len(self.input_text)
            elif event.key == pygame.K_UP:
                # Scroll up
                self.scroll_offset = max(0, self.scroll_offset - 1)
            elif event.key == pygame.K_DOWN:
                # Scroll down
                max_scroll = max(0, len(self.text_lines) - self.max_lines)
                self.scroll_offset = min(max_scroll, self.scroll_offset + 1)
            elif event.unicode and event.unicode.isprintable():
                # Add character
                self.input_text = (self.input_text[:self.cursor_position] + 
                                 event.unicode + 
                                 self.input_text[self.cursor_position:])
                self.cursor_position += 1
    
    def handle_mouse_click(self, pos: Tuple[int, int]) -> bool:
        """Handle mouse clicks on terminal. Returns True if click was handled."""
        if not self.expanded and self.arrow_rect.collidepoint(pos):
            # Click on expansion arrow
            self.toggle()
            return True
        
        return False
    
    def _submit_input(self):
        """Submit current input line."""
        if self.input_text.strip():
            # Add input to text history
            self.text_lines.append(f"> {self.input_text}")
            
            # Send input to persona engine
            self.event_bus.publish("terminal_input_submitted", {
                "text": self.input_text,
                "timestamp": time.time()
            })
            
            # Clear input
            self.input_text = ""
            self.cursor_position = 0
            
            # Auto-scroll to bottom
            self.scroll_offset = max(0, len(self.text_lines) - self.max_lines)
    
    def add_response(self, text: str):
        """Add AI response to terminal."""
        # Split long responses into multiple lines
        max_width = 100  # Characters per line
        lines = []
        
        for paragraph in text.split('\n'):
            if len(paragraph) <= max_width:
                lines.append(paragraph)
            else:
                # Wrap long lines
                words = paragraph.split(' ')
                current_line = ""
                
                for word in words:
                    if len(current_line + ' ' + word) <= max_width:
                        current_line = (current_line + ' ' + word).strip()
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                
                if current_line:
                    lines.append(current_line)
        
        # Add lines to terminal
        for line in lines:
            self.text_lines.append(line)
        
        # Trim history if too long
        while len(self.text_lines) > 200:  # Keep last 200 lines
            self.text_lines.pop(0)
        
        # Auto-scroll to bottom
        self.scroll_offset = max(0, len(self.text_lines) - self.max_lines)
    
    def render(self, surface: pygame.Surface):
        """Render terminal interface."""
        if self.expansion_progress == 0.0:
            # Render only the expansion arrow
            self._render_expansion_arrow(surface)
        else:
            # Render terminal content
            self._render_terminal_content(surface)
    
    def _render_expansion_arrow(self, surface: pygame.Surface):
        """Render the small expansion arrow at top of screen."""
        # Arrow background
        pygame.draw.rect(surface, Palette.GRID, self.arrow_rect)
        pygame.draw.rect(surface, Palette.WHITE, self.arrow_rect, 1)
        
        # Down arrow
        center_x = self.arrow_rect.centerx
        center_y = self.arrow_rect.centery
        
        arrow_points = [
            (center_x - 5, center_y - 2),
            (center_x + 5, center_y - 2),
            (center_x, center_y + 3)
        ]
        
        pygame.draw.polygon(surface, Palette.WHITE, arrow_points)
    
    def _render_terminal_content(self, surface: pygame.Surface):
        """Render expanded terminal content."""
        # Calculate current height based on expansion progress
        current_height = int(self.collapsed_height + 
                           (self.expanded_height - self.collapsed_height) * self.expansion_progress)
        
        # Terminal background
        terminal_rect = pygame.Rect(0, Config.SCREEN_HEIGHT - current_height, 
                                  self.full_width, current_height)
        
        # Background with transparency
        terminal_surface = pygame.Surface((self.full_width, current_height), pygame.SRCALPHA)
        terminal_surface.fill((*Palette.BLACK, 230))  # Semi-transparent black
        
        # Border
        pygame.draw.rect(terminal_surface, Palette.GRID, 
                        (0, 0, self.full_width, current_height), 2)
        
        # Header bar
        header_height = 25
        header_rect = pygame.Rect(0, 0, self.full_width, header_height)
        pygame.draw.rect(terminal_surface, Palette.GRID, header_rect)
        
        # Header text
        header_font = self.font_manager.get_font('small')
        header_text = header_font.render("HERMES TERMINAL", True, Palette.WHITE)
        terminal_surface.blit(header_text, (10, 5))
        
        # Close button
        close_rect = pygame.Rect(self.full_width - 30, 5, 20, 15)
        pygame.draw.rect(terminal_surface, Palette.WHITE, close_rect, 1)
        close_text = header_font.render("×", True, Palette.WHITE)
        terminal_surface.blit(close_text, (self.full_width - 25, 3))
        
        if self.expansion_progress > 0.5:  # Only render text when mostly expanded
            # Render text content
            self._render_text_content(terminal_surface, current_height, header_height)
        
        surface.blit(terminal_surface, (0, Config.SCREEN_HEIGHT - current_height))
    
    def _render_text_content(self, terminal_surface: pygame.Surface, 
                           terminal_height: int, header_height: int):
        """Render terminal text content and input."""
        font = self.font_manager.get_font('terminal')
        line_height = font.get_height() + 2
        
        # Content area
        content_y_start = header_height + 5
        content_height = terminal_height - header_height - 40  # Leave space for input
        visible_lines = content_height // line_height
        
        # Render text lines
        y = content_y_start
        start_line = max(0, len(self.text_lines) - visible_lines + self.scroll_offset)
        
        for i in range(min(visible_lines, len(self.text_lines) - start_line)):
            line_index = start_line + i
            line_text = self.text_lines[line_index]
            
            # Color coding for different line types
            if line_text.startswith("> "):
                text_color = Palette.CYAN  # User input
            elif "error" in line_text.lower() or "warning" in line_text.lower():
                text_color = Palette.ALERT  # Errors/warnings
            else:
                text_color = Palette.WHITE  # Normal text
            
            text_surface = font.render(line_text, True, text_color)
            terminal_surface.blit(text_surface, (10, y))
            y += line_height
        
        # Input area
        input_y = terminal_height - 35
        pygame.draw.line(terminal_surface, Palette.GRID, 
                        (0, input_y - 5), (self.full_width, input_y - 5), 1)
        
        # Input prompt
        prompt_text = font.render("> ", True, Palette.AMBER)
        terminal_surface.blit(prompt_text, (10, input_y))
        
        # Input text
        input_display = self.input_text
        input_surface = font.render(input_display, True, Palette.WHITE)
        terminal_surface.blit(input_surface, (30, input_y))
        
        # Cursor
        if self.expansion_progress >= 1.0:  # Only show cursor when fully expanded
            show_cursor = int(self.cursor_blink_time * 2) % 2 == 0
            if show_cursor:
                cursor_x = 30 + font.size(input_display[:self.cursor_position])[0]
                pygame.draw.line(terminal_surface, Palette.WHITE,
                               (cursor_x, input_y), (cursor_x, input_y + line_height), 1)
    
    def _on_toggle(self, event_data):
        """Handle terminal toggle event."""
        self.toggle()
    
    def _on_input(self, event_data):
        """Handle input event."""
        # This could be used for programmatic text input
        pass

class BasePanel:
    """Base class for UI panels with common functionality."""
    
    def __init__(self, rect: pygame.Rect, event_bus: EventBus, state: HermesState,
                 font_manager: FontManager):
        self.rect = rect
        self.event_bus = event_bus
        self.state = state
        self.font_manager = font_manager
        self.text_renderer = TextRenderer(font_manager)
        
        # Panel state
        self.visible = True
        self.enabled = True
        self.background_color = Palette.BLACK
        self.border_color = Palette.GRID
        self.border_width = 1
        
        # Surface for off-screen rendering
        self.surface = pygame.Surface((rect.width, rect.height))
    
    def update(self, delta_time: float):
        """Update panel state. Override in subclasses."""
        pass
    
    def render(self, target_surface: pygame.Surface):
        """Render panel to target surface."""
        if not self.visible:
            return
            
        # Clear panel surface
        self.surface.fill(self.background_color)
        
        # Render panel content
        self._render_content()
        
        # Draw border if specified
        if self.border_width > 0:
            pygame.draw.rect(self.surface, self.border_color, 
                           self.surface.get_rect(), self.border_width)
        
        # Blit to target
        target_surface.blit(self.surface, self.rect)
    
    def _render_content(self):
        """Render panel content. Override in subclasses."""
        # Default: render panel name
        text = self.text_renderer.render_tactical_text(
            self.surface, "Base Panel", (10, 10), Palette.WHITE
        )
    
    def handle_mouse_click(self, pos: Tuple[int, int]) -> bool:
        """Handle mouse click. Returns True if click was handled."""
        if not self.enabled or not self.visible:
            return False
            
        # Convert to local coordinates
        local_pos = (pos[0] - self.rect.x, pos[1] - self.rect.y)
        
        # Check if click is within panel
        if 0 <= local_pos[0] <= self.rect.width and 0 <= local_pos[1] <= self.rect.height:
            return self._handle_local_click(local_pos)
        
        return False
    
    def _handle_local_click(self, local_pos: Tuple[int, int]) -> bool:
        """Handle click in local coordinates. Override in subclasses."""
        return False
    
    def set_visible(self, visible: bool):
        """Set panel visibility."""
        self.visible = visible
    
    def set_enabled(self, enabled: bool):
        """Set panel enabled state."""
        self.enabled = enabled

# Widget initialization function
def initialize_widgets(event_bus: EventBus, state: HermesState) -> Dict[str, Any]:
    """Initialize all UI widgets and return widget manager."""
    if not PYGAME_AVAILABLE:
        return {}
    
    # Initialize core components
    font_manager = FontManager()
    text_renderer = TextRenderer(font_manager)
    
    # Initialize widgets
    voice_orb = VoiceOrb(event_bus, state)
    terminal = TerminalWidget(event_bus, state, font_manager)
    
    # Set initial orb position (will be updated by UI panels)
    voice_orb.set_position((Config.SCREEN_WIDTH - 80, Config.SCREEN_HEIGHT - 80))
    
    return {
        'font_manager': font_manager,
        'text_renderer': text_renderer,
        'voice_orb': voice_orb,
        'terminal': terminal,
        'geometric_primitives': GeometricPrimitives(),
        'particle_system': ParticleSystem()
    }

# Export all widget classes
__all__ = [
    'FontManager', 'TextRenderer', 'GeometricPrimitives', 'ParticleSystem',
    'VoiceOrb', 'TerminalWidget', 'BasePanel', 'initialize_widgets'
]