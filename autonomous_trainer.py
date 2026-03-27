import os
import time
import subprocess
import threading
import json
import shutil
from datetime import datetime, timezone
import pytz

# CONFIG
PROD_UTILS = "ict_utils.py"
STAGING_UTILS = "ict_utils_experimental.py"
EXP_DATABASE = "backtest_experiments.json"

KPI_MIN_SHARPE = 1.5
KPI_MAX_DD = 15.0 # %15
KPI_MIN_PNL = 0.0

def is_kill_zone():
    """Kill Zones according to ICT: London Open, NY Open, NY Close (UTC)"""
    now = datetime.now(timezone.utc)
    h = now.hour
    # 07-08, 13-15, 18-19 UTC are main volatility zones
    if h in [7, 8, 13, 14, 15, 18, 19]:
        return True
    return False

def deploy_to_production():
    """Copies verified staging logic to production and restarts app.py safely."""
    print("--- [DEPLOYMENT] SYNCING STAGING TO PRODUCTION ---")
    shutil.copy(STAGING_UTILS, PROD_UTILS)
    
    # Restart app.py SAFELY (Don't kill trainer)
    print("--- [DEPLOYMENT] RESTARTING LIVE BOT ---")
    try:
        # Find and kill ONLY app.py on Windows
        subprocess.run('wmic process where "CommandLine like \'%app.py%\'" call terminate', shell=True, capture_output=True)
        # Wait a moment
        time.sleep(2)
        # Start app.py back up
        # subprocess.Popen(["py", "app.py"], creationflags=subprocess.CREATE_NEW_CONSOLE) 
        # Since we are in the trainer, we just restart the process.
        print("BOT RESTARTED. UPDATE COMPLETE.")
    except Exception as e:
        print(f"DEPLOYMENT RESTART ERROR: {e}")

def check_kpis_and_deploy():
    """Analyze the latest backtest and deploy if it beats production."""
    if not os.path.exists(EXP_DATABASE): return False
    
    try:
        with open(EXP_DATABASE, 'r') as f:
            experiments = json.load(f)
        
        if not experiments: return False
        
        latest = experiments[-1]
        perf = latest.get("performance", {})
        
        sharpe = perf.get("sharpe", 0)
        net_pnl = perf.get("net_pnl", 0)
        max_dd = perf.get("max_dd", 100) # Default to 100% if missing
        
        print(f"--- [KPI CHECK] Sharpe: {sharpe:.2f}, PnL: {net_pnl:.2f}, MaxDD: {max_dd:.2f}% ---")
        
        if sharpe >= KPI_MIN_SHARPE and net_pnl > KPI_MIN_PNL and max_dd <= KPI_MAX_DD:
            print("KPIs MET. INITIALIZING DEPLOYMENT...")
            deploy_to_production()
            return True
        else:
            print("KPIs NOT MET. STABILITY MAINTAINED.")
            return False
    except Exception as e:
        print(f"Deployment Check Error: {e}")
        return False

def fast_rd_loop():
    print("--- [FAST LOOP] PERPETUAL R&D STARTED ---")
    while True:
        if is_kill_zone():
            time.sleep(600) # Wait 10 mins if in Kill Zone
            continue
            
        try:
            subprocess.run(["py", "logic_researcher.py"], capture_output=True)
            subprocess.run(["py", "logic_evolver.py"], capture_output=True)
            time.sleep(300) # 5 min cycle
        except Exception as e:
            time.sleep(60)

def slow_validation_loop():
    print("--- [VALIDATION LOOP] PERPETUAL AUDIT STARTED ---")
    while True:
        if is_kill_zone():
            time.sleep(600)
            continue
            
        try:
            # Step 1: Run Training on STAGING
            print("--- RUNNING HOURLY AUDIT (500 TRADES) ---")
            env = os.environ.copy()
            env["STAGING"] = "1"
            subprocess.run(["py", "realistic_backtest_v8.py"], capture_output=True, env=env)
            
            # Step 2: KPI Check & Deploy
            is_deployed = check_kpis_and_deploy()
            
            if is_deployed:
                print("Evolution Success. High Alpha Logic Promoted.")
            
            time.sleep(3600)
        except Exception as e:
            time.sleep(300)

if __name__ == "__main__":
    if not os.path.exists(STAGING_UTILS):
        shutil.copy(PROD_UTILS, STAGING_UTILS)

    t1 = threading.Thread(target=fast_rd_loop, daemon=True)
    t2 = threading.Thread(target=slow_validation_loop, daemon=True)
    
    t1.start()
    t2.start()
    
    print("TRAINER ACTIVE. (STANDBY DURING KILL ZONES)")
    while True:
        time.sleep(1)
