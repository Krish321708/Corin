"""
HERMES Omnimind Absolute Edition
UI Panels & Viewport Renderers
Complete rendering system for all interface panels, terrain, globe, status displays, 
brainstorming mode, and tactical overlays.
"""

import math
import random
import time
from collections import deque
from typing import Dict, List, Optional, Tuple, Any, Union
import json

# Core system imports
from config import Config
from palette import Palette
from state import HermesState
from event_bus import EventBus
from math_engine import Vector3, Matrix4x4, PerlinNoise3D, catmull_rom
from ui_widgets import (FontManager, TextRenderer, GeometricPrimitives, 
                       VoiceOrb, TerminalWidget, BasePanel)

# Pygame imports
try:
    import pygame
    import pygame.gfxdraw
    import numpy as np
    PYGAME_AVAILABLE = True
except ImportError:
    print("Warning: Pygame not available for UI panels")
    PYGAME_AVAILABLE = False

class HeaderBarRenderer(BasePanel):
    """System header bar with title, status overlays, and uptime display."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        rect = pygame.Rect(0, 0, Config.SCREEN_WIDTH, Config.HEADER_HEIGHT)
        super().__init__(rect, event_bus, state, font_manager)
        
        self.border_width = 0  # No border for header
        
        # Animation state
        self.glow_pulse = 0.0
        
    def update(self, delta_time: float):
        """Update header animations."""
        self.glow_pulse += delta_time * 2.0
    
    def _render_content(self):
        """Render header bar content."""
        # Clear with black background
        self.surface.fill(Palette.BLACK)
        
        # Main title (centered)
        title_text = "HERMES - Omnimind Absolute Edition :: [cite: Jarvis-Integration:StarkCore]"
        title_font = self.font_manager.get_font('medium')
        title_surface = title_font.render(title_text, True, Palette.WHITE)
        
        # Center the title
        title_x = (self.rect.width - title_surface.get_width()) // 2
        title_y = (self.rect.height - title_surface.get_height()) // 2
        
        # Add subtle glow effect to title
        glow_alpha = int(30 + 15 * math.sin(self.glow_pulse))
        for offset in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            glow_surface = title_font.render(title_text, True, Palette.CYAN)
            glow_surface.set_alpha(glow_alpha)
            self.surface.blit(glow_surface, (title_x + offset[0], title_y + offset[1]))
        
        self.surface.blit(title_surface, (title_x, title_y))
        
        # Left-aligned status overlay
        self._render_left_status()
        
        # Right-aligned status overlay
        self._render_right_status()
        
        # Bottom border
        pygame.draw.line(self.surface, Palette.GRID, 
                        (0, self.rect.height - 1), (self.rect.width, self.rect.height - 1), 1)
    
    def _render_left_status(self):
        """Render left-aligned diagnostic status block."""
        status_lines = [
            "ARC REACTOR: OPTIMAL",
            "MARK SUIT INTEGRITY: 98.7%",
            "DIAGNOSTICS STREAM: ACTIVE",
            "NEURAL LINK: SYNCHRONIZED"
        ]
        
        font = self.font_manager.get_font('small')
        y_offset = 2
        
        for i, line in enumerate(status_lines):
            # Color coding for different status types
            if "OPTIMAL" in line or "ACTIVE" in line or "SYNCHRONIZED" in line:
                color = Palette.CYAN
            elif "98.7%" in line:
                color = Palette.AMBER
            else:
                color = Palette.LIGHT_GRAY
            
            text_surface = font.render(line, True, color)
            self.surface.blit(text_surface, (10, y_offset))
            y_offset += font.get_height()
    
    def _render_right_status(self):
        """Render right-aligned system metrics."""
        # Get uptime
        boot_time = self.state.get("boot_time", time.time())
        uptime_seconds = int(time.time() - boot_time)
        uptime_hours = uptime_seconds // 3600
        uptime_minutes = (uptime_seconds % 3600) // 60
        uptime_secs = uptime_seconds % 60
        
        # Get system metrics
        cpu_temp = self.state.get("cpu_temp", 0.0)
        active_threads = self.state.get("active_threads", 0)
        
        status_lines = [
            f"UP: {uptime_hours:02d}:{uptime_minutes:02d}:{uptime_secs:02d}",
            f"CPU TEMP: {cpu_temp:.1f}°C",
            f"THREADS: {active_threads}",
            f"STATUS: NOMINAL"
        ]
        
        font = self.font_manager.get_font('small')
        
        for i, line in enumerate(status_lines):
            # Color coding based on values
            if "TEMP:" in line:
                if cpu_temp > Config.TEMPERATURE_WARNING:
                    color = Palette.ALERT
                elif cpu_temp > Config.TEMPERATURE_CRITICAL * 0.8:
                    color = Palette.AMBER
                else:
                    color = Palette.CYAN
            else:
                color = Palette.LIGHT_GRAY
            
            text_surface = font.render(line, True, color)
            text_x = self.rect.width - text_surface.get_width() - 10
            text_y = 2 + i * font.get_height()
            self.surface.blit(text_surface, (text_x, text_y))

class TerrainRenderer(BasePanel):
    """3D topological terrain with audio FFT modulation and telemetry overlays."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        rect = pygame.Rect(0, Config.HEADER_HEIGHT, 
                          Config.LEFT_VIEWPORT_WIDTH, 
                          Config.LEFT_VIEWPORT_HEIGHT)
        super().__init__(rect, event_bus, state, font_manager)
        
        # Terrain generation
        self.perlin = PerlinNoise3D(seed=42)
        self.grid_density = Config.TERRAIN_GRID_DENSITY  # 40x40 grid
        self.terrain_points = []
        
        # Camera parameters
        self.camera_pitch = Config.TERRAIN_CAMERA_PITCH  # -0.3 radians
        self.camera_distance = Config.TERRAIN_CAMERA_DISTANCE  # 350 units
        self.focal_length = Config.TERRAIN_FOCAL_LENGTH  # 400
        
        # Animation state
        self.time_offset = 0.0
        
        # Telemetry overlays
        self.telemetry_data = []
        self.preview_graph_data = deque(maxlen=60)  # 1 second at 60fps
        
        # Initialize terrain grid
        self._generate_terrain_grid()
        
        # Subscribe to audio updates
        self.event_bus.subscribe("audio_data_updated", self._on_audio_data)
    
    def _generate_terrain_grid(self):
        """Generate base terrain grid points."""
        self.terrain_points = []
        
        for x_index in range(self.grid_density):
            for z_index in range(self.grid_density):
                # Normalize coordinates to [-1, 1] range
                x = (x_index / (self.grid_density - 1)) * 2 - 1
                z = (z_index / (self.grid_density - 1)) * 2 - 1
                
                # Store base coordinates
                self.terrain_points.append({
                    'x': x,
                    'z': z,
                    'x_index': x_index,
                    'z_index': z_index,
                    'base_height': 0.0,
                    'fft_height': 0.0,
                    'total_height': 0.0
                })
    
    def update(self, delta_time: float):
        """Update terrain animations and FFT modulation."""
        self.time_offset += delta_time
        
        # Update base terrain heights using Fractal Brownian Motion
        self._update_terrain_heights()
        
        # Apply FFT modulation
        self._apply_fft_modulation()
        
        # Update telemetry data
        self._update_telemetry()
    
    def _update_terrain_heights(self):
        """Update terrain heights using Fractal Brownian Motion."""
        for point in self.terrain_points:
            x, z = point['x'], point['z']
            
            # Fractal Brownian Motion with 5 octaves
            height = 0.0
            amplitude = 1.0
            frequency = 1.0
            persistence = Config.TERRAIN_PERSISTENCE  # 0.5
            lacunarity = Config.TERRAIN_LACUNARITY  # 2.0
            
            for octave in range(5):
                # Add time-based animation
                noise_x = x * frequency + self.time_offset * 0.1
                noise_z = z * frequency + self.time_offset * 0.08
                noise_t = self.time_offset * 0.05
                
                octave_noise = self.perlin.noise(noise_x, noise_z, noise_t)
                height += octave_noise * amplitude
                
                frequency *= lacunarity
                amplitude *= persistence
            
            point['base_height'] = height * 0.3  # Scale down the height
    
    def _apply_fft_modulation(self):
        """Apply FFT audio data to terrain heights."""
        # Get FFT data
        fft_bands = self.state.get("audio_fft", np.zeros(64))
        audio_volume = self.state.get("audio_volume", 0.0)
        
        if len(fft_bands) < 64:
            fft_bands = np.zeros(64)
        
        for point in self.terrain_points:
            x, z = point['x'], point['z']
            
            # Calculate distance from center for frequency mapping
            center_distance = math.sqrt(x*x + z*z)
            
            # Map distance to FFT band (0 to 63)
            fft_index = int(min(63, center_distance * 32))
            fft_magnitude = float(fft_bands[fft_index])
            
            # Apply FFT height modulation with distance falloff
            distance_falloff = max(0.1, 1.0 - center_distance * 0.5)
            fft_height = fft_magnitude * distance_falloff * audio_volume * 0.5
            
            point['fft_height'] = fft_height
            point['total_height'] = point['base_height'] + fft_height
    
    def _update_telemetry(self):
        """Update telemetry display data."""
        # Generate telemetry stream data
        self.telemetry_data = [
            f"Datastream Matrix Source: {random.randint(700, 800)}. / {random.randint(1200, 1300)}",
            f"{random.randint(2000, 2099)}..{random.randint(900, 999)}.{random.randint(9, 10)}..{random.randint(30, 50)}.{random.randint(100, 150)}-C",
            f"{random.randint(1020000, 1030000)}",
            f"{random.randint(89000, 90000)}"
        ]
        
        # Update preview graph data
        audio_volume = self.state.get("audio_volume", 0.0)
        self.preview_graph_data.append(audio_volume)
    
    def _render_content(self):
        """Render terrain and overlays."""
        # Clear background
        self.surface.fill(Palette.BLACK)
        
        # Render terrain mesh
        self._render_terrain_mesh()
        
        # Render corner brackets
        GeometricPrimitives.draw_corner_brackets(
            self.surface, self.surface.get_rect(),
            Palette.GRID, Config.CORNER_BRACKET_LENGTH, 1
        )
        
        # Render telemetry overlays
        self._render_telemetry_overlays()
        
        # Render LLM stream overlay
        self._render_llm_stream_overlay()
    
    def _render_terrain_mesh(self):
        """Render 3D terrain mesh with perspective projection."""
        # Create transformation matrices
        pitch_matrix = Matrix4x4.rotation_x(self.camera_pitch)
        
        # Project and sort points by depth
        projected_points = []
        
        for point in self.terrain_points:
            # Create 3D point
            world_pos = Vector3(point['x'] * 100, point['total_height'] * 80, 
                              point['z'] * 100 + self.camera_distance)
            
            # Apply camera rotation
            rotated_pos = pitch_matrix.transform_point(world_pos)
            
            # Perspective projection
            if rotated_pos.z > 0:  # Avoid division by zero/negative z
                screen_x = (rotated_pos.x * self.focal_length / rotated_pos.z) + self.rect.width // 2
                screen_y = (rotated_pos.y * self.focal_length / rotated_pos.z) + self.rect.height // 2
                
                # Calculate depth brightness
                depth_factor = max(0.1, min(1.0, 200.0 / rotated_pos.z))
                brightness = int(255 * depth_factor)
                
                # Determine point size based on height and depth
                height_factor = abs(point['total_height']) + 0.5
                point_size = max(1, int(height_factor * depth_factor * 3))
                
                projected_points.append({
                    'screen_pos': (int(screen_x), int(screen_y)),
                    'depth': rotated_pos.z,
                    'brightness': brightness,
                    'size': point_size,
                    'height': point['total_height']
                })
        
        # Sort by depth (back to front)
        projected_points.sort(key=lambda p: p['depth'], reverse=True)
        
        # Render points
        for proj_point in projected_points:
            screen_x, screen_y = proj_point['screen_pos']
            
            # Check bounds
            if (0 <= screen_x < self.rect.width and 0 <= screen_y < self.rect.height):
                brightness = proj_point['brightness']
                size = proj_point['size']
                height = proj_point['height']
                
                # Color based on height and brightness
                if height > 0.1:  # Peaks - brighter
                    color = (brightness, brightness, min(255, int(brightness * 1.2)))
                elif height < -0.1:  # Valleys - dimmer
                    color = (int(brightness * 0.6), int(brightness * 0.6), int(brightness * 0.8))
                else:  # Mid-level
                    color = (brightness, brightness, brightness)
                
                # Draw point
                if size == 1:
                    self.surface.set_at((screen_x, screen_y), color)
                else:
                    pygame.draw.circle(self.surface, color, (screen_x, screen_y), size)
    
    def _render_telemetry_overlays(self):
        """Render telemetry text overlays."""
        font = self.font_manager.get_font('small')
        
        # Left column telemetry
        left_x, left_y = Config.TELEMETRY_LEFT_POS  # (20, 80)
        for i, line in enumerate(self.telemetry_data):
            text_surface = font.render(line, True, Palette.LIGHT_GRAY)
            self.surface.blit(text_surface, (left_x, left_y + i * font.get_height()))
        
        # Right column telemetry (right-aligned)
        right_telemetry = ["-8/7C6", "259112A", "2001520", "10022007", "10200000"]
        right_x = Config.TELEMETRY_RIGHT_X  # 1100 (relative to left viewport)
        
        for i, line in enumerate(right_telemetry):
            text_surface = font.render(line, True, Palette.LIGHT_GRAY)
            text_x = right_x - text_surface.get_width()
            text_y = left_y + i * font.get_height()
            self.surface.blit(text_surface, (text_x, text_y))
        
        # Preview graph (bottom-left)
        self._render_preview_graph()
    
    def _render_preview_graph(self):
        """Render small preview graph labeled '.268'."""
        graph_x, graph_y = Config.PREVIEW_GRAPH_POS  # (20, 520)
        graph_width, graph_height = 120, 60
        
        # Graph background
        graph_rect = pygame.Rect(graph_x, graph_y, graph_width, graph_height)
        pygame.draw.rect(self.surface, Palette.INK, graph_rect)
        pygame.draw.rect(self.surface, Palette.GRID, graph_rect, 1)
        
        # Graph data
        if len(self.preview_graph_data) > 1:
            points = []
            for i, value in enumerate(self.preview_graph_data):
                x = graph_x + int((i / max(1, len(self.preview_graph_data) - 1)) * graph_width)
                y = graph_y + graph_height - int(value * graph_height)
                points.append((x, y))
            
            # Draw line graph
            if len(points) > 1:
                pygame.draw.lines(self.surface, Palette.CYAN, False, points, 1)
        
        # Graph label
        label_font = self.font_manager.get_font('small')
        label_surface = label_font.render(".268", True, Palette.WHITE)
        self.surface.blit(label_surface, (graph_x, graph_y - label_font.get_height() - 2))
    
    def _render_llm_stream_overlay(self):
        """Render LLM response stream overlay."""
        # Get LLM stream text
        llm_stream = self.state.get("llm_stream", "")
        
        if llm_stream.strip():
            # Overlay dimensions
            overlay_x = Config.LLM_OVERLAY_X  # 50
            overlay_y = Config.LLM_OVERLAY_Y  # 500
            overlay_width = Config.LLM_OVERLAY_WIDTH  # 1150
            overlay_height = Config.LLM_OVERLAY_HEIGHT  # 80
            
            # Semi-transparent background
            overlay_surface = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
            overlay_surface.fill((*Palette.BLACK, 200))  # Semi-transparent
            
            # Border
            pygame.draw.rect(overlay_surface, Palette.GRID, 
                           (0, 0, overlay_width, overlay_height), 1)
            
            # Render text with wrapping
            font = self.font_manager.get_font('normal')
            self.text_renderer.render_multiline_text(
                overlay_surface, llm_stream, (10, 10), 
                overlay_width - 20, Palette.WHITE, 'normal'
            )
            
            self.surface.blit(overlay_surface, (overlay_x, overlay_y))
    
    def _on_audio_data(self, event_data):
        """Handle audio data updates for terrain modulation."""
        # Audio data is processed in update() method
        pass

class GlobeRenderer(BasePanel):
    """Rotating wireframe vector globe with news coordinate plotting."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        # Globe occupies upper portion of right-top viewport
        rect = pygame.Rect(Config.RIGHT_TOP_VIEWPORT_X, Config.HEADER_HEIGHT,
                          Config.RIGHT_TOP_VIEWPORT_WIDTH, 
                          Config.GLOBE_HEIGHT)  # 196 pixels height
        super().__init__(rect, event_bus, state, font_manager)
        
        # Globe parameters
        self.center = (self.rect.width // 2, self.rect.height // 2)
        self.radius = Config.GLOBE_RADIUS  # 80 pixels
        self.sphere_points = []
        
        # Rotation state
        self.yaw_rotation = 0.0
        self.pitch_rotation = Config.GLOBE_PITCH_TILT  # 0.2 radians
        
        # Generate sphere points using Fibonacci spiral
        self._generate_sphere_points()
        
        # News coordinates
        self.news_coordinates = []
        
        # Subscribe to events
        self.event_bus.subscribe("news_data_updated", self._on_news_update)
        self.event_bus.subscribe("article_clicked", self._on_article_clicked)
    
    def _generate_sphere_points(self):
        """Generate sphere points using golden ratio Fibonacci spiral."""
        num_points = Config.GLOBE_POINT_COUNT  # 400 points
        self.sphere_points = []
        
        golden_ratio = (1 + math.sqrt(5)) / 2
        
        for i in range(num_points):
            # Fibonacci spiral distribution
            theta = 2 * math.pi * i / golden_ratio
            phi = math.acos(1 - 2 * (i + 0.5) / num_points)
            
            # Convert to Cartesian coordinates
            x = math.sin(phi) * math.cos(theta)
            y = math.sin(phi) * math.sin(theta)
            z = math.cos(phi)
            
            self.sphere_points.append(Vector3(x, y, z))
    
    def update(self, delta_time: float):
        """Update globe rotation and news coordinates."""
        # Continuous rotation
        self.yaw_rotation += delta_time * Config.GLOBE_ROTATION_SPEED  # 0.3 rad/s
        
        # Update news coordinates from state
        globe_coords = self.state.get("globe_coordinates", [])
        self.news_coordinates = globe_coords
    
    def _render_content(self):
        """Render rotating globe with news coordinates."""
        # Clear background
        self.surface.fill(Palette.BLACK)
        
        # Create rotation matrices
        yaw_matrix = Matrix4x4.rotation_y(self.yaw_rotation)
        pitch_matrix = Matrix4x4.rotation_x(self.pitch_rotation)
        rotation_matrix = Matrix4x4.multiply(pitch_matrix, yaw_matrix)
        
        # Transform and render sphere points
        self._render_sphere_wireframe(rotation_matrix)
        
        # Render news coordinate points
        self._render_news_coordinates(rotation_matrix)
        
        # Render globe border/frame
        pygame.draw.circle(self.surface, Palette.GRID, self.center, self.radius + 2, 1)
    
    def _render_sphere_wireframe(self, rotation_matrix: Matrix4x4):
        """Render wireframe sphere structure."""
        visible_points = []
        
        # Transform all points and cull back-facing
        for point in self.sphere_points:
            # Apply rotation
            rotated_point = rotation_matrix.transform_point(point)
            
            # Backface culling (view vector is (0, 0, -1))
            if rotated_point.z > -0.1:  # Point is facing towards viewer
                # Project to screen coordinates
                screen_x = self.center[0] + int(rotated_point.x * self.radius)
                screen_y = self.center[1] + int(rotated_point.y * self.radius)
                
                visible_points.append({
                    'pos': (screen_x, screen_y),
                    'world_pos': rotated_point,
                    'original': point
                })
        
        # Draw longitude and latitude lines by connecting nearby points
        self._draw_globe_grid_lines(visible_points)
        
        # Draw individual points
        for point_data in visible_points:
            screen_pos = point_data['pos']
            if (0 <= screen_pos[0] < self.rect.width and 
                0 <= screen_pos[1] < self.rect.height):
                pygame.draw.circle(self.surface, Palette.GRID, screen_pos, 1)
    
    def _draw_globe_grid_lines(self, visible_points: List[Dict]):
        """Draw great-circle grid lines connecting sphere points."""
        # Connect points that are close to each other in original coordinates
        connection_threshold = 0.3
        
        for i, point_a in enumerate(visible_points):
            for j, point_b in enumerate(visible_points[i+1:], i+1):
                # Calculate distance in original sphere coordinates
                orig_a = point_a['original']
                orig_b = point_b['original']
                
                distance = math.sqrt(
                    (orig_a.x - orig_b.x)**2 + 
                    (orig_a.y - orig_b.y)**2 + 
                    (orig_a.z - orig_b.z)**2
                )
                
                if distance < connection_threshold:
                    # Draw line between projected points
                    pos_a = point_a['pos']
                    pos_b = point_b['pos']
                    
                    # Check if both points are on screen
                    if (0 <= pos_a[0] < self.rect.width and 0 <= pos_a[1] < self.rect.height and
                        0 <= pos_b[0] < self.rect.width and 0 <= pos_b[1] < self.rect.height):
                        pygame.draw.line(self.surface, Palette.GRID, pos_a, pos_b, 1)
    
    def _render_news_coordinates(self, rotation_matrix: Matrix4x4):
        """Render news event coordinates as pins on the globe."""
        for news_event in self.news_coordinates:
            coords = news_event.get('coordinates')
            if not coords or len(coords) != 2:
                continue
            
            lat, lon = coords
            
            # Convert lat/lon to 3D sphere coordinates
            lat_rad = math.radians(lat)
            lon_rad = math.radians(lon)
            
            # Sphere coordinates (radius = 1)
            x = math.cos(lat_rad) * math.cos(lon_rad)
            z = math.cos(lat_rad) * math.sin(lon_rad)
            y = math.sin(lat_rad)
            
            world_point = Vector3(x, y, z)
            
            # Apply rotation
            rotated_point = rotation_matrix.transform_point(world_point)
            
            # Only render if facing viewer
            if rotated_point.z > -0.1:
                # Project to screen
                screen_x = self.center[0] + int(rotated_point.x * self.radius)
                screen_y = self.center[1] + int(rotated_point.y * self.radius)
                
                if (0 <= screen_x < self.rect.width and 0 <= screen_y < self.rect.height):
                    # Draw news pin
                    confidence = news_event.get('confidence', 0.5)
                    pin_size = int(2 + confidence * 3)
                    
                    # Outer circle
                    pygame.draw.circle(self.surface, Palette.WHITE, 
                                     (screen_x, screen_y), pin_size + 1, 1)
                    
                    # Inner filled circle
                    pygame.draw.circle(self.surface, Palette.CYAN, 
                                     (screen_x, screen_y), pin_size)
    
    def _handle_local_click(self, local_pos: Tuple[int, int]) -> bool:
        """Handle clicks on globe for news coordinate selection."""
        # Check if click is near any news coordinates
        click_threshold = 10  # pixels
        
        # Create current rotation matrix for coordinate transformation
        yaw_matrix = Matrix4x4.rotation_y(self.yaw_rotation)
        pitch_matrix = Matrix4x4.rotation_x(self.pitch_rotation)
        rotation_matrix = Matrix4x4.multiply(pitch_matrix, yaw_matrix)
        
        for news_event in self.news_coordinates:
            coords = news_event.get('coordinates')
            if not coords:
                continue
                
            lat, lon = coords
            
            # Convert to 3D and project
            lat_rad = math.radians(lat)
            lon_rad = math.radians(lon)
            
            x = math.cos(lat_rad) * math.cos(lon_rad)
            z = math.cos(lat_rad) * math.sin(lon_rad)
            y = math.sin(lat_rad)
            
            world_point = Vector3(x, y, z)
            rotated_point = rotation_matrix.transform_point(world_point)
            
            if rotated_point.z > -0.1:  # Visible
                screen_x = self.center[0] + int(rotated_point.x * self.radius)
                screen_y = self.center[1] + int(rotated_point.y * self.radius)
                
                # Check distance to click
                distance = math.sqrt((local_pos[0] - screen_x)**2 + (local_pos[1] - screen_y)**2)
                
                if distance <= click_threshold:
                    # Clicked on this coordinate
                    self.event_bus.publish("article_clicked", {
                        "article_id": news_event.get('id'),
                        "coordinates": coords,
                        "headline": news_event.get('headline')
                    })
                    return True
        
        return False
    
    def _on_news_update(self, event_data):
        """Handle news data updates."""
        # News coordinates are updated in update() method
        pass
    
    def _on_article_clicked(self, event_data):
        """Handle article click events."""
        # Trigger tactical overlay display
        pass

class NewsFeedRenderer(BasePanel):
    """Live scrolling news feed with clickable articles."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        # News feed occupies lower portion of right-top viewport  
        rect = pygame.Rect(Config.RIGHT_TOP_VIEWPORT_X, 
                          Config.HEADER_HEIGHT + Config.GLOBE_HEIGHT,
                          Config.RIGHT_TOP_VIEWPORT_WIDTH,
                          Config.RIGHT_TOP_VIEWPORT_HEIGHT - Config.GLOBE_HEIGHT)
        super().__init__(rect, event_bus, state, font_manager)
        
        # Scrolling state
        self.scroll_offset = 0.0
        self.auto_scroll_speed = 20.0  # pixels per second
        
        # Article display
        self.displayed_articles = []
        self.article_rects = []
        
        # Subscribe to news updates
        self.event_bus.subscribe("news_data_updated", self._on_news_update)
    
    def update(self, delta_time: float):
        """Update scrolling and article display."""
        # Auto-scroll
        self.scroll_offset += self.auto_scroll_speed * delta_time
        
        # Get latest articles
        news_articles = self.state.get("news_articles", [])
        self.displayed_articles = news_articles[:10]  # Show latest 10
        
        # Reset scroll if we've scrolled past all content
        if len(self.displayed_articles) > 0:
            total_content_height = len(self.displayed_articles) * 60  # Approximate
            if self.scroll_offset > total_content_height:
                self.scroll_offset = -self.rect.height
    
    def _render_content(self):
        """Render scrolling news feed."""
        # Clear background
        self.surface.fill(Palette.BLACK)
        
        # Border
        pygame.draw.rect(self.surface, Palette.GRID, self.surface.get_rect(), 1)
        
        # Header
        header_font = self.font_manager.get_font('small')
        header_text = header_font.render("LIVE NEWS FEED", True, Palette.AMBER)
        self.surface.blit(header_text, (5, 5))
        
        # Render articles
        self._render_article_list()
    
    def _render_article_list(self):
        """Render scrolling list of news articles."""
        if not self.displayed_articles:
            # No articles message
            font = self.font_manager.get_font('small')
            no_news_text = font.render("Loading news data...", True, Palette.LIGHT_GRAY)
            self.surface.blit(no_news_text, (10, 30))
            return
        
        font = self.font_manager.get_font('micro')
        source_font = self.font_manager.get_font('micro')
        
        y_pos = 25 - int(self.scroll_offset)
        self.article_rects = []
        
        for i, article in enumerate(self.displayed_articles):
            # Skip if article is completely off-screen
            if y_pos > self.rect.height or y_pos < -80:
                y_pos += 55
                continue
            
            # Article background (alternating colors)
            article_rect = pygame.Rect(2, y_pos, self.rect.width - 4, 50)
            bg_color = Palette.INK if i % 2 == 0 else Palette.BLACK
            pygame.draw.rect(self.surface, bg_color, article_rect)
            
            # Store clickable area
            self.article_rects.append({
                'rect': article_rect,
                'article': article
            })
            
            # Article headline (truncated)
            headline = article.get('headline', 'No headline')
            if len(headline) > 45:
                headline = headline[:42] + "..."
            
            headline_surface = font.render(headline, True, Palette.WHITE)
            self.surface.blit(headline_surface, (5, y_pos + 2))
            
            # Source and location
            source = article.get('source', 'Unknown')
            location = article.get('location', 'GLOBAL')
            if len(location) > 20:
                location = location[:17] + "..."
            
            source_text = f"{source} | {location}"
            source_surface = source_font.render(source_text, True, Palette.LIGHT_GRAY)
            self.surface.blit(source_surface, (5, y_pos + 18))
            
            # Confidence indicator for geographic articles
            if not article.get('is_global', True):
                confidence = article.get('confidence', 0.0)
                conf_text = f"Confidence: {confidence:.1f}"
                conf_surface = source_font.render(conf_text, True, Palette.CYAN)
                self.surface.blit(conf_surface, (5, y_pos + 30))
            
            # Global indicator
            if article.get('is_global', True):
                global_surface = source_font.render("GLOBAL EVENT", True, Palette.AMBER)
                self.surface.blit(global_surface, (5, y_pos + 30))
            
            y_pos += 55
    
    def _handle_local_click(self, local_pos: Tuple[int, int]) -> bool:
        """Handle clicks on news articles."""
        for article_data in self.article_rects:
            if article_data['rect'].collidepoint(local_pos):
                # Clicked on this article
                article = article_data['article']
                self.event_bus.publish("article_clicked", {
                    "article_id": article.get('id'),
                    "headline": article.get('headline'),
                    "coordinates": article.get('coordinates')
                })
                return True
        
        return False
    
    def _on_news_update(self, event_data):
        """Handle news data updates."""
        # Articles are updated in update() method
        pass

class PersonalMonitorRenderer(BasePanel):
    """Personal monitor panel with social feeds, media, and notifications."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        rect = pygame.Rect(Config.RIGHT_BOTTOM_VIEWPORT_X, Config.RIGHT_BOTTOM_VIEWPORT_Y,
                          Config.RIGHT_BOTTOM_VIEWPORT_WIDTH, Config.RIGHT_BOTTOM_VIEWPORT_HEIGHT)
        super().__init__(rect, event_bus, state, font_manager)
        
        # Section rectangles
        self.media_rect = pygame.Rect(10, 10, self.rect.width - 20, 120)
        self.social_rect = pygame.Rect(10, 140, self.rect.width - 20, 120)
        self.alerts_rect = pygame.Rect(10, 270, self.rect.width - 20, 120)
        
        # Animation state
        self.alert_flash_time = 0.0
        
        # Clickable message areas
        self.message_rects = []
    
    def update(self, delta_time: float):
        """Update animations and social data."""
        self.alert_flash_time += delta_time * 4.0
    
    def _render_content(self):
        """Render personal monitor sections."""
        # Clear background
        self.surface.fill(Palette.BLACK)
        
        # Main border
        pygame.draw.rect(self.surface, Palette.GRID, self.surface.get_rect(), 1)
        
        # Render sections
        self._render_media_feeds()
        self._render_social_feeds() 
        self._render_critical_notifications()
    
    def _render_media_feeds(self):
        """Render media feed thumbnails with vector graphics."""
        # Section border
        pygame.draw.rect(self.surface, Palette.GRID, self.media_rect, 1)
        
        # Section header
        font = self.font_manager.get_font('small')
        header_text = font.render("MEDIA FEEDS", True, Palette.AMBER)
        self.surface.blit(header_text, (self.media_rect.x + 5, self.media_rect.y + 2))
        
        # Four media boxes
        box_width = (self.media_rect.width - 30) // 4
        box_height = 60
        box_y = self.media_rect.y + 25
        
        media_items = [
            "SUIT STATUS", "DRONE ARRAY", "SHIELD MATRIX", "ARC MONITOR"
        ]
        
        for i, item in enumerate(media_items):
            box_x = self.media_rect.x + 10 + i * (box_width + 5)
            box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
            
            # Box background and border
            pygame.draw.rect(self.surface, Palette.INK, box_rect)
            pygame.draw.rect(self.surface, Palette.GRID, box_rect, 1)
            
            # Radar sweep effect
            center_x = box_x + box_width // 2
            center_y = box_y + box_height // 2
            sweep_angle = time.time() * 3.0 + i * 1.5
            
            GeometricPrimitives.draw_radar_sweep(
                self.surface, (center_x, center_y), 
                box_width // 3, sweep_angle, Palette.CYAN, 0.3
            )
            
            # Parallel scan lines
            for line_y in range(box_y + 5, box_y + box_height - 5, 4):
                pygame.draw.line(self.surface, Palette.GRID,
                               (box_x + 2, line_y), (box_x + box_width - 2, line_y), 1)
            
            # Label
            label_font = self.font_manager.get_font('micro')
            label_surface = label_font.render(item, True, Palette.WHITE)
            label_x = box_x + (box_width - label_surface.get_width()) // 2
            self.surface.blit(label_surface, (label_x, box_y + box_height + 2))
    
    def _render_social_feeds(self):
        """Render social network feeds and messages."""
        # Section border
        pygame.draw.rect(self.surface, Palette.GRID, self.social_rect, 1)
        
        # Section header
        font = self.font_manager.get_font('small')
        header_text = font.render("SOCIAL NETWORKS", True, Palette.CYAN)
        self.surface.blit(header_text, (self.social_rect.x + 5, self.social_rect.y + 2))
        
        # Get social feeds from state
        social_feeds = self.state.get("social_feeds", [])
        recent_messages = self.state.get("recent_messages", [])
        
        # Combine and display
        all_social_items = list(social_feeds) + recent_messages[:2]  # Limit to avoid overflow
        
        y_pos = self.social_rect.y + 20
        message_font = self.font_manager.get_font('micro')
        self.message_rects = []
        
        for i, item in enumerate(all_social_items[:4]):  # Show max 4 items
            # Avatar/icon area
            avatar_size = 20
            avatar_rect = pygame.Rect(self.social_rect.x + 10, y_pos, avatar_size, avatar_size)
            pygame.draw.rect(self.surface, Palette.GRID, avatar_rect)
            pygame.draw.rect(self.surface, Palette.LIGHT_GRAY, avatar_rect, 1)
            
            # User/platform info
            if 'platform' in item:  # Recent message
                user = f"{item['platform']}: {item.get('sender', 'Unknown')}"
                message = item.get('preview', item.get('subject', 'New message'))
                color = Palette.WHITE
            else:  # Social feed
                user = item.get('user', 'Unknown')
                message = item.get('msg', 'No message')
                color = Palette.LIGHT_GRAY
            
            # User name
            user_surface = message_font.render(user[:25], True, color)
            self.surface.blit(user_surface, (avatar_rect.right + 5, y_pos))
            
            # Message preview
            message_text = message[:40] + "..." if len(message) > 40 else message
            message_surface = message_font.render(message_text, True, Palette.LIGHT_GRAY)
            self.surface.blit(message_surface, (avatar_rect.right + 5, y_pos + 12))
            
            # Store clickable area for messages
            if 'platform' in item:
                click_rect = pygame.Rect(self.social_rect.x + 5, y_pos - 2,
                                       self.social_rect.width - 10, 22)
                self.message_rects.append({
                    'rect': click_rect,
                    'message': item
                })
            
            y_pos += 25
    
    def _render_critical_notifications(self):
        """Render critical notifications with alert animations."""
        # Section border
        pygame.draw.rect(self.surface, Palette.GRID, self.alerts_rect, 1)
        
        # Section header
        font = self.font_manager.get_font('small')
        header_text = font.render("CRITICAL NOTIFICATIONS", True, Palette.ALERT)
        self.surface.blit(header_text, (self.alerts_rect.x + 5, self.alerts_rect.y + 2))
        
        # Get alerts from state
        security_alerts = self.state.get("security_alerts", [])
        hardware_alerts = self.state.get("hardware_alerts", [])
        network_alerts = self.state.get("network_alerts", [])
        
        all_alerts = list(security_alerts) + hardware_alerts + network_alerts
        
        y_pos = self.alerts_rect.y + 20
        alert_font = self.font_manager.get_font('micro')
        
        for i, alert in enumerate(all_alerts[:4]):  # Show max 4 alerts
            # Flashing alert icon
            flash_alpha = int(128 + 127 * math.sin(self.alert_flash_time + i))
            
            # Bell icon
            icon_x = self.alerts_rect.x + 10
            icon_size = 12
            
            # Simple bell shape
            pygame.draw.circle(self.surface, (*Palette.ALERT, flash_alpha),
                             (icon_x + icon_size//2, y_pos + icon_size//2), icon_size//2)
            
            # Alert message
            if isinstance(alert, dict):
                alert_text = alert.get('message', str(alert))
            else:
                alert_text = str(alert)
            
            # Truncate long alerts
            if len(alert_text) > 45:
                alert_text = alert_text[:42] + "..."
            
            alert_surface = alert_font.render(alert_text, True, Palette.ALERT)
            self.surface.blit(alert_surface, (icon_x + icon_size + 5, y_pos))
            
            y_pos += 25
    
    def _handle_local_click(self, local_pos: Tuple[int, int]) -> bool:
        """Handle clicks on social messages."""
        for message_data in self.message_rects:
            if message_data['rect'].collidepoint(local_pos):
                # Clicked on social message
                message = message_data['message']
                
                # Trigger social app interface
                self.event_bus.publish("social_message_clicked", {
                    "platform": message.get('platform'),
                    "message_data": message
                })
                return True
        
        return False

class DiagnosticPanelsRenderer(BasePanel):
    """Four diagnostic panels showing system metrics with live graphs."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        rect = pygame.Rect(0, Config.BOTTOM_STATUS_Y, Config.SCREEN_WIDTH, Config.BOTTOM_STATUS_HEIGHT)
        super().__init__(rect, event_bus, state, font_manager)
        
        # Panel dimensions
        panel_width = Config.SCREEN_WIDTH // 4
        panel_height = Config.BOTTOM_STATUS_HEIGHT
        
        # Individual panel rects
        self.temp_panel_rect = pygame.Rect(0, 0, panel_width, panel_height)
        self.network_panel_rect = pygame.Rect(panel_width, 0, panel_width, panel_height)
        self.resources_panel_rect = pygame.Rect(panel_width * 2, 0, panel_width, panel_height)
        self.health_panel_rect = pygame.Rect(panel_width * 3, 0, panel_width, panel_height)
        
        # EKG heartbeat state
        self.heartbeat_time = 0.0
        
    def update(self, delta_time: float):
        """Update diagnostic animations."""
        self.heartbeat_time += delta_time
    
    def _render_content(self):
        """Render all four diagnostic panels."""
        # Clear background
        self.surface.fill(Palette.BLACK)
        
        # Panel separators
        for i in range(1, 4):
            x = i * (Config.SCREEN_WIDTH // 4)
            pygame.draw.line(self.surface, Palette.GRID, 
                           (x, 0), (x, self.rect.height), 1)
        
        # Render individual panels
        self._render_temperature_panel()
        self._render_network_panel()
        self._render_resources_panel()
        self._render_health_panel()
    
    def _render_temperature_panel(self):
        """Render CPU temperature line graph."""
        # Panel border and header
        pygame.draw.rect(self.surface, Palette.GRID, self.temp_panel_rect, 1)
        
        font = self.font_manager.get_font('small')
        header = font.render("CPU TEMPERATURE", True, Palette.AMBER)
        self.surface.blit(header, (self.temp_panel_rect.x + 5, self.temp_panel_rect.y + 2))
        
        # Graph area
        graph_rect = pygame.Rect(self.temp_panel_rect.x + 10, self.temp_panel_rect.y + 25,
                               self.temp_panel_rect.width - 20, self.temp_panel_rect.height - 40)
        
        # Grid lines at temperature thresholds
        temp_thresholds = [30, 50, 70, 85]  # °C
        for temp in temp_thresholds:
            y = graph_rect.bottom - int((temp - 20) / 70 * graph_rect.height)  # 20-90°C range
            if graph_rect.y <= y <= graph_rect.bottom:
                color = Palette.ALERT if temp >= 70 else Palette.GRID
                GeometricPrimitives.draw_tactical_line(
                    self.surface, (graph_rect.left, y), (graph_rect.right, y),
                    color, 1, [3, 3] if temp < 70 else None
                )
        
        # Temperature history
        temp_history = self.state.get("temp_history", [])
        current_temp = self.state.get("cpu_temp", 40.0)
        
        if len(temp_history) > 1:
            points = []
            for i, (timestamp, temp) in enumerate(temp_history[-60:]):  # Last 60 readings
                x = graph_rect.left + int((i / 59) * graph_rect.width)
                y = graph_rect.bottom - int((temp - 20) / 70 * graph_rect.height)
                y = max(graph_rect.top, min(graph_rect.bottom, y))
                points.append((x, y))
            
            if len(points) > 1:
                # Color based on temperature level
                line_color = Palette.LIGHT_GRAY
                if current_temp > Config.TEMPERATURE_WARNING:
                    line_color = Palette.ALERT
                elif current_temp > Config.TEMPERATURE_WARNING * 0.8:
                    line_color = Palette.AMBER
                
                # Render smooth curve using Catmull-Rom interpolation
                if len(points) >= 4:
                    interpolated_points = []
                    for i in range(1, len(points) - 2):
                        p0, p1, p2, p3 = points[i-1], points[i], points[i+1], points[i+2]
                        
                        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
                            interp_x = catmull_rom(p0[0], p1[0], p2[0], p3[0], t)
                            interp_y = catmull_rom(p0[1], p1[1], p2[1], p3[1], t)
                            interpolated_points.append((int(interp_x), int(interp_y)))
                    
                    if len(interpolated_points) > 1:
                        pygame.draw.lines(self.surface, line_color, False, interpolated_points, 2)
                else:
                    pygame.draw.lines(self.surface, line_color, False, points, 2)
        
        # Current temperature display
        temp_text = f"{current_temp:.1f}°C"
        temp_surface = self.font_manager.get_font('normal').render(temp_text, True, Palette.WHITE)
        self.surface.blit(temp_surface, (self.temp_panel_rect.x + 5, self.temp_panel_rect.bottom - 20))
    
    def _render_network_panel(self):
        """Render network ping latency scatter plot."""
        # Panel border and header
        pygame.draw.rect(self.surface, Palette.GRID, self.network_panel_rect, 1)
        
        font = self.font_manager.get_font('small')
        header = font.render("NETWORK LATENCY", True, Palette.CYAN)
        self.surface.blit(header, (self.network_panel_rect.x + 5, self.network_panel_rect.y + 2))
        
        # Graph area
        graph_rect = pygame.Rect(self.network_panel_rect.x + 10, self.network_panel_rect.y + 25,
                               self.network_panel_rect.width - 20, self.network_panel_rect.height - 40)
        
        # Grid lines for latency thresholds
        latency_thresholds = [50, 100, 200, 500]  # ms
        for latency in latency_thresholds:
            y = graph_rect.bottom - int((latency / 600) * graph_rect.height)  # 0-600ms range
            if graph_rect.y <= y <= graph_rect.bottom:
                color = Palette.ALERT if latency >= 200 else Palette.GRID
                GeometricPrimitives.draw_tactical_line(
                    self.surface, (graph_rect.left, y), (graph_rect.right, y),
                    color, 1, [3, 3] if latency < 200 else None
                )
        
        # Ping history
        ping_history = self.state.get("ping_history", [])
        current_ping = self.state.get("ping_ms", 0.0)
        internet_up = self.state.get("internet_up", True)
        
        if len(ping_history) > 0:
            for i, (timestamp, ping_ms, connected) in enumerate(ping_history[-60:]):
                if connected and ping_ms < 999:
                    x = graph_rect.left + int((i / 59) * graph_rect.width)
                    y = graph_rect.bottom - int((ping_ms / 600) * graph_rect.height)
                    y = max(graph_rect.top, min(graph_rect.bottom, y))
                    
                    # Color based on latency
                    if ping_ms < 50:
                        color = Palette.CYAN
                    elif ping_ms < 100:
                        color = Palette.AMBER
                    else:
                        color = Palette.ALERT
                    
                    pygame.draw.circle(self.surface, color, (x, y), 2)
        
        # Current status display
        if internet_up:
            status_text = f"{current_ping:.0f}ms"
            status_color = Palette.WHITE
        else:
            status_text = "OFFLINE"
            status_color = Palette.ALERT
        
        status_surface = self.font_manager.get_font('normal').render(status_text, True, status_color)
        self.surface.blit(status_surface, (self.network_panel_rect.x + 5, self.network_panel_rect.bottom - 20))
    
    def _render_resources_panel(self):
        """Render CPU and RAM usage with individual core loads."""
        # Panel border and header
        pygame.draw.rect(self.surface, Palette.GRID, self.resources_panel_rect, 1)
        
        font = self.font_manager.get_font('small')
        header = font.render("SYSTEM RESOURCES", True, Palette.AMBER)
        self.surface.blit(header, (self.resources_panel_rect.x + 5, self.resources_panel_rect.y + 2))
        
        # Get resource data
        cpu_usage = self.state.get("cpu_usage", 0.0)
        ram_usage = self.state.get("ram_usage", 0.0)
        cpu_per_core = self.state.get("cpu_per_core", [])
        cpu_history = self.state.get("cpu_history", [])
        ram_history = self.state.get("ram_history", [])
        
        # Main usage area
        usage_rect = pygame.Rect(self.resources_panel_rect.x + 10, self.resources_panel_rect.y + 25,
                               self.resources_panel_rect.width - 20, 60)
        
        # CPU usage filled area
        if len(cpu_history) > 1:
            points = [(usage_rect.left, usage_rect.bottom)]
            
            for i, (timestamp, usage) in enumerate(cpu_history[-30:]):  # Last 30 readings
                x = usage_rect.left + int((i / 29) * usage_rect.width)
                y = usage_rect.bottom - int((usage / 100) * 30)  # Upper half for CPU
                points.append((x, y))
            
            points.append((usage_rect.right, usage_rect.bottom))
            
            # Create filled polygon with alpha
            cpu_surface = pygame.Surface((usage_rect.width, usage_rect.height), pygame.SRCALPHA)
            cpu_points = [(p[0] - usage_rect.x, p[1] - usage_rect.y) for p in points]
            pygame.draw.polygon(cpu_surface, (*Palette.CYAN, 100), cpu_points)
            self.surface.blit(cpu_surface, (usage_rect.x, usage_rect.y))
        
        # RAM usage filled area
        if len(ram_history) > 1:
            points = [(usage_rect.left, usage_rect.center[1])]
            
            for i, (timestamp, usage) in enumerate(ram_history[-30:]):
                x = usage_rect.left + int((i / 29) * usage_rect.width)
                y = usage_rect.center[1] + int((usage / 100) * 30)  # Lower half for RAM
                points.append((x, y))
            
            points.append((usage_rect.right, usage_rect.center[1]))
            
            # Create filled polygon with alpha
            ram_surface = pygame.Surface((usage_rect.width, usage_rect.height), pygame.SRCALPHA)
            ram_points = [(p[0] - usage_rect.x, p[1] - usage_rect.y) for p in points]
            pygame.draw.polygon(ram_surface, (*Palette.AMBER, 100), ram_points)
            self.surface.blit(ram_surface, (usage_rect.x, usage_rect.y))
        
        # Individual CPU cores
        core_rect = pygame.Rect(self.resources_panel_rect.x + 10, self.resources_panel_rect.y + 90,
                               self.resources_panel_rect.width - 20, 40)
        
        if cpu_per_core:
            core_width = core_rect.width // len(cpu_per_core)
            
            for i, core_usage in enumerate(cpu_per_core):
                core_x = core_rect.x + i * core_width
                core_height = int((core_usage / 100) * core_rect.height)
                
                bar_rect = pygame.Rect(core_x + 1, core_rect.bottom - core_height,
                                     core_width - 2, core_height)
                
                # Color based on usage
                if core_usage > 80:
                    color = Palette.ALERT
                elif core_usage > 60:
                    color = Palette.AMBER
                else:
                    color = Palette.CYAN
                
                pygame.draw.rect(self.surface, color, bar_rect)
        
        # Usage percentages
        cpu_text = f"CPU: {cpu_usage:.0f}%"
        ram_text = f"RAM: {ram_usage:.0f}%"
        
        cpu_surface = self.font_manager.get_font('micro').render(cpu_text, True, Palette.WHITE)
        ram_surface = self.font_manager.get_font('micro').render(ram_text, True, Palette.WHITE)
        
        self.surface.blit(cpu_surface, (self.resources_panel_rect.x + 5, self.resources_panel_rect.bottom - 35))
        self.surface.blit(ram_surface, (self.resources_panel_rect.x + 5, self.resources_panel_rect.bottom - 20))
    
    def _render_health_panel(self):
        """Render system health dial and EKG heartbeat."""
        # Panel border and header
        pygame.draw.rect(self.surface, Palette.GRID, self.health_panel_rect, 1)
        
        font = self.font_manager.get_font('small')
        header = font.render("SYSTEM HEALTH", True, Palette.WHITE)
        self.surface.blit(header, (self.health_panel_rect.x + 5, self.health_panel_rect.y + 2))
        
        # Health dial (left half)
        dial_center = (self.health_panel_rect.x + 60, self.health_panel_rect.y + 70)
        dial_radius = 40
        
        # Get health data
        system_health = self.state.get("system_health", {})
        overall_health = system_health.get("overall", 100.0)
        
        # Draw semicircle background
        pygame.draw.arc(self.surface, Palette.GRID, 
                       (dial_center[0] - dial_radius, dial_center[1] - dial_radius,
                        dial_radius * 2, dial_radius * 2),
                       0, math.pi, 3)
        
        # Health arc (colored based on health level)
        health_angle = (overall_health / 100.0) * math.pi
        
        if overall_health > 75:
            health_color = Palette.CYAN
        elif overall_health > 50:
            health_color = Palette.AMBER
        else:
            health_color = Palette.ALERT
        
        pygame.draw.arc(self.surface, health_color,
                       (dial_center[0] - dial_radius, dial_center[1] - dial_radius,
                        dial_radius * 2, dial_radius * 2),
                       0, health_angle, 5)
        
        # Health percentage
        health_text = f"{overall_health:.0f}%"
        health_surface = self.font_manager.get_font('small').render(health_text, True, Palette.WHITE)
        text_x = dial_center[0] - health_surface.get_width() // 2
        text_y = dial_center[1] + 10
        self.surface.blit(health_surface, (text_x, text_y))
        
        # EKG heartbeat (right half)
        ekg_rect = pygame.Rect(self.health_panel_rect.x + 120, self.health_panel_rect.y + 30,
                              self.health_panel_rect.width - 130, 80)
        
        self._render_ekg_heartbeat(ekg_rect)
    
    def _render_ekg_heartbeat(self, ekg_rect: pygame.Rect):
        """Render live EKG heartbeat pulse."""
        # EKG baseline
        baseline_y = ekg_rect.centery
        pygame.draw.line(self.surface, Palette.GRID,
                        (ekg_rect.left, baseline_y), (ekg_rect.right, baseline_y), 1)
        
        # Generate heartbeat waveform
        points = []
        samples = ekg_rect.width
        
        for i in range(samples):
            # Time position
            t = (self.heartbeat_time * 2.0 + (i / samples) * 4.0) % 2.0  # 2-second cycle
            
            # EKG waveform using combined sine waves
            if 0.0 <= t < 0.1:  # P wave
                y_offset = 5 * math.sin((t / 0.1) * math.pi)
            elif 0.15 <= t < 0.25:  # QRS complex
                if 0.15 <= t < 0.17:  # Q
                    y_offset = -8 * math.sin(((t - 0.15) / 0.02) * math.pi)
                elif 0.17 <= t < 0.22:  # R
                    y_offset = 25 * math.sin(((t - 0.17) / 0.05) * math.pi)
                else:  # S
                    y_offset = -12 * math.sin(((t - 0.22) / 0.03) * math.pi)
            elif 0.35 <= t < 0.55:  # T wave
                y_offset = 8 * math.sin(((t - 0.35) / 0.2) * math.pi)
            else:  # Baseline
                y_offset = 0
            
            x = ekg_rect.left + i
            y = baseline_y - int(y_offset)
            points.append((x, y))
        
        # Draw EKG line
        if len(points) > 1:
            pygame.draw.lines(self.surface, Palette.CYAN, False, points, 2)

class BrainstormingModeRenderer:
    """Full-screen brainstorming mode interface."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        self.event_bus = event_bus
        self.state = state
        self.font_manager = font_manager
        self.text_renderer = TextRenderer(font_manager)
        
        # Mode state
        self.active = False
        self.fade_progress = 0.0
        
        # Terrain for background
        self.terrain_renderer = TerrainRenderer(event_bus, state, font_manager)
        
        # Chat interface
        self.conversation_history = []
        self.current_input = ""
        
        # Voice visualization
        self.voice_waveform = deque(maxlen=100)
        self.waveform_time = 0.0
        
        # Subscribe to events
        self.event_bus.subscribe("brainstorming_mode_toggle", self._on_toggle)
        self.event_bus.subscribe("voice_transcript", self._on_voice_input)
        self.event_bus.subscribe("audio_data_updated", self._on_audio_data)
    
    def set_active(self, active: bool):
        """Set brainstorming mode state."""
        self.active = active
        self.fade_progress = 1.0 if active else 0.0
    
    def update(self, delta_time: float):
        """Update brainstorming mode."""
        if not self.active:
            return
        
        self.waveform_time += delta_time
        
        # Update terrain background
        self.terrain_renderer.update(delta_time)
    
    def render(self, surface: pygame.Surface):
        """Render brainstorming mode interface."""
        if not self.active:
            return
        
        # Clear with black
        surface.fill(Palette.BLACK)
        
        # Render terrain as background (dimmed)
        terrain_surface = self.terrain_renderer.surface.copy()
        terrain_surface.set_alpha(50)  # Very dim
        surface.blit(terrain_surface, (0, Config.HEADER_HEIGHT))
        
        # Header with mode info
        self._render_header(surface)
        
        # Central agent name and waveform
        self._render_central_display(surface)
        
        # Chat columns
        self._render_chat_interface(surface)
        
        # Bottom controls
        self._render_bottom_interface(surface)
        
        # Exit button
        self._render_exit_button(surface)
    
    def _render_header(self, surface: pygame.Surface):
        """Render brainstorming mode header."""
        header_rect = pygame.Rect(0, 0, Config.SCREEN_WIDTH, 60)
        
        # Header background
        header_surface = pygame.Surface((header_rect.width, header_rect.height), pygame.SRCALPHA)
        header_surface.fill((*Palette.BLACK, 180))
        surface.blit(header_surface, header_rect)
        
        # Mode title
        font = self.font_manager.get_font('large')
        title_text = "BRAINSTORMING MODE - NEURAL INTERFACE ACTIVE"
        title_surface = font.render(title_text, True, Palette.CYAN)
        title_x = (Config.SCREEN_WIDTH - title_surface.get_width()) // 2
        surface.blit(title_surface, (title_x, 10))
        
        # System stats
        stats_font = self.font_manager.get_font('small')
        uptime = self.state.get("boot_time", time.time())
        uptime_text = f"UPTIME: {int(time.time() - uptime)}s"
        
        stats_surface = stats_font.render(uptime_text, True, Palette.LIGHT_GRAY)
        surface.blit(stats_surface, (Config.SCREEN_WIDTH - stats_surface.get_width() - 20, 35))
    
    def _render_central_display(self, surface: pygame.Surface):
        """Render central agent name and voice waveform."""
        center_x = Config.SCREEN_WIDTH // 2
        center_y = Config.SCREEN_HEIGHT // 2 - 100
        
        # Current persona
        current_mode = self.state.get("current_persona_mode", "archer")
        agent_name = current_mode.upper()
        
        # Agent name
        name_font = self.font_manager.get_font('huge')
        name_surface = name_font.render(agent_name, True, Palette.WHITE)
        name_x = center_x - name_surface.get_width() // 2
        surface.blit(name_surface, (name_x, center_y - 50))
        
        # Voice waveform visualization
        waveform_rect = pygame.Rect(center_x - 200, center_y + 20, 400, 60)
        self._render_waveform(surface, waveform_rect)
    
    def _render_waveform(self, surface: pygame.Surface, waveform_rect: pygame.Rect):
        """Render voice activity waveform."""
        # Waveform background
        pygame.draw.rect(surface, Palette.INK, waveform_rect)
        pygame.draw.rect(surface, Palette.GRID, waveform_rect, 1)
        
        # Get audio data
        audio_volume = self.state.get("audio_volume", 0.0)
        is_listening = self.state.get("voice_listening", False)
        is_speaking = self.state.get("voice_speaking", False)
        
        # Generate waveform data
        if len(self.voice_waveform) < 100:
            self.voice_waveform.extend([0.0] * (100 - len(self.voice_waveform)))
        
        # Add current audio level
        if is_listening or is_speaking:
            self.voice_waveform.append(audio_volume)
        else:
            self.voice_waveform.append(0.0)
        
        # Render waveform
        if len(self.voice_waveform) > 1:
            points = []
            for i, level in enumerate(self.voice_waveform):
                x = waveform_rect.left + int((i / 99) * waveform_rect.width)
                y = waveform_rect.centery - int(level * waveform_rect.height * 0.4)
                points.append((x, y))
            
            if len(points) > 1:
                color = Palette.CYAN if is_listening else (Palette.AMBER if is_speaking else Palette.LIGHT_GRAY)
                pygame.draw.lines(surface, color, False, points, 2)
        
        # Status text
        status_text = "LISTENING..." if is_listening else ("SPEAKING..." if is_speaking else "READY")
        status_color = Palette.CYAN if is_listening else (Palette.AMBER if is_speaking else Palette.WHITE)
        
        status_surface = self.font_manager.get_font('small').render(status_text, True, status_color)
        status_x = waveform_rect.centerx - status_surface.get_width() // 2
        surface.blit(status_surface, (status_x, waveform_rect.bottom + 5))
    
    def _render_chat_interface(self, surface: pygame.Surface):
        """Render left and right chat columns."""
        # Left column - User input
        left_rect = pygame.Rect(50, Config.SCREEN_HEIGHT // 2 + 50, 400, 200)
        self._render_chat_column(surface, left_rect, "YOUR INPUT", Palette.CYAN, True)
        
        # Right column - AI responses  
        right_rect = pygame.Rect(Config.SCREEN_WIDTH - 450, Config.SCREEN_HEIGHT // 2 + 50, 400, 200)
        self._render_chat_column(surface, right_rect, "ARCHER RESPONSE", Palette.AMBER, False)
    
    def _render_chat_column(self, surface: pygame.Surface, column_rect: pygame.Rect, 
                           title: str, color: Tuple[int, int, int], is_user_column: bool):
        """Render individual chat column."""
        # Column background
        column_surface = pygame.Surface((column_rect.width, column_rect.height), pygame.SRCALPHA)
        column_surface.fill((*Palette.BLACK, 150))
        
        # Border
        pygame.draw.rect(column_surface, color, (0, 0, column_rect.width, column_rect.height), 2)
        
        # Title
        title_font = self.font_manager.get_font('medium')
        title_surface = title_font.render(title, True, color)
        column_surface.blit(title_surface, (10, 5))
        
        # Chat content
        content_rect = pygame.Rect(10, 30, column_rect.width - 20, column_rect.height - 40)
        
        # Get relevant conversation data
        if is_user_column:
            # Show recent user inputs
            last_transcript = self.state.get("last_transcript", "")
            if last_transcript:
                self.text_renderer.render_multiline_text(
                    column_surface, last_transcript, (content_rect.x, content_rect.y),
                    content_rect.width, Palette.WHITE, 'normal'
                )
        else:
            # Show AI responses
            llm_stream = self.state.get("llm_stream", "")
            if llm_stream:
                self.text_renderer.render_multiline_text(
                    column_surface, llm_stream, (content_rect.x, content_rect.y),
                    content_rect.width, Palette.WHITE, 'normal'
                )
        
        surface.blit(column_surface, column_rect)
    
    def _render_bottom_interface(self, surface: pygame.Surface):
        """Render bottom control interface."""
        bottom_y = Config.SCREEN_HEIGHT - 120
        
        # Microphone orb
        orb_center = (Config.SCREEN_WIDTH // 2, bottom_y + 30)
        orb_radius = 25
        
        # Orb background
        is_listening = self.state.get("voice_listening", False)
        orb_color = Palette.CYAN if is_listening else Palette.WHITE
        
        pygame.draw.circle(surface, orb_color, orb_center, orb_radius)
        pygame.draw.circle(surface, Palette.BLACK, orb_center, orb_radius - 3)
        
        # Microphone icon
        pygame.draw.circle(surface, orb_color, orb_center, 8, 2)
        pygame.draw.line(surface, orb_color, 
                        (orb_center[0], orb_center[1] + 8),
                        (orb_center[0], orb_center[1] + 15), 2)
        
        # Instructions
        instruction_text = "HOLD SPACE TO SPEAK"
        instruction_surface = self.font_manager.get_font('normal').render(instruction_text, True, Palette.WHITE)
        instruction_x = Config.SCREEN_WIDTH // 2 - instruction_surface.get_width() // 2
        surface.blit(instruction_surface, (instruction_x, bottom_y + 70))
        
        # Context panel (left)
        context_rect = pygame.Rect(50, bottom_y, 200, 100)
        self._render_context_panel(surface, context_rect)
        
        # Voice settings panel (right)
        settings_rect = pygame.Rect(Config.SCREEN_WIDTH - 250, bottom_y, 200, 100)
        self._render_voice_settings_panel(surface, settings_rect)
        
        # Network status (bottom bar)
        self._render_network_status_bar(surface)
    
    def _render_context_panel(self, surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render conversation context panel."""
        # Panel background
        panel_surface = pygame.Surface((panel_rect.width, panel_rect.height), pygame.SRCALPHA)
        panel_surface.fill((*Palette.INK, 200))
        pygame.draw.rect(panel_surface, Palette.GRID, (0, 0, panel_rect.width, panel_rect.height), 1)
        
        # Title
        title_font = self.font_manager.get_font('small')
        title_surface = title_font.render("CONTEXT", True, Palette.AMBER)
        panel_surface.blit(title_surface, (5, 5))
        
        # Context info
        context_lines = [
            "SESSION: ACTIVE",
            "MODE: BRAINSTORM",
            "DEPTH: NEURAL"
        ]
        
        info_font = self.font_manager.get_font('micro')
        y_pos = 25
        
        for line in context_lines:
            line_surface = info_font.render(line, True, Palette.LIGHT_GRAY)
            panel_surface.blit(line_surface, (5, y_pos))
            y_pos += info_font.get_height() + 2
        
        surface.blit(panel_surface, panel_rect)
    
    def _render_voice_settings_panel(self, surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render voice settings panel."""
        # Panel background
        panel_surface = pygame.Surface((panel_rect.width, panel_rect.height), pygame.SRCALPHA)
        panel_surface.fill((*Palette.INK, 200))
        pygame.draw.rect(panel_surface, Palette.GRID, (0, 0, panel_rect.width, panel_rect.height), 1)
        
        # Title
        title_font = self.font_manager.get_font('small')
        title_surface = title_font.render("VOICE SETTINGS", True, Palette.CYAN)
        panel_surface.blit(title_surface, (5, 5))
        
        # Settings info
        settings_lines = [
            "RATE: OPTIMAL",
            "CLARITY: HIGH", 
            "RESPONSE: INSTANT"
        ]
        
        info_font = self.font_manager.get_font('micro')
        y_pos = 25
        
        for line in settings_lines:
            line_surface = info_font.render(line, True, Palette.LIGHT_GRAY)
            panel_surface.blit(line_surface, (5, y_pos))
            y_pos += info_font.get_height() + 2
        
        surface.blit(panel_surface, panel_rect)
    
    def _render_network_status_bar(self, surface: pygame.Surface):
        """Render bottom network status bar."""
        bar_rect = pygame.Rect(0, Config.SCREEN_HEIGHT - 25, Config.SCREEN_WIDTH, 25)
        
        # Bar background
        bar_surface = pygame.Surface((bar_rect.width, bar_rect.height), pygame.SRCALPHA)
        bar_surface.fill((*Palette.BLACK, 180))
        
        # Network status
        internet_up = self.state.get("internet_up", True)
        ping_ms = self.state.get("ping_ms", 0.0)
        
        status_text = f"NETWORK: {'ONLINE' if internet_up else 'OFFLINE'} | LATENCY: {ping_ms:.0f}ms"
        status_color = Palette.CYAN if internet_up else Palette.ALERT
        
        status_font = self.font_manager.get_font('small')
        status_surface = status_font.render(status_text, True, status_color)
        bar_surface.blit(status_surface, (20, 5))
        
        # System resources
        cpu_usage = self.state.get("cpu_usage", 0.0)
        ram_usage = self.state.get("ram_usage", 0.0)
        
        resources_text = f"CPU: {cpu_usage:.0f}% | RAM: {ram_usage:.0f}%"
        resources_surface = status_font.render(resources_text, True, Palette.WHITE)
        resources_x = bar_rect.width - resources_surface.get_width() - 20
        bar_surface.blit(resources_surface, (resources_x, 5))
        
        surface.blit(bar_surface, bar_rect)
    
    def _render_exit_button(self, surface: pygame.Surface):
        """Render ESC to exit button."""
        exit_font = self.font_manager.get_font('small')
        exit_text = "ESC TO EXIT"
        exit_surface = exit_font.render(exit_text, True, Palette.ALERT)
        
        exit_x = Config.SCREEN_WIDTH - exit_surface.get_width() - 20
        exit_y = 20
        
        # Background
        exit_bg_rect = pygame.Rect(exit_x - 5, exit_y - 2, 
                                  exit_surface.get_width() + 10, 
                                  exit_surface.get_height() + 4)
        
        exit_bg_surface = pygame.Surface((exit_bg_rect.width, exit_bg_rect.height), pygame.SRCALPHA)
        exit_bg_surface.fill((*Palette.BLACK, 180))
        surface.blit(exit_bg_surface, exit_bg_rect)
        
        surface.blit(exit_surface, (exit_x, exit_y))
    
    def _on_toggle(self, event_data):
        """Handle brainstorming mode toggle."""
        self.set_active(not self.active)
    
    def _on_voice_input(self, event_data):
        """Handle voice input in brainstorming mode."""
        if self.active:
            text = event_data.get("text", "")
            if text.strip():
                self.conversation_history.append({
                    "type": "user",
                    "text": text,
                    "timestamp": time.time()
                })
    
    def _on_audio_data(self, event_data):
        """Handle audio data for waveform visualization."""
        # Audio data is processed in update() method
        pass

class HudsonActivityOverlay:
    """Semi-transparent Hudson activity overlay."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        self.event_bus = event_bus
        self.state = state
        self.font_manager = font_manager
        
        # Overlay state
        self.visible = False
        self.activity_log = deque(maxlen=50)
        
        # Subscribe to Hudson activity events
        self.event_bus.subscribe("hudson_activity", self._on_hudson_activity)
        self.event_bus.subscribe("hudson_overlay_toggle", self._on_toggle)
    
    def set_visible(self, visible: bool):
        """Set overlay visibility."""
        self.visible = visible
    
    def render(self, surface: pygame.Surface):
        """Render Hudson activity overlay."""
        if not self.visible:
            return
        
        # Overlay dimensions
        overlay_width = 600
        overlay_height = 400
        overlay_x = (Config.SCREEN_WIDTH - overlay_width) // 2
        overlay_y = (Config.SCREEN_HEIGHT - overlay_height) // 2
        
        # Semi-transparent background
        overlay_surface = pygame.Surface((overlay_width, overlay_height), pygame.SRCALPHA)
        overlay_surface.fill((*Palette.BLACK, 200))
        
        # Border
        pygame.draw.rect(overlay_surface, Palette.AMBER, 
                        (0, 0, overlay_width, overlay_height), 2)
        
        # Header
        header_font = self.font_manager.get_font('medium')
        header_text = header_font.render("HUDSON ACTIVITY LOG", True, Palette.AMBER)
        header_x = (overlay_width - header_text.get_width()) // 2
        overlay_surface.blit(header_text, (header_x, 10))
        
        # Activity log
        self._render_activity_log(overlay_surface, overlay_width, overlay_height)
        
        # Close instruction
        close_font = self.font_manager.get_font('small')
        close_text = close_font.render("Press H to close", True, Palette.LIGHT_GRAY)
        close_x = overlay_width - close_text.get_width() - 10
        overlay_surface.blit(close_text, (close_x, overlay_height - 25))
        
        surface.blit(overlay_surface, (overlay_x, overlay_y))
    
    def _render_activity_log(self, overlay_surface: pygame.Surface, 
                           overlay_width: int, overlay_height: int):
        """Render Hudson's current activities."""
        # Get Hudson activity data
        github_status = self.state.get("github_activity", "Monitoring repositories...")
        rss_status = self.state.get("rss_activity", "Scraping news sources...")
        social_status = self.state.get("social_activity", "Checking social feeds...")
        
        # Current activities
        current_activities = [
            f"GitHub Monitor: {github_status}",
            f"News Scraper: {rss_status}",  
            f"Social Monitor: {social_status}",
            "Hardware Monitor: Active",
            "Network Monitor: Active",
            "Audio Processing: Active"
        ]
        
        # Render activity list
        font = self.font_manager.get_font('normal')
        y_pos = 40
        
        for activity in current_activities:
            # Status indicator
            indicator_color = Palette.CYAN
            pygame.draw.circle(overlay_surface, indicator_color, (20, y_pos + 8), 3)
            
            # Activity text
            activity_surface = font.render(activity, True, Palette.WHITE)
            overlay_surface.blit(activity_surface, (35, y_pos))
            
            y_pos += font.get_height() + 5
        
        # Recent activity log
        if self.activity_log:
            log_y = y_pos + 20
            log_font = self.font_manager.get_font('small')
            
            log_header = log_font.render("RECENT ACTIVITY:", True, Palette.AMBER)
            overlay_surface.blit(log_header, (15, log_y))
            log_y += log_header.get_height() + 5
            
            for entry in list(self.activity_log)[-10:]:  # Show last 10 entries
                timestamp = entry.get('timestamp', '')
                message = entry.get('message', '')
                
                log_text = f"{timestamp}: {message}"
                if len(log_text) > 70:
                    log_text = log_text[:67] + "..."
                
                log_surface = log_font.render(log_text, True, Palette.LIGHT_GRAY)
                overlay_surface.blit(log_surface, (15, log_y))
                log_y += log_font.get_height() + 2
                
                if log_y > overlay_height - 40:  # Stop if reaching bottom
                    break
    
    def _on_hudson_activity(self, event_data):
        """Handle Hudson activity updates."""
        activity = {
            'timestamp': time.strftime("%H:%M:%S"),
            'message': event_data.get('message', 'Unknown activity'),
            'category': event_data.get('category', 'general')
        }
        
        self.activity_log.append(activity)
    
    def _on_toggle(self, event_data):
        """Handle overlay toggle."""
        self.set_visible(not self.visible)

class SocialReplacementPanel:
    """Replacement panel for social app interfaces."""
    
    def __init__(self, event_bus: EventBus, state: HermesState, font_manager: FontManager):
        self.event_bus = event_bus
        self.state = state
        self.font_manager = font_manager
        
        # Panel state
        self.active = False
        self.current_platform = None
        self.current_message_data = None
        
        # Auto-return timer
        self.auto_return_timer = 0.0
        self.auto_return_delay = 3.0  # 3 seconds after message sent
        
        # Subscribe to events
        self.event_bus.subscribe("social_message_clicked", self._on_message_clicked)
        self.event_bus.subscribe("message_sent", self._on_message_sent)
    
    def set_active(self, active: bool, platform: str = None, message_data: Dict = None):
        """Set social panel active state."""
        self.active = active
        self.current_platform = platform
        self.current_message_data = message_data
        self.auto_return_timer = 0.0
    
    def update(self, delta_time: float):
        """Update social panel."""
        if self.active:
            self.auto_return_timer += delta_time
    
    def render(self, surface: pygame.Surface):
        """Render social app replacement interface."""
        if not self.active:
            return
        
        # Use left viewport area
        panel_rect = pygame.Rect(0, Config.HEADER_HEIGHT,
                               Config.LEFT_VIEWPORT_WIDTH, 
                               Config.LEFT_VIEWPORT_HEIGHT)
        
        # Panel background
        panel_surface = pygame.Surface((panel_rect.width, panel_rect.height))
        panel_surface.fill(Palette.BLACK)
        
        # Platform-specific rendering
        if self.current_platform == "whatsapp":
            self._render_whatsapp_interface(panel_surface, panel_rect)
        elif self.current_platform == "instagram":
            self._render_instagram_interface(panel_surface, panel_rect)
        elif self.current_platform == "gmail":
            self._render_gmail_interface(panel_surface, panel_rect)
        else:
            self._render_generic_interface(panel_surface, panel_rect)
        
        # Return button
        self._render_return_button(panel_surface, panel_rect)
        
        surface.blit(panel_surface, panel_rect)
    
    def _render_whatsapp_interface(self, panel_surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render WhatsApp-style interface."""
        # Header
        header_font = self.font_manager.get_font('medium')
        header_text = f"WhatsApp - {self.current_message_data.get('sender', 'Contact')}"
        header_surface = header_font.render(header_text, True, Palette.CYAN)
        panel_surface.blit(header_surface, (20, 20))
        
        # Message preview
        message_font = self.font_manager.get_font('normal')
        message_preview = self.current_message_data.get('preview', 'No message preview')
        
        # Wrap message text
        max_width = panel_rect.width - 40
        wrapped_lines = []
        words = message_preview.split(' ')
        current_line = ""
        
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if message_font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    wrapped_lines.append(current_line)
                current_line = word
        if current_line:
            wrapped_lines.append(current_line)
        
        y_pos = 60
        for line in wrapped_lines[:10]:  # Limit lines
            line_surface = message_font.render(line, True, Palette.WHITE)
            panel_surface.blit(line_surface, (20, y_pos))
            y_pos += message_font.get_height() + 2
        
        # Orb menu representation
        self._render_orb_menu(panel_surface, panel_rect)
    
    def _render_instagram_interface(self, panel_surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render Instagram-style interface."""
        # Similar to WhatsApp but with Instagram branding
        header_font = self.font_manager.get_font('medium')
        header_text = f"Instagram DM - {self.current_message_data.get('sender', 'User')}"
        header_surface = header_font.render(header_text, True, Palette.AMBER)
        panel_surface.blit(header_surface, (20, 20))
        
        # Message content
        message_font = self.font_manager.get_font('normal')
        message_text = self.current_message_data.get('preview', '[Media Message]')
        message_surface = message_font.render(message_text, True, Palette.WHITE)
        panel_surface.blit(message_surface, (20, 60))
        
        # Orb menu
        self._render_orb_menu(panel_surface, panel_rect)
    
    def _render_gmail_interface(self, panel_surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render Gmail-style interface."""
        # Email header
        header_font = self.font_manager.get_font('medium')
        subject = self.current_message_data.get('subject', 'No Subject')
        header_text = f"Gmail - {subject[:40]}"
        header_surface = header_font.render(header_text, True, Palette.WHITE)
        panel_surface.blit(header_surface, (20, 20))
        
        # Sender
        sender_font = self.font_manager.get_font('small')
        sender_text = f"From: {self.current_message_data.get('sender', 'Unknown')}"
        sender_surface = sender_font.render(sender_text, True, Palette.LIGHT_GRAY)
        panel_surface.blit(sender_surface, (20, 50))
        
        # Email snippet
        snippet_font = self.font_manager.get_font('normal')
        snippet_text = self.current_message_data.get('snippet', 'Email content preview...')
        
        # Wrap email content
        max_width = panel_rect.width - 40
        y_pos = 80
        
        for line in snippet_text.split('\n')[:15]:  # Limit lines
            if snippet_font.size(line)[0] <= max_width:
                line_surface = snippet_font.render(line, True, Palette.WHITE)
                panel_surface.blit(line_surface, (20, y_pos))
            else:
                # Word wrap long lines
                words = line.split(' ')
                current_line = ""
                
                for word in words:
                    test_line = f"{current_line} {word}".strip()
                    if snippet_font.size(test_line)[0] <= max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            line_surface = snippet_font.render(current_line, True, Palette.WHITE)
                            panel_surface.blit(line_surface, (20, y_pos))
                            y_pos += snippet_font.get_height()
                        current_line = word
                
                if current_line:
                    line_surface = snippet_font.render(current_line, True, Palette.WHITE)
                    panel_surface.blit(line_surface, (20, y_pos))
            
            y_pos += snippet_font.get_height() + 2
        
        # Orb menu
        self._render_orb_menu(panel_surface, panel_rect)
    
    def _render_generic_interface(self, panel_surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render generic social interface."""
        # Generic header
        header_font = self.font_manager.get_font('medium')
        header_text = "Social Message Interface"
        header_surface = header_font.render(header_text, True, Palette.WHITE)
        panel_surface.blit(header_surface, (20, 20))
        
        # Loading message
        loading_font = self.font_manager.get_font('normal')
        loading_text = "Loading social interface..."
        loading_surface = loading_font.render(loading_text, True, Palette.LIGHT_GRAY)
        panel_surface.blit(loading_surface, (20, 60))
    
    def _render_orb_menu(self, panel_surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render floating orb menu with response options."""
        # Orb position (bottom right corner)
        orb_x = panel_rect.width - 100
        orb_y = panel_rect.height - 100
        orb_radius = 30
        
        # Orb background
        pygame.draw.circle(panel_surface, Palette.CYAN, (orb_x, orb_y), orb_radius)
        pygame.draw.circle(panel_surface, Palette.BLACK, (orb_x, orb_y), orb_radius - 3)
        
        # Orb center indicator
        pygame.draw.circle(panel_surface, Palette.WHITE, (orb_x, orb_y), 5)
        
        # Menu options (when expanded)
        menu_font = self.font_manager.get_font('small')
        menu_options = [
            "RESPOND",
            "DRAFT", 
            "CHAT STYLE"
        ]
        
        # Render menu options around orb
        angle_step = 2 * math.pi / len(menu_options)
        for i, option in enumerate(menu_options):
            angle = i * angle_step
            option_x = orb_x + int(60 * math.cos(angle))
            option_y = orb_y + int(60 * math.sin(angle))
            
            # Option background
            option_surface = menu_font.render(option, True, Palette.WHITE)
            option_rect = option_surface.get_rect(center=(option_x, option_y))
            
            # Background rectangle
            bg_rect = option_rect.inflate(10, 4)
            pygame.draw.rect(panel_surface, Palette.INK, bg_rect)
            pygame.draw.rect(panel_surface, Palette.GRID, bg_rect, 1)
            
            panel_surface.blit(option_surface, option_rect)
    
    def _render_return_button(self, panel_surface: pygame.Surface, panel_rect: pygame.Rect):
        """Render return to normal view button."""
        button_font = self.font_manager.get_font('small')
        button_text = "RETURN TO TERRAIN"
        button_surface = button_font.render(button_text, True, Palette.ALERT)
        
        button_x = 20
        button_y = panel_rect.height - 30
        
        # Button background
        button_rect = pygame.Rect(button_x - 5, button_y - 2,
                                button_surface.get_width() + 10,
                                button_surface.get_height() + 4)
        
        pygame.draw.rect(panel_surface, Palette.INK, button_rect)
        pygame.draw.rect(panel_surface, Palette.ALERT, button_rect, 1)
        
        panel_surface.blit(button_surface, (button_x, button_y))
    
    def _on_message_clicked(self, event_data):
        """Handle social message click."""
        platform = event_data.get("platform")
        message_data = event_data.get("message_data")
        
        if platform and message_data:
            self.set_active(True, platform, message_data)
    
    def _on_message_sent(self, event_data):
        """Handle message sent event for auto-return."""
        if self.active:
            # Start auto-return timer
            self.auto_return_timer = 0.0
            
            # Check if timer expires
            if hasattr(self, '_return_timer_thread'):
                return
            
            def return_timer():
                import threading
                time.sleep(self.auto_return_delay)
                if self.auto_return_timer >= self.auto_return_delay:
                    self.set_active(False)
            
            self._return_timer_thread = threading.Thread(target=return_timer, daemon=True)
            self._return_timer_thread.start()

# Initialize all panels function
def initialize_panels(event_bus: EventBus, state: HermesState, 
                     font_manager: FontManager) -> Dict[str, Any]:
    """Initialize all UI panels and return panel manager."""
    if not PYGAME_AVAILABLE:
        return {}
    
    # Initialize all panel renderers
    panels = {
        'header_bar': HeaderBarRenderer(event_bus, state, font_manager),
        'terrain': TerrainRenderer(event_bus, state, font_manager),
        'globe': GlobeRenderer(event_bus, state, font_manager),
        'news_feed': NewsFeedRenderer(event_bus, state, font_manager),
        'personal_monitor': PersonalMonitorRenderer(event_bus, state, font_manager),
        'diagnostics': DiagnosticPanelsRenderer(event_bus, state, font_manager),
        'brainstorming': BrainstormingModeRenderer(event_bus, state, font_manager),
        'hudson_overlay': HudsonActivityOverlay(event_bus, state, font_manager),
        'social_replacement': SocialReplacementPanel(event_bus, state, font_manager)
    }
    
    return panels

# Export all panel classes
__all__ = [
    'HeaderBarRenderer', 'TerrainRenderer', 'GlobeRenderer', 'NewsFeedRenderer',
    'PersonalMonitorRenderer', 'DiagnosticPanelsRenderer', 'BrainstormingModeRenderer',
    'HudsonActivityOverlay', 'SocialReplacementPanel', 'initialize_panels'
]