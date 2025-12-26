"""
Reward Visualization System for BVR 3D Environment

This module provides functionality to visualize individual reward components
over episodes, with each reward component as a separate curve.
"""
import os, json
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Any
from config import GlobalConfig as cfg


class RewardVisualizer:
    """
    Handles visualization of reward components during episodes
    """
    
    def __init__(self, env_id: int, reward_plot_path: str):
        self.env_id = env_id
        self.reward_tracking_enabled = True 
        self.reward_plot_path = reward_plot_path
        
        # Create directory for reward plots
        os.makedirs(self.reward_plot_path, exist_ok=True)
        
        # Initialize tracking structures
        self.episode_data = {}
        self.reset_tracking()
    
    def reset_tracking(self):
        """Reset tracking for a new episode"""
        self.episode_data = {
            'steps': [],
            'total_rewards': [],  # Will store average total reward across agents
            'component_rewards': {},  # component_name -> [rewards for each step]
            'agent_data': {}  # agent_uid -> {steps, total_rewards, component_rewards}
        }
    
    def track_step_rewards(self, info: Dict[str, Any], reward_components_breakdown: Dict[str, float], agent_uid: str = "A00"):
        """
        Track reward components for a single step
        
        Args:
            info: Environment info dict containing current_step
            reward_components_breakdown: Dict mapping component name to reward value
            agent_uid: The agent ID for this reward breakdown
        """
            
        current_step = info.get("current_step", 0)
        
        # Initialize agent-specific tracking if needed
        if agent_uid not in self.episode_data['agent_data']:
            self.episode_data['agent_data'][agent_uid] = {
                'steps': [],
                'total_rewards': [],
                'component_rewards': {}
            }
        
        # Add step for this agent
        agent_data = self.episode_data['agent_data'][agent_uid]
        agent_data['steps'].append(current_step)
        
        # Calculate and store total reward for this agent
        total_reward = sum([x for name, x in reward_components_breakdown.items() if name != "TOTAL"])
        agent_data['total_rewards'].append(total_reward)
        
        # Store individual component rewards for this agent
        for component_name, reward_value in reward_components_breakdown.items():
            if component_name not in agent_data['component_rewards']:
                agent_data['component_rewards'][component_name] = []
            agent_data['component_rewards'][component_name].append(reward_value)
        
        # Also track aggregated across all agents (for the overall plot)
        if current_step not in self.episode_data['steps']:
            self.episode_data['steps'].append(current_step)
            # Initialize aggregated values
            self.episode_data['total_rewards'].append(total_reward)
            for component_name, reward_value in reward_components_breakdown.items():
                if component_name not in self.episode_data['component_rewards']:
                    self.episode_data['component_rewards'][component_name] = []
                # Pad with zeros for previous steps where this agent didn't have data
                while len(self.episode_data['component_rewards'][component_name]) < len(self.episode_data['steps']) - 1:
                    self.episode_data['component_rewards'][component_name].append(0.0)
                self.episode_data['component_rewards'][component_name].append(reward_value)
        else:
            # Update aggregated values - add to existing values
            step_idx = self.episode_data['steps'].index(current_step)
            self.episode_data['total_rewards'][step_idx] += total_reward
            for component_name, reward_value in reward_components_breakdown.items():
                # Pad if needed (for agents that start reporting later)
                while len(self.episode_data['component_rewards'][component_name]) <= step_idx:
                    self.episode_data['component_rewards'][component_name].append(0.0)
                self.episode_data['component_rewards'][component_name][step_idx] += reward_value
    
    def plot_episode_rewards(self, episode_num: int, agent_uid: str = "A00"):
        """
        Plot reward components for the current episode
        
        Args:
            episode_num: Episode number for filename
            agent_uid: Agent identifier for the plot
        """ 
            
        if not self.episode_data['steps']:
            return  # No data to plot
        
        if not os.path.exists(self.reward_plot_path):
            os.makedirs(self.reward_plot_path)
        
        # # Create the plot
        # plt.figure(figsize=(14, 8))
        
        # # Plot total reward (aggregated across all agents)
        # plt.plot(self.episode_data['steps'], self.episode_data['total_rewards'], 
        #         label='Total Reward (All Agents)', linewidth=2, color='black', linestyle='--')
        
        # # Plot each reward component (aggregated across all agents)
        # colors = plt.cm.tab20(np.linspace(0, 1, len(self.episode_data['component_rewards'])))
        # for idx, (component_name, rewards) in enumerate(self.episode_data['component_rewards'].items()):
        #     plt.plot(self.episode_data['steps'], rewards, 
        #             label=component_name, 
        #             color=colors[idx % len(colors)],
        #             alpha=0.7)
        
        # plt.xlabel('Step')
        # plt.ylabel('Reward')
        # plt.title(f'Reward Components Over Episode {episode_num} - Environment {self.env_id}')
        # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        # plt.grid(True, alpha=0.3)
        # plt.tight_layout()
        
        # # Save the plot
        # plot_filename = os.path.join(self.reward_plot_path, 
        #                            f"reward_breakdown_episode_{episode_num}_env_{self.env_id}.png")
        # plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
        # plt.close()
        
        # print(f"Saved reward plot: {plot_filename}")
        
        # Additionally, plot individual agent data if needed
        for agent_id in self.episode_data['agent_data']:
            self._plot_agent_rewards(episode_num, agent_id)
    
    def _plot_agent_rewards(self, episode_num: int, agent_uid: str):
        """
        Plot reward components for a specific agent
        
        Args:
            episode_num: Episode number for filename
            agent_uid: Agent identifier for the plot
        """
        if agent_uid not in self.episode_data['agent_data']:
            return
            
        agent_data = self.episode_data['agent_data'][agent_uid]
        if not agent_data['steps']:
            return  # No data to plot
        
        # Create the plot for this agent
        plt.figure(figsize=(14, 8))
        
        # Plot total reward for this agent
        plt.plot(agent_data['steps'], agent_data['total_rewards'], 
                label=f'Total Reward ({agent_uid})', linewidth=2, color='black', linestyle='--')
        
        # Plot each reward component for this agent
        colors = plt.cm.tab20(np.linspace(0, 1, len(agent_data['component_rewards'])))
        for idx, (component_name, rewards) in enumerate(agent_data['component_rewards'].items()):
            plt.plot(agent_data['steps'], rewards, 
                    label=f'{component_name} ({agent_uid})', 
                    color=colors[idx % len(colors)],
                    alpha=0.7)
        
        plt.xlabel('Step')
        plt.ylabel('Reward')
        plt.title(f'Reward Components Over Episode {episode_num} - Agent {agent_uid}')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, alpha=0.3)
        plt.yscale('symlog', linthresh=1e-2)  # linear near 0, log elsewhere
        plt.tight_layout()
        
        # Save the plot
        plot_filename = os.path.join(self.reward_plot_path, 
                                   f"reward_breakdown_episode_{episode_num}_agent_{agent_uid}_env_{self.env_id}.png")
        plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
        plt.close()

        with open(plot_filename.replace(".png", ".json"), "w") as f:
            json.dump(agent_data, f, indent=2)
        
        # print(f"Saved agent reward plot: {plot_filename}")