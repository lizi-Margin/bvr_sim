import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
from .api.api_router import get_api_class

from .skill_manager import SkillManager

HUMAN_PROMPT = "MISSION: Air Superiority. Engage enemies beyond 20nm. Maintain altitude advantage."

EMERGENCY_RULES = {
    "missile_warning": {"skill": "missile_evasion"},
    "low_fuel": {"skill": "disengage"}
}


class StrategicLLM:
    """LLM-powered strategic planning"""

    def __init__(self):
        from .agent import AgentConfig
        self.model = AgentConfig.model
        self.planning_interval = AgentConfig.planning_interval
        self.last_plan_time = 0
        self.api = get_api_class(self.model)()
        self.skill_manager = SkillManager()

    def should_replan(self, obs):
        """Check if planning is needed"""
        current_time = obs.get("time", 0)
        return current_time - self.last_plan_time >= self.planning_interval

    async def select_skill(self, obs):
        """Select skill with parameters"""
        if not self.should_replan(obs):
            return self.last_selection

        # Check emergency conditions
        emergency_skill = self._check_emergencies(obs)
        if emergency_skill:
            self.last_selection = emergency_skill
            return emergency_skill

        # LLM planning
        prompt = self._create_planning_prompt(obs, HUMAN_PROMPT)

        try:
            response = await self.api.chat_completion(prompt)
            skill_name, skill_params = self._parse_llm_response(response)
            self.last_selection = SkillSelection(skill_name, skill_params)
        except:
            # Fallback to default
            self.last_selection = SkillSelection("crank_maneuver", {"direction": "left", "offset_angle": 30})

        self.last_plan_time = obs.get("time", 0)
        return self.last_selection

    def _check_emergencies(self, obs):
        """Check emergency conditions"""
        threats = obs.get("threat_assessment", "").lower()
        fuel = obs.get("self_status", {}).get("resources", {}).get("fuel", "100%")

        if "missile" in threats:
            return SkillSelection("missile_evasion", {"break_direction": "right"})

        if "%" in fuel and float(fuel.replace("%", "")) < 15:
            return SkillSelection("disengage", {"priority": "high"})

        return None

    def _create_planning_prompt(self, obs, mission):
        """Create planning prompt for LLM"""
        return f"""
{mission}

Current situation:
{obs.get('situation_summary', '')}
{obs.get('self_status', '')}
{obs.get('threat_assessment', '')}

Available skills: {list(self.skill_manager.skills.keys())}
Select a skill and parameters in JSON format: {{"skill": "name", "params": {{"param": "value"}}}}
"""

    def _parse_llm_response(self, response):
        """Parse LLM response"""
        try:
            import json
            data = json.loads(response)
            return data.get("skill", "crank_maneuver"), data.get("params", {})
        except:
            return "crank_maneuver", {"direction": "left", "offset_angle": 30}


class SkillSelection:
    """Skill selection with parameters"""
    def __init__(self, skill_name, skill_params, reasoning="", confidence=0.8):
        self.skill_name = skill_name
        self.skill_params = skill_params
        self.reasoning = reasoning
        self.confidence = confidence