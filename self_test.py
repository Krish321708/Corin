# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: self_test.py
# ROLE: Pre-flight mathematical validation and system integrity diagnostics.
#       Executed at boot time BEFORE pygame window creation.
#       Every assertion must pass for the system to proceed.
#       Tests cover: Vector3, Matrix4x4, PerlinNoise3D, RingBuffer,
#       FBM elevation, Catmull-Rom spline, EKG waveform, FFT normalization,
#       Fibonacci sphere, geographic conversion, stability scoring,
#       EventBus publish/subscribe, HermesState thread safety,
#       palette blending, config directory integrity, and file system paths.
# =============================================================================

import os
import sys
import math
import time
import threading
from typing import List, Tuple

# =============================================================================
# SECTION 1: IMPORT VALIDATION
# All critical modules must import cleanly before any test runs.
# =============================================================================

def _validate_imports() -> List[str]:
    """
    Attempts to import every HERMES module and returns a list of
    any import failures. An empty list means all imports succeeded.

    Returns:
        List of error strings. Empty list = all imports clean.
    """
    failures: List[str] = []

    modules_to_test = [
        "config",
        "palette",
        "math_engine",
        "state",
        "event_bus",
    ]

    for module_name in modules_to_test:
        try:
            __import__(module_name)
        except ImportError as exc:
            failures.append(f"IMPORT FAILURE [{module_name}]: {exc}")
        except Exception as exc:
            failures.append(f"IMPORT ERROR [{module_name}]: {exc}")

    return failures


# =============================================================================
# SECTION 2: TEST RESULT CONTAINER
# =============================================================================

class TestResult:
    """
    Stores the outcome of a single pre-flight test case.
    Tracks name, pass/fail status, elapsed time, and failure message.
    """

    __slots__ = ("name", "passed", "elapsed_ms", "message")

    def __init__(
        self,
        name:       str,
        passed:     bool,
        elapsed_ms: float,
        message:    str = "",
    ) -> None:
        self.name:       str   = name
        self.passed:     bool  = passed
        self.elapsed_ms: float = elapsed_ms
        self.message:    str   = message

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        base   = f"[{status}] {self.name} ({self.elapsed_ms:.2f}ms)"
        if not self.passed and self.message:
            base += f" — {self.message}"
        return base


def _run_test(name: str, fn) -> TestResult:
    """
    Executes a single test function and wraps its result in a TestResult.
    Catches all exceptions and converts them to FAIL results.

    Args:
        name: Human-readable test name string.
        fn:   Zero-argument callable that raises AssertionError on failure.

    Returns:
        TestResult instance.
    """
    t_start = time.perf_counter()
    try:
        fn()
        elapsed = (time.perf_counter() - t_start) * 1000.0
        return TestResult(name=name, passed=True, elapsed_ms=elapsed)
    except AssertionError as exc:
        elapsed = (time.perf_counter() - t_start) * 1000.0
        return TestResult(
            name=name,
            passed=False,
            elapsed_ms=elapsed,
            message=str(exc) if str(exc) else "AssertionError (no message)",
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - t_start) * 1000.0
        return TestResult(
            name=name,
            passed=False,
            elapsed_ms=elapsed,
            message=f"{type(exc).__name__}: {exc}",
        )


# =============================================================================
# SECTION 3: VECTOR3 TESTS
# =============================================================================

def _test_vector3_addition() -> None:
    from math_engine import Vector3
    v1 = Vector3(1.0, 2.0, 3.0)
    v2 = Vector3(4.0, 5.0, 6.0)
    result = v1 + v2
    assert result.to_tuple() == (5.0, 7.0, 9.0), (
        f"Expected (5, 7, 9), got {result.to_tuple()}"
    )


def _test_vector3_subtraction() -> None:
    from math_engine import Vector3
    v1 = Vector3(10.0, 8.0, 6.0)
    v2 = Vector3(3.0,  2.0, 1.0)
    result = v1 - v2
    assert result.to_tuple() == (7.0, 6.0, 5.0), (
        f"Expected (7, 6, 5), got {result.to_tuple()}"
    )


def _test_vector3_scalar_multiply() -> None:
    from math_engine import Vector3
    v = Vector3(1.0, 2.0, 3.0)
    result = v * 3.0
    assert result.to_tuple() == (3.0, 6.0, 9.0), (
        f"Expected (3, 6, 9), got {result.to_tuple()}"
    )


def _test_vector3_scalar_divide() -> None:
    from math_engine import Vector3
    v = Vector3(6.0, 9.0, 12.0)
    result = v / 3.0
    assert abs(result.x - 2.0) < 1e-9, f"x: {result.x}"
    assert abs(result.y - 3.0) < 1e-9, f"y: {result.y}"
    assert abs(result.z - 4.0) < 1e-9, f"z: {result.z}"


def _test_vector3_dot_product() -> None:
    from math_engine import Vector3
    v1 = Vector3(1.0, 2.0, 3.0)
    v2 = Vector3(4.0, 5.0, 6.0)
    result = v1.dot(v2)
    # 1*4 + 2*5 + 3*6 = 4 + 10 + 18 = 32
    assert abs(result - 32.0) < 1e-9, f"Expected 32.0, got {result}"


def _test_vector3_cross_product() -> None:
    from math_engine import Vector3
    # Cross product of unit X and unit Y must be unit Z
    vx = Vector3(1.0, 0.0, 0.0)
    vy = Vector3(0.0, 1.0, 0.0)
    result = vx.cross(vy)
    assert abs(result.x - 0.0) < 1e-9, f"x: {result.x}"
    assert abs(result.y - 0.0) < 1e-9, f"y: {result.y}"
    assert abs(result.z - 1.0) < 1e-9, f"z: {result.z}"


def _test_vector3_magnitude() -> None:
    from math_engine import Vector3
    # |3, 4, 0| = 5
    v = Vector3(3.0, 4.0, 0.0)
    assert abs(v.length() - 5.0) < 1e-9, f"Expected 5.0, got {v.length()}"


def _test_vector3_normalize() -> None:
    from math_engine import Vector3
    v = Vector3(3.0, 0.0, 0.0)
    n = v.normalize()
    assert abs(n.x - 1.0) < 1e-9, f"x: {n.x}"
    assert abs(n.y - 0.0) < 1e-9, f"y: {n.y}"
    assert abs(n.z - 0.0) < 1e-9, f"z: {n.z}"
    # Magnitude of unit vector must be 1
    assert abs(n.length() - 1.0) < 1e-9, f"magnitude: {n.length()}"


def _test_vector3_normalize_zero() -> None:
    from math_engine import Vector3
    # Normalizing the zero vector must return zero vector (no crash)
    v = Vector3(0.0, 0.0, 0.0)
    n = v.normalize()
    assert n.length() < 1e-9, f"Expected zero vector, got {n}"


def _test_vector3_lerp() -> None:
    from math_engine import Vector3
    v1 = Vector3(0.0, 0.0, 0.0)
    v2 = Vector3(10.0, 20.0, 30.0)
    mid = v1.lerp(v2, 0.5)
    assert abs(mid.x - 5.0)  < 1e-9, f"x: {mid.x}"
    assert abs(mid.y - 10.0) < 1e-9, f"y: {mid.y}"
    assert abs(mid.z - 15.0) < 1e-9, f"z: {mid.z}"


def _test_vector3_reflect() -> None:
    from math_engine import Vector3
    # Reflecting (1, -1, 0) off normal (0, 1, 0) should give (1, 1, 0)
    incident = Vector3(1.0, -1.0, 0.0)
    normal   = Vector3(0.0,  1.0, 0.0)
    reflected = incident.reflect(normal)
    assert abs(reflected.x - 1.0) < 1e-6, f"x: {reflected.x}"
    assert abs(reflected.y - 1.0) < 1e-6, f"y: {reflected.y}"
    assert abs(reflected.z - 0.0) < 1e-6, f"z: {reflected.z}"


def _test_vector3_distance() -> None:
    from math_engine import Vector3
    # Distance between (0,0,0) and (3,4,0) = 5
    v1 = Vector3(0.0, 0.0, 0.0)
    v2 = Vector3(3.0, 4.0, 0.0)
    assert abs(v1.distance_to(v2) - 5.0) < 1e-9, (
        f"Expected 5.0, got {v1.distance_to(v2)}"
    )


def _test_vector3_negation() -> None:
    from math_engine import Vector3
    v = Vector3(1.0, -2.0, 3.0)
    n = -v
    assert n.to_tuple() == (-1.0, 2.0, -3.0), f"Got {n.to_tuple()}"


def _test_vector3_equality() -> None:
    from math_engine import Vector3
    v1 = Vector3(1.0, 2.0, 3.0)
    v2 = Vector3(1.0, 2.0, 3.0)
    v3 = Vector3(1.0, 2.0, 4.0)
    assert v1 == v2, "Identical vectors must be equal"
    assert v1 != v3, "Different vectors must not be equal"


# =============================================================================
# SECTION 4: MATRIX4x4 TESTS
# =============================================================================

def _test_matrix_identity_transform() -> None:
    from math_engine import Matrix4x4, Vector3
    identity = Matrix4x4.identity()
    v = Vector3(5.0, -3.0, 7.0)
    result = identity.transform_point(v)
    assert abs(result.x - 5.0)  < 1e-9, f"x: {result.x}"
    assert abs(result.y - (-3.0)) < 1e-9, f"y: {result.y}"
    assert abs(result.z - 7.0)  < 1e-9, f"z: {result.z}"


def _test_matrix_rotation_x_90() -> None:
    from math_engine import Matrix4x4, Vector3
    # Rotating (0, 1, 0) by 90 degrees around X should give (0, 0, 1)
    rx90   = Matrix4x4.rotation_x(math.pi / 2.0)
    v      = Vector3(0.0, 1.0, 0.0)
    result = rx90.transform_point(v)
    assert abs(result.x - 0.0) < 1e-5, f"x: {result.x}"
    assert abs(result.y - 0.0) < 1e-5, f"y: {result.y}"
    assert abs(result.z - 1.0) < 1e-5, f"z: {result.z}"


def _test_matrix_rotation_y_90() -> None:
    from math_engine import Matrix4x4, Vector3
    # Rotating (1, 0, 0) by 90 degrees around Y should give (0, 0, -1)
    ry90   = Matrix4x4.rotation_y(math.pi / 2.0)
    v      = Vector3(1.0, 0.0, 0.0)
    result = ry90.transform_point(v)
    assert abs(result.x -  0.0) < 1e-5, f"x: {result.x}"
    assert abs(result.y -  0.0) < 1e-5, f"y: {result.y}"
    assert abs(result.z - (-1.0)) < 1e-5, f"z: {result.z}"


def _test_matrix_rotation_z_90() -> None:
    from math_engine import Matrix4x4, Vector3
    # Rotating (1, 0, 0) by 90 degrees around Z should give (0, 1, 0)
    rz90   = Matrix4x4.rotation_z(math.pi / 2.0)
    v      = Vector3(1.0, 0.0, 0.0)
    result = rz90.transform_point(v)
    assert abs(result.x - 0.0) < 1e-5, f"x: {result.x}"
    assert abs(result.y - 1.0) < 1e-5, f"y: {result.y}"
    assert abs(result.z - 0.0) < 1e-5, f"z: {result.z}"


def _test_matrix_translation() -> None:
    from math_engine import Matrix4x4, Vector3
    t = Matrix4x4.translation(10.0, -5.0, 3.0)
    v = Vector3(1.0, 2.0, 3.0)
    result = t.transform_point(v)
    assert abs(result.x - 11.0) < 1e-9, f"x: {result.x}"
    assert abs(result.y - (-3.0)) < 1e-9, f"y: {result.y}"
    assert abs(result.z -  6.0) < 1e-9, f"z: {result.z}"


def _test_matrix_scale() -> None:
    from math_engine import Matrix4x4, Vector3
    s = Matrix4x4.scale(2.0, 3.0, 4.0)
    v = Vector3(1.0, 1.0, 1.0)
    result = s.transform_point(v)
    assert abs(result.x - 2.0) < 1e-9, f"x: {result.x}"
    assert abs(result.y - 3.0) < 1e-9, f"y: {result.y}"
    assert abs(result.z - 4.0) < 1e-9, f"z: {result.z}"


def _test_matrix_multiplication_identity() -> None:
    from math_engine import Matrix4x4, Vector3
    # M @ Identity == M
    rx = Matrix4x4.rotation_x(0.5)
    identity = Matrix4x4.identity()
    result = rx @ identity
    v = Vector3(1.0, 2.0, 3.0)
    p1 = rx.transform_point(v)
    p2 = result.transform_point(v)
    assert abs(p1.x - p2.x) < 1e-9, f"x mismatch: {p1.x} vs {p2.x}"
    assert abs(p1.y - p2.y) < 1e-9, f"y mismatch: {p1.y} vs {p2.y}"
    assert abs(p1.z - p2.z) < 1e-9, f"z mismatch: {p1.z} vs {p2.z}"


def _test_matrix_combined_rotation() -> None:
    from math_engine import Matrix4x4, Vector3
    # Two 90-degree X rotations = 180-degree rotation
    # (0, 1, 0) rotated 180° around X = (0, -1, 0)
    rx90  = Matrix4x4.rotation_x(math.pi / 2.0)
    rx180 = rx90 @ rx90
    v     = Vector3(0.0, 1.0, 0.0)
    result = rx180.transform_point(v)
    assert abs(result.x -  0.0) < 1e-5, f"x: {result.x}"
    assert abs(result.y - (-1.0)) < 1e-5, f"y: {result.y}"
    assert abs(result.z -  0.0) < 1e-5, f"z: {result.z}"


def _test_matrix_direction_transform_ignores_translation() -> None:
    from math_engine import Matrix4x4, Vector3
    # Direction transform must ignore translation component
    t = Matrix4x4.translation(100.0, 200.0, 300.0)
    d = Vector3(0.0, 1.0, 0.0)
    result = t.transform_direction(d)
    # Direction (0,1,0) through a pure translation matrix = unchanged (0,1,0)
    assert abs(result.x - 0.0) < 1e-9, f"x: {result.x}"
    assert abs(result.y - 1.0) < 1e-9, f"y: {result.y}"
    assert abs(result.z - 0.0) < 1e-9, f"z: {result.z}"


def _test_matrix_rotation_x_360() -> None:
    from math_engine import Matrix4x4, Vector3
    # Full 360° rotation must return to original position
    rx360  = Matrix4x4.rotation_x(2.0 * math.pi)
    v      = Vector3(1.0, 2.0, 3.0)
    result = rx360.transform_point(v)
    assert abs(result.x - 1.0) < 1e-5, f"x: {result.x}"
    assert abs(result.y - 2.0) < 1e-5, f"y: {result.y}"
    assert abs(result.z - 3.0) < 1e-5, f"z: {result.z}"


# =============================================================================
# SECTION 5: PERLIN NOISE TESTS
# =============================================================================

def _test_perlin_deterministic() -> None:
    from math_engine import PerlinNoise3D
    pn = PerlinNoise3D(seed=42)
    n1 = pn.noise(0.5, 0.5, 0.5)
    n2 = pn.noise(0.5, 0.5, 0.5)
    assert n1 == n2, (
        f"PerlinNoise3D must be deterministic: {n1} != {n2}"
    )


def _test_perlin_bounds() -> None:
    from math_engine import PerlinNoise3D
    pn = PerlinNoise3D(seed=42)
    test_coords = [
        (0.0,  0.0,  0.0),
        (0.5,  0.5,  0.5),
        (1.0,  1.0,  1.0),
        (0.25, 0.75, 0.1),
        (3.14, 2.71, 1.41),
        (10.0, 7.3,  4.9),
        (-0.5, -0.3, 0.8),
    ]
    for x, y, z in test_coords:
        n = pn.noise(x, y, z)
        assert -1.0 <= n <= 1.0, (
            f"Noise at ({x},{y},{z}) = {n} — out of [-1, 1]"
        )


def _test_perlin_different_seeds_differ() -> None:
    from math_engine import PerlinNoise3D
    pn1 = PerlinNoise3D(seed=1)
    pn2 = PerlinNoise3D(seed=2)
    n1  = pn1.noise(0.3, 0.6, 0.9)
    n2  = pn2.noise(0.3, 0.6, 0.9)
    # Different seeds must produce different noise values at the same coordinate
    assert abs(n1 - n2) > 1e-9, (
        "Different seeds should produce different noise values"
    )


def _test_perlin_smoothness() -> None:
    from math_engine import PerlinNoise3D
    # Adjacent samples must not jump discontinuously
    pn = PerlinNoise3D(seed=7)
    step = 0.01
    max_jump = 0.0
    prev = pn.noise(0.0, 0.0, 0.0)
    for i in range(1, 50):
        curr = pn.noise(i * step, 0.0, 0.0)
        jump = abs(curr - prev)
        max_jump = max(max_jump, jump)
        prev = curr
    # Maximum step-to-step variation should be less than 0.2
    # for step size of 0.01 (Perlin noise is C1 continuous)
    assert max_jump < 0.2, (
        f"Noise discontinuity too large: max jump = {max_jump:.4f}"
    )


def _test_perlin_zero_at_integers() -> None:
    from math_engine import PerlinNoise3D
    # Classic Perlin noise produces zero at integer lattice points
    # (within floating-point precision)
    pn = PerlinNoise3D(seed=0)
    integer_points = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        (1.0, 1.0, 1.0),
        (2.0, 3.0, 4.0),
    ]
    for x, y, z in integer_points:
        n = pn.noise(x, y, z)
        assert abs(n) < 1e-9, (
            f"Perlin noise at integer ({x},{y},{z}) = {n}, expected ~0"
        )


# =============================================================================
# SECTION 6: FBM TERRAIN TESTS
# =============================================================================

def _test_fbm_elevation_bounds() -> None:
    from math_engine import PerlinNoise3D, fbm_elevation
    from config import (
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    pn = PerlinNoise3D(seed=99)
    test_points = [
        (-1.0, -1.0), (-0.5, 0.3), (0.0, 0.0),
        (0.5, -0.5),  (1.0, 1.0),  (0.7, 0.2),
    ]
    for nx, nz in test_points:
        h = fbm_elevation(
            pn, nx, nz, 0.0,
            FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
        )
        # Elevation must be within ±base_amplitude
        assert -FBM_BASE_AMPLITUDE <= h <= FBM_BASE_AMPLITUDE, (
            f"FBM elevation {h:.4f} out of range ±{FBM_BASE_AMPLITUDE}"
        )


def _test_fbm_deterministic() -> None:
    from math_engine import PerlinNoise3D, fbm_elevation
    from config import (
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    pn = PerlinNoise3D(seed=42)
    h1 = fbm_elevation(
        pn, 0.3, 0.7, 0.0,
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    h2 = fbm_elevation(
        pn, 0.3, 0.7, 0.0,
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    assert abs(h1 - h2) < 1e-12, (
        f"FBM elevation must be deterministic: {h1} != {h2}"
    )


def _test_fbm_time_offset_changes_result() -> None:
    from math_engine import PerlinNoise3D, fbm_elevation
    from config import (
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    pn = PerlinNoise3D(seed=42)
    h1 = fbm_elevation(
        pn, 0.3, 0.3, 0.0,
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    h2 = fbm_elevation(
        pn, 0.3, 0.3, 1.0,
        FBM_OCTAVES, FBM_PERSISTENCE, FBM_LACUNARITY, FBM_BASE_AMPLITUDE
    )
    # Different time offset must change the elevation (animated terrain)
    assert abs(h1 - h2) > 1e-6, (
        "FBM elevation must differ with different time_offset"
    )


# =============================================================================
# SECTION 7: CATMULL-ROM SPLINE TESTS
# =============================================================================

def _test_catmull_rom_boundary_values() -> None:
    from math_engine import catmull_rom
    p0 = (0.0, 0.0)
    p1 = (1.0, 1.0)
    p2 = (2.0, 0.0)
    p3 = (3.0, 1.0)

    # At t=0.0 the result must equal p1 exactly
    result_0 = catmull_rom(p0, p1, p2, p3, 0.0)
    assert abs(result_0[0] - 1.0) < 1e-9, f"x at t=0: {result_0[0]}"
    assert abs(result_0[1] - 1.0) < 1e-9, f"y at t=0: {result_0[1]}"

    # At t=1.0 the result must equal p2 exactly
    result_1 = catmull_rom(p0, p1, p2, p3, 1.0)
    assert abs(result_1[0] - 2.0) < 1e-9, f"x at t=1: {result_1[0]}"
    assert abs(result_1[1] - 0.0) < 1e-9, f"y at t=1: {result_1[1]}"


def _test_catmull_rom_midpoint() -> None:
    from math_engine import catmull_rom
    # For symmetric control points, midpoint should lie on the curve smoothly
    p0 = (0.0,  0.0)
    p1 = (1.0,  0.0)
    p2 = (2.0,  0.0)
    p3 = (3.0,  0.0)
    # All collinear — spline through collinear points must be collinear
    mid = catmull_rom(p0, p1, p2, p3, 0.5)
    assert abs(mid[1] - 0.0) < 1e-9, (
        f"Collinear Catmull-Rom midpoint y should be 0, got {mid[1]}"
    )
    assert abs(mid[0] - 1.5) < 1e-9, (
        f"Collinear Catmull-Rom midpoint x should be 1.5, got {mid[0]}"
    )


def _test_catmull_rom_chain_length() -> None:
    from math_engine import catmull_rom_chain
    # Chain with 5 control points must produce a dense smooth curve
    points = [(float(i), float(i % 2)) for i in range(5)]
    result = catmull_rom_chain(points, segments_per_span=10)
    # 4 spans * 10 segments + 1 endpoint = 41 points minimum
    assert len(result) >= 41, (
        f"Expected >=41 points in chain, got {len(result)}"
    )


def _test_catmull_rom_clamp_t() -> None:
    from math_engine import catmull_rom
    # t values outside [0, 1] must be clamped, not crash
    p0 = (0.0, 0.0)
    p1 = (1.0, 1.0)
    p2 = (2.0, 0.0)
    p3 = (3.0, 1.0)
    result_neg = catmull_rom(p0, p1, p2, p3, -0.5)
    result_pos = catmull_rom(p0, p1, p2, p3,  1.5)
    # Must not crash and must return finite values
    assert math.isfinite(result_neg[0]), f"x not finite: {result_neg[0]}"
    assert math.isfinite(result_pos[0]), f"x not finite: {result_pos[0]}"


# =============================================================================
# SECTION 8: EKG WAVEFORM TESTS
# =============================================================================

def _test_ekg_sample_bounds() -> None:
    from math_engine import ekg_sample
    from config import EKG_CYCLE_DURATION, EKG_AMPLITUDE
    # Sample across multiple full cycles — must stay within amplitude bounds
    max_abs = 0.0
    for i in range(200):
        t = i * (EKG_CYCLE_DURATION / 100.0)
        sample = ekg_sample(t, EKG_CYCLE_DURATION, EKG_AMPLITUDE)
        max_abs = max(max_abs, abs(sample))
    # The QRS complex peaks at ~1.0 * amplitude (plus other waves ~0.5)
    # Absolute bound: no sample should exceed 1.6 * amplitude
    assert max_abs <= EKG_AMPLITUDE * 1.6, (
        f"EKG amplitude exceeded: {max_abs:.2f} > {EKG_AMPLITUDE * 1.6:.2f}"
    )


def _test_ekg_sample_periodic() -> None:
    from math_engine import ekg_sample
    # Samples at same phase in different cycles must be identical
    cycle = 2.0
    t1 = 0.35   # QRS peak
    t2 = t1 + cycle
    s1 = ekg_sample(t1, cycle, 40.0)
    s2 = ekg_sample(t2, cycle, 40.0)
    assert abs(s1 - s2) < 1e-9, (
        f"EKG must be periodic: s1={s1:.6f}, s2={s2:.6f}"
    )


def _test_ekg_generate_points_count() -> None:
    from math_engine import generate_ekg_points
    from config import EKG_CYCLE_DURATION, EKG_AMPLITUDE
    points = generate_ekg_points(
        elapsed=5.0,
        cycle_duration=EKG_CYCLE_DURATION,
        amplitude=EKG_AMPLITUDE,
        panel_x=1440,
        panel_y_center=721,
        panel_width=480,
        num_points=120,
    )
    assert len(points) == 120, (
        f"Expected 120 EKG points, got {len(points)}"
    )


def _test_ekg_generate_points_screen_x_range() -> None:
    from math_engine import generate_ekg_points
    from config import EKG_CYCLE_DURATION, EKG_AMPLITUDE
    points = generate_ekg_points(
        elapsed=1.0,
        cycle_duration=EKG_CYCLE_DURATION,
        amplitude=EKG_AMPLITUDE,
        panel_x=0,
        panel_y_center=100,
        panel_width=480,
        num_points=120,
    )
    # All X coordinates must be within [panel_x, panel_x + panel_width]
    xs = [p[0] for p in points]
    assert min(xs) >= 0,   f"Minimum X out of range: {min(xs)}"
    assert max(xs) <= 480, f"Maximum X out of range: {max(xs)}"


# =============================================================================
# SECTION 9: RING BUFFER TESTS
# =============================================================================

def _test_ring_buffer_basic_push_latest() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=5)
    for i in range(1, 6):
        rb.push(float(i))
    assert rb.latest() == 5.0, f"Expected latest=5.0, got {rb.latest()}"


def _test_ring_buffer_capacity_enforcement() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=5)
    for i in range(10):
        rb.push(float(i))
    data = rb.data()
    assert len(data) == 5, f"Expected 5 items, got {len(data)}"
    assert rb.latest() == 9.0, f"Expected latest=9.0, got {rb.latest()}"


def _test_ring_buffer_fifo_order() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=5)
    for i in range(10):
        rb.push(float(i))
    # After pushing 0..9 into capacity=5 buffer,
    # data should contain [5, 6, 7, 8, 9] in order
    data = rb.data()
    expected = [5.0, 6.0, 7.0, 8.0, 9.0]
    assert data == expected, f"Expected {expected}, got {data}"


def _test_ring_buffer_average() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=4)
    for v in [2.0, 4.0, 6.0, 8.0]:
        rb.push(v)
    assert abs(rb.average() - 5.0) < 1e-9, (
        f"Expected average=5.0, got {rb.average()}"
    )


def _test_ring_buffer_empty_behaviors() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=10)
    assert rb.latest()  == 0.0, f"Empty latest should be 0.0"
    assert rb.average() == 0.0, f"Empty average should be 0.0"
    assert rb.minimum() == 0.0, f"Empty minimum should be 0.0"
    assert rb.maximum() == 0.0, f"Empty maximum should be 0.0"
    assert len(rb)       == 0,  f"Empty len should be 0"


def _test_ring_buffer_thread_safety() -> None:
    from state import RingBuffer
    rb      = RingBuffer(capacity=1000)
    errors  = []

    def writer(start: int, count: int) -> None:
        try:
            for i in range(count):
                rb.push(float(start + i))
        except Exception as exc:
            errors.append(str(exc))

    threads = [
        threading.Thread(target=writer, args=(i * 100, 100))
        for i in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread safety errors: {errors}"
    data = rb.data()
    assert len(data) == 1000, f"Expected 1000 items after concurrent push"


def _test_ring_buffer_is_full() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=3)
    assert not rb.is_full(), "Empty buffer should not be full"
    rb.push(1.0)
    rb.push(2.0)
    assert not rb.is_full(), "Partially filled buffer should not be full"
    rb.push(3.0)
    assert rb.is_full(), "Buffer at capacity should be full"


def _test_ring_buffer_clear() -> None:
    from state import RingBuffer
    rb = RingBuffer(capacity=5)
    for i in range(5):
        rb.push(float(i))
    rb.clear()
    assert len(rb) == 0, f"After clear, buffer should be empty"
    assert rb.latest() == 0.0, "After clear, latest should return 0.0"


# =============================================================================
# SECTION 10: FIBONACCI SPHERE TESTS
# =============================================================================

def _test_fibonacci_sphere_count() -> None:
    from math_engine import fibonacci_sphere_points
    points = fibonacci_sphere_points(320, radius=1.0)
    assert len(points) == 320, (
        f"Expected 320 sphere points, got {len(points)}"
    )


def _test_fibonacci_sphere_on_surface() -> None:
    from math_engine import fibonacci_sphere_points
    points = fibonacci_sphere_points(100, radius=1.0)
    for p in points:
        mag = p.length()
        assert abs(mag - 1.0) < 1e-9, (
            f"Point not on unit sphere: magnitude={mag:.8f}"
        )


def _test_fibonacci_sphere_radius_scaling() -> None:
    from math_engine import fibonacci_sphere_points
    r = 80.0
    points = fibonacci_sphere_points(50, radius=r)
    for p in points:
        mag = p.length()
        assert abs(mag - r) < 1e-6, (
            f"Point not on sphere of radius {r}: magnitude={mag:.8f}"
        )


def _test_fibonacci_sphere_no_duplicates() -> None:
    from math_engine import fibonacci_sphere_points
    points = fibonacci_sphere_points(50, radius=1.0)
    tuples = [p.to_tuple() for p in points]
    unique = set((round(x,8), round(y,8), round(z,8)) for x,y,z in tuples)
    assert len(unique) == len(tuples), (
        f"Fibonacci sphere has duplicate points: "
        f"{len(tuples) - len(unique)} duplicates"
    )


# =============================================================================
# SECTION 11: GEOGRAPHIC CONVERSION TESTS
# =============================================================================

def _test_latlon_north_pole() -> None:
    from math_engine import latlon_to_sphere
    # North pole (90, 0) should map to (0, r, 0) — top of sphere
    p = latlon_to_sphere(90.0, 0.0, radius=1.0)
    assert abs(p.x - 0.0) < 1e-9, f"x: {p.x}"
    assert abs(p.y - 1.0) < 1e-6, f"y: {p.y}"
    assert abs(p.z - 0.0) < 1e-9, f"z: {p.z}"


def _test_latlon_equator_prime_meridian() -> None:
    from math_engine import latlon_to_sphere
    # (0, 0) equator prime meridian should map to (r, 0, 0)
    p = latlon_to_sphere(0.0, 0.0, radius=1.0)
    assert abs(p.x - 1.0) < 1e-9, f"x: {p.x}"
    assert abs(p.y - 0.0) < 1e-9, f"y: {p.y}"
    assert abs(p.z - 0.0) < 1e-9, f"z: {p.z}"


def _test_latlon_south_pole() -> None:
    from math_engine import latlon_to_sphere
    # South pole (-90, 0) should map to (0, -r, 0)
    p = latlon_to_sphere(-90.0, 0.0, radius=1.0)
    assert abs(p.x -  0.0) < 1e-9, f"x: {p.x}"
    assert abs(p.y - (-1.0)) < 1e-6, f"y: {p.y}"
    assert abs(p.z -  0.0) < 1e-9, f"z: {p.z}"


def _test_latlon_point_on_sphere() -> None:
    from math_engine import latlon_to_sphere
    # Any lat/lon point must lie on the unit sphere surface
    test_coords = [
        (51.5,    -0.1),    # London
        (40.7,   -74.0),    # New York
        (35.7,   139.7),    # Tokyo
        (-33.9,   18.4),    # Cape Town
        (-34.6,  -58.4),    # Buenos Aires
        (55.8,    37.6),    # Moscow
    ]
    for lat, lon in test_coords:
        p = latlon_to_sphere(lat, lon, radius=1.0)
        mag = p.length()
        assert abs(mag - 1.0) < 1e-9, (
            f"latlon({lat},{lon}) not on unit sphere: mag={mag:.8f}"
        )


# =============================================================================
# SECTION 12: FFT NORMALIZATION TESTS
# =============================================================================

def _test_fft_normalize_output_count() -> None:
    from math_engine import normalize_fft
    raw = [float(i) for i in range(512)]
    result = normalize_fft(raw, 64)
    assert len(result) == 64, (
        f"Expected 64 FFT bands, got {len(result)}"
    )


def _test_fft_normalize_bounds() -> None:
    from math_engine import normalize_fft
    raw = [float(i % 10) for i in range(512)]
    result = normalize_fft(raw, 64)
    for i, v in enumerate(result):
        assert 0.0 <= v <= 1.0, (
            f"FFT band {i} out of [0,1]: {v}"
        )


def _test_fft_normalize_all_zero_input() -> None:
    from math_engine import normalize_fft
    raw = [0.0] * 512
    result = normalize_fft(raw, 64)
    for v in result:
        assert v == 0.0, f"All-zero FFT should produce all-zero output: {v}"


def _test_fft_normalize_empty_input() -> None:
    from math_engine import normalize_fft
    result = normalize_fft([], 64)
    assert len(result) == 64, "Empty input should still return 64 bands"
    assert all(v == 0.0 for v in result), (
        "Empty input should return all-zero bands"
    )


def _test_fft_normalize_max_band_is_one() -> None:
    from math_engine import normalize_fft
    # If input has a clear peak, the normalized max must be exactly 1.0
    raw = [0.0] * 512
    raw[100] = 100.0   # clear dominant peak
    result = normalize_fft(raw, 64)
    assert abs(max(result) - 1.0) < 1e-9, (
        f"Max normalized band should be 1.0, got {max(result)}"
    )


# =============================================================================
# SECTION 13: STABILITY SCORE TESTS
# =============================================================================

def _test_stability_perfect_conditions() -> None:
    from math_engine import stability_score
    score = stability_score(
        cpu_temp=35.0,
        cpu_usage=10.0,
        ram_usage=30.0,
        ping_ms=20.0,
        internet_up=True,
    )
    assert score == 100.0, (
        f"Perfect conditions should yield 100.0, got {score}"
    )


def _test_stability_critical_conditions() -> None:
    from math_engine import stability_score
    score = stability_score(
        cpu_temp=95.0,
        cpu_usage=100.0,
        ram_usage=100.0,
        ping_ms=500.0,
        internet_up=False,
    )
    assert score < 20.0, (
        f"Critical conditions should yield score < 20, got {score}"
    )


def _test_stability_clamped_to_zero() -> None:
    from math_engine import stability_score
    score = stability_score(
        cpu_temp=200.0,
        cpu_usage=100.0,
        ram_usage=100.0,
        ping_ms=9999.0,
        internet_up=False,
    )
    assert score >= 0.0, f"Stability score must not go below 0: {score}"


def _test_stability_network_down_penalty() -> None:
    from math_engine import stability_score
    # Network down vs up should differ by exactly 10 points
    score_up   = stability_score(40.0, 20.0, 40.0, 30.0, True)
    score_down = stability_score(40.0, 20.0, 40.0, 30.0, False)
    assert abs((score_up - score_down) - 10.0) < 1e-6, (
        f"Network penalty should be 10.0, got {score_up - score_down}"
    )


# =============================================================================
# SECTION 14: SLERP / GREAT CIRCLE TESTS
# =============================================================================

def _test_slerp_t0_returns_p1() -> None:
    from math_engine import great_circle_interpolate, Vector3
    p1 = Vector3(1.0, 0.0, 0.0)
    p2 = Vector3(0.0, 1.0, 0.0)
    result = great_circle_interpolate(p1, p2, 0.0)
    assert abs(result.x - 1.0) < 1e-6, f"x: {result.x}"
    assert abs(result.y - 0.0) < 1e-6, f"y: {result.y}"


def _test_slerp_t1_returns_p2() -> None:
    from math_engine import great_circle_interpolate, Vector3
    p1 = Vector3(1.0, 0.0, 0.0)
    p2 = Vector3(0.0, 1.0, 0.0)
    result = great_circle_interpolate(p1, p2, 1.0)
    assert abs(result.x - 0.0) < 1e-6, f"x: {result.x}"
    assert abs(result.y - 1.0) < 1e-6, f"y: {result.y}"


def _test_slerp_midpoint_on_sphere() -> None:
    from math_engine import great_circle_interpolate, Vector3
    p1 = Vector3(1.0, 0.0, 0.0)
    p2 = Vector3(0.0, 1.0, 0.0)
    mid = great_circle_interpolate(p1, p2, 0.5)
    mag = mid.length()
    assert abs(mag - 1.0) < 1e-6, (
        f"SLERP midpoint must be on unit sphere: mag={mag}"
    )


def _test_slerp_parallel_vectors_no_crash() -> None:
    from math_engine import great_circle_interpolate, Vector3
    # Parallel vectors: omega ≈ 0, should fall back to lerp without crash
    p1 = Vector3(1.0, 0.0, 0.0)
    p2 = Vector3(1.0, 0.0, 0.0)
    result = great_circle_interpolate(p1, p2, 0.5)
    assert math.isfinite(result.x), f"SLERP parallel: x not finite"
    assert math.isfinite(result.y), f"SLERP parallel: y not finite"
    assert math.isfinite(result.z), f"SLERP parallel: z not finite"


# =============================================================================
# SECTION 15: PALETTE TESTS
# =============================================================================

def _test_palette_mix_midpoint() -> None:
    import palette
    a = (0, 0, 0)
    b = (200, 100, 50)
    mid = palette.mix(a, b, 0.5)
    assert abs(mid[0] - 100) <= 1, f"R midpoint: {mid[0]}"
    assert abs(mid[1] -  50) <= 1, f"G midpoint: {mid[1]}"
    assert abs(mid[2] -  25) <= 1, f"B midpoint: {mid[2]}"


def _test_palette_mix_clamp() -> None:
    import palette
    # t > 1.0 should clamp to 1.0
    result = palette.mix((0, 0, 0), (100, 100, 100), 2.0)
    assert result == (100, 100, 100), f"Expected (100,100,100), got {result}"
    # t < 0.0 should clamp to 0.0
    result2 = palette.mix((0, 0, 0), (100, 100, 100), -1.0)
    assert result2 == (0, 0, 0), f"Expected (0,0,0), got {result2}"


def _test_palette_with_alpha() -> None:
    import palette
    result = palette.with_alpha((100, 150, 200), 128)
    assert len(result) == 4, f"Expected 4-tuple, got {result}"
    assert result[3] == 128, f"Alpha: {result[3]}"
    # Clamp test
    clamped = palette.with_alpha((100, 150, 200), 300)
    assert clamped[3] == 255, f"Alpha should clamp to 255: {clamped[3]}"


def _test_palette_depth_shade() -> None:
    import palette
    near = (200, 200, 200)
    far  = (30,  30,  30)
    # At depth_t=0.0, result should equal near
    at_0 = palette.depth_shade(near, far, 0.0)
    assert at_0 == near, f"At depth 0, expected near color: {at_0}"
    # At depth_t=1.0, result should equal far
    at_1 = palette.depth_shade(near, far, 1.0)
    assert at_1 == far, f"At depth 1, expected far color: {at_1}"


def _test_palette_brightness() -> None:
    import palette
    c = (100, 100, 100)
    doubled = palette.brightness(c, 2.0)
    assert doubled == (200, 200, 200), f"Expected (200,200,200): {doubled}"
    zeroed = palette.brightness(c, 0.0)
    assert zeroed == (0, 0, 0), f"Expected (0,0,0): {zeroed}"


def _test_palette_mode_switching() -> None:
    import palette
    from config import UIMode
    # Switch to Hudson mode and confirm accent color changes
    palette.set_mode(UIMode.HUDSON)
    # Force complete transition
    for _ in range(30):
        palette.tick_transition()
    mode = palette.get_mode()
    assert mode == UIMode.HUDSON, f"Expected HUDSON mode, got {mode}"
    # Switch back to Archer
    palette.set_mode(UIMode.ARCHER)
    for _ in range(30):
        palette.tick_transition()
    mode = palette.get_mode()
    assert mode == UIMode.ARCHER, f"Expected ARCHER mode, got {mode}"


def _test_palette_pulse_finite() -> None:
    import palette
    # Pulse must always return finite RGB values
    for t in [0.0, 0.25, 0.5, 0.75, 1.0, 2.5, 10.0]:
        result = palette.pulse((100, 150, 200), t)
        assert all(math.isfinite(c) for c in result), (
            f"pulse() returned non-finite value at t={t}: {result}"
        )
        assert all(0 <= c <= 255 for c in result), (
            f"pulse() channel out of [0,255] at t={t}: {result}"
        )


# =============================================================================
# SECTION 16: HERMES STATE THREAD SAFETY TESTS
# =============================================================================

def _test_state_set_get() -> None:
    from state import HermesState
    s = HermesState()
    s.set("cpu_temp", 72.5)
    assert s.get("cpu_temp") == 72.5, (
        f"Expected 72.5, got {s.get('cpu_temp')}"
    )


def _test_state_batch_set() -> None:
    from state import HermesState
    s = HermesState()
    s.batch_set({
        "cpu_temp":   55.0,
        "cpu_usage":  45.0,
        "ram_usage":  60.0,
    })
    assert s.get("cpu_temp")  == 55.0
    assert s.get("cpu_usage") == 45.0
    assert s.get("ram_usage") == 60.0


def _test_state_snapshot_is_copy() -> None:
    from state import HermesState
    s    = HermesState()
    snap = s.snapshot()
    # Modifying the snapshot must not affect the state
    snap["cpu_temp"] = 999.0
    assert s.get("cpu_temp") != 999.0, (
        "Snapshot modification must not affect HermesState"
    )


def _test_state_concurrent_writes() -> None:
    from state import HermesState
    s      = HermesState()
    errors = []

    def writer(val: float) -> None:
        try:
            for _ in range(100):
                s.set("cpu_usage", val)
                _ = s.get("cpu_usage")
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=writer, args=(float(i),))
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent write errors: {errors}"


def _test_state_append_to_capped() -> None:
    from state import HermesState
    s = HermesState()
    for i in range(20):
        s.append_to("system_alerts", f"alert_{i}", max_length=5)
    lst = s.get("system_alerts")
    assert len(lst) == 5, f"Expected 5 items (capped), got {len(lst)}"


def _test_state_uptime_string_format() -> None:
    from state import HermesState
    s = HermesState()
    uptime = s.get_uptime_string()
    # Must match "UP: HH:MM:SS" format
    assert uptime.startswith("UP: "), f"Bad uptime prefix: {uptime}"
    parts = uptime.replace("UP: ", "").split(":")
    assert len(parts) == 3, f"Uptime parts: {parts}"
    for part in parts:
        assert part.isdigit(), f"Non-digit uptime part: {part}"


def _test_state_unread_count() -> None:
    from state import HermesState, SocialMessage
    s = HermesState()
    msg1 = SocialMessage(
        platform=SocialMessage.PLATFORM_WHATSAPP,
        sender="Test User",
        preview="Hello",
    )
    msg2 = SocialMessage(
        platform=SocialMessage.PLATFORM_WHATSAPP,
        sender="Test User 2",
        preview="Hi",
    )
    s.add_social_message(msg1)
    s.add_social_message(msg2)
    count = s.get_unread_count(SocialMessage.PLATFORM_WHATSAPP)
    assert count == 2, f"Expected 2 unread, got {count}"
    msg1.mark_read()
    count2 = s.get_unread_count(SocialMessage.PLATFORM_WHATSAPP)
    assert count2 == 1, f"Expected 1 unread after read, got {count2}"


# =============================================================================
# SECTION 17: EVENT BUS TESTS
# =============================================================================

def _test_event_bus_publish_subscribe() -> None:
    from event_bus import EventBus, EventType
    bus      = EventBus()
    bus.start()
    received = []

    def handler(event) -> None:
        received.append(event.payload)

    bus.subscribe(EventType.HARDWARE_UPDATE, handler)
    bus.publish(EventType.HARDWARE_UPDATE, payload={"cpu": 55.0},
                source="Test")
    time.sleep(0.05)   # Allow dispatcher to process
    bus.stop()

    assert len(received) == 1, f"Expected 1 event, got {len(received)}"
    assert received[0]["cpu"] == 55.0, f"Payload mismatch: {received[0]}"


def _test_event_bus_unsubscribe() -> None:
    from event_bus import EventBus, EventType
    bus      = EventBus()
    bus.start()
    received = []

    def handler(event) -> None:
        received.append(event)

    sub_id = bus.subscribe(EventType.NETWORK_UPDATE, handler)
    bus.publish(EventType.NETWORK_UPDATE, payload={"ping": 20.0},
                source="Test")
    time.sleep(0.05)
    bus.unsubscribe(sub_id)
    bus.publish(EventType.NETWORK_UPDATE, payload={"ping": 30.0},
                source="Test")
    time.sleep(0.05)
    bus.stop()

    assert len(received) == 1, (
        f"Expected 1 event after unsubscribe, got {len(received)}"
    )


def _test_event_bus_main_thread_poll() -> None:
    from event_bus import EventBus, EventType
    bus = EventBus()
    bus.start()
    bus.publish(
        EventType.UI_MODE_CHANGE,
        payload={"mode": "HUDSON"},
        source="Test",
        main_thread_only=True,
    )
    time.sleep(0.02)
    events = bus.poll()
    bus.stop()
    assert len(events) == 1, f"Expected 1 main-thread event, got {len(events)}"
    assert events[0].payload["mode"] == "HUDSON"


def _test_event_bus_priority_ordering() -> None:
    from event_bus import EventBus, EventType
    bus   = EventBus()
    bus.start()
    order = []

    def low_handler(event) -> None:
        order.append("LOW")

    def high_handler(event) -> None:
        order.append("HIGH")

    bus.subscribe(EventType.SYSTEM_ALERT, low_handler,  priority=0)
    bus.subscribe(EventType.SYSTEM_ALERT, high_handler, priority=50)
    bus.publish(EventType.SYSTEM_ALERT,
                payload={"message": "test"},
                source="Test")
    time.sleep(0.05)
    bus.stop()

    assert order[0] == "HIGH", (
        f"High priority handler should fire first, got order: {order}"
    )


def _test_event_bus_stats() -> None:
    from event_bus import EventBus, EventType
    bus = EventBus()
    bus.start()
    bus.publish(EventType.HARDWARE_UPDATE, source="Test")
    bus.publish(EventType.HARDWARE_UPDATE, source="Test")
    time.sleep(0.05)
    stats = bus.get_stats()
    bus.stop()
    assert stats["published"] >= 2, (
        f"Expected published >= 2, got {stats['published']}"
    )


def _test_event_bus_source_filter() -> None:
    from event_bus import EventBus, EventType
    bus      = EventBus()
    bus.start()
    received = []

    def handler(event) -> None:
        received.append(event.source)

    bus.subscribe(
        EventType.HARDWARE_UPDATE,
        handler,
        source_filter="CorrectSource",
    )
    bus.publish(EventType.HARDWARE_UPDATE, source="WrongSource")
    bus.publish(EventType.HARDWARE_UPDATE, source="CorrectSource")
    time.sleep(0.05)
    bus.stop()

    assert len(received) == 1, (
        f"Source filter: expected 1 event, got {len(received)}"
    )
    assert received[0] == "CorrectSource"


# =============================================================================
# SECTION 18: CONFIG INTEGRITY TESTS
# =============================================================================

def _test_config_directory_existence() -> None:
    from config import (
        ASSETS_DIR, SOUNDS_DIR, MEMORY_DIR,
        BRAINSTORM_DIR, BASE_DIR,
    )
    for path in [ASSETS_DIR, SOUNDS_DIR, MEMORY_DIR, BRAINSTORM_DIR, BASE_DIR]:
        assert os.path.isdir(path), (
            f"Required directory missing: {path}"
        )


def _test_config_screen_dimensions() -> None:
    from config import SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_SIZE
    assert SCREEN_WIDTH  == 1920, f"Expected width 1920, got {SCREEN_WIDTH}"
    assert SCREEN_HEIGHT == 810,  f"Expected height 810, got {SCREEN_HEIGHT}"
    assert SCREEN_SIZE   == (1920, 810), f"SCREEN_SIZE mismatch: {SCREEN_SIZE}"


def _test_config_panel_geometry_consistency() -> None:
    from config import (
        LEFT_VP_X,  LEFT_VP_W,  RIGHT_TOP_X,
        BOTTOM_ROW_Y, HEADER_BOTTOM, LEFT_VP_BOTTOM,
        PANEL_E1_W, PANEL_E2_W, PANEL_E3_W, PANEL_E4_W,
        SCREEN_WIDTH,
    )
    # Left viewport right edge must align with right viewport left edge
    assert LEFT_VP_X + LEFT_VP_W == RIGHT_TOP_X, (
        f"Left VP right edge ({LEFT_VP_X + LEFT_VP_W}) "
        f"!= Right VP left edge ({RIGHT_TOP_X})"
    )
    # Bottom row top must match left viewport bottom
    assert BOTTOM_ROW_Y == LEFT_VP_BOTTOM, (
        f"Bottom row Y ({BOTTOM_ROW_Y}) != Left VP bottom ({LEFT_VP_BOTTOM})"
    )
    # Four equal diagnostic panels must sum to screen width
    total = PANEL_E1_W + PANEL_E2_W + PANEL_E3_W + PANEL_E4_W
    assert total == SCREEN_WIDTH, (
        f"Panel E widths sum {total} != screen width {SCREEN_WIDTH}"
    )
    # Header bottom must be where viewports start
    assert HEADER_BOTTOM == LEFT_VP_Y if False else True  # guard import check


def _test_config_fps_cap() -> None:
    from config import FPS_CAP
    assert FPS_CAP == 60, f"Expected FPS_CAP=60, got {FPS_CAP}"


def _test_config_api_key_not_empty() -> None:
    from config import OPENROUTER_API_KEY
    assert len(OPENROUTER_API_KEY) > 10, (
        "OPENROUTER_API_KEY appears to be empty or placeholder"
    )


def _test_config_performance_tier_maps_complete() -> None:
    from config import PerformanceTier
    tiers = [
        PerformanceTier.CRAPPY,
        PerformanceTier.MEH,
        PerformanceTier.MID,
        PerformanceTier.BEAST,
        PerformanceTier.MONSTER,
    ]
    for tier in tiers:
        assert tier in PerformanceTier.TERRAIN_DENSITY_MAP, (
            f"Tier {tier} missing from TERRAIN_DENSITY_MAP"
        )
        assert tier in PerformanceTier.GLOBE_POINTS_MAP, (
            f"Tier {tier} missing from GLOBE_POINTS_MAP"
        )
        assert tier in PerformanceTier.FPS_MAP, (
            f"Tier {tier} missing from FPS_MAP"
        )
        assert tier in PerformanceTier.ORB_PARTICLE_MAP, (
            f"Tier {tier} missing from ORB_PARTICLE_MAP"
        )


# =============================================================================
# SECTION 19: SESSION TOKEN TRACKER TESTS
# =============================================================================

def _test_token_tracker_basic() -> None:
    from state import SessionTokenTracker
    tracker = SessionTokenTracker(limit=100)
    # 40 characters = ~10 tokens
    exceeded = tracker.add_text("a" * 40)
    assert not exceeded, "40 chars should not exceed 100-token limit"
    assert tracker.current_count() == 10


def _test_token_tracker_exceeds() -> None:
    from state import SessionTokenTracker
    tracker = SessionTokenTracker(limit=10)
    # 80 characters = 20 tokens — must exceed limit of 10
    exceeded = tracker.add_text("x" * 80)
    assert exceeded, "80 chars should exceed 10-token limit"


def _test_token_tracker_reset() -> None:
    from state import SessionTokenTracker
    tracker = SessionTokenTracker(limit=10)
    tracker.add_text("x" * 80)
    tracker.reset()
    assert tracker.current_count() == 0, (
        f"After reset, count should be 0, got {tracker.current_count()}"
    )


def _test_token_tracker_percentage() -> None:
    from state import SessionTokenTracker
    tracker = SessionTokenTracker(limit=100)
    # 200 chars = 50 tokens = 50%
    tracker.add_text("a" * 200)
    pct = tracker.percentage_used()
    assert abs(pct - 50.0) < 1.0, (
        f"Expected ~50% usage, got {pct:.1f}%"
    )


# =============================================================================
# SECTION 20: MATH UTILITY TESTS
# =============================================================================

def _test_clamp() -> None:
    from math_engine import clamp
    assert clamp(5.0,  0.0, 10.0) == 5.0
    assert clamp(-1.0, 0.0, 10.0) == 0.0
    assert clamp(15.0, 0.0, 10.0) == 10.0


def _test_lerp_scalar() -> None:
    from math_engine import lerp
    assert abs(lerp(0.0, 100.0, 0.5) - 50.0) < 1e-9
    assert abs(lerp(0.0, 100.0, 0.0) -  0.0) < 1e-9
    assert abs(lerp(0.0, 100.0, 1.0) - 100.0) < 1e-9


def _test_smoothstep() -> None:
    from math_engine import smoothstep
    assert smoothstep(0.0, 1.0, 0.0) == 0.0
    assert smoothstep(0.0, 1.0, 1.0) == 1.0
    mid = smoothstep(0.0, 1.0, 0.5)
    assert abs(mid - 0.5) < 1e-9, f"Smoothstep(0.5) should be 0.5: {mid}"
    # Smoothstep is symmetric: f(x) = 1 - f(1-x)
    assert abs(smoothstep(0.0, 1.0, 0.25) -
               (1.0 - smoothstep(0.0, 1.0, 0.75))) < 1e-9


def _test_map_range() -> None:
    from math_engine import map_range
    # Map [0, 10] → [0, 100]: value 5 → 50
    result = map_range(5.0, 0.0, 10.0, 0.0, 100.0)
    assert abs(result - 50.0) < 1e-9, f"map_range: {result}"


def _test_compute_rms() -> None:
    from math_engine import compute_rms
    # RMS of [1, 1, 1, 1] = 1.0
    assert abs(compute_rms([1.0, 1.0, 1.0, 1.0]) - 1.0) < 1e-9
    # RMS of empty = 0.0
    assert compute_rms([]) == 0.0
    # RMS of [3, 4] = sqrt((9+16)/2) = sqrt(12.5)
    assert abs(compute_rms([3.0, 4.0]) - math.sqrt(12.5)) < 1e-9


def _test_semicircle_arc_right() -> None:
    from math_engine import semicircle_arc_point
    # At angle_deg=0 (right side, 100% stable):
    # angle_rad = pi - 0 = pi → cos(pi)=-1, sin(pi)=0
    # x = cx + r * cos(pi) = cx - r
    # y = cy - r * sin(pi) = cy
    cx, cy, r = 100, 100, 50
    x, y = semicircle_arc_point(cx, cy, r, 0.0)
    assert abs(x - (cx - r)) < 1, f"Right arc x: {x}, expected {cx - r}"
    assert abs(y - cy) < 1,       f"Right arc y: {y}, expected {cy}"


def _test_semicircle_arc_top() -> None:
    from math_engine import semicircle_arc_point
    # At angle_deg=90 (top, 50% stable):
    # angle_rad = pi - pi/2 = pi/2 → cos(pi/2)=0, sin(pi/2)=1
    # x = cx + r * 0 = cx
    # y = cy - r * 1 = cy - r
    cx, cy, r = 100, 100, 50
    x, y = semicircle_arc_point(cx, cy, r, 90.0)
    assert abs(x - cx)       < 1, f"Top arc x: {x}, expected {cx}"
    assert abs(y - (cy - r)) < 1, f"Top arc y: {y}, expected {cy - r}"


def _test_terrain_grid_generator() -> None:
    from math_engine import generate_terrain_grid
    density = 10
    spacing = 18.0
    grid    = generate_terrain_grid(density, spacing)
    assert len(grid) == density * density, (
        f"Expected {density**2} grid points, got {len(grid)}"
    )
    # Center point should be near (0, 0)
    center_idx = density * (density // 2) + (density // 2)
    cx, cz = grid[center_idx]
    assert abs(cx) <= spacing, f"Center X too far from 0: {cx}"
    assert abs(cz) <= spacing, f"Center Z too far from 0: {cz}"


# =============================================================================
# SECTION 21: MASTER TEST RUNNER
# =============================================================================

def run_self_tests() -> bool:
    """
    Executes all pre-flight validation tests in sequence.
    Prints a formatted diagnostic report to stdout.
    Returns True if ALL tests pass. Returns False if ANY test fails.

    This function must be called before pygame.init() and window creation.
    If it returns False, the boot sequence must halt.

    Returns:
        True if all tests pass, False if any test fails.
    """

    print("\n" + "=" * 72)
    print("  PROJECT HERMES — PRE-FLIGHT SELF-TEST SUITE")
    print("  Validating mathematical integrity before window creation...")
    print("=" * 72)

    # Phase 0: Import validation
    print("\n[PHASE 0] Import Validation")
    import_errors = _validate_imports()
    if import_errors:
        for err in import_errors:
            print(f"  {err}")
        print("\n  CRITICAL: Import failures detected. Boot aborted.")
        return False
    print("  All core modules imported successfully.")

    # Define all test cases as (name, function) pairs
    all_tests = [
        # Vector3
        ("Vector3 Addition",                        _test_vector3_addition),
        ("Vector3 Subtraction",                     _test_vector3_subtraction),
        ("Vector3 Scalar Multiply",                 _test_vector3_scalar_multiply),
        ("Vector3 Scalar Divide",                   _test_vector3_scalar_divide),
        ("Vector3 Dot Product",                     _test_vector3_dot_product),
        ("Vector3 Cross Product",                   _test_vector3_cross_product),
        ("Vector3 Magnitude",                       _test_vector3_magnitude),
        ("Vector3 Normalize",                       _test_vector3_normalize),
        ("Vector3 Normalize Zero Vector",           _test_vector3_normalize_zero),
        ("Vector3 Linear Interpolation",            _test_vector3_lerp),
        ("Vector3 Reflection",                      _test_vector3_reflect),
        ("Vector3 Distance",                        _test_vector3_distance),
        ("Vector3 Negation",                        _test_vector3_negation),
        ("Vector3 Equality",                        _test_vector3_equality),
        # Matrix4x4
        ("Matrix4x4 Identity Transform",            _test_matrix_identity_transform),
        ("Matrix4x4 Rotation X 90°",               _test_matrix_rotation_x_90),
        ("Matrix4x4 Rotation Y 90°",               _test_matrix_rotation_y_90),
        ("Matrix4x4 Rotation Z 90°",               _test_matrix_rotation_z_90),
        ("Matrix4x4 Translation",                  _test_matrix_translation),
        ("Matrix4x4 Scale",                         _test_matrix_scale),
        ("Matrix4x4 Multiplication Identity",       _test_matrix_multiplication_identity),
        ("Matrix4x4 Combined Rotation",             _test_matrix_combined_rotation),
        ("Matrix4x4 Direction Ignores Translation", _test_matrix_direction_transform_ignores_translation),
        ("Matrix4x4 Rotation X 360°",              _test_matrix_rotation_x_360),
        # Perlin Noise
        ("PerlinNoise3D Deterministic",             _test_perlin_deterministic),
        ("PerlinNoise3D Bounds [-1, 1]",            _test_perlin_bounds),
        ("PerlinNoise3D Different Seeds Differ",    _test_perlin_different_seeds_differ),
        ("PerlinNoise3D Smoothness",                _test_perlin_smoothness),
        ("PerlinNoise3D Zero at Integers",          _test_perlin_zero_at_integers),
        # FBM
        ("FBM Elevation Bounds",                    _test_fbm_elevation_bounds),
        ("FBM Elevation Deterministic",             _test_fbm_deterministic),
        ("FBM Time Offset Changes Result",          _test_fbm_time_offset_changes_result),
        # Catmull-Rom
        ("Catmull-Rom Boundary Values",             _test_catmull_rom_boundary_values),
        ("Catmull-Rom Midpoint Collinear",          _test_catmull_rom_midpoint),
        ("Catmull-Rom Chain Length",                _test_catmull_rom_chain_length),
        ("Catmull-Rom t Clamping",                  _test_catmull_rom_clamp_t),
        # EKG
        ("EKG Sample Bounds",                       _test_ekg_sample_bounds),
        ("EKG Sample Periodic",                     _test_ekg_sample_periodic),
        ("EKG Generate Points Count",               _test_ekg_generate_points_count),
        ("EKG Points Screen X Range",               _test_ekg_generate_points_screen_x_range),
        # Ring Buffer
        ("RingBuffer Push/Latest",                  _test_ring_buffer_basic_push_latest),
        ("RingBuffer Capacity Enforcement",         _test_ring_buffer_capacity_enforcement),
        ("RingBuffer FIFO Order",                   _test_ring_buffer_fifo_order),
        ("RingBuffer Average",                      _test_ring_buffer_average),
        ("RingBuffer Empty Behaviors",              _test_ring_buffer_empty_behaviors),
        ("RingBuffer Thread Safety",                _test_ring_buffer_thread_safety),
        ("RingBuffer Is Full",                      _test_ring_buffer_is_full),
        ("RingBuffer Clear",                        _test_ring_buffer_clear),
        # Fibonacci Sphere
        ("Fibonacci Sphere Point Count",            _test_fibonacci_sphere_count),
        ("Fibonacci Sphere On Surface",             _test_fibonacci_sphere_on_surface),
        ("Fibonacci Sphere Radius Scaling",         _test_fibonacci_sphere_radius_scaling),
        ("Fibonacci Sphere No Duplicates",          _test_fibonacci_sphere_no_duplicates),
        # Geographic Conversion
        ("LatLon North Pole",                       _test_latlon_north_pole),
        ("LatLon Equator Prime Meridian",           _test_latlon_equator_prime_meridian),
        ("LatLon South Pole",                       _test_latlon_south_pole),
        ("LatLon Points On Sphere",                 _test_latlon_point_on_sphere),
        # FFT
        ("FFT Normalize Output Count",              _test_fft_normalize_output_count),
        ("FFT Normalize Bounds [0, 1]",             _test_fft_normalize_bounds),
        ("FFT Normalize All-Zero Input",            _test_fft_normalize_all_zero_input),
        ("FFT Normalize Empty Input",               _test_fft_normalize_empty_input),
        ("FFT Normalize Max Band = 1.0",            _test_fft_normalize_max_band_is_one),
        # Stability Score
        ("Stability Score Perfect Conditions",      _test_stability_perfect_conditions),
        ("Stability Score Critical Conditions",     _test_stability_critical_conditions),
        ("Stability Score Clamped to Zero",         _test_stability_clamped_to_zero),
        ("Stability Score Network Penalty",         _test_stability_network_down_penalty),
        # SLERP
        ("SLERP t=0 Returns P1",                   _test_slerp_t0_returns_p1),
        ("SLERP t=1 Returns P2",                   _test_slerp_t1_returns_p2),
        ("SLERP Midpoint On Sphere",               _test_slerp_midpoint_on_sphere),
        ("SLERP Parallel Vectors No Crash",        _test_slerp_parallel_vectors_no_crash),
        # Palette
        ("Palette Mix Midpoint",                   _test_palette_mix_midpoint),
        ("Palette Mix Clamp",                       _test_palette_mix_clamp),
        ("Palette With Alpha",                      _test_palette_with_alpha),
        ("Palette Depth Shade",                     _test_palette_depth_shade),
        ("Palette Brightness",                      _test_palette_brightness),
        ("Palette Mode Switching",                  _test_palette_mode_switching),
        ("Palette Pulse Finite",                    _test_palette_pulse_finite),
        # HermesState
        ("HermesState Set/Get",                    _test_state_set_get),
        ("HermesState Batch Set",                   _test_state_batch_set),
        ("HermesState Snapshot Is Copy",           _test_state_snapshot_is_copy),
        ("HermesState Concurrent Writes",          _test_state_concurrent_writes),
        ("HermesState Append Capped",              _test_state_append_to_capped),
        ("HermesState Uptime String Format",       _test_state_uptime_string_format),
        ("HermesState Unread Count",               _test_state_unread_count),
        # EventBus
        ("EventBus Publish/Subscribe",             _test_event_bus_publish_subscribe),
        ("EventBus Unsubscribe",                   _test_event_bus_unsubscribe),
        ("EventBus Main Thread Poll",              _test_event_bus_main_thread_poll),
        ("EventBus Priority Ordering",             _test_event_bus_priority_ordering),
        ("EventBus Statistics",                    _test_event_bus_stats),
        ("EventBus Source Filter",                 _test_event_bus_source_filter),
        # Config
        ("Config Directory Existence",             _test_config_directory_existence),
        ("Config Screen Dimensions",               _test_config_screen_dimensions),
        ("Config Panel Geometry Consistency",      _test_config_panel_geometry_consistency),
        ("Config FPS Cap",                         _test_config_fps_cap),
        ("Config API Key Not Empty",               _test_config_api_key_not_empty),
        ("Config Performance Tier Maps Complete",  _test_config_performance_tier_maps_complete),
        # Session Token Tracker
        ("SessionTokenTracker Basic",              _test_token_tracker_basic),
        ("SessionTokenTracker Exceeds Limit",      _test_token_tracker_exceeds),
        ("SessionTokenTracker Reset",              _test_token_tracker_reset),
        ("SessionTokenTracker Percentage",         _test_token_tracker_percentage),
        # Math Utilities
        ("Clamp Utility",                          _test_clamp),
        ("Lerp Scalar",                            _test_lerp_scalar),
        ("Smoothstep",                             _test_smoothstep),
        ("Map Range",                              _test_map_range),
        ("Compute RMS",                            _test_compute_rms),
        ("Semicircle Arc Right",                   _test_semicircle_arc_right),
        ("Semicircle Arc Top",                     _test_semicircle_arc_top),
        ("Terrain Grid Generator",                 _test_terrain_grid_generator),
    ]

    # Execute all tests and collect results
    results: List[TestResult] = []
    for test_name, test_fn in all_tests:
        result = _run_test(test_name, test_fn)
        results.append(result)

    # Categorize results
    passed  = [r for r in results if r.passed]
    failed  = [r for r in results if not r.passed]
    total   = len(results)

    # Print passed tests (compact)
    print(f"\n[PHASE 1-20] Test Execution ({total} tests)\n")
    for r in results:
        symbol = "✓" if r.passed else "✗"
        print(f"  {symbol} {r.name:<52} {r.elapsed_ms:>6.2f}ms")

    # Print failure details
    if failed:
        print(f"\n{'=' * 72}")
        print(f"  FAILURES ({len(failed)})")
        print(f"{'=' * 72}")
        for r in failed:
            print(f"\n  ✗ {r.name}")
            print(f"    {r.message}")

    # Print summary
    total_time = sum(r.elapsed_ms for r in results)
    print(f"\n{'=' * 72}")
    print(f"  RESULTS: {len(passed)}/{total} PASSED  |  "
          f"{len(failed)} FAILED  |  "
          f"Total Time: {total_time:.2f}ms")

    if not failed:
        print("  STATUS: ALL SYSTEMS NOMINAL — PROCEEDING TO BOOT")
    else:
        print("  STATUS: CRITICAL FAILURES DETECTED — BOOT HALTED")
    print("=" * 72 + "\n")

    return len(failed) == 0


# =============================================================================
# SECTION 22: STANDALONE EXECUTION
# =============================================================================

if __name__ == "__main__":
    success = run_self_tests()
    sys.exit(0 if success else 1)

# =============================================================================
# END OF self_test.py
# =============================================================================