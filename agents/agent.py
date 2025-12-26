import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from observation_space import create_observation_space
from .bvr_strategist import StrategicLLM
from .skill_manager import SkillManager

class AgentConfig:
    model = "qwen3-8b"
    planning_interval = 15.0


class Agent:
    """BVR LLM Red Agent"""

    def __init__(self):
        self.planning_interval = AgentConfig.planning_interval

        self.skill_manager = SkillManager()
        self.strategist = StrategicLLM()

        self.step_count = 0
        self.llm_calls = 0
        self.current_skill = None

    def step(self, obs: str, info=None):
        """Agent step"""
        self.step_count += 1
        assert isinstance(obs, str)

        # Select skill
        import asyncio
        skill_selection = asyncio.run(self.strategist.select_skill(obs))
        if skill_selection:
            self.llm_calls += 1
            skill = self.skill_manager.create_skill(skill_selection.skill_name, skill_selection.skill_params)
            action, completed = skill.execute(obs)
            self.current_skill = skill_selection.skill_name
        else:
            raise ValueError("No skill selected")
            

        # Convert to environment action format
        return action

    def reset(self, episode_config=None):
        """Reset agent"""
        self.step_count = 0
        self.current_skill = None
