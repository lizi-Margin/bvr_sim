## BVR Sim: 针对现有BVR强化学习环境的改进
### TABLE I: Overview of Simulation environments

| 对比维度 | High Fidelity| Open Source| 比例引导法 | 角度/比例复合引导律 | 空空导弹气动阻力+重力仿真 | 模仿学习轨迹序列化支持 | 异构机型支持 |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **AirSim**              | √ | √ | × | × | × | × | √ |
| **Gazebo**              | √ | √ | × | × | × | × | × |
| **X-plane**             | √ | √ | × | × | × | × | √ |
| **WUKONG**              | √ | × | √ | √ | × | × | × |
| **JSBSim**              | √ | √ | × | × | × | × | × |
| **General Motion Model**| × | √ | √ | × | × | × | × |
| **BVRGym**              | √ | √ | √ | × | × | × | √ |
| **LAG (Light Air Game)**| √ | √ | × | × | × | × | × |
| **BVR Sim (Ours)**      | √ | √ | √ | √ | √ | √ | √ |


### 其他特点
* 端到端策略而不是规则分层 (相对BVRGym)
* reward设计 (Reward Shaping and Distill Reward)
* 专业的飞行控制律 (分层: 默认使用底层飞控, 强化学习专注于决策)
* 自博弈/规则baseline双支持

### Refercence
BVR Gym: A Reinforcement Learning Environment for Beyond-Visual-Range Air Combat
https://arxiv.org/abs/2403.17533
MISSION/bvr_sim_v3/paper_BVR-Gym.pdf
MISSION/bvr_sim_v3/paper_BVR-Gym.txt

B-ACE: An Open Lightweight Beyond Visual Range Air Combat Simulation Environment for Multi-Agent Reinforcement Learning
https://doi.org/10.13140/RG.2.2.11999.57762
MISSION/bvr_sim_v3/paper_B-ACE.pdf
MISSION/bvr_sim_v3/paper_B-ACE.txt


WUKONG: Beyond-Visual-Range Air Combat Tactics Auto-Generation by Reinforcement Learning
https://ieeexplore.ieee.org/document/9207088
MISSION/bvr_sim_v3/paper_WUKONG.pdf
MISSION/bvr_sim_v3/paper_WUKONG.txt

