"""
Spawn Manager for BVR 3D Environment

Handles randomized spawn position generation for teams.
"""

import numpy as np
from uhtk.c3utils.i3utils import nm_to_meters


class SpawnManager:
    """
    Manages spawn positions for BVR air combat scenarios.

    Simple circular spawn strategy:
    - Center at origin (0, 0, 0)
    - Random engagement axis
    - Teams at opposite ends of diameter
    - Simple circular distribution within formation radius
    """

    def __init__(self, config: dict):
        """
        Initialize spawn manager.

        Args:
            config: Environment configuration dict
        """
        # Initial separation between teams (in nautical miles)
        self.initial_separation_nm = config.get('initial_separation_nm', 37.2)
        self.initial_separation_m = nm_to_meters(self.initial_separation_nm)

        # Formation spread radius (in nautical miles)
        self.formation_radius_nm = config.get('formation_max_spread_nm', 2.0) / 2.0
        self.formation_radius_m = nm_to_meters(self.formation_radius_nm)

        # Altitude range
        self.min_altitude = config.get('min_altitude', 4000.0)
        self.max_altitude = config.get('max_altitude', 8000.0)

    def generate_spawn(self, num_red: int, num_blue: int, initial_separation_nm_override: float = None):
        # Random engagement axis (0 to 2π)
        engagement_axis = np.random.uniform(0, 2 * np.pi)

        # Calculate team center positions (opposite ends of diameter)
        if initial_separation_nm_override is None:
            half_sep = self.initial_separation_m / 2.0
        else:
            half_sep = nm_to_meters(initial_separation_nm_override) / 2.0

        red_center = np.array([
            -half_sep * np.cos(engagement_axis),
            -half_sep * np.sin(engagement_axis),
            0.0
        ])

        blue_center = np.array([
            half_sep * np.cos(engagement_axis),
            half_sep * np.sin(engagement_axis),
            0.0
        ])

        # Generate positions for each team
        red_positions = self._generate_circular_formation(red_center, num_red)
        blue_positions = self._generate_circular_formation(blue_center, num_blue)

        return red_positions, blue_positions, engagement_axis

    def _generate_circular_formation(self, center: np.ndarray, num_agents: int):
        """
        Generate agent positions in a circular formation around center.

        Args:
            center: [x, y, z] center position (z is ignored, altitude randomized)
            num_agents: Number of agents to spawn

        Returns:
            List of [x, y, z] position arrays
        """
        positions = []

        # Random base altitude for this formation
        base_altitude = np.random.uniform(self.min_altitude, self.max_altitude)

        if num_agents == 1:
            # Single agent at center
            pos = np.array([center[0], center[1], base_altitude], dtype=float)
            positions.append(pos)
        else:
            # Multiple agents in circular pattern
            for i in range(num_agents):
                # Random angle and radius within formation circle
                angle = np.random.uniform(0, 2 * np.pi)
                radius = np.random.uniform(0, self.formation_radius_m)

                # Calculate position
                x = center[0] + radius * np.cos(angle)
                y = center[1] + radius * np.sin(angle)
                z = base_altitude + np.random.uniform(-300, 300)  # Small altitude variation

                positions.append(np.array([x, y, z], dtype=float))

        return positions
