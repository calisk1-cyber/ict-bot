import sys
import os
import pandas as pd
from backtest_ict import ICTBacktest

# Add current directory to path
sys.path.append(os.getcwd())

def main():
    ticker = "EURUSD"
    # Dukascopy verileri eurusd_1m.csv, eurusd_5m.csv vb. olarak kaydedildi.
    
    print(f"[{ticker}] 1 Yillik V2 ICT Backtest Baslatiliyor...")
    print("Veri Kaynagi: Dukascopy (Local CSV)")
    print("Islem Siniri: 1000")
    
    # ICTBacktest init
    # 1y 1h ve 4h verisi oldugu icin bunlari kullanalim
    bt = ICTBacktest(ticker=ticker, balance=10000, period="1y")
    bt.tfs = {'signal': '1h', 'structure': '4h', 'bias': '1d'}
    
    try:
        # Backtest'i calistir (1000 islem limiti ile)
        report = bt.run(max_total_trades=1000)
        
        print("\n" + "="*50)
        print("BACKTEST SONUÇLARI (EURUSD 1Y)")
        print("="*50)
        print(f"Toplam İşlem: {report['total_trades']}")
        print(f"Win Rate: %{report['win_rate']:.2f}")
        print(f"Net Kar/Zarar: %{report['pnl_percent']:.2f}")
        print(f"Max Drawdown: %{report['max_drawdown']:.2f}")
        print(f"Bakiye: ${report['final_balance']:.2f}")
        print("="*50)
        
        # Aylik kirilim varsa yazdir
        if 'monthly_returns' in report and report['monthly_returns']:
            print("\nAylık Getiriler:")
            for month, ret in report['monthly_returns'].items():
                print(f"- {month}: %{ret:.2f}")
        
    except Exception as e:
        print(f"\n[ERROR] Backtest sirasinda hata: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
