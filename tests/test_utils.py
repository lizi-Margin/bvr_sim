"""
Utility functions for test scripts.
"""

import os
import sys
import numpy as np


def is_running_in_claude_code() -> bool:
    """检测是否在 Claude Code (或类似 agent 环境) 中运行"""
    # 检查环境变量
    if os.environ.get("CLAUDE_CODE", "").lower() == "true":
        return True
    # 检查是否在 vscode 终端中 (通常有 CODESESSION 等变量)
    if os.environ.get("CODESESSION"):
        return True
    # 检查 stdout 是否是非交互式 (通过 isatty)
    if hasattr(sys.stdout, 'isatty') and not sys.stdout.isatty():
        return True
    # 检查是否是通过 run_tests.py 调用
    if any('run_tests.py' in arg for arg in sys.argv):
        return True
    return False


class FpsMonitor:
    """FPS 监控器，支持 agent 模式和交互模式"""

    def __init__(self, is_agent: bool = False, alpha: float = 0.9):
        """
        Args:
            is_agent: 是否在 agent 环境中运行
            alpha: 移动平均的衰减因子
        """
        self.is_agent = is_agent
        self.alpha = alpha
        self.mean_step_time = 0.0
        self.all_step_times = []

    def step(self, step_time: float) -> None:
        """记录一步的时间"""
        self.all_step_times.append(step_time)
        if not self.is_agent:
            self.mean_step_time = self.alpha * self.mean_step_time + (1 - self.alpha) * step_time

    def print_progress(self) -> None:
        """打印当前进度（仅非 agent 模式）"""
        if not self.is_agent and self.mean_step_time > 0:
            fps = 1.0 / self.mean_step_time
            print(f"\rfps: {fps:.2f}, mean time: {self.mean_step_time:.6f}s", end="")

    def print_summary(self) -> None:
        """打印最终统计（agent 模式或结束时）"""
        if self.is_agent and self.all_step_times:
            final_fps = 1.0 / np.mean(self.all_step_times)
            final_mean_time = np.mean(self.all_step_times)
            print(f"\n[Agent Summary] FPS: {final_fps:.2f}, Mean Step Time: {final_mean_time:.6f}s")
