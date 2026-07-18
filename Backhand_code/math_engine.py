# =============================================================================
# PROJECT HERMES - OMNIMIND ABSOLUTE EDITION
# FILE: math_engine.py
# ROLE: Rigorous 3D coordinate mathematics, matrix-based camera projectives,
#       deterministic 3D value noise (Perlin), spline curve interpolation,
#       Fibonacci sphere distribution, FBM terrain generation, EKG waveform
#       mathematics, and all geometric utility functions used across the system.
#       Zero dependencies on pygame or UI modules. Pure mathematics only.
# =============================================================================

import math
import random
from typing import List, Tuple, Optional

# Attempt numpy import with pure-Python fallback flag
try:
    import numpy as np
    NUMPY_AVAILABLE: bool = True
except ImportError:
    NUMPY_AVAILABLE: bool = False

# =============================================================================
# SECTION 1: VECTOR3 - THREE-DIMENSIONAL COORDINATE VECTOR
# =============================================================================

class Vector3:
    """
    Immutable-style three-dimensional floating point vector.
    Supports all standard linear algebra operations required by the
    terrain renderer, globe renderer, and camera projection pipeline.
    """

    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x: float = float(x)
        self.y: float = float(y)
        self.z: float = float(z)

    # -------------------------------------------------------------------------
    # Arithmetic operators
    # -------------------------------------------------------------------------

    def __add__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3":
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> "Vector3":
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> "Vector3":
        if abs(scalar) < 1e-12:
            raise ZeroDivisionError("Vector3 division by near-zero scalar.")
        inv = 1.0 / scalar
        return Vector3(self.x * inv, self.y * inv, self.z * inv)

    def __neg__(self) -> "Vector3":
        return Vector3(-self.x, -self.y, -self.z)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector3):
            return False
        return (abs(self.x - other.x) < 1e-9 and
                abs(self.y - other.y) < 1e-9 and
                abs(self.z - other.z) < 1e-9)

    def __repr__(self) -> str:
        return f"Vector3({self.x:.6f}, {self.y:.6f}, {self.z:.6f})"

    # -------------------------------------------------------------------------
    # Core linear algebra
    # -------------------------------------------------------------------------

    def dot(self, other: "Vector3") -> float:
        """
        Computes the scalar dot product of this vector and another.
        Used extensively in backface culling and lighting calculations.

        dot(A, B) = Ax*Bx + Ay*By + Az*Bz
        """
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vector3") -> "Vector3":
        """
        Computes the vector cross product (this × other).
        Result is perpendicular to both input vectors.

        cross(A, B) = (Ay*Bz - Az*By,  Az*Bx - Ax*Bz,  Ax*By - Ay*Bx)
        """
        return Vector3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        """
        Computes the Euclidean magnitude of the vector.
        |V| = sqrt(Vx² + Vy² + Vz²)
        """
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def length_squared(self) -> float:
        """
        Returns squared magnitude. Avoids sqrt for performance
        when only relative comparison is needed.
        """
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalize(self) -> "Vector3":
        """
        Returns the unit vector in the same direction.
        Returns zero vector if magnitude is below epsilon threshold.
        """
        mag = self.length()
        if mag < 1e-12:
            return Vector3(0.0, 0.0, 0.0)
        return self / mag

    def distance_to(self, other: "Vector3") -> float:
        """Euclidean distance between this point and another."""
        return (self - other).length()

    def lerp(self, other: "Vector3", t: float) -> "Vector3":
        """
        Linear interpolation between this vector and target.

        lerp(A, B, t) = A + t * (B - A)

        Args:
            other: Target Vector3.
            t:     Blend factor [0.0, 1.0].

        Returns:
            Interpolated Vector3.
        """
        t = max(0.0, min(1.0, t))
        return Vector3(
            self.x + (other.x - self.x) * t,
            self.y + (other.y - self.y) * t,
            self.z + (other.z - self.z) * t,
        )

    def reflect(self, normal: "Vector3") -> "Vector3":
        """
        Reflects this vector across a surface normal.

        reflect(V, N) = V - 2 * dot(V, N) * N
        """
        n = normal.normalize()
        factor = 2.0 * self.dot(n)
        return Vector3(
            self.x - factor * n.x,
            self.y - factor * n.y,
            self.z - factor * n.z,
        )

    def to_tuple(self) -> Tuple[float, float, float]:
        """Returns the vector as a plain (x, y, z) Python tuple."""
        return (self.x, self.y, self.z)

    def to_tuple2d(self) -> Tuple[float, float]:
        """Returns only the X and Y components as a 2D tuple."""
        return (self.x, self.y)

    @staticmethod
    def from_tuple(t: Tuple) -> "Vector3":
        """Constructs a Vector3 from any indexable sequence of length >= 3."""
        return Vector3(float(t[0]), float(t[1]), float(t[2]))

    @staticmethod
    def zero() -> "Vector3":
        """Returns the zero vector (0, 0, 0)."""
        return Vector3(0.0, 0.0, 0.0)

    @staticmethod
    def up() -> "Vector3":
        """Returns the world up vector (0, 1, 0)."""
        return Vector3(0.0, 1.0, 0.0)

    @staticmethod
    def forward() -> "Vector3":
        """Returns the world forward vector (0, 0, -1)."""
        return Vector3(0.0, 0.0, -1.0)


# =============================================================================
# SECTION 2: MATRIX4x4 - HOMOGENEOUS TRANSFORMATION MATRIX
# =============================================================================

class Matrix4x4:
    """
    Row-major 4x4 homogeneous transformation matrix.
    Supports rotation, translation, scaling, and perspective projection.
    All values stored as a flat list of 16 floats in row-major order:

    | m[0]  m[1]  m[2]  m[3]  |   Row 0
    | m[4]  m[5]  m[6]  m[7]  |   Row 1
    | m[8]  m[9]  m[10] m[11] |   Row 2
    | m[12] m[13] m[14] m[15] |   Row 3
    """

    __slots__ = ("m",)

    def __init__(self, values: Optional[List[float]] = None) -> None:
        if values is not None:
            if len(values) != 16:
                raise ValueError("Matrix4x4 requires exactly 16 float values.")
            self.m: List[float] = [float(v) for v in values]
        else:
            # Default to identity matrix
            self.m = [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ]

    def __repr__(self) -> str:
        rows = []
        for row in range(4):
            base = row * 4
            rows.append(
                f"  [{self.m[base]:.4f}, {self.m[base+1]:.4f}, "
                f"{self.m[base+2]:.4f}, {self.m[base+3]:.4f}]"
            )
        return "Matrix4x4(\n" + "\n".join(rows) + "\n)"

    # -------------------------------------------------------------------------
    # Matrix multiplication
    # -------------------------------------------------------------------------

    def __matmul__(self, other: "Matrix4x4") -> "Matrix4x4":
        """
        Matrix multiplication (self @ other).
        Standard 4x4 matrix product using row-column dot products.
        """
        a = self.m
        b = other.m
        result = [0.0] * 16

        for row in range(4):
            for col in range(4):
                total = 0.0
                for k in range(4):
                    total += a[row * 4 + k] * b[k * 4 + col]
                result[row * 4 + col] = total

        return Matrix4x4(result)

    # -------------------------------------------------------------------------
    # Point and vector transformation
    # -------------------------------------------------------------------------

    def transform_point(self, v: Vector3) -> Vector3:
        """
        Transforms a 3D point by this 4x4 matrix (applies translation).
        Treats the input as a homogeneous point (w=1).

        result = M * [x, y, z, 1]^T
        """
        m = self.m
        x = m[0]*v.x + m[1]*v.y + m[2]*v.z  + m[3]
        y = m[4]*v.x + m[5]*v.y + m[6]*v.z  + m[7]
        z = m[8]*v.x + m[9]*v.y + m[10]*v.z + m[11]
        w = m[12]*v.x + m[13]*v.y + m[14]*v.z + m[15]

        if abs(w) > 1e-12 and abs(w - 1.0) > 1e-9:
            inv_w = 1.0 / w
            return Vector3(x * inv_w, y * inv_w, z * inv_w)
        return Vector3(x, y, z)

    def transform_direction(self, v: Vector3) -> Vector3:
        """
        Transforms a direction vector (ignores translation, w=0).
        Used for normal vector transformations.
        """
        m = self.m
        x = m[0]*v.x + m[1]*v.y + m[2]*v.z
        y = m[4]*v.x + m[5]*v.y + m[6]*v.z
        z = m[8]*v.x + m[9]*v.y + m[10]*v.z
        return Vector3(x, y, z)

    # -------------------------------------------------------------------------
    # Static factory constructors
    # -------------------------------------------------------------------------

    @staticmethod
    def identity() -> "Matrix4x4":
        """Returns the 4x4 identity matrix."""
        return Matrix4x4()

    @staticmethod
    def rotation_x(angle_rad: float) -> "Matrix4x4":
        """
        Rotation matrix around the X axis by angle_rad radians.

        Rx(θ) = | 1    0       0    0 |
                | 0  cos(θ) -sin(θ)  0 |
                | 0  sin(θ)  cos(θ)  0 |
                | 0    0       0    1 |
        """
        c = math.cos(angle_rad)
        s = math.sin(angle_rad)
        return Matrix4x4([
            1.0, 0.0, 0.0, 0.0,
            0.0,   c,  -s, 0.0,
            0.0,   s,   c, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])

    @staticmethod
    def rotation_y(angle_rad: float) -> "Matrix4x4":
        """
        Rotation matrix around the Y axis by angle_rad radians.

        Ry(θ) = |  cos(θ)  0  sin(θ)  0 |
                |    0     1    0     0 |
                | -sin(θ)  0  cos(θ)  0 |
                |    0     0    0     1 |
        """
        c = math.cos(angle_rad)
        s = math.sin(angle_rad)
        return Matrix4x4([
              c, 0.0,   s, 0.0,
            0.0, 1.0, 0.0, 0.0,
             -s, 0.0,   c, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])

    @staticmethod
    def rotation_z(angle_rad: float) -> "Matrix4x4":
        """
        Rotation matrix around the Z axis by angle_rad radians.

        Rz(θ) = | cos(θ) -sin(θ)  0  0 |
                | sin(θ)  cos(θ)  0  0 |
                |   0       0     1  0 |
                |   0       0     0  1 |
        """
        c = math.cos(angle_rad)
        s = math.sin(angle_rad)
        return Matrix4x4([
              c,  -s, 0.0, 0.0,
              s,   c, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])

    @staticmethod
    def translation(tx: float, ty: float, tz: float) -> "Matrix4x4":
        """
        Translation matrix by (tx, ty, tz).

        T = | 1  0  0  tx |
            | 0  1  0  ty |
            | 0  0  1  tz |
            | 0  0  0   1 |
        """
        return Matrix4x4([
            1.0, 0.0, 0.0,  tx,
            0.0, 1.0, 0.0,  ty,
            0.0, 0.0, 1.0,  tz,
            0.0, 0.0, 0.0, 1.0,
        ])

    @staticmethod
    def scale(sx: float, sy: float, sz: float) -> "Matrix4x4":
        """
        Uniform or non-uniform scaling matrix.

        S = | sx  0   0   0 |
            |  0  sy  0   0 |
            |  0   0  sz  0 |
            |  0   0   0  1 |
        """
        return Matrix4x4([
             sx, 0.0, 0.0, 0.0,
            0.0,  sy, 0.0, 0.0,
            0.0, 0.0,  sz, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])

    @staticmethod
    def perspective(focal_length: float, cx: float, cy: float) -> "Matrix4x4":
        """
        Simplified perspective projection matrix for the terrain renderer.
        Maps 3D world coordinates to 2D screen pixel coordinates.

        Projects point (X, Y, Z) to screen:
            screen_x = cx + (X * focal_length) / Z
            screen_y = cy + (Y * focal_length) / Z

        Encoded as a matrix for composability.

        Args:
            focal_length: Camera focal length in pixels.
            cx:           Screen horizontal center offset.
            cy:           Screen vertical center offset.
        """
        f = focal_length
        return Matrix4x4([
            f,   0.0, cx,  0.0,
            0.0, f,   cy,  0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
        ])


# =============================================================================
# SECTION 3: CAMERA PROJECTION PIPELINE
# =============================================================================

def project_point(
    world_pos: Vector3,
    pitch_matrix: Matrix4x4,
    focal_length: float,
    camera_depth: float,
    viewport_cx: float,
    viewport_cy: float,
) -> Optional[Tuple[int, int, float]]:
    """
    Full perspective projection pipeline for a single 3D world point.

    Pipeline stages:
        1. Apply pitch rotation matrix to world position.
        2. Translate point along Z axis by camera_depth (push scene back).
        3. Perspective divide: screen_x = cx + (X * f) / Z
                               screen_y = cy + (Y * f) / Z
        4. Return pixel coordinates and normalized depth scalar.

    Args:
        world_pos:    Vector3 in world coordinates.
        pitch_matrix: Pre-computed pitch rotation Matrix4x4.
        focal_length: Camera focal length (pixels).
        camera_depth: Z translation offset (depth into scene).
        viewport_cx:  Horizontal screen center offset (pixels).
        viewport_cy:  Vertical screen center offset (pixels).

    Returns:
        (screen_x, screen_y, depth_t) tuple where depth_t is in [0.0, 1.0],
        or None if the point is behind the camera (Z <= 0).
    """
    # Stage 1: Apply pitch rotation
    rotated = pitch_matrix.transform_point(world_pos)

    # Stage 2: Apply depth translation (camera pushes scene backwards)
    z_translated = rotated.z + camera_depth

    # Stage 3: Reject points behind the camera plane
    if z_translated <= 0.1:
        return None

    # Stage 4: Perspective divide
    inv_z = focal_length / z_translated
    screen_x = int(viewport_cx + rotated.x * inv_z)
    screen_y = int(viewport_cy + rotated.y * inv_z)

    # Stage 5: Compute normalized depth scalar for brightness shading
    # Map Z range [camera_depth, camera_depth * 4] to [0.0 (near), 1.0 (far)]
    depth_near = camera_depth * 0.5
    depth_far  = camera_depth * 4.0
    depth_t    = max(0.0, min(1.0,
        (z_translated - depth_near) / (depth_far - depth_near)
    ))

    return (screen_x, screen_y, depth_t)


# =============================================================================
# SECTION 4: PERLIN NOISE 3D - DETERMINISTIC VALUE NOISE
# =============================================================================

class PerlinNoise3D:
    """
    Deterministic 3D gradient noise implementation (Ken Perlin's improved
    algorithm). Produces smooth, continuous noise values in range [-1.0, 1.0].

    Seeded for reproducibility — same seed always produces identical noise fields.
    Used for FBM terrain elevation and globe surface texture variation.
    """

    # Perlin's canonical gradient direction table (16 gradient vectors)
    _GRAD3: List[Tuple[float, float, float]] = [
        ( 1.0,  1.0,  0.0), (-1.0,  1.0,  0.0),
        ( 1.0, -1.0,  0.0), (-1.0, -1.0,  0.0),
        ( 1.0,  0.0,  1.0), (-1.0,  0.0,  1.0),
        ( 1.0,  0.0, -1.0), (-1.0,  0.0, -1.0),
        ( 0.0,  1.0,  1.0), ( 0.0, -1.0,  1.0),
        ( 0.0,  1.0, -1.0), ( 0.0, -1.0, -1.0),
        ( 1.0,  1.0,  0.0), (-1.0,  1.0,  0.0),
        ( 0.0, -1.0,  1.0), ( 0.0, -1.0, -1.0),
    ]

    def __init__(self, seed: int = 0) -> None:
        """
        Initializes the noise generator with a deterministic permutation table.

        Args:
            seed: Integer seed for reproducible noise output.
        """
        self._seed: int = seed
        rng = random.Random(seed)

        # Build permutation table: shuffle [0..255] then double it
        perm_base = list(range(256))
        rng.shuffle(perm_base)
        self._perm: List[int] = perm_base * 2    # length 512, avoids modulo in hot path

    @staticmethod
    def _fade(t: float) -> float:
        """
        Perlin's quintic fade (smoothstep) function.
        Smooths interpolation to eliminate visible grid artifacts.

        f(t) = 6t⁵ - 15t⁴ + 10t³
        """
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        """Linear interpolation between a and b by factor t."""
        return a + t * (b - a)

    def _grad(self, hash_val: int, x: float, y: float, z: float) -> float:
        """
        Selects a gradient vector from the table using the hash value,
        then computes its dot product with the offset vector (x, y, z).

        Args:
            hash_val: Permutation table lookup result.
            x, y, z:  Fractional position offsets within the unit cube.

        Returns:
            Gradient dot product scalar.
        """
        g = self._GRAD3[hash_val & 15]
        return g[0] * x + g[1] * y + g[2] * z

    def noise(self, x: float, y: float, z: float) -> float:
        """
        Evaluates 3D Perlin gradient noise at position (x, y, z).

        Algorithm:
            1. Find unit cube containing the point.
            2. Compute relative position within the cube.
            3. Apply quintic fade curves to each dimension.
            4. Hash corners of the cube using permutation table.
            5. Trilinear interpolation of gradient dot products.

        Args:
            x, y, z: World-space coordinates (any range, noise tiles at integers).

        Returns:
            Noise value in approximately [-1.0, 1.0].
        """
        p = self._perm

        # Step 1: Integer unit cube coordinates
        xi = int(math.floor(x)) & 255
        yi = int(math.floor(y)) & 255
        zi = int(math.floor(z)) & 255

        # Step 2: Fractional offsets within the cube
        xf = x - math.floor(x)
        yf = y - math.floor(y)
        zf = z - math.floor(z)

        # Step 3: Quintic fade curves
        u = self._fade(xf)
        v = self._fade(yf)
        w = self._fade(zf)

        # Step 4: Hash all 8 cube corners
        aaa = p[p[p[ xi   ] +  yi   ] +  zi  ]
        aba = p[p[p[ xi   ] + (yi+1)] +  zi  ]
        aab = p[p[p[ xi   ] +  yi   ] + (zi+1)]
        abb = p[p[p[ xi   ] + (yi+1)] + (zi+1)]
        baa = p[p[p[(xi+1)] +  yi   ] +  zi  ]
        bba = p[p[p[(xi+1)] + (yi+1)] +  zi  ]
        bab = p[p[p[(xi+1)] +  yi   ] + (zi+1)]
        bbb = p[p[p[(xi+1)] + (yi+1)] + (zi+1)]

        # Step 5: Trilinear interpolation of gradient contributions
        x1 = self._lerp(
            self._grad(aaa, xf,       yf,       zf      ),
            self._grad(baa, xf - 1.0, yf,       zf      ),
            u
        )
        x2 = self._lerp(
            self._grad(aba, xf,       yf - 1.0, zf      ),
            self._grad(bba, xf - 1.0, yf - 1.0, zf      ),
            u
        )
        y1 = self._lerp(x1, x2, v)

        x3 = self._lerp(
            self._grad(aab, xf,       yf,       zf - 1.0),
            self._grad(bab, xf - 1.0, yf,       zf - 1.0),
            u
        )
        x4 = self._lerp(
            self._grad(abb, xf,       yf - 1.0, zf - 1.0),
            self._grad(bbb, xf - 1.0, yf - 1.0, zf - 1.0),
            u
        )
        y2 = self._lerp(x3, x4, v)

        return self._lerp(y1, y2, w)


# =============================================================================
# SECTION 5: FRACTAL BROWNIAN MOTION (FBM) TERRAIN ELEVATION
# =============================================================================

def fbm_elevation(
    noise: PerlinNoise3D,
    nx: float,
    nz: float,
    time_offset: float,
    octaves: int,
    persistence: float,
    lacunarity: float,
    base_amplitude: float,
) -> float:
    """
    Fractal Brownian Motion elevation function for terrain grid vertices.
    Accumulates multiple octaves of Perlin noise at increasing frequencies
    and decreasing amplitudes to produce natural-looking terrain.

    Mathematical formulation:
        H(x, z) = Σ(i=0 to octaves-1) [ amplitude_i * noise(freq_i * x,
                                                               freq_i * z,
                                                               time_offset) ]
        where:
            amplitude_i = persistence^i
            freq_i      = lacunarity^i

    Args:
        noise:          PerlinNoise3D instance (seeded for determinism).
        nx:             Normalized X coordinate in [-1.0, 1.0].
        nz:             Normalized Z coordinate in [-1.0, 1.0].
        time_offset:    Slow time drift to animate the terrain subtly.
        octaves:        Number of FBM accumulation layers (default 5).
        persistence:    Amplitude decay per octave (default 0.5).
        lacunarity:     Frequency multiplier per octave (default 2.0).
        base_amplitude: World-unit scaling for the maximum elevation.

    Returns:
        Elevation value in approximately [-base_amplitude, +base_amplitude].
    """
    total:     float = 0.0
    amplitude: float = 1.0
    frequency: float = 1.0
    max_value: float = 0.0     # Used for normalization

    for _ in range(octaves):
        total     += noise.noise(nx * frequency, nz * frequency, time_offset) * amplitude
        max_value += amplitude
        amplitude *= persistence
        frequency *= lacunarity

    # Normalize to [-1, 1] then scale by base amplitude
    if max_value > 0.0:
        return (total / max_value) * base_amplitude
    return 0.0


# =============================================================================
# SECTION 6: FFT DISPLACEMENT COMPUTATION
# =============================================================================

def compute_fft_displacement(
    fft_bands: List[float],
    grid_x: float,
    grid_z: float,
    grid_half: float,
    fft_scale: float,
) -> float:
    """
    Applies real-time FFT audio frequency band data as terrain displacement.
    The displacement is localized by distance from the grid center — points
    farther from center receive less FFT influence, creating a wave peak
    structure concentrated at the terrain's center region.

    Mathematical formulation:
        fft_index = clamp(int(band_x * 64), 0, 63)
        band_val  = fft_bands[fft_index]
        dist_norm = sqrt(grid_x² + grid_z²) / grid_half
        displacement = band_val * fft_scale * (1.0 - dist_norm)

    Args:
        fft_bands:  List of 64 normalized FFT amplitude values [0.0, 1.0].
        grid_x:     Grid point X in world space (centered around 0).
        grid_z:     Grid point Z in world space (centered around 0).
        grid_half:  Half-width of the grid in world units (for normalization).
        fft_scale:  Maximum displacement in world units.

    Returns:
        Vertical displacement offset to add to FBM elevation.
    """
    if not fft_bands or len(fft_bands) == 0:
        return 0.0

    # Map X position to FFT band index
    band_t     = max(0.0, min(1.0, (grid_x / grid_half) * 0.5 + 0.5))
    band_index = min(len(fft_bands) - 1, int(band_t * len(fft_bands)))
    band_val   = float(fft_bands[band_index])

    # Distance falloff from center
    dist = math.sqrt(grid_x * grid_x + grid_z * grid_z)
    if grid_half > 0.0:
        dist_norm = min(1.0, dist / grid_half)
    else:
        dist_norm = 0.0

    # Displacement decreases towards edges
    local_scale = max(0.0, 1.0 - dist_norm)
    return band_val * fft_scale * local_scale


# =============================================================================
# SECTION 7: FIBONACCI SPHERE DISTRIBUTION
# =============================================================================

def fibonacci_sphere_points(n: int, radius: float = 1.0) -> List[Vector3]:
    """
    Distributes N points evenly across a unit sphere surface using the
    golden ratio Fibonacci spiral method.

    This avoids clustering at poles (unlike latitude/longitude sampling)
    and produces a visually balanced wireframe globe point distribution.

    Mathematical formulation:
        φ = π * (3 - √5)           # Golden angle in radians (~2.399963 rad)
        For i in range(n):
            y   = 1 - (i / (n - 1)) * 2     # y goes from 1 to -1
            r   = √(1 - y²)                  # radius at this y slice
            θ   = φ * i                      # accumulated golden angle
            x   = cos(θ) * r
            z   = sin(θ) * r

    Args:
        n:      Number of points to distribute.
        radius: Sphere radius (scales all output coordinates).

    Returns:
        List of n Vector3 points on the sphere surface.
    """
    points: List[Vector3] = []
    golden_angle: float = math.pi * (3.0 - math.sqrt(5.0))   # ~2.39996 radians

    for i in range(n):
        # Y coordinate: linearly spaced from +1 to -1 across all points
        if n > 1:
            y = 1.0 - (i / float(n - 1)) * 2.0
        else:
            y = 0.0

        # Radius of the horizontal circle at this latitude
        r = math.sqrt(max(0.0, 1.0 - y * y))

        # Longitude angle using golden ratio stepping
        theta = golden_angle * float(i)

        x = math.cos(theta) * r
        z = math.sin(theta) * r

        points.append(Vector3(x * radius, y * radius, z * radius))

    return points


# =============================================================================
# SECTION 8: GLOBE ROTATION PIPELINE
# =============================================================================

def rotate_globe_point(
    point: Vector3,
    yaw: float,
    tilt: float,
) -> Vector3:
    """
    Applies continuous yaw rotation and fixed tilt to a globe sphere point.
    Used every frame to animate the spinning wireframe globe.

    Rotation sequence (row-major, applied right-to-left):
        1. Rotate around Y axis by yaw angle (continuous spin)
        2. Rotate around X axis by tilt angle (static lean)

    Args:
        point: Original Vector3 on the sphere surface.
        yaw:   Accumulated yaw angle in radians (increases each frame).
        tilt:  Fixed tilt angle in radians (set from config).

    Returns:
        Transformed Vector3 after rotation.
    """
    # Stage 1: Yaw rotation (Y axis)
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    x1 = cos_y * point.x + sin_y * point.z
    y1 = point.y
    z1 = -sin_y * point.x + cos_y * point.z

    # Stage 2: Tilt rotation (X axis)
    cos_x = math.cos(tilt)
    sin_x = math.sin(tilt)
    x2 = x1
    y2 = cos_x * y1 - sin_x * z1
    z2 = sin_x * y1 + cos_x * z1

    return Vector3(x2, y2, z2)


def backface_cull(rotated_point: Vector3, view_vector: Vector3) -> bool:
    """
    Geometric backface culling for globe points.
    Determines if a sphere surface point is on the rear-facing hemisphere
    and should be hidden from rendering.

    A point is culled if its dot product with the view vector is negative:
        dot(rotated_point.normalize(), view_vector) < 0

    Args:
        rotated_point: Transformed globe vertex (post-rotation).
        view_vector:   Camera view direction vector (typically Vector3(0,0,-1)).

    Returns:
        True if the point should be CULLED (not rendered).
        False if the point is front-facing and should be rendered.
    """
    n = rotated_point.normalize()
    return n.dot(view_vector) < 0.0


def project_globe_point(
    rotated: Vector3,
    center_x: int,
    center_y: int,
    radius: int,
    focal_length: float = 500.0,
) -> Tuple[int, int, float]:
    """
    Projects a rotated globe point from 3D sphere space to 2D screen pixels.
    Uses a simple orthographic-with-depth projection scaled to globe radius.

    Args:
        rotated:       Post-rotation Vector3 on unit sphere surface.
        center_x:      Screen X pixel coordinate of globe center.
        center_y:      Screen Y pixel coordinate of globe center.
        radius:        Globe display radius in pixels.
        focal_length:  Perspective depth scaling factor.

    Returns:
        (screen_x, screen_y, depth_t) where depth_t in [0.0, 1.0],
        0.0 = front-center, 1.0 = edge/rim.
    """
    # Perspective scaling based on Z depth
    z_offset = rotated.z + 2.5    # shift into positive Z space
    if z_offset < 0.01:
        z_offset = 0.01

    scale = radius / max(0.01, z_offset) * 1.5

    screen_x = int(center_x + rotated.x * scale)
    screen_y = int(center_y - rotated.y * scale)

    # Depth: 0.0 = facing directly toward camera (front center)
    # Use normalized Z for depth shading
    depth_t = max(0.0, min(1.0, (1.0 - rotated.z) * 0.5))

    return (screen_x, screen_y, depth_t)


# =============================================================================
# SECTION 9: GEOGRAPHIC COORDINATE CONVERSION
# =============================================================================

def latlon_to_sphere(
    latitude_deg: float,
    longitude_deg: float,
    radius: float = 1.0,
) -> Vector3:
    """
    Converts geographic latitude/longitude coordinates (degrees) to a 3D
    Cartesian point on a sphere surface of given radius.

    Standard spherical coordinate conversion:
        lat_rad = latitude  * π / 180
        lon_rad = longitude * π / 180
        x = radius * cos(lat_rad) * cos(lon_rad)
        y = radius * sin(lat_rad)
        z = radius * cos(lat_rad) * sin(lon_rad)

    Args:
        latitude_deg:  Geographic latitude in degrees [-90, +90].
        longitude_deg: Geographic longitude in degrees [-180, +180].
        radius:        Sphere radius (world units or normalized 1.0).

    Returns:
        Vector3 point on sphere surface.
    """
    lat_rad = math.radians(latitude_deg)
    lon_rad = math.radians(longitude_deg)

    x = radius * math.cos(lat_rad) * math.cos(lon_rad)
    y = radius * math.sin(lat_rad)
    z = radius * math.cos(lat_rad) * math.sin(lon_rad)

    return Vector3(x, y, z)


# =============================================================================
# SECTION 10: CATMULL-ROM SPLINE INTERPOLATION
# =============================================================================

def catmull_rom(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    t: float,
) -> Tuple[float, float]:
    """
    Catmull-Rom cubic spline interpolation between four control points.
    Produces a smooth curve that passes exactly through p1 and p2.
    Used for smoothing real-time line graphs in Panels E.1, E.2, E.3.

    Mathematical formulation (matrix form, alpha=0.5 centripetal):
        Q(t) = 0.5 * [
            (-t³ + 2t² - t    ) * P0 +
            ( 3t³ - 5t² + 2   ) * P1 +
            (-3t³ + 4t² + t   ) * P2 +
            ( t³  - t²        ) * P3
        ]

    Args:
        p0, p1, p2, p3: Control point (x, y) tuples.
                        Curve passes through p1→p2.
        t:              Interpolation parameter in [0.0, 1.0].

    Returns:
        Interpolated (x, y) tuple point on the spline.
    """
    t  = max(0.0, min(1.0, t))
    t2 = t  * t
    t3 = t2 * t

    # Catmull-Rom basis coefficients
    c0 = -t3 + 2.0 * t2 - t
    c1 =  3.0 * t3 - 5.0 * t2 + 2.0
    c2 = -3.0 * t3 + 4.0 * t2 + t
    c3 =  t3 - t2

    x = 0.5 * (c0 * p0[0] + c1 * p1[0] + c2 * p2[0] + c3 * p3[0])
    y = 0.5 * (c0 * p0[1] + c1 * p1[1] + c2 * p2[1] + c3 * p3[1])

    return (x, y)


def catmull_rom_chain(
    points: List[Tuple[float, float]],
    segments_per_span: int = 12,
) -> List[Tuple[float, float]]:
    """
    Generates a full smooth curve through a list of control points by
    chaining Catmull-Rom segments end-to-end.

    For N input points, generates N-1 spans.
    Clamps phantom endpoints at the curve boundaries by repeating
    the first and last points.

    Args:
        points:             List of (x, y) control point tuples. Minimum 2.
        segments_per_span:  Number of interpolated sub-points per span.
                            Higher = smoother curve, higher CPU cost.

    Returns:
        List of interpolated (x, y) tuples forming the smooth curve.
    """
    if len(points) < 2:
        return list(points)

    if len(points) == 2:
        # Degenerate: just return the two points (linear)
        return [points[0], points[1]]

    # Extend control points with phantom endpoints
    extended: List[Tuple[float, float]] = (
        [points[0]] + list(points) + [points[-1]]
    )

    result: List[Tuple[float, float]] = []

    # Iterate over spans (each span: p[i] → p[i+1])
    for i in range(1, len(extended) - 2):
        p0 = extended[i - 1]
        p1 = extended[i    ]
        p2 = extended[i + 1]
        p3 = extended[i + 2]

        for s in range(segments_per_span):
            t = s / float(segments_per_span)
            result.append(catmull_rom(p0, p1, p2, p3, t))

    # Append the final endpoint
    result.append(points[-1])

    return result


# =============================================================================
# SECTION 11: EKG HEARTBEAT WAVEFORM MATHEMATICS
# =============================================================================

def ekg_sample(elapsed: float, cycle_duration: float, amplitude: float) -> float:
    """
    Computes the vertical displacement of the EKG heartbeat waveform
    at a given elapsed time.

    The waveform is a superposition of multiple sinusoidal components
    modulated by a sharp Gaussian envelope to simulate the QRS complex
    of a cardiac trace:

        t_mod  = (elapsed % cycle_duration) / cycle_duration   # [0, 1]

        Components:
            Baseline drift:  0.1 * sin(2π * t_mod)
            P-wave:          0.15 * exp(-((t_mod - 0.15)/0.03)²)
            QRS complex:     1.0  * exp(-((t_mod - 0.35)/0.015)²)
            S-wave notch:   -0.25 * exp(-((t_mod - 0.42)/0.025)²)
            T-wave:          0.35 * exp(-((t_mod - 0.65)/0.06)²)

        Total = amplitude * sum(components)

    Args:
        elapsed:        Total elapsed time in seconds.
        cycle_duration: Duration of one full cardiac cycle in seconds.
        amplitude:      Peak pixel displacement.

    Returns:
        Vertical Y displacement in pixels (positive = up on screen).
    """
    t_mod = (elapsed % cycle_duration) / cycle_duration

    two_pi = 2.0 * math.pi

    # Baseline respiratory drift
    baseline = 0.08 * math.sin(two_pi * t_mod)

    # P-wave (atrial depolarization)
    p_center = 0.15
    p_wave   = 0.15 * math.exp(-((t_mod - p_center) / 0.030) ** 2)

    # QRS complex (ventricular depolarization — sharp spike)
    qrs_center = 0.35
    qrs_wave   = 1.00 * math.exp(-((t_mod - qrs_center) / 0.012) ** 2)

    # S-wave notch (immediately post-QRS dip)
    s_center = 0.42
    s_wave   = -0.28 * math.exp(-((t_mod - s_center) / 0.022) ** 2)

    # T-wave (ventricular repolarization)
    t_center = 0.65
    t_wave   = 0.35 * math.exp(-((t_mod - t_center) / 0.060) ** 2)

    total = baseline + p_wave + qrs_wave + s_wave + t_wave

    return amplitude * total


def generate_ekg_points(
    elapsed: float,
    cycle_duration: float,
    amplitude: float,
    panel_x: int,
    panel_y_center: int,
    panel_width: int,
    num_points: int,
    scroll_speed: float = 1.0,
) -> List[Tuple[int, int]]:
    """
    Generates a list of screen pixel coordinates tracing the EKG waveform
    across the full width of Panel E.4.

    The waveform scrolls left in real time using elapsed time as a phase offset.

    Args:
        elapsed:        Total elapsed session time in seconds.
        cycle_duration: Cardiac cycle period in seconds.
        amplitude:      Peak pixel displacement from center Y.
        panel_x:        Left edge X pixel of the panel.
        panel_y_center: Vertical center Y pixel of the EKG trace.
        panel_width:    Pixel width of the EKG display area.
        num_points:     Number of sample points (horizontal resolution).
        scroll_speed:   Time units per pixel width (controls scroll rate).

    Returns:
        List of (screen_x, screen_y) integer pixel tuples.
    """
    points: List[Tuple[int, int]] = []

    for i in range(num_points):
        # Map pixel position to time offset (scrolling backward as time advances)
        x_norm    = i / float(max(1, num_points - 1))
        t_offset  = elapsed - (1.0 - x_norm) * cycle_duration * scroll_speed
        y_disp    = ekg_sample(t_offset, cycle_duration, amplitude)

        screen_x  = panel_x + int(x_norm * panel_width)
        screen_y  = panel_y_center - int(y_disp)   # invert Y (screen coords)

        points.append((screen_x, screen_y))

    return points


# =============================================================================
# SECTION 12: GENERAL MATHEMATICAL UTILITIES
# =============================================================================

def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamps value to [minimum, maximum] inclusive."""
    return max(minimum, min(maximum, value))


def lerp(a: float, b: float, t: float) -> float:
    """
    Scalar linear interpolation.
    lerp(a, b, t) = a + t * (b - a)
    """
    return a + clamp(t, 0.0, 1.0) * (b - a)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """
    Hermite smoothstep interpolation between edge0 and edge1.
    Returns 0 for x <= edge0, 1 for x >= edge1, smooth S-curve between.

    t = clamp((x - edge0) / (edge1 - edge0), 0, 1)
    result = t² * (3 - 2t)
    """
    if edge1 <= edge0:
        return 0.0
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def map_range(
    value: float,
    in_min: float,
    in_max: float,
    out_min: float,
    out_max: float,
) -> float:
    """
    Maps a value from one numeric range to another.
    Equivalent to Arduino's map() function but floating-point.

    result = out_min + (value - in_min) / (in_max - in_min) * (out_max - out_min)
    """
    if abs(in_max - in_min) < 1e-12:
        return out_min
    t = (value - in_min) / (in_max - in_min)
    return out_min + clamp(t, 0.0, 1.0) * (out_max - out_min)


def normalize_fft(
    raw_fft: List[float],
    num_bands: int,
    log_scale: bool = True,
) -> List[float]:
    """
    Normalizes and compresses a raw FFT magnitude array into N frequency bands.
    Optionally applies logarithmic compression to match human hearing perception.

    Steps:
        1. Divide raw FFT into num_bands equal-width buckets.
        2. Average the magnitude within each bucket.
        3. Apply log compression: band = log10(1 + 9 * band) [maps 0→0, 1→1]
        4. Normalize all bands to [0.0, 1.0] by dividing by global maximum.

    Args:
        raw_fft:   List of raw FFT magnitude values (half-spectrum).
        num_bands: Number of output frequency bands (default 64).
        log_scale: Apply logarithmic compression. Default True.

    Returns:
        List of num_bands floats in range [0.0, 1.0].
    """
    if not raw_fft or len(raw_fft) == 0:
        return [0.0] * num_bands

    raw_len    = len(raw_fft)
    bands      = [0.0] * num_bands
    chunk_size = max(1, raw_len // num_bands)

    for b in range(num_bands):
        start = b * chunk_size
        end   = min(raw_len, start + chunk_size)
        if start >= raw_len:
            bands[b] = 0.0
        else:
            chunk     = raw_fft[start:end]
            bands[b]  = sum(chunk) / len(chunk)

    # Logarithmic compression
    if log_scale:
        for b in range(num_bands):
            bands[b] = math.log10(1.0 + 9.0 * max(0.0, bands[b]))

    # Global normalization
    max_val = max(bands)
    if max_val > 1e-10:
        for b in range(num_bands):
            bands[b] = bands[b] / max_val

    return bands


def compute_rms(samples: List[float]) -> float:
    """
    Computes the Root Mean Square (RMS) of an audio sample buffer.
    Used for raw volume level display and terrain modulation strength.

    RMS = sqrt( (1/N) * Σ(sample²) )

    Args:
        samples: List of audio sample values (any numeric range).

    Returns:
        RMS scalar (same units as input samples).
    """
    if not samples:
        return 0.0
    mean_sq = sum(s * s for s in samples) / len(samples)
    return math.sqrt(mean_sq)


def stability_score(
    cpu_temp: float,
    cpu_usage: float,
    ram_usage: float,
    ping_ms: float,
    internet_up: bool,
) -> float:
    """
    Computes a composite system stability score in range [0.0, 100.0].
    Used for the Panel E.4 semicircle health gauge.

    Scoring algorithm:
        temp_penalty  = clamp((cpu_temp  - 40) / 45 * 30, 0, 30)
        cpu_penalty   = clamp((cpu_usage - 50) / 50 * 25, 0, 25)
        ram_penalty   = clamp((ram_usage - 60) / 40 * 20, 0, 20)
        ping_penalty  = clamp((ping_ms   - 50) / 250 * 15, 0, 15)
        net_penalty   = 10 if not internet_up else 0

        score = 100 - (temp_penalty + cpu_penalty + ram_penalty
                       + ping_penalty + net_penalty)

    Args:
        cpu_temp:    CPU temperature in degrees Celsius.
        cpu_usage:   CPU utilization percentage [0, 100].
        ram_usage:   RAM utilization percentage [0, 100].
        ping_ms:     Network round-trip latency in milliseconds.
        internet_up: True if internet connectivity is confirmed.

    Returns:
        Stability score clamped to [0.0, 100.0].
    """
    temp_penalty = clamp((cpu_temp  - 40.0)  / 45.0  * 30.0, 0.0, 30.0)
    cpu_penalty  = clamp((cpu_usage - 50.0)  / 50.0  * 25.0, 0.0, 25.0)
    ram_penalty  = clamp((ram_usage - 60.0)  / 40.0  * 20.0, 0.0, 20.0)
    ping_penalty = clamp((ping_ms   - 50.0)  / 250.0 * 15.0, 0.0, 15.0)
    net_penalty  = 10.0 if not internet_up else 0.0

    raw_score = 100.0 - (temp_penalty + cpu_penalty + ram_penalty
                         + ping_penalty + net_penalty)
    return clamp(raw_score, 0.0, 100.0)


def semicircle_arc_point(
    cx: float,
    cy: float,
    radius: float,
    angle_deg: float,
) -> Tuple[int, int]:
    """
    Computes the pixel coordinate of a point on a semicircle arc.
    Used for the Panel E.4 health gauge needle endpoint.

    The semicircle spans from 180° (left) to 0° (right), with the
    open face pointing downward (gauge reads left=bad, right=good).

    angle_deg = 0° → right  (100% stable)
    angle_deg = 90° → top   (50% stable)
    angle_deg = 180° → left (0% stable)

    Args:
        cx:        Center X pixel.
        cy:        Center Y pixel.
        radius:    Arc radius in pixels.
        angle_deg: Angle in degrees [0, 180] across the arc.

    Returns:
        (screen_x, screen_y) integer pixel coordinate.
    """
    angle_rad = math.radians(180.0 - angle_deg)
    x = int(cx + radius * math.cos(angle_rad))
    y = int(cy - radius * math.sin(angle_rad))
    return (x, y)


def great_circle_interpolate(
    p1: Vector3,
    p2: Vector3,
    t: float,
) -> Vector3:
    """
    Spherical linear interpolation (SLERP) between two unit sphere points.
    Used to place stipple dots along globe great-circle connection lines.

    SLERP formula:
        Ω = arccos(dot(p1, p2))
        result = (sin((1-t)*Ω) / sin(Ω)) * p1 + (sin(t*Ω) / sin(Ω)) * p2

    Falls back to linear interpolation if Ω is near zero (parallel vectors).

    Args:
        p1: Start Vector3 on unit sphere surface.
        p2: End Vector3 on unit sphere surface.
        t:  Interpolation parameter in [0.0, 1.0].

    Returns:
        Interpolated Vector3 on the unit sphere surface.
    """
    t = clamp(t, 0.0, 1.0)

    dot_product = clamp(p1.dot(p2), -1.0, 1.0)
    omega       = math.acos(dot_product)

    if omega < 1e-6:
        # Vectors nearly parallel — linear blend
        return p1.lerp(p2, t)

    sin_omega = math.sin(omega)
    w1 = math.sin((1.0 - t) * omega) / sin_omega
    w2 = math.sin(t * omega)         / sin_omega

    return Vector3(
        w1 * p1.x + w2 * p2.x,
        w1 * p1.y + w2 * p2.y,
        w1 * p1.z + w2 * p2.z,
    )


# =============================================================================
# SECTION 13: TERRAIN GRID GENERATOR
# =============================================================================

def generate_terrain_grid(
    density: int,
    spacing: float,
) -> List[Tuple[float, float]]:
    """
    Generates the base (X, Z) world coordinates for all terrain grid vertices.
    The grid is centered at world origin (0, 0).

    For a grid of NxN density:
        x_i = (i - N/2) * spacing   for i in range(N)
        z_j = (j - N/2) * spacing   for j in range(N)

    Args:
        density: Number of points per side (NxN grid = density² total points).
        spacing: World-unit distance between adjacent grid vertices.

    Returns:
        List of (world_x, world_z) tuples for all density² grid vertices,
        ordered row by row (Z outer loop, X inner loop).
    """
    half = density / 2.0
    grid: List[Tuple[float, float]] = []

    for j in range(density):
        for i in range(density):
            world_x = (i - half) * spacing
            world_z = (j - half) * spacing
            grid.append((world_x, world_z))

    return grid


# =============================================================================
# SECTION 14: WAVEFORM VISUALIZATION MATHEMATICS (BRAINSTORM MODE)
# =============================================================================

def generate_waveform_points(
    fft_bands: List[float],
    center_x: int,
    center_y: int,
    width: int,
    height: int,
    num_points: int,
    elapsed: float,
    speaking: bool,
) -> List[Tuple[int, int]]:
    """
    Generates the 2D screen points for the brainstorming mode central waveform
    visualizer. The waveform responds to live FFT audio data when speaking,
    and produces a gentle idle animation when silent.

    When speaking (speaking=True):
        - Each point's Y displacement is driven by the FFT band at that position.
        - Amplitude scales with the band value.
        - Slight time-based phase shifting creates flowing motion.

    When silent (speaking=False):
        - Gentle sine wave idle animation with low amplitude.

    Args:
        fft_bands:  Normalized FFT band list [0.0, 1.0] (64 bands expected).
        center_x:   Horizontal center of the waveform display area.
        center_y:   Vertical center of the waveform display area.
        width:      Total pixel width of the waveform display.
        height:     Total pixel height (constrains max amplitude).
        num_points: Number of horizontal sample points.
        elapsed:    Total elapsed time in seconds (for animation phase).
        speaking:   True if voice is actively captured or AI is speaking.

    Returns:
        List of (screen_x, screen_y) pixel coordinate tuples.
    """
    points: List[Tuple[int, int]] = []
    half_w    = width  / 2.0
    max_amp   = height / 2.5   # maximum pixel amplitude

    for i in range(num_points):
        # Normalize position across width [-1, 1]
        x_norm  = (i / float(max(1, num_points - 1))) * 2.0 - 1.0
        screen_x = int(center_x - half_w + i * (width / float(max(1, num_points - 1))))

        if speaking and fft_bands:
            # Map point position to FFT band
            band_idx = min(len(fft_bands) - 1,
                           int(abs(x_norm) * (len(fft_bands) - 1)))
            band_val = fft_bands[band_idx]

            # Multi-layer sinusoidal modulation driven by FFT amplitude
            phase1   = elapsed * 3.5 + x_norm * math.pi * 3.0
            phase2   = elapsed * 5.2 + x_norm * math.pi * 5.0
            phase3   = elapsed * 1.8 + x_norm * math.pi * 1.5

            wave  = (
                0.55 * math.sin(phase1) +
                0.30 * math.sin(phase2) +
                0.15 * math.sin(phase3)
            )
            y_disp = wave * band_val * max_amp

            # Taper amplitude at edges for smooth envelope
            taper  = 1.0 - x_norm * x_norm   # parabolic taper
            y_disp *= taper

        else:
            # Idle gentle breathing animation
            phase   = elapsed * 1.2 + x_norm * math.pi * 2.0
            y_disp  = math.sin(phase) * max_amp * 0.08

        screen_y = int(center_y - y_disp)
        points.append((screen_x, screen_y))

    return points


# =============================================================================
# SECTION 15: ORB PARTICLE MATHEMATICS
# =============================================================================

class OrbParticle:
    """
    Single orbiting particle for the voice orb visual system.
    Each particle follows an elliptical orbit around the orb center,
    with randomized inclination, phase offset, radius, and speed.
    """

    __slots__ = (
        "radius", "inclination", "phase", "speed",
        "size", "trail_length", "trail_positions",
    )

    def __init__(
        self,
        radius: float,
        inclination: float,
        phase: float,
        speed: float,
        size: float,
        trail_length: int,
    ) -> None:
        self.radius:          float               = radius
        self.inclination:     float               = inclination
        self.phase:           float               = phase
        self.speed:           float               = speed
        self.size:            float               = size
        self.trail_length:    int                 = trail_length
        self.trail_positions: List[Tuple[int,int]] = []

    def update(self, elapsed: float, center_x: int, center_y: int) -> Tuple[int, int]:
        """
        Computes the current screen position of this particle.

        Orbit equations (inclined ellipse):
            angle = phase + elapsed * speed
            x_orbit = radius * cos(angle)
            y_orbit = radius * sin(angle) * cos(inclination)

        Args:
            elapsed:  Total elapsed time in seconds.
            center_x: Orb center screen X.
            center_y: Orb center screen Y.

        Returns:
            Current (screen_x, screen_y) pixel position.
        """
        angle   = self.phase + elapsed * self.speed
        x_orbit = self.radius * math.cos(angle)
        y_orbit = self.radius * math.sin(angle) * math.cos(self.inclination)

        screen_x = int(center_x + x_orbit)
        screen_y = int(center_y + y_orbit)

        # Record trail
        self.trail_positions.append((screen_x, screen_y))
        if len(self.trail_positions) > self.trail_length:
            self.trail_positions.pop(0)

        return (screen_x, screen_y)


def generate_orb_particles(
    count: int,
    base_radius: float,
    mode: str,
) -> List["OrbParticle"]:
    """
    Generates a set of OrbParticle instances with randomized orbital parameters.
    Particle behavior (speed, radius spread, trail length) varies by UI mode:

        ARCHER: Smooth, flowing orbits. Uniform radii. Long trails.
        HUDSON: Rigid, mechanical stepped orbits. Tighter radii. Short trails.
        BOTH:   Chaotic mix of both styles. Variable radii. Mixed trails.

    Args:
        count:       Number of particles to generate.
        base_radius: Base orbital radius in pixels.
        mode:        UIMode string ("ARCHER", "HUDSON", or "BOTH").

    Returns:
        List of OrbParticle instances ready for update/draw loops.
    """
    from config import UIMode
    rng = random.Random(42)   # seeded for consistent initial layout
    particles: List[OrbParticle] = []

    for i in range(count):
        if mode == UIMode.ARCHER:
            # Smooth, evenly spaced inclinations, moderate speed variation
            inclination  = (i / float(max(1, count))) * math.pi
            radius       = base_radius + rng.uniform(-8.0, 8.0)
            phase        = (i / float(max(1, count))) * 2.0 * math.pi
            speed        = rng.uniform(0.4, 0.9)
            size         = rng.uniform(1.5, 3.0)
            trail_length = 18

        elif mode == UIMode.HUDSON:
            # Clustered inclinations simulating mechanical ring orbits
            ring_idx     = i % 4
            inclination  = ring_idx * (math.pi / 4.0)
            radius       = base_radius + ring_idx * 6.0
            phase        = (i / float(max(1, count))) * 2.0 * math.pi
            speed        = rng.choice([0.3, 0.6, 0.9, 1.2])
            size         = rng.uniform(1.0, 2.0)
            trail_length = 8

        else:
            # BOTH: chaotic — random inclination, mixed radius, variable speed
            inclination  = rng.uniform(0.0, math.pi)
            radius       = base_radius + rng.uniform(-15.0, 20.0)
            phase        = rng.uniform(0.0, 2.0 * math.pi)
            speed        = rng.uniform(0.2, 1.5)
            size         = rng.uniform(1.0, 4.0)
            trail_length = rng.randint(6, 24)

        particles.append(OrbParticle(
            radius=max(5.0, radius),
            inclination=inclination,
            phase=phase,
            speed=speed,
            size=size,
            trail_length=trail_length,
        ))

    return particles


# =============================================================================
# END OF math_engine.py
# =============================================================================