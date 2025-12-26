import json
import numpy as np
import os
from .bvr_env import BVR3DEnv
from .agents.agent import Agent as RedAgent

# Load environment config
with open("demo_config.json", "r") as fin:
    env_config = json.load(fin)

sim = BVR3DEnv(env_config)
obs = sim.reset(seed=None)
red_agents = [RedAgent()]

while not sim.done:
    actions = []
    for agent in red_agents:
        action_dict = agent.step(obs)
        actions.append(action_dict)
    sim.step(actions)
input("单局推演结束，按Enter退出。")
    

    
