"""
Visualization script for BVR Sim performance benchmark results.
Generates publication-quality charts for thesis/paper.
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Set style for better-looking plots
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['font.size'] = 11
plt.rcParams['figure.figsize'] = (14, 10)

# Read the CSV file
csv_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("benchmark_results_20260324_035734.csv")
df = pd.read_csv(csv_file)

# Extract data for each backend
python_data = df[df['backend'] == 'Python'].sort_values('team_size')
cpp_data = df[df['backend'] == 'C++'].sort_values('team_size')

# Parse team sizes for x-axis labels
team_sizes = [int(x.split('v')[0]) for x in python_data['team_size']]
team_size_labels = python_data['team_size'].values

# Create a comprehensive figure with multiple subplots
fig = plt.figure(figsize=(16, 12))

# Subplot 1: FPS Comparison
ax1 = plt.subplot(2, 3, 1)
x = np.arange(len(team_sizes))
width = 0.35

bars1 = ax1.bar(x - width/2, python_data['fps'].values, width, label='Python', color='#1f77b4', alpha=0.8)
bars2 = ax1.bar(x + width/2, cpp_data['fps'].values, width, label='C++', color='#ff7f0e', alpha=0.8)

ax1.set_xlabel('Team Size (NvN)', fontsize=12, fontweight='bold')
ax1.set_ylabel('FPS (steps/second)', fontsize=12, fontweight='bold')
ax1.set_title('FPS Comparison: Python vs C++', fontsize=13, fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels(team_size_labels)
ax1.legend(fontsize=11)
ax1.grid(axis='y', alpha=0.3)

# Add value labels on bars
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}',
                ha='center', va='bottom', fontsize=9)

# Subplot 2: Performance Speedup (C++ vs Python)
ax2 = plt.subplot(2, 3, 2)
speedup = (cpp_data['fps'].values / python_data['fps'].values)
colors = ['#2ca02c' if x >= 5 else '#d62728' for x in speedup]
bars = ax2.bar(team_size_labels, speedup, color=colors, alpha=0.8, edgecolor='black', linewidth=1.5)

ax2.set_xlabel('Team Size (NvN)', fontsize=12, fontweight='bold')
ax2.set_ylabel('Speedup Factor (C++/Python)', fontsize=12, fontweight='bold')
ax2.set_title('Performance Speedup: C++ Backend', fontsize=13, fontweight='bold')
ax2.axhline(y=5.0, color='red', linestyle='--', linewidth=2, label='5x Target')
ax2.legend(fontsize=11)
ax2.grid(axis='y', alpha=0.3)

# Add value labels
for bar, val in zip(bars, speedup):
    ax2.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
            f'{val:.2f}x',
            ha='center', va='bottom', fontsize=10, fontweight='bold')

# Subplot 3: FPS/Agent Comparison (Normalized)
ax3 = plt.subplot(2, 3, 3)
bars1 = ax3.bar(x - width/2, python_data['fps_per_agent'].values, width, label='Python', color='#1f77b4', alpha=0.8)
bars2 = ax3.bar(x + width/2, cpp_data['fps_per_agent'].values, width, label='C++', color='#ff7f0e', alpha=0.8)

ax3.set_xlabel('Team Size (NvN)', fontsize=12, fontweight='bold')
ax3.set_ylabel('FPS/Agent (steps/second/agent)', fontsize=12, fontweight='bold')
ax3.set_title('Normalized Performance (FPS per Agent)', fontsize=13, fontweight='bold')
ax3.set_xticks(x)
ax3.set_xticklabels(team_size_labels)
ax3.legend(fontsize=11)
ax3.grid(axis='y', alpha=0.3)
ax3.set_yscale('log')

# Add value labels
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}',
                ha='center', va='bottom', fontsize=8)

# Subplot 4: Execution Time Comparison
ax4 = plt.subplot(2, 3, 4)
bars1 = ax4.bar(x - width/2, python_data['total_time_s'].values, width, label='Python', color='#1f77b4', alpha=0.8)
bars2 = ax4.bar(x + width/2, cpp_data['total_time_s'].values, width, label='C++', color='#ff7f0e', alpha=0.8)

ax4.set_xlabel('Team Size (NvN)', fontsize=12, fontweight='bold')
ax4.set_ylabel('Total Time (seconds)', fontsize=12, fontweight='bold')
ax4.set_title('Total Execution Time for 3 Episodes', fontsize=13, fontweight='bold')
ax4.set_xticks(x)
ax4.set_xticklabels(team_size_labels)
ax4.legend(fontsize=11)
ax4.grid(axis='y', alpha=0.3)

# Add value labels
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}s',
                ha='center', va='bottom', fontsize=8)

# Subplot 5: FPS Trend Lines
ax5 = plt.subplot(2, 3, 5)
ax5.plot(team_sizes, python_data['fps'].values, marker='o', linewidth=2.5, markersize=8,
         label='Python', color='#1f77b4')
ax5.plot(team_sizes, cpp_data['fps'].values, marker='s', linewidth=2.5, markersize=8,
         label='C++', color='#ff7f0e')

ax5.set_xlabel('Team Size (NvN)', fontsize=12, fontweight='bold')
ax5.set_ylabel('FPS (steps/second)', fontsize=12, fontweight='bold')
ax5.set_title('FPS Trend with Increasing Team Size', fontsize=13, fontweight='bold')
ax5.set_xticks(team_sizes)
ax5.legend(fontsize=11)
ax5.grid(True, alpha=0.3)

# Add annotations for key points
for i, size in enumerate(team_sizes):
    ax5.annotate(f'{python_data.iloc[i]["fps"]:.1f}',
                xy=(size, python_data.iloc[i]['fps']),
                xytext=(0, 10), textcoords='offset points',
                ha='center', fontsize=8, color='#1f77b4')
    ax5.annotate(f'{cpp_data.iloc[i]["fps"]:.1f}',
                xy=(size, cpp_data.iloc[i]['fps']),
                xytext=(0, -15), textcoords='offset points',
                ha='center', fontsize=8, color='#ff7f0e')

# Subplot 6: Summary Statistics Table
ax6 = plt.subplot(2, 3, 6)
ax6.axis('off')

# Create summary statistics
summary_data = []
for i in range(len(team_sizes)):
    size = team_size_labels[i]
    py_fps = python_data.iloc[i]['fps']
    cpp_fps = cpp_data.iloc[i]['fps']
    speedup = cpp_fps / py_fps

    summary_data.append([
        size,
        f"{py_fps:.2f}",
        f"{cpp_fps:.2f}",
        f"{speedup:.2f}x"
    ])

# Create table
table = ax6.table(cellText=summary_data,
                  colLabels=['Team', 'Python\nFPS', 'C++ FPS', 'Speedup'],
                  cellLoc='center',
                  loc='center',
                  bbox=[0, 0, 1, 1],
                  colWidths=[0.15, 0.25, 0.25, 0.25])

table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 2.5)

# Style the header
for i in range(4):
    table[(0, i)].set_facecolor('#4CAF50')
    table[(0, i)].set_text_props(weight='bold', color='white')

# Alternate row colors
for i in range(1, len(summary_data) + 1):
    for j in range(4):
        if i % 2 == 0:
            table[(i, j)].set_facecolor('#f0f0f0')
        else:
            table[(i, j)].set_facecolor('#ffffff')

ax6.set_title('Summary Statistics', fontsize=13, fontweight='bold', pad=20)

# Add overall title
fig.suptitle('BVR Sim Performance Benchmark Results\nPython (BVR3DEnv) vs C++ (BVR3DEnvCpp) Backend',
             fontsize=16, fontweight='bold', y=0.98)

plt.tight_layout(rect=[0, 0, 1, 0.96])

# Save figure
output_path = "benchmark_visualization.png"
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"[DONE] Visualization saved to: {output_path}")

# Create an additional detailed comparison chart
fig2, ax = plt.subplots(figsize=(14, 8))

x = np.arange(len(team_sizes))
width = 0.25

# Calculate speedup for this chart
speedup_arr = (cpp_data['fps'].values / python_data['fps'].values)

# Triple bar chart
bars1 = ax.bar(x - width, python_data['fps'].values, width, label='Python (FPS)',
               color='#1f77b4', alpha=0.85, edgecolor='black', linewidth=1)
bars2 = ax.bar(x, cpp_data['fps'].values, width, label='C++ (FPS)',
               color='#ff7f0e', alpha=0.85, edgecolor='black', linewidth=1)
bars3 = ax.bar(x + width, speedup_arr * 50, width, label='Speedup (×50 for visualization)',
               color='#2ca02c', alpha=0.85, edgecolor='black', linewidth=1)

ax.set_xlabel('Team Size (NvN)', fontsize=14, fontweight='bold')
ax.set_ylabel('FPS / Speedup Factor', fontsize=14, fontweight='bold')
ax.set_title('Comprehensive Performance Comparison: Python vs C++ Backend\n(3 episodes, 3000 total steps per configuration)',
             fontsize=15, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(team_size_labels, fontsize=12)
ax.legend(fontsize=12, loc='upper right')
ax.grid(axis='y', alpha=0.3)

# Add value labels
for bars in [bars1, bars2]:
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.0f}',
                ha='center', va='bottom', fontsize=9, fontweight='bold')

# Add speedup labels
for i, (bar, val) in enumerate(zip(bars3, speedup_arr)):
    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
            f'{val:.2f}x',
            ha='center', va='bottom', fontsize=9, fontweight='bold', color='darkgreen')

plt.tight_layout()
output_path2 = "benchmark_detailed_comparison.png"
plt.savefig(output_path2, dpi=300, bbox_inches='tight')
print(f"[DONE] Detailed comparison saved to: {output_path2}")

# Print summary statistics
print("\n" + "="*80)
print("PERFORMANCE BENCHMARK SUMMARY")
print("="*80)
print(f"\n{'Team Size':<12} {'Python FPS':<15} {'C++ FPS':<15} {'Speedup':<12} {'Time Saved':<15}")
print("-"*80)

for i in range(len(team_sizes)):
    py_fps = python_data.iloc[i]['fps']
    cpp_fps = cpp_data.iloc[i]['fps']
    py_time = python_data.iloc[i]['total_time_s']
    cpp_time = cpp_data.iloc[i]['total_time_s']
    speedup = cpp_fps / py_fps
    time_saved = py_time - cpp_time

    print(f"{team_size_labels[i]:<12} {py_fps:<15.2f} {cpp_fps:<15.2f} {speedup:<12.2f}x {time_saved:<15.1f}s")

print("-"*80)
avg_speedup = speedup_arr.mean()
print(f"\n[STAT] Average Speedup: {avg_speedup:.2f}x")
print(f"[STAT] Max Speedup: {speedup_arr.max():.2f}x ({team_size_labels[speedup_arr.argmax()]})")
print(f"[STAT] Min Speedup: {speedup_arr.min():.2f}x ({team_size_labels[speedup_arr.argmin()]})")
print("\n" + "="*80)
