import math,  time
from typing import Dict, Any, List, Optional

class RunningStats:
    """Online mean and standard deviation calculator."""

    __slots__ = ("count", "mean", "_m2")

    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self._m2 = 0.0

    def update(self, value: float):
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self._m2 += delta * delta2

    def std(self) -> float:
        if self.count <= 1:
            return 0.0
        return math.sqrt(self._m2 / (self.count - 1))


class StepProfiler:
    """Collects per-stage timings and running statistics when enabled."""

    def __init__(self, name: str, report_interval = 100):
        self.name = name
        self._marks = []
        self._stats: Dict[str, RunningStats] = {}

        self.report_interval = report_interval
        self._report_call_count = 0

    def start(self):
        self._marks = [("_step_start_", time.time())]

    def mark(self, name: str):
        self._marks.append((name, time.time()))
    
    def stop(self):
        if len(self._marks) <= 0:
            raise ValueError("wtf")
        self._marks.append(("_step_end_", time.time()))

        _, prev_time = self._marks[0]
        for name, current_time in self._marks[1:]:
            delta = current_time - prev_time
            stats = self._stats.setdefault(name, RunningStats())
            stats.update(delta)
            prev_time = current_time
        self._marks = []

    def report(self):
        self._report_call_count += 1
        if self._report_call_count % self.report_interval != 0:
            return []

        report = []
        for name, stats in self._stats.items():
            report.append((name, stats.mean, stats.std(), stats.count))

        # if report:
        #     print_buff = "{BVR3DEnv step time:\n"
        #     for stage, delta, mean_v, std_v, count in report:
        #         print_buff += (
        #             f"\t{stage}: {delta: .6f}s "
        #             f"(mean={mean_v: .6f}s, std={std_v: .6f}s, n={count})\n"
        #         )
        #     print_buff += "}"
        #     print(print_buff)   
        if report:
            # Column widths
            col_stage = max(len(r[0]) for r in report)
            w = {
                "mean": 10,
                "std": 10,
                "n": 6,
            }

            header = (
                f"{'stage'.ljust(col_stage)}"
                f" | {'mean'.rjust(w['mean'])}"
                f" | {'std'.rjust(w['std'])}"
                f" | {'n'.rjust(w['n'])}"
            )
            sep = "-" * len(header)

            lines = ["{ %s step time:" % self.name, header, sep]

            for stage, mean_v, std_v, count in report:
                lines.append(
                    f"{stage.ljust(col_stage)}"
                    f" | {mean_v:>{w['mean']}.6f}"
                    f" | {std_v:>{w['std']}.6f}"
                    f" | {count:>{w['n']}}"
                )

            lines.append("}")
            print("\n".join(lines))
        return report
