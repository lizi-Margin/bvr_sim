# 插件化系统 (Plugin System)

本章节介绍BVR Sim的插件化系统，允许用户自定义奖励函数和观测空间编码。

## 快速开始

```python
# 自定义奖励
from experimental.custom_reward_plugin import CustomFormationReward, get_custom_reward_manager
from bvr_sim.src_py.reward.reward_components import RewardManager

# 方法1: 直接使用自定义组件
manager = RewardManager()
manager.add_component(CustomFormationReward(weight=0.05))

# 方法2: 使用预配置的管理器
manager = get_custom_reward_manager()
```

```python
# 自定义观测空间
from experimental.custom_observation_plugin import CustomEnergyObservationSpace
from bvr_sim import BVR3DEnv

# 在环境中使用自定义观测空间
env = BVR3DEnv(
    config,
    logdir,
    observation_space=CustomEnergyObservationSpace()
)
```

## C++底层API

### 奖励插件API (`reward_components.hxx`)

```cpp
class RewardComponent {
public:
    virtual double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) = 0;

    virtual void reset() = 0;
};
```

**实现步骤:**

1. 继承 `RewardComponent` 类
2. 实现 `compute()` 方法计算奖励值
3. 实现 `reset()` 方法重置状态
4. 在 `reward_manager.cxx` 中注册组件

**C++奖励组件示例:**

```cpp
#include "reward_components.hxx"

class MyCustomReward : public bvr_sim::RewardComponent {
public:
    MyCustomReward(double weight = 1.0, const std::string& name = "my_reward")
        : RewardComponent(weight, name) {}

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const bvr_sim::RewardInfo& info) override {
        
        // 获取代理状态
        double altitude = agent->position[2];
        
        // 计算奖励
        return altitude > 5000.0 ? 1.0 : 0.0;
    }

    void reset() override {}
};
```

### 观测插件API (`observation_space.hxx`)

```cpp
class ObservationSpace {
public:
    virtual int get_obs_dim(int num_red, int num_blue) const = 0;
    virtual std::vector<double> extract_obs(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles
    ) const = 0;
};
```

**实现步骤:**

1. 继承 `ObservationSpace` 类
2. 实现 `get_obs_dim()` 返回观测维度
3. 实现 `extract_obs()` 提取和归一化观测
4. 在 `rl_manager.cxx` 中注册观测空间

## Python插件系统

### 奖励插件 (`bvr_sim/src_py/reward/reward_components.py`)

所有奖励组件继承自 `RewardComponent` 基类:

```python
class RewardComponent(ABC):
    def __init__(self, weight: float = 1.0, name: str = "base"):
        self.weight = weight
        self.name = name

    @abstractmethod
    def compute(self, env, agent_uid: str, info: Dict) -> float:
        pass
```

**可用的奖励组件:**

| 组件名 | 说明 |
|-------|------|
| `EngageEnemyReward` | 鼓励接近敌机 |
| `EnemyDistanceReward` | 基于敌机距离的奖励 |
| `AltitudeAdvantageReward` | 海拔优势奖励 |
| `SafeAltitudeReward` | 安全高度范围奖励 |
| `MissileLaunchReward` | 导弹发射奖励 |
| `MissileResultReward` | 导弹命中/miss奖励 |
| `MissileEvasionReward` | 导弹规避奖励 |
| `SpeedReward` | 速度保持奖励 |
| `SurvivalReward` | 生存奖励 |
| `WinLossReward` | 赢/输奖励 |

### 观测插件 (`bvr_sim/src_py/observation_space.py`)

所有观测空间继承自 `ObservationSpace` 基类:

```python
class ObservationSpace(ABC):
    @abstractmethod
    def get_obs_dim(self, num_red: int, num_blue: int) -> int:
        pass

    @abstractmethod
    def extract_obs(self, agent, all_agents, all_missiles) -> np.ndarray:
        pass
```

**可用的观测空间:**

| 空间名 | 维度 | 说明 |
|-------|------|------|
| `CompactObsSpace` | ~60-100 | 紧凑观测，包含基础状态 |
| `ExtendedObsSpace` | ~100-150 | 扩展观测，包含更多细节 |

## 自定义奖励示例

### 1. 边界距离奖励

```python
from experimental.custom_reward_plugin import CustomDistanceToBoundaryReward

# 惩罚靠近仿真边界
reward = CustomDistanceToBoundaryReward(
    weight=0.01,
    boundary_radius=40000.0,  # 40km边界
    safe_distance=5000.0       # 5km安全区
)
```

### 2. 编队保持奖励

```python
from experimental.custom_reward_plugin import CustomFormationReward

# 鼓励保持编队间距
reward = CustomFormationReward(
    weight=0.05,
    formation_distance=2000.0,  # 目标间距2km
    tolerance=500.0              # 允许500m偏差
)
```

### 3. 敌机聚焦奖励

```python
from experimental.custom_reward_plugin import CustomEnemyFocusReward

# 鼓励多架飞机协同攻击同一目标
reward = CustomEnemyFocusReward(
    weight=0.02,
    focus_threshold=2  # 2架飞机攻击同一目标得满奖
)
```

## 自定义观测示例

### 1. 能量状态观测

```python
from experimental.custom_observation_plugin import CustomEnergyObservationSpace

# 包含能量特征的观测
obs_space = CustomEnergyObservationSpace()
# 观测包含: 位置、速度、高度、能量状态、能量优势
```

### 2. 导弹告警观测

```python
from experimental.custom_observation_plugin import CustomMissileWarningObservationSpace

# 增强的导弹告警系统
obs_space = CustomMissileWarningObservationSpace()
# 包含: 近/中/远距离导弹数量、距离、威胁级别
```

### 3. 威胁等级观测

```python
from experimental.custom_observation_plugin import CustomThreatLevelObservationSpace

# 综合威胁评估
obs_space = CustomThreatLevelObservationSpace(max_enemies=5)
# 包含: 每个敌机的威胁得分、锁定状态、导弹发射指示
```

## 注册到ScenarioConfig

```python
# rl_envs/env_wrapper.py
class ScenarioConfig:
    # ...
    
    # 使用自定义奖励管理器
    def get_reward_manager(self):
        from bvr_sim.src_py.reward.reward_components import RewardManager
        from experimental.custom_reward_plugin import CustomFormationReward
        
        manager = RewardManager()
        manager.add_component(CustomFormationReward(weight=0.05))
        # ... 添加其他组件
        return manager
```

## API参考

### C++ SimulatedObject状态访问

所有仿真对象通过 `Register` 系统导出状态:

```cpp
// 基本属性
agent->uid           // 唯一ID
agent->color         // 阵营 (Red/Blue)
agent->is_alive      // 是否存活
agent->position      // 位置 [x, y, z]
agent->velocity      // 速度 [vx, vy, vz]

// 飞机特有属性
agent->aircraft_model
agent->get_speed()
agent->get_altitude()
agent->get_heading()
agent->get_roll()
agent->get_pitch()

// 武器系统
agent->launched_missiles
agent->enemies_lock
```

### Python env状态访问

```python
# 代理
env.agents[agent_uid]      # 获取代理对象
env.agents[agent_uid].position
env.agents[agent_uid].velocity
env.agents[agent_uid].is_alive

# 敌机和盟友
agent.enemies              # 敌机列表
agent.partners             # 盟友列表

# 导弹
env.missiles[missile_uid]  # 获取导弹对象
agent.launched_missiles    # 发射的导弹
agent.under_missiles       # 面临的导弹
```

## 性能考虑

1. **避免复杂计算**: 奖励函数在每步调用，应保持高效
2. **使用向量化**: 在Python中使用NumPy向量化操作
3. **缓存计算**: 对于需要历史状态的奖励，使用类成员缓存
4. **C++实现**: 对于性能关键的奖励，考虑在C++中实现

## 调试技巧

```python
# 打印奖励分解
info = env.step(action)
breakdown = env.reward_manager.get_reward_breakdown(agent_uid, info)
print(breakdown)  # 查看各组件贡献

# 检查观测维度
obs_dim = env.observation_space.get_obs_dim(num_red, num_blue)
print(f"Observation dimension: {obs_dim}")
```

## 参考实现

- `experimental/custom_reward_plugin.py` - Python自定义奖励示例
- `experimental/custom_observation_plugin.py` - Python自定义观测示例
- `bvr_sim/src_cxx/rl/reward_components.cxx` - C++奖励组件
- `bvr_sim/src_cxx/rl/observation_space.hxx` - C++观测空间
