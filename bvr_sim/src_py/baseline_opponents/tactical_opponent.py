import numpy as np
from abc import ABC, abstractmethod
from typing import List, Optional
from ..simulator import Aircraft, Missile
from .simple_opponents import BaseOpponent3D
from uhtk.c3utils.i3utils import nm_to_meters, meters_to_nm, get_mps, feet_to_meters

class TacticalOpponent3D(BaseOpponent3D):
    """
    Tactical 3D opponent with situation awareness

    Refactored from lag's juece.py MyStrategy class.
    Implements a state machine: Evade → Guide → Attack → Search
    """

    def __init__(self):
        super().__init__("Tactical3D")
        self.last_shoot_time = -30
        self.crank_direction = 1  # For crank maneuvers
        self.crank_switch_time = 0
    
    def _get_active_missile(self, missiles_targeting_me: List[Missile]) -> List[Missile]:
        """Get the active missile if any"""
        active_missile = []
        for idx in range(len(missiles_targeting_me)):
            if hasattr(missiles_targeting_me[idx], 'radar_on') and missiles_targeting_me[idx].radar_on:
                active_missile.append(missiles_targeting_me[idx])
            if not hasattr(missiles_targeting_me[idx], 'radar_on'):
                # print(f"Missile {idx} has no radar_on attribute")
                active_missile.append(missiles_targeting_me[idx])
        return active_missile

    def get_action(
        self,
        agent: Aircraft,
        enemies: List[Aircraft],
        partners: List[Aircraft],
        missiles_targeting_me: List[Missile]
    ) -> dict:
        """Tactical decision-making with priority-based state machine"""
        self.time_counter += agent.dt

        if not agent.is_alive:
            return self._get_default_action(agent)

        alive_enemies = [e for e in agent.enemies_lock if e.is_alive]
        if len(alive_enemies) == 0:
            alive_enemies = [e for e in enemies if e.is_alive]
        if len(alive_enemies) == 0:
            return self._get_default_action(agent)
        target = min(
            alive_enemies,
            key=lambda e:
                np.linalg.norm(e.position - agent.position) +  len(e.under_missiles) * 10_000
        )


        missiles_in_flight = [m for m in agent.launched_missiles if (m.is_alive and m.target.uid == target.uid)]
        active_missiles = self._get_active_missile(missiles_targeting_me)

        # Priority 1: Evade incoming missiles (highest priority)
        if len(active_missiles) > 0:
            return self._evade_missiles(agent, active_missiles)

        # Priority 2: Guide missiles in flight
        if len(missiles_in_flight) > 0 and len(alive_enemies) > 0:
            return self._guide_missiles(agent, missiles_in_flight, alive_enemies)

        # Priority 3: Attack when no missiles in flight
        if len(alive_enemies) > 0 and agent.num_left_missiles > 0:
            return self._tactical_attack(agent, target, alive_enemies)

        # Priority 4: No enemies - maintain course
        return self._get_default_action(agent)

    def _evade_missiles(
        self,
        agent: Aircraft,
        missiles: List[Missile]
    ) -> dict:
        """Evade incoming missiles - turn away and dive/climb"""
        # Find closest missile
        closest_missile = min(missiles,
                             key=lambda m: np.linalg.norm(m.position - agent.position))

        rel_pos = closest_missile.position - agent.position
        distance = np.linalg.norm(rel_pos)

        # Calculate missile bearing
        missile_heading = np.arctan2(rel_pos[1], rel_pos[0])

        # Turn away (opposite direction)
        desired_heading = missile_heading + np.pi
        delta_heading = self._get_heading_action(agent, desired_heading)

        # Dive if high, maintain if low (to reduce radar lock and increase distance)
        if distance < 15000.0:  # Close range: aggressive maneuver
            if agent.get_altitude() > 4000.0:
                delta_altitude = -125  # Dive
            else:
                delta_altitude = 20  # Climb
            target_speed = get_mps(1.2, agent.get_altitude())
        else:  # Far range: crank maneuver
            if agent.get_altitude() > 4000.0:
                delta_altitude = -30  # Gentle dive
            else:
                delta_altitude = 0
            target_speed = get_mps(1.0, agent.get_altitude())

        speed_diff = target_speed - agent.get_speed()
        delta_speed = speed_diff

        ##############
        delta_altitude = 0
        ##############
        return self._build_action_from_rates(
            agent,
            delta_heading=delta_heading,
            delta_altitude=delta_altitude,
            delta_speed=delta_speed,
            shoot=False
        )

    def _guide_missiles(
        self,
        agent: Aircraft,
        missiles_in_flight: List[Missile],
        enemies: List[Aircraft]
    ) -> dict:
        """Guide missiles with crank maneuver to maintain datalink"""
        # Get target of first missile
        target = missiles_in_flight[0].target 
        if target not in enemies or not target.is_alive:
            return self._get_default_action(agent)

        rel_pos = target.position - agent.position
        distance = np.linalg.norm(rel_pos)
        target_heading = np.arctan2(rel_pos[1], rel_pos[0])

        # Crank maneuver: offset heading by ±30 degrees
        crank_offset = np.deg2rad(30) * self.crank_direction
        desired_heading = target_heading + crank_offset

        # Switch crank direction periodically
        if self.time_counter - self.crank_switch_time > 20:  # Every 20 seconds
            self.crank_direction *= -1
            self.crank_switch_time = self.time_counter

        delta_heading = self._get_heading_action(agent, desired_heading)

        target_altitude = max(agent.get_altitude() - 30, feet_to_meters(7000.0))
        # target_altitude = agent.get_altitude() - 100
        altitude_diff = target_altitude - agent.get_altitude()
        delta_altitude = altitude_diff


        # Moderate speed for guidance
        target_speed = 250.0
        speed_diff = target_speed - agent.get_speed()
        delta_speed = speed_diff * 0.5

        # Can shoot additional missiles if conditions are good
        shoot = False
        time_since_last_shoot = self.time_counter - self.last_shoot_time
        if (agent.num_left_missiles > 0 and
            time_since_last_shoot > 50 and
            target in agent.enemies_lock):
            # Check if first missile is far from target
            missile_to_target = np.linalg.norm(missiles_in_flight[0].position - target.position)
            if missile_to_target > 20000.0 and distance < 45000.0:
                shoot = True
                self.last_shoot_time = self.time_counter

        shoot_jsow = 1.0
        if agent.num_left_missiles < agent.num_missiles/2:
            shoot_jsow = 0.0
        return self._build_action_from_rates(
            agent,
            delta_heading=delta_heading,
            delta_altitude=delta_altitude,
            delta_speed=delta_speed,
            shoot=shoot,
            other_commands={
                "shoot_jsow": float(shoot_jsow),
            }
        )

    def _tactical_attack(
        self,
        agent: Aircraft,
        target: Aircraft,
        enemies: List[Aircraft]
    ) -> dict:
        """Tactical attack: position for optimal shot"""
        rel_pos = target.position - agent.position
        distance = np.linalg.norm(rel_pos)

        # Head towards enemy
        desired_heading = self._calculate_heading_to_target(agent, target.position)
        delta_heading = self._get_heading_action(agent, desired_heading)

        # # Altitude strategy: climb for range advantage
        # if distance > nm_to_meters(20):  # Far: climb to increase missile range
        #     # target_altitude = min(agent.get_altitude() + 500.0, 8000.0)
        #     target_altitude = max(agent.get_altitude() + 200.0, 8000.0)
        # else:  # Close: maintain altitude advantage
        #     target_altitude = max(nearest_enemy.get_altitude() + 500.0, 5000.0)
        target_altitude = agent.get_altitude() + 150

        altitude_diff = target_altitude - agent.get_altitude()
        delta_altitude = altitude_diff


        # Speed: accelerate if far, moderate if close
        if distance > 45000.0:
            target_speed = 350.0
        else:
            target_speed = 280.0

        speed_diff = target_speed - agent.get_speed()
        delta_speed = speed_diff * 0.6

        # Shoot tactically
        shoot = False
        time_since_last_shoot = self.time_counter - self.last_shoot_time
        if (target in agent.enemies_lock and
            agent.num_left_missiles > 0 and
            time_since_last_shoot > 10):
            if distance < nm_to_meters(8.0):
                shoot = True
                self.last_shoot_time = self.time_counter
            elif distance < nm_to_meters(38.0):
                # if agent.get_pitch() > np.deg2rad(5.0):
                    shoot = True
                    self.last_shoot_time = self.time_counter

        return self._build_action_from_rates(
            agent,
            delta_heading=delta_heading,
            delta_altitude=delta_altitude,
            delta_speed=delta_speed,
            shoot=shoot
        )

    def _get_default_action(self, agent: Aircraft) -> dict:
        """Default action (no control input)"""
        return self._build_action_from_rates(agent, 0.0, 0.0, 0.0, False)


    # def _build_action_from_rates(
    #     self,
    #     agent: Aircraft,
    #     delta_heading: float,
    #     delta_altitude: float,
    #     delta_speed: float,
    #     shoot: bool,
    #     other_commands: dict = {}
    # ) -> dict:
    #     return {
    #         'delta_heading': float(delta_heading),
    #         'delta_altitude': float(delta_altitude),
    #         'delta_speed': float(delta_speed),
    #         'shoot': 1.0 if shoot else 0.0,
    #         'other_commands': {
    #             "shoot_jsow": 1.0,
    #         }
    #     }
