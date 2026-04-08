import re
import math

def analyze_log(filename):
    with open(filename, 'r') as f:
        content = f.read()

    # Extract trades
    # 2026-01-13 00:45:00+00:00 | EUR_USD | SHORT | PnL: -1000.00 | SL
    trade_pattern = r"\| (LONG|SHORT) \| PnL: ([\-\d\.]+) \| (SL|TP)"
    trades = re.findall(trade_pattern, content)
    
    max_streak = 0
    curr_streak = 0
    total_trades = 0
    wins = 0
    
    pnls = []
    
    for t_dir, pnl_str, status in trades:
        pnl = float(pnl_str)
        pnls.append(pnl)
        total_trades += 1
        if status == 'SL':
            curr_streak += 1
            max_streak = max(max_streak, curr_streak)
        else:
            wins += 1
            curr_streak = 0
            
    # SPREAD SIMULATION (Assume 1 pip cost)
    # Average SL distance is approx 15 pips. 1 pip = 6.6% of risk.
    # New PnL calculation:
    sim_balance = 100000
    start_balance = 100000
    spread_pips = 1.0 # Significant cost
    
    spread_adjusted_balance = 100000
    
    for t_dir, pnl_str, status in trades:
        # A loss of 1% now becomes 1.066% due to spread?
        # Or more accurately, the Reward is reduced and Risk is increased.
        # RR 1:3 becomes (1-spread):(3-spread) -> 1.06:2.94?
        # Let's be conservative: Subtract 7% of absolute PnL as slippage/spread/comm
        raw_pnl = float(pnl_str)
        cost = abs(raw_pnl) * 0.08 # 8% cost reflects ~1.2 pip spread on 15 pip SL
        
        # compounding sim with costs
        if status == 'TP':
            spread_adjusted_balance *= 1.027 # 3% profit - cost
        else:
            spread_adjusted_balance *= 0.989 # 1% loss + cost
            
    print(f"Analysis of {total_trades} trades:")
    print(f"Max Consecutive Losses: {max_streak}")
    print(f"Win Rate: {(wins/total_trades)*100:.1f}%")
    print(f"Original Final Balance (Est): ${math.prod([(1.03 if s=='TP' else 0.99) for d,p,s in trades])*100000:,.2f}")
    print(f"Spread-Adjusted Final Balance (8% cost): ${spread_adjusted_balance:,.2f}")

if __name__ == "__main__":
    analyze_log("c:/Users/LENOVO/Desktop/bot/master_1000_portfolio_log.txt")
