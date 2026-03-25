import yfinance as yf
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from ict_utils import (
    get_timeframes_for_period, is_kill_zone, find_fvg,
    find_order_blocks, find_bos_choch, find_ifvg, find_breaker_blocks,
    find_liquidity_sweep, find_ote, find_asian_range, calculate_signal_score,
    get_market_regime, REGIME_RULES, download_full_history,
    find_turtle_soup, detect_amd_phases, find_ipda_levels, find_smt_divergence,
    detect_amd_phases_v2, find_turtle_soup_v2, find_ipda_v2, find_order_blocks_v2
)
from daily_risk_manager import DailyRiskManager
import pandas_ta as ta

load_dotenv(override=True)

# ============================================================
# TRAILING STOP STRATEJILERI
# ============================================================
class TrailingStopStrategy:
    """4 farkli trailing stop / exit stratejisi."""

    @staticmethod
    def fixed_target(entry, atr, direction, rr=3.0):
        """A: Sabit hedef, trailing yok (saf 1:3 R:R)"""
        sl = entry - atr * 1.5 if direction == 'LONG' else entry + atr * 1.5
        tp = entry + atr * (1.5 * rr) if direction == 'LONG' else entry - atr * (1.5 * rr)
        return sl, tp, None, None  # (sl, tp, be_trigger, partial_tp)

    @staticmethod
    def breakeven_at_2r(entry, atr, direction):
        """B: 2R'da BE'ye cek, 3R'da tam cik"""
        sl = entry - atr * 1.5 if direction == 'LONG' else entry + atr * 1.5
        risk = atr * 1.5
        be_trigger = entry + risk * 2 if direction == 'LONG' else entry - risk * 2
        tp = entry + risk * 3 if direction == 'LONG' else entry - risk * 3
        return sl, tp, be_trigger, None

    @staticmethod
    def breakeven_at_25r(entry, atr, direction):
        """C: 2.5R'da BE'ye cek, 4R'da tam cik"""
        sl = entry - atr * 1.5 if direction == 'LONG' else entry + atr * 1.5
        risk = atr * 1.5
        be_trigger = entry + risk * 2.5 if direction == 'LONG' else entry - risk * 2.5
        tp = entry + risk * 4 if direction == 'LONG' else entry - risk * 4
        return sl, tp, be_trigger, None

    @staticmethod
    def partial_close(entry, atr, direction):
        """D: ICT klasik - 2R'da %50 kapat, kalanini 5R'da kapat"""
        sl = entry - atr * 1.5 if direction == 'LONG' else entry + atr * 1.5
        risk = atr * 1.5
        partial_tp = entry + risk * 2 if direction == 'LONG' else entry - risk * 2
        final_tp = entry + risk * 5 if direction == 'LONG' else entry - risk * 5
        return sl, final_tp, None, partial_tp  # be_trigger=None, partial_tp


STRATEGIES = {
    'A_fixed_3r':      TrailingStopStrategy.fixed_target,
    'B_be_at_2r':      TrailingStopStrategy.breakeven_at_2r,
    'C_be_at_25r':     TrailingStopStrategy.breakeven_at_25r,
    'D_partial_close': TrailingStopStrategy.partial_close,
}

STRATEGY_LABELS = {
    'A_fixed_3r':      'A) Sabit 3R hedef',
    'B_be_at_2r':      'B) BE @ 2R, TP 3R',
    'C_be_at_25r':     'C) BE @ 2.5R, TP 4R',
    'D_partial_close': 'D) %50 @ 2R, rest 5R',
}

class ICTBacktest:
    def __init__(self, ticker, period, balance=1000, risk_per_trade=1.0, loss_limit=-2.0, profit_target=5.0, max_trades=6, trail_strategy='D_partial_close'):
        self.ticker = ticker
        self.period = period
        self.initial_balance = balance
        self.balance = balance
        self.tfs = get_timeframes_for_period(period)
        self.max_total_trades = max_trades
        
        # Dataframes init
        self.df_signal = pd.DataFrame()
        self.df_struct = pd.DataFrame()
        self.df_bias = pd.DataFrame()
        self.df_daily = pd.DataFrame()
        self.df_vix = pd.DataFrame()
        self.df_smt = pd.DataFrame()
        
        self.trail_strategy = trail_strategy
        self.trail_fn = STRATEGIES.get(trail_strategy, TrailingStopStrategy.fixed_target)
        self.rm = DailyRiskManager(initial_balance=balance)
        self.trades = []
        self.equity_curve = {'labels': ['Baslangic'], 'data': [balance]}

    def load_data(self):
        print(f"[{self.ticker}] Timeframes: Bias={self.tfs['bias']}, Struct={self.tfs['structure']}, Signal={self.tfs['signal']}")
        
        import os
        # MTF adlandirma farkliligini gider (label vs interval)
        # Robust filename matching
        base = self.ticker.lower().replace('=x', '')
        
        # Try specific mtf names first
        s_file = f"{base}_signal_{self.tfs['signal']}.csv" if os.path.exists(f"{base}_signal_{self.tfs['signal']}.csv") else f"{base}_{self.tfs['signal']}.csv"
        st_file = f"{base}_struct_{self.tfs['structure']}.csv" if os.path.exists(f"{base}_struct_{self.tfs['structure']}.csv") else f"{base}_{self.tfs['structure']}.csv"
        b_file = f"{base}_{self.tfs['bias']}.csv" if os.path.exists(f"{base}_{self.tfs['bias']}.csv") else f"{base}_1d.csv"
        
        alt_names = {
            'signal': s_file,
            'struct': st_file,
            'bias': b_file
        }
            
        found_any = False
        print(f"[DEBUG] CWD: {os.getcwd()}")
        print(f"[DEBUG] ListDIR: {os.listdir('.')}")
        print(f"[DEBUG] Looking for files: {alt_names}")
        
        if os.path.exists(alt_names['bias']):
            print(f"[{self.ticker}] Bias CSV yukleniyor...")
            self.df_bias = pd.read_csv(alt_names['bias'], index_col=0)
            if not self.df_bias.empty:
                self.df_bias.index = pd.to_datetime(self.df_bias.index, errors='coerce')
                self.df_bias = self.df_bias[self.df_bias.index.notna()]
                if not isinstance(self.df_bias.index, pd.DatetimeIndex):
                    self.df_bias.index = pd.DatetimeIndex(self.df_bias.index)
                if self.df_bias.index.tz is not None:
                    self.df_bias.index = self.df_bias.index.tz_convert(None)
                else:
                    self.df_bias.index = self.df_bias.index.tz_localize(None)
                if isinstance(self.df_bias.columns, pd.MultiIndex): self.df_bias.columns = self.df_bias.columns.droplevel(1)
                for col in ['Open', 'High', 'Low', 'Close']:
                    self.df_bias[col] = pd.to_numeric(self.df_bias[col], errors='coerce')
                self.df_bias['EMA_200'] = ta.ema(self.df_bias['Close'].squeeze(), length=200)
                found_any = True
        
        if os.path.exists(alt_names['struct']):
            print(f"[{self.ticker}] Struct CSV yukleniyor...")
            self.df_struct = pd.read_csv(alt_names['struct'], index_col=0)
            if not self.df_struct.empty:
                self.df_struct = self.df_struct[~self.df_struct.index.isin(['Ticker', 'Datetime'])]
                self.df_struct.index = pd.to_datetime(self.df_struct.index, errors='coerce')
                self.df_struct = self.df_struct[self.df_struct.index.notna()]
                if not isinstance(self.df_struct.index, pd.DatetimeIndex):
                    self.df_struct.index = pd.DatetimeIndex(self.df_struct.index)
                if self.df_struct.index.tz is not None:
                    self.df_struct.index = self.df_struct.index.tz_convert(None)
                else:
                    self.df_struct.index = self.df_struct.index.tz_localize(None)
                if isinstance(self.df_struct.columns, pd.MultiIndex): self.df_struct.columns = self.df_struct.columns.droplevel(1)
                for col in ['Open', 'High', 'Low', 'Close']:
                    self.df_struct[col] = pd.to_numeric(self.df_struct[col], errors='coerce')
                from ict_utils import find_bos_choch
                self.df_struct = find_bos_choch(self.df_struct)
                self.df_struct.sort_index(inplace=True)
                found_any = True
        
        if os.path.exists(alt_names['signal']):
            print(f"[{self.ticker}] Signal CSV yukleniyor...")
            self.df_signal = pd.read_csv(alt_names['signal'], index_col=0)
            if not self.df_signal.empty:
                self.df_signal = self.df_signal[~self.df_signal.index.isin(['Ticker', 'Datetime'])]
                self.df_signal.index = pd.to_datetime(self.df_signal.index, errors='coerce')
                self.df_signal = self.df_signal[self.df_signal.index.notna()]
                if not isinstance(self.df_signal.index, pd.DatetimeIndex):
                    self.df_signal.index = pd.DatetimeIndex(self.df_signal.index)
                if self.df_signal.index.tz is not None:
                    self.df_signal.index = self.df_signal.index.tz_convert(None)
                else:
                    self.df_signal.index = self.df_signal.index.tz_localize(None)
                self.df_signal.sort_index(inplace=True)
                if isinstance(self.df_signal.columns, pd.MultiIndex): self.df_signal.columns = self.df_signal.columns.droplevel(1)
                for col in ['Open', 'High', 'Low', 'Close']:
                    self.df_signal[col] = pd.to_numeric(self.df_signal[col], errors='coerce')
                found_any = True

        if found_any:
            self._apply_indicators_to_signal()
            return

        from ict_utils import download_full_history
        yf_ticker = self.ticker + "=X" if "EURUSD" in self.ticker or "GBPUSD" in self.ticker else self.ticker
        if self.period in ['3mo', '6mo', '1y']:
            months = {'3mo':3, '6mo':6, '1y':12}[self.period]
            try:
                self.df_bias = yf.download(yf_ticker, period=self.period, interval=self.tfs['bias'], progress=False)
                if isinstance(self.df_bias.columns, pd.MultiIndex): self.df_bias.columns = self.df_bias.columns.droplevel(1)
                if self.df_bias.index.tz is None: self.df_bias.index = self.df_bias.index.tz_localize('UTC')
                else: self.df_bias.index = self.df_bias.index.tz_convert('UTC')
                self.df_bias['EMA_200'] = ta.ema(self.df_bias['Close'].squeeze(), length=200)
            except Exception as e:
                print(f"Bias Error: {e}")
                self.df_bias = pd.DataFrame()
                
            try:
                self.df_struct = download_full_history(self.ticker, months=months, interval=self.tfs['structure'])
                if self.df_struct.index.tz is None: self.df_struct.index = self.df_struct.index.tz_localize('UTC')
                else: self.df_struct.index = self.df_struct.index.tz_convert('UTC')
                self.df_struct = find_bos_choch(self.df_struct)
            except Exception as e:
                print(f"Struct Error: {e}")
                self.df_struct = pd.DataFrame()
                
            try:
                self.df_signal = download_full_history(self.ticker, months=months, interval=self.tfs['signal'])
                if self.df_signal.index.tz is None: self.df_signal.index = self.df_signal.index.tz_localize('UTC')
                else: self.df_signal.index = self.df_signal.index.tz_convert('UTC')
            except Exception as e:
                print(f"Signal Error: {e}")
                self.df_signal = pd.DataFrame()
        else:
            try:
                self.df_bias = yf.download(yf_ticker, period=self.period, interval=self.tfs['bias'], progress=False)
                if isinstance(self.df_bias.columns, pd.MultiIndex): self.df_bias.columns = self.df_bias.columns.droplevel(1)
                if self.df_bias.index.tz is not None:
                    self.df_bias.index = self.df_bias.index.tz_convert(None)
                else:
                    self.df_bias.index = self.df_bias.index.tz_localize(None)
                self.df_bias['EMA_200'] = ta.ema(self.df_bias['Close'].squeeze(), length=200)
            except:
                self.df_bias = pd.DataFrame()
                
            try:
                self.df_struct = yf.download(self.ticker, period=self.period, interval=self.tfs['structure'], progress=False)
                if isinstance(self.df_struct.columns, pd.MultiIndex): self.df_struct.columns = self.df_struct.columns.droplevel(1)
                if self.df_struct.index.tz is None: self.df_struct.index = self.df_struct.index.tz_localize('UTC')
                else: self.df_struct.index = self.df_struct.index.tz_convert('UTC')
                self.df_struct = find_bos_choch(self.df_struct)
            except:
                self.df_struct = pd.DataFrame()
                
            try:
                self.df_signal = yf.download(self.ticker, period=self.period, interval=self.tfs['signal'], progress=False)
                if self.df_signal.empty: raise Exception("Boş veri")
            except:
                print(f"[{self.ticker}] {self.tfs['signal']} çekilemedi, {self.tfs['structure']} resampled edilecek.")
                self.df_signal = self.df_struct.copy()
            
            if not self.df_signal.empty:
                if isinstance(self.df_signal.columns, pd.MultiIndex): self.df_signal.columns = self.df_signal.columns.droplevel(1)
                if self.df_signal.index.tz is None: self.df_signal.index = self.df_signal.index.tz_localize('UTC')
                else: self.df_signal.index = self.df_signal.index.tz_convert('UTC')
        
        self._apply_indicators_to_signal()

    def _apply_indicators_to_signal(self):
        """Sinyal zaman dilimine tum ICT indikatorlerini uygular."""
        if self.df_signal.empty: return
        
        from ict_utils import (find_fvg, find_order_blocks, find_ifvg, find_breaker_blocks, 
                             find_liquidity_sweep, find_bos_choch, find_ote, find_asian_range,
                             find_turtle_soup, detect_amd_phases)
        
        self.df_signal['ATR_14'] = ta.atr(self.df_signal['High'].squeeze(), self.df_signal['Low'].squeeze(), self.df_signal['Close'].squeeze(), length=14)
        self.df_signal = find_fvg(self.df_signal)
        self.df_signal = find_order_blocks(self.df_signal) # V1 adds columns
        self.df_signal = find_ifvg(self.df_signal)
        self.df_signal = find_breaker_blocks(self.df_signal)
        self.df_signal = find_liquidity_sweep(self.df_signal)
        self.df_signal = find_bos_choch(self.df_signal)
        self.df_signal = find_ote(self.df_signal)
        self.df_signal = find_asian_range(self.df_signal)
        self.df_signal = find_turtle_soup(self.df_signal)
        self.df_signal = detect_amd_phases(self.df_signal)
        
        yf_ticker = self.ticker + "=X" if "USD" in self.ticker else self.ticker
        # Daily & VIX for regime
        try:
            self.df_daily = yf.download(yf_ticker, period='2y', interval='1d', progress=False)
            if isinstance(self.df_daily.columns, pd.MultiIndex): self.df_daily.columns = self.df_daily.columns.droplevel(1)
            if not self.df_daily.empty:
                if self.df_daily.index.tz is not None: self.df_daily.index = self.df_daily.index.tz_convert(None)
                else: self.df_daily.index = self.df_daily.index.tz_localize(None)
            
            self.df_vix = yf.download('^VIX', period='2y', interval='1d', progress=False)
            if isinstance(self.df_vix.columns, pd.MultiIndex): self.df_vix.columns = self.df_vix.columns.droplevel(1)
            if not self.df_vix.empty:
                if self.df_vix.index.tz is not None: self.df_vix.index = self.df_vix.index.tz_convert(None)
                else: self.df_vix.index = self.df_vix.index.tz_localize(None)
            
            # SMT for GBPUSD=X (example, can be adjusted)
            smt_ticker = 'GBPUSD=X' if self.ticker == 'EURUSD=X' else 'EURUSD=X' if self.ticker == 'GBPUSD=X' else 'GBPUSD=X'
            self.df_smt = yf.download(smt_ticker, period='2y', interval='1d', progress=False)
            if isinstance(self.df_smt.columns, pd.MultiIndex): self.df_smt.columns = self.df_smt.columns.droplevel(1)
            if not self.df_smt.empty:
                if self.df_smt.index.tz is not None: self.df_smt.index = self.df_smt.index.tz_convert(None)
                else: self.df_smt.index = self.df_smt.index.tz_localize(None)
        except Exception as e:
            print(f"Global Data Error: {e}")
            self.df_daily = pd.DataFrame()
            self.df_vix = pd.DataFrame()
            self.df_smt = pd.DataFrame()

    def run(self, max_total_trades=1000):
        self.load_data()
        if not hasattr(self, 'df_signal') or self.df_signal.empty: 
            print("Hata: Sinyal verisi bos.")
            return {
                'total_trades': 0, 'win_rate': 0, 'pnl_percent': 0, 
                'max_drawdown': 0, 'final_balance': self.initial_balance,
                'trades': [], 'monthly_returns': {}, 'error': 'Veri bos'
            }
            
        pending_signal = None
        current_trade = None
        last_regime = 'NEUTRAL'
        last_regime_date = None
        
        print(f"\n[{self.ticker}] Backtest Basliyor... ({self.trail_strategy})")
        if max_total_trades: print(f"Islem Siniri: {max_total_trades}")
            
        for i in range(len(self.df_signal)):
            if max_total_trades and len(self.trades) >= max_total_trades:
                print(f"\n--- {max_total_trades} islem sinirina ulasildi. ---")
                break
            
            t = self.df_signal.index[i]
            if hasattr(t, 'tz_localize') and t.tzinfo is not None:
                t = t.tz_localize(None)
            row = self.df_signal.iloc[i]
            self.rm.update_date(t.date())
            
            # Regime update daily
            curr_date = t.date()
            if last_regime_date != curr_date:
                last_regime_date = curr_date
                if not self.df_daily.empty:
                    daily_up_to = self.df_daily[self.df_daily.index.date < curr_date]
                    vix_val = self.df_vix[self.df_vix.index.date < curr_date]['Close'].iloc[-1] if not self.df_vix.empty else None
                    last_regime = get_market_regime(daily_up_to, vix_val)
            
            regime_rules = REGIME_RULES.get(last_regime, REGIME_RULES['NEUTRAL'])
            
            # Position management
            if current_trade:
                entry = current_trade['entry']
                direction = current_trade['direction']
                risk_per_share = abs(entry - current_trade['original_sl'])
                
                # Update Fav Excursion
                fav_move = (row['High'] - entry) if direction == 'LONG' else (entry - row['Low'])
                current_trade['max_fav_excursion'] = max(current_trade['max_fav_excursion'], float(fav_move))

                # BE Check
                if current_trade.get('be_trigger') and not current_trade['be_locked']:
                    if (direction == 'LONG' and row['High'] >= current_trade['be_trigger']) or \
                       (direction == 'SHORT' and row['Low'] <= current_trade['be_trigger']):
                        current_trade['sl'] = entry
                        current_trade['be_locked'] = True

                # Partial Check
                if current_trade.get('partial_tp') and not current_trade['partial_hit']:
                    if (direction == 'LONG' and row['High'] >= current_trade['partial_tp']) or \
                       (direction == 'SHORT' and row['Low'] <= current_trade['partial_tp']):
                        pnl = current_trade['reward'] * 0.5
                        self.rm.register_trade_result(pnl)
                        current_trade['risk'] *= 0.5
                        current_trade['reward'] *= 0.5
                        current_trade['sl'] = entry
                        current_trade['partial_hit'] = True
                        self.trades.append({
                            'date': t.strftime('%Y-%m-%d %H:%M') + ' [PARTIAL]',
                            'ticker': self.ticker, 'dir': direction, 'entry': f"{entry:.4f}",
                            'exit': f"{current_trade['partial_tp']:.4f}", 'pnl_pct': (pnl/current_trade['entry_bal'])*100,
                            'rr': '1:2', 'actual_r': 2.0, 'setup_type': current_trade['setup_type']
                        })

                # Exit Check
                exit_price = 0
                close_trade = False
                if direction == 'LONG':
                    if row['Low'] <= current_trade['sl']: exit_price = current_trade['sl']; close_trade = True
                    elif row['High'] >= current_trade['tp']: exit_price = current_trade['tp']; close_trade = True
                else:
                    if row['High'] >= current_trade['sl']: exit_price = current_trade['sl']; close_trade = True
                    elif row['Low'] <= current_trade['tp']: exit_price = current_trade['tp']; close_trade = True

                if close_trade:
                    pnl = (exit_price - entry) / risk_per_share * current_trade['risk'] if risk_per_share > 0 else -current_trade['risk']
                    if exit_price == current_trade['tp']: pnl = current_trade['reward'] # fix rounding
                    self.rm.register_trade_result(pnl)
                    self.trades.append({
                        'date': t.strftime('%Y-%m-%d %H:%M'),
                        'ticker': self.ticker, 'dir': direction, 'entry': f"{entry:.4f}",
                        'exit': f"{exit_price:.4f}", 'pnl_pct': (pnl/current_trade['entry_bal'])*100,
                        'rr_achieved': float(current_trade['max_fav_excursion']/risk_per_share) if risk_per_share > 0 else 0,
                        'actual_r': float(pnl/current_trade['risk']) if current_trade['risk'] > 0 else 0,
                        'setup_type': current_trade['setup_type'], 'kill_zone': current_trade['kill_zone'],
                        'regime': last_regime, 'reasons': ', '.join(current_trade['reasons'])
                    })
                    self.equity_curve['labels'].append(t.strftime('%m-%d %H:%M'))
                    self.equity_curve['data'].append(self.rm.balance)
                    current_trade = None
                continue

            # Confirmation logic
            if pending_signal:
                p = pending_signal
                confirmed = (row['Close'] > row['Open']) if p['direction'] == 'LONG' else (row['Close'] < row['Open'])
                if confirmed:
                    entry = float(row['Close'])
                    atr_val = float(row.get('ATR_14', entry*0.005))
                    sl, tp, be, ptp = self.trail_fn(entry, atr_val, p['direction'])
                    risk = self.rm.balance * min(regime_rules.get('risk', 0.01), self.rm.get_risk_pct())
                    current_trade = {
                        'direction': p['direction'], 'entry': entry, 'sl': sl, 'original_sl': sl, 'tp': tp,
                        'be_trigger': be, 'partial_tp': ptp, 'partial_hit': False, 'be_locked': False,
                        'risk': risk, 'reward': risk * (abs(tp-entry)/abs(sl-entry) if abs(sl-entry)>0 else 3.0),
                        'entry_bal': self.rm.balance, 'score': p['score'], 'reasons': p['reasons'],
                        'setup_type': p['setup_type'], 'kill_zone': p['kill_zone'], 'max_fav_excursion': 0.0
                    }
                pending_signal = None
                continue

            # Entry Logic
            if not regime_rules.get('trade', True): continue
            can_trade, _ = self.rm.can_trade_today()
            if not can_trade: continue
            
            kz = is_kill_zone(t)
            if not kz: continue

            # MTF check (strictly bias-free)
            b_match = pd.DataFrame()
            if not self.df_bias.empty and isinstance(self.df_bias.index, pd.DatetimeIndex):
                b_match = self.df_bias[self.df_bias.index + pd.Timedelta(hours=1) <= t]
            
            s_match = pd.DataFrame()
            if not self.df_struct.empty and isinstance(self.df_struct.index, pd.DatetimeIndex):
                s_match = self.df_struct[self.df_struct.index + pd.Timedelta(minutes=15) <= t]
                
            if b_match.empty or s_match.empty: continue
            
            bias = "BULLISH" if b_match.iloc[-1]['Close'] > b_match.iloc[-1].get('EMA_200', 0) else "BEARISH"
            
            # Advanced Signals (V2)
            sig_slice = self.df_signal.iloc[max(0, i-300):i+1]
            amd_res = detect_amd_phases_v2(sig_slice)
            ts_res = find_turtle_soup_v2(sig_slice.tail(60), lookback=20)
            ob_res = find_order_blocks_v2(sig_slice.tail(50))
            
            # Advanced Indicators (Placeholder for H1 V2)
            ote, asr, ifvg, breaker = False, False, False, False
            
            # Scores
            b_sc, b_rs, _ = calculate_signal_score(
                bias, row.get('BOS_Bull'), ote, asr, ifvg, breaker, True,
                direction='BULLISH',
                turtle_soup_v2=ts_res[0] if ts_res and ts_res[0].get('direction')=='LONG' else None,
                amd_v2=amd_res if amd_res and amd_res.get('direction')=='LONG' else None,
                active_ob_v2=ob_res[0] if ob_res and ob_res[0]['type']=='BULLISH_OB' else None
            )
            s_sc, s_rs, _ = calculate_signal_score(
                bias, row.get('BOS_Bear'), ote, asr, ifvg, breaker, True,
                direction='BEARISH',
                turtle_soup_v2=ts_res[0] if ts_res and ts_res[0].get('direction')=='SHORT' else None,
                amd_v2=amd_res if amd_res and amd_res.get('direction')=='SHORT' else None,
                active_ob_v2=ob_res[0] if ob_res and ob_res[0]['type']=='BEARISH_OB' else None
            )

            direction = None
            if b_sc >= regime_rules.get('min_score', 50) and b_sc >= s_sc:
                direction, score, reasons = 'LONG', b_sc, b_rs
            elif s_sc >= regime_rules.get('min_score', 50) and s_sc > b_sc:
                direction, score, reasons = 'SHORT', s_sc, s_rs

            if direction:
                pending_signal = {
                    'direction': direction, 'score': score, 'reasons': reasons,
                    'setup_type': 'V2_Setup', 'kill_zone': kz
                }

        rep = self.rm.get_report_data()
        
        # Calculate monthly returns for runner script
        monthly_returns = {}
        if self.trades:
            for tr in self.trades:
                m_key = str(tr['date'])[:7] # YYYY-MM
                monthly_returns[m_key] = monthly_returns.get(m_key, 0) + tr['pnl_pct']

        return {
            "total_trades": rep['total_trades'],
            "win_rate": rep['win_rate'],
            "pnl_percent": rep['net_pnl'],
            "max_drawdown": rep['max_drawdown'],
            "final_balance": self.rm.balance,
            "equity": self.equity_curve,
            "trades": sorted(self.trades, key=lambda x: x['date'], reverse=True),
            "monthly_returns": monthly_returns,
            "metrics": {
                "net_pnl": rep['net_pnl'],
                "win_rate": rep['win_rate'],
                "total_trades": rep['total_trades'],
                "max_drawdown": rep['max_drawdown'],
                "avg_rr_realized": np.mean([t.get('actual_r', 0) for t in self.trades]) if self.trades else 0
            }
        }

def api_run_backtest(params):
    watch = [t.strip() for t in str(params.get('ticker', 'PLTR')).split(',')]
    period = params.get('period', '30d')
    init_b = float(params.get('initial_balance', 1000))
    
    bot = ICTBacktest(watch[0], period, init_b)
    bot.load_data()
    return bot.run()

def run_multi_backtest(period='30d', balance=10000):
    pairs = {
        'EURUSD=X': {'name': 'EUR/USD', 'type': 'forex'},
        'GBPUSD=X': {'name': 'GBP/USD', 'type': 'forex'},
        'GC=F':     {'name': 'Altın',   'type': 'commodity'}
    }
    
    results = {}
    threads = []
    
    import threading
    
    def run_single(ticker, info):
        bt = ICTBacktest(ticker, period, balance/3)
        bt.load_data()
        res = bt.run()
        if 'error' not in res:
            res['name'] = info['name']
            results[ticker] = res
    
    for ticker, info in pairs.items():
        t = threading.Thread(target=run_single, args=(ticker, info))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    print_comparison_report(results)
    return results

def print_comparison_report(results):
    print("=" * 60)
    print("MULTI-ASSET BACKTEST KARŞILAŞTIRMA RAPORU")
    print("=" * 60)
    
    valid_results = {k: v for k, v in results.items() if 'metrics' in v}
    
    for ticker, r in valid_results.items():
        m = r['metrics']
        days = max(1, len(m.get('equity', {}).get('labels', [])) - 1)
        daily_avg = m['total_trades'] / days if days > 0 else 0
        print(f"""
        {r['name']} ({ticker})
        -------------------------
        Toplam İşlem    : {m['total_trades']}
        Günlük Ort.     : {daily_avg:.1f}
        Win Rate        : %{m['win_rate']:.1f}
        Net PnL         : %{m['net_pnl']:.2f}
        Max Drawdown    : %{m['max_drawdown']:.2f}
        Sharpe Ratio    : {m['sharpe_ratio']:.2f}
        En iyi sinyal   : {m.get('best_setup', 'Bilinmiyor')}
        """)
        
        # Monthly grouping
        trades = r.get('trades', [])
        if trades:
            monthly_stats = {}
            for t in trades:
                date_str = str(t['date'])[:7] # YYYY-MM
                if date_str not in monthly_stats:
                    monthly_stats[date_str] = {'wins':0, 'total':0, 'pnl':0}
                monthly_stats[date_str]['total'] += 1
                if t['pnl_pct'] > 0: monthly_stats[date_str]['wins'] += 1
                monthly_stats[date_str]['pnl'] += t['pnl_pct']
                
            print("        Aylik Performans:")
            for k, v in sorted(monthly_stats.items()):
                wr = (v['wins'] / v['total']) * 100 if v['total'] else 0
                print(f"          {k}: {v['total']} islem, Win: %{wr:.1f}, PnL: %{v['pnl']:.2f}")
    
    if valid_results:
        best = max(valid_results.items(), key=lambda x: x[1]['metrics']['net_pnl'])
        print(f"*** EN IYI PERFORMANS: {best[1]['name']} ***")

def run_strategy_comparison(ticker='SPY', period='1y', balance=10000):
    """4 trailing stop stratejisini SPY 1 yillik test ile karsilastir."""
    print(f"\n{'='*60}")
    print(f"TRAILING STOP STRATEJI KARSILASTIRMASI — {ticker} ({period})")
    print(f"{'='*60}")
    print(f"{'Strateji':<28} | {'Islem':>6} | {'WR%':>6} | {'PnL%':>8} | {'MaxDD%':>8} | {'Sharpe':>7}")
    print(f"{'-'*28}-+-{'-'*6}-+-{'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}")

    strategy_results = {}

    # Veriyi 1 kez yukle, tum stratejiler icin yeniden kullan
    print("Veri yukleniyor (1 kez)...")
    base_bt = ICTBacktest(ticker, period, balance, trail_strategy='A_fixed_3r')
    base_bt.load_data()

    for strategy_key, label in STRATEGY_LABELS.items():
        # Ayni veriyi paylasarak backtest objesi olustur
        bt = ICTBacktest('SPY', '30d', 10000, trail_strategy=strategy_key)
        # Loaded verileri kopyala — tekrar indirme
        import copy
        bt.df_signal = base_bt.df_signal.copy()
        bt.df_struct = base_bt.df_struct.copy()
        bt.df_bias = base_bt.df_bias.copy()
        bt.df_daily = base_bt.df_daily.copy() if not base_bt.df_daily.empty else pd.DataFrame()
        bt.df_vix = base_bt.df_vix.copy() if not base_bt.df_vix.empty else pd.DataFrame()
        bt.tfs = base_bt.tfs

        res = bt.run()
        if 'error' not in res:
            m = res['metrics']
            strategy_results[strategy_key] = {'label': label, 'metrics': m, 'trades': res.get('trades', [])}
            print(f"{label:<28} | {m['total_trades']:>6} | {m['win_rate']:>5.1f}% | {m['net_pnl']:>+7.2f}% | {m['max_drawdown']:>7.2f}% | {m['sharpe_ratio']:>+6.2f}")
        else:
            print(f"{label:<28} | HATA: {res['error']}")

    # En iyi sonuclari bul
    if strategy_results:
        best_pnl = max(strategy_results.items(), key=lambda x: x[1]['metrics']['net_pnl'])
        best_dd  = min(strategy_results.items(), key=lambda x: x[1]['metrics']['max_drawdown'])
        best_wr  = max(strategy_results.items(), key=lambda x: x[1]['metrics']['win_rate'])

        print(f"\n{'='*60}")
        print(f"EN YUKSEK Net PnL   : {best_pnl[1]['label']} ({best_pnl[1]['metrics']['net_pnl']:+.2f}%)")
        print(f"EN DUSUK Max Drawdown: {best_dd[1]['label']} ({best_dd[1]['metrics']['max_drawdown']:.2f}%)")
        print(f"EN YUKSEK Win Rate  : {best_wr[1]['label']} ({best_wr[1]['metrics']['win_rate']:.1f}%)")

        # Kazanan: Net PnL + MaxDD birlikte en iyisi (skor)
        def score_fn(item):
            m = item[1]['metrics']
            return m['net_pnl'] - m['max_drawdown'] * 0.5 + m['win_rate'] * 0.3
        winner = max(strategy_results.items(), key=score_fn)
        print(f"\n*** KAZANAN STRATEJI (PnL - 0.5*DD + 0.3*WR): {winner[1]['label']} ***")

        # Aylik breakdown sadece kazanan icin goster
        print(f"\nKazanan ({winner[1]['label']}) — Aylik Performans:")
        monthly_stats = {}
        for tr in winner[1].get('trades', []):
            date_str = str(tr['date'])[:7]
            if date_str not in monthly_stats:
                monthly_stats[date_str] = {'wins': 0, 'total': 0, 'pnl': 0}
            monthly_stats[date_str]['total'] += 1
            if tr['pnl_pct'] > 0: monthly_stats[date_str]['wins'] += 1
            monthly_stats[date_str]['pnl'] += tr['pnl_pct']
        for k, v in sorted(monthly_stats.items()):
            wr = (v['wins'] / v['total']) * 100 if v['total'] else 0
            print(f"  {k}: {v['total']:>3} islem | WR: {wr:>5.1f}% | PnL: {v['pnl']:>+7.2f}%")

        # Aylik breakdown bittikten sonra Sinyal Breakdown dökümü
        print(f"\nKazanan ({winner[1]['label']}) — Sinyal / Setup Dökümü:")
        print(f"{'Sinyal Tipi':<20} | {'Islem':>5} | {'WR%':>5} | {'Avg RR':>6}")
        print("-" * 45)
        
        signal_stats = {}
        for tr in winner[1].get('trades', []):
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

    return strategy_results


if __name__ == '__main__':
    run_strategy_comparison('SPY', '1y', 10000)
