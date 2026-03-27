import subprocess
import os
import json
import time

def run_command(cmd):
    print(f"Executing: {cmd}")
    # Set STAGING=1 to ensure backtests hit the experimental file
    env = os.environ.copy()
    env["STAGING"] = "1"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    if result.stdout: print(result.stdout)
    if result.stderr: print(result.stderr)
    return result.returncode == 0

def master_training_loop():
    print("--- EXPERT V6: MASTER TRAINING LOOP STARTING ---")
    
    # PHASE 1: Initial Backtest
    print("\n--- PHASE 1: INITIAL BACKTEST ---")
    if not run_command("py realistic_backtest_v8.py"):
        print("Error: Backtest failed.")
        return

    # PHASE 2: AI Analysis
    print("\n--- PHASE 2: AI OPTIMIZATION ---")
    if not run_command("py ai_optimizer.py --backtest"):
        print("Error: AI Optimization failed.")
        return

    # PHASE 3: Second Backtest
    print("\n--- PHASE 3: EVOLVED BACKTEST ---")
    if not run_command("py realistic_backtest_v8.py"):
        print("Error: Second backtest failed.")
        return

    print("\n--- TRAINING LOOP COMPLETED! ---")
    print("Sistem artık geçmiş hatalarından ders çıkardı ve optimized_weights.json güncellendi.")

if __name__ == "__main__":
    master_training_loop()
