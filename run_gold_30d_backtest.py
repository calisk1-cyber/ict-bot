import sys
import os
import pandas as pd
from backtest_ict import ICTBacktest

def main():
    # Gold Ticker
    ticker = "GC=F"
    
    print(f"[{ticker}] 30 Gunluk V2 ICT Backtest Baslatiliyor...")
    print(f"Veri Kaynagi: Dukascopy (Local CSV - XAUUSD)")
    
    # Gold icin 1h bias, 15m struct, 5m signal (30 gunluk periyot icin ideali)
    backtester = ICTBacktest(
        ticker=ticker,
        period='30d',
        balance=10000.0,
        trail_strategy='D_partial_close'
    )
    
    # ICTBacktest icinde 'GC=F' -> 'xauusd' donusumunu alt_names'de handle etmistik
    # ama dosyalarin xauusd_*.csv oldugundan emin olmaliyiz.
    
    report = backtester.run()
    
    if 'error' in report and report['error'] == 'Veri bos' :
        print(f"\n[ERROR] Backtest baslatilamadi: {report['error']}")
        return

    print("\n" + "="*50)
    print(f"BACKTEST SONUCCLARI ({ticker} 30D)")
    print("="*50)
    print(f"Toplam Islem: {report['total_trades']}")
    print(f"Win Rate: %{report['win_rate']:.2f}")
    print(f"Net Kar/Zarar: %{report['pnl_percent']:.2f}")
    print(f"Max Drawdown: %{report['max_drawdown']:.2f}")
    print(f"Bakiye: ${report['final_balance']:.2f}")
    print("="*50)

    # Sinyal Bazli Tablo
    trades = report.get('trades', [])
    if trades:
        print(f"\n{'Sinyal Tipi':<20} | {'Islem':>5} | {'WR%':>5} | {'Avg RR':>6}")
        print("-" * 45)
        
        signal_stats = {}
        for tr in trades:
            st = tr.get('setup_type', 'Other')
            if st not in signal_stats:
                signal_stats[st] = {'wins': 0, 'total': 0, 'rr_sum': 0}
            signal_stats[st]['total'] += 1
            if tr.get('actual_r', 0) > 0: signal_stats[st]['wins'] += 1
            signal_stats[st]['rr_sum'] += tr.get('actual_r', 0)
            
        for k, v in sorted(signal_stats.items(), key=lambda x: x[1]['total'], reverse=True):
            wr = (v['wins'] / v['total']) * 100 if v['total'] else 0
            avg_rr = v['rr_sum'] / v['total'] if v['total'] else 0
            print(f"{k:<20} | {v['total']:>5} | {wr:>4.1f}% | {avg_rr:>6.2f}")

    # Aylik Getiriler (V2'de eklemistik)
    if 'monthly_returns' in report and report['monthly_returns']:
        print("\nAylik Getiriler:")
        for month, pnl in report['monthly_returns'].items():
            print(f"- {month}: %{pnl:.2f}")

if __name__ == "__main__":
    main()
