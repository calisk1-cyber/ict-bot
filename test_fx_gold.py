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
        self.tfs = get_timeframes_for_period(period)
        
        self.trail_strategy = trail_strategy
        self.trail_fn = STRATEGIES.get(trail_strategy, TrailingStopStrategy.fixed_target)
        self.rm = DailyRiskManager(initial_balance=balance)
        self.trades = []
        self.equity_curve = {'labels': ['Baslangic'], 'data': [balance]}
        
    def load_data(self):
        print(f"[{self.ticker}] Timeframes: Bias={self.tfs['bias']}, Struct={self.tfs['structure']}, Signal={self.tfs['signal']}")
        
        from ict_utils import download_full_history
        
        if self.period in ['3mo', '6mo', '1y']:
            months = {'3mo':3, '6mo':6, '1y':12}[self.period]
            try:
                self.df_bias = yf.download(self.ticker, period=self.period, interval=self.tfs['bias'], progress=False)
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
                self.df_bias = yf.download(self.ticker, period=self.period, interval=self.tfs['bias'], progress=False)
                if isinstance(self.df_bias.columns, pd.MultiIndex): self.df_bias.columns = self.df_bias.columns.droplevel(1)
                if self.df_bias.index.tz is None: self.df_bias.index = self.df_bias.index.tz_localize('UTC')
                else: self.df_bias.index = self.df_bias.index.tz_convert('UTC')
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
                
            if isinstance(self.df_signal.columns, pd.MultiIndex): self.df_signal.columns = self.df_signal.columns.droplevel(1)
            if self.df_signal.index.tz is None: self.df_signal.index = self.df_signal.index.tz_localize('UTC')
            else: self.df_signal.index = self.df_signal.index.tz_convert('UTC')
        
        # Apply ALL 6 indicators to signal TF
        self.df_signal['ATR_14'] = ta.atr(self.df_signal['High'].squeeze(), self.df_signal['Low'].squeeze(), self.df_signal['Close'].squeeze(), length=14)
        self.df_signal = find_fvg(self.df_signal)
        self.df_signal = find_order_blocks(self.df_signal)
        self.df_signal = find_ifvg(self.df_signal)
        self.df_signal = find_breaker_blocks(self.df_signal)
        self.df_signal = find_liquidity_sweep(self.df_signal)
        # OTE requires swing highs from struct or signal. We'll use signal's BOS first to get swings
        self.df_signal = find_bos_choch(self.df_signal)
        self.df_signal = find_ote(self.df_signal)
        self.df_signal = find_asian_range(self.df_signal)
        
        # Turtle Soup + AMD indicators on signal TF
        self.df_signal = find_turtle_soup(self.df_signal)
        self.df_signal = detect_amd_phases(self.df_signal)

        # Daily data for regime filter
        try:
            self.df_daily = yf.download(self.ticker, period='2y', interval='1d', progress=False)
            if isinstance(self.df_daily.columns, pd.MultiIndex): self.df_daily.columns = self.df_daily.columns.droplevel(1)
        except:
            self.df_daily = pd.DataFrame()

        # VIX data for regime filter
        try:
            self.df_vix = yf.download('^VIX', period='2y', interval='1d', progress=False)
            if isinstance(self.df_vix.columns, pd.MultiIndex): self.df_vix.columns = self.df_vix.columns.droplevel(1)
        except:
            self.df_vix = pd.DataFrame()

        # SMT correlated asset (QQQ for SPY; skip if same)
        smt_ticker = 'QQQ' if self.ticker == 'SPY' else ('SPY' if self.ticker == 'QQQ' else None)
        self.df_smt = pd.DataFrame()
        if smt_ticker:
            try:
                # Use download_full_history to bypass 60-day limit for intraday data
                months_map = {'1mo': 1, '3mo': 3, '6mo': 6, '1y': 12, '2y': 24}
                months = months_map.get(self.period, 12)
                self.df_smt = download_full_history(smt_ticker, months=months, interval=self.tfs['signal'])
                if self.df_smt is not None and not self.df_smt.empty:
                    if self.df_smt.index.tz is None: 
                        self.df_smt.index = self.df_smt.index.tz_localize('UTC')
                    else: 
                        self.df_smt.index = self.df_smt.index.tz_convert('UTC')
                    print(f"[SMT] {smt_ticker} verisi yuklendi ({len(self.df_smt)} mum)")
            except Exception as e:
                print(f"[SMT] {smt_ticker} yuklenemedi: {e}")

    def run(self):
        if self.df_signal.empty or self.df_struct.empty or self.df_bias.empty: 
            return {"error": "Veri hatasi"}
            
        current_trade = None
        pending_signal = None   # Confirmation mumu icin bekleme
        last_regime = 'NEUTRAL'
        last_regime_date = None
        
        for i, (t, row) in enumerate(self.df_signal.iterrows()):
            self.rm.update_date(t.date())
            
            # --- REGIME GUNCELLEME (gunde 1 kez) ---
            current_date = t.date()
            if last_regime_date != current_date:
                last_regime_date = current_date
                if not self.df_daily.empty:
                    # STRICT AVOIDANCE OF LOOK-AHEAD: only use daily data strictly before today
                    daily_up_to = self.df_daily[self.df_daily.index.date < current_date]
                    vix_val = None
                    if hasattr(self, 'df_vix') and not self.df_vix.empty:
                        vix_up = self.df_vix[self.df_vix.index.date < current_date]
                        if not vix_up.empty:
                            vix_val = float(vix_up['Close'].iloc[-1])
                    last_regime = get_market_regime(daily_up_to, vix_val)
            
            regime_rules = REGIME_RULES.get(last_regime, REGIME_RULES['NEUTRAL'])
            
            # --- ACIK POZISYON YONETIMI ---
            if current_trade:
                entry = current_trade['entry']
                direction = current_trade['direction']
                original_sl = current_trade['original_sl']
                risk_per_share = abs(entry - original_sl)
                be_trigger = current_trade.get('be_trigger')
                partial_tp = current_trade.get('partial_tp')
                partial_hit = current_trade.get('partial_hit', False)

                # Fiyat hareketi
                if direction == 'LONG':
                    fav_move = float(row['High']) - entry
                else:
                    fav_move = entry - float(row['Low'])
                if fav_move > current_trade['max_fav_excursion']:
                    current_trade['max_fav_excursion'] = fav_move

                # BE trigger: strateji belirledi mi?
                if be_trigger and not current_trade.get('be_locked') and risk_per_share > 0:
                    if direction == 'LONG' and float(row['High']) >= be_trigger:
                        current_trade['sl'] = entry  # breakeven
                        current_trade['be_locked'] = True
                    elif direction == 'SHORT' and float(row['Low']) <= be_trigger:
                        current_trade['sl'] = entry
                        current_trade['be_locked'] = True

                close_trade = False
                pnl_amt = 0
                exit_price = 0

                # Partial close hit check (D stratejisi)
                if partial_tp and not partial_hit:
                    if direction == 'LONG' and float(row['High']) >= partial_tp:
                        # %50 kapat, BE'ye don
                        half_reward = current_trade['reward'] * 0.5
                        pnl_amt = half_reward
                        current_trade['risk'] = current_trade['risk'] * 0.5
                        current_trade['reward'] = current_trade['reward'] * 0.5
                        current_trade['sl'] = entry  # BE'ye cek
                        current_trade['partial_hit'] = True
                        self.rm.register_trade_result(pnl_amt)
                        # Kismi kapanisi kaydet ama pozisyon acik kalmaya devam eder
                        self.trades.append({
                            'date': t.strftime('%Y-%m-%d %H:%M') + ' [PARTIAL]',
                            'ticker': self.ticker,
                            'dir': direction,
                            'entry': f"{entry:.4f}",
                            'exit': f"{partial_tp:.4f}",
                            'pnl_pct': (pnl_amt / current_trade['entry_bal']) * 100,
                            'rr': '1:2',
                            'rr_achieved': 2.0,
                            'actual_r': 2.0,
                            'ai': 'ONAYLA',
                            'reasons': ', '.join(current_trade['reasons']),
                            'setup_type': current_trade['setup_type'],
                            'kill_zone': current_trade['kill_zone'],
                            'regime': current_trade.get('regime', 'NEUTRAL'),
                            'strategy': self.trail_strategy
                        })
                    elif direction == 'SHORT' and float(row['Low']) <= partial_tp:
                        half_reward = current_trade['reward'] * 0.5
                        pnl_amt = half_reward
                        current_trade['risk'] = current_trade['risk'] * 0.5
                        current_trade['reward'] = current_trade['reward'] * 0.5
                        current_trade['sl'] = entry
                        current_trade['partial_hit'] = True
                        self.rm.register_trade_result(pnl_amt)
                        self.trades.append({
                            'date': t.strftime('%Y-%m-%d %H:%M') + ' [PARTIAL]',
                            'ticker': self.ticker,
                            'dir': direction,
                            'entry': f"{entry:.4f}",
                            'exit': f"{partial_tp:.4f}",
                            'pnl_pct': (pnl_amt / current_trade['entry_bal']) * 100,
                            'rr': '1:2',
                            'rr_achieved': 2.0,
                            'actual_r': 2.0,
                            'ai': 'ONAYLA',
                            'reasons': ', '.join(current_trade['reasons']),
                            'setup_type': current_trade['setup_type'],
                            'kill_zone': current_trade['kill_zone'],
                            'regime': current_trade.get('regime', 'NEUTRAL'),
                            'strategy': self.trail_strategy
                        })

                if current_trade['direction'] == 'LONG':
                    if row['Low'] <= current_trade['sl']:
                        pnl_amt = (current_trade['sl'] - entry) / risk_per_share * current_trade['risk'] if risk_per_share > 0 else -current_trade['risk']
                        exit_price = current_trade['sl']
                        close_trade = True
                    elif row['High'] >= current_trade['tp']:
                        pnl_amt = current_trade['reward']
                        exit_price = current_trade['tp']
                        close_trade = True
                else:
                    if row['High'] >= current_trade['sl']:
                        pnl_amt = (entry - current_trade['sl']) / risk_per_share * current_trade['risk'] if risk_per_share > 0 else -current_trade['risk']
                        exit_price = current_trade['sl']
                        close_trade = True
                    elif row['Low'] <= current_trade['tp']:
                        pnl_amt = current_trade['reward']
                        exit_price = current_trade['tp']
                        close_trade = True
                        
                if close_trade:
                    rr_achieved = current_trade['max_fav_excursion'] / risk_per_share if risk_per_share > 0 else 0
                    actual_r = pnl_amt / current_trade['risk'] if current_trade['risk'] > 0 else 0
                    
                    self.rm.register_trade_result(pnl_amt)
                    pnl_pct = (pnl_amt / current_trade['entry_bal']) * 100
                    self.trades.append({
                        'date': t.strftime('%Y-%m-%d %H:%M'),
                        'ticker': self.ticker,
                        'dir': current_trade['direction'],
                        'entry': f"{current_trade['entry']:.4f}",
                        'exit': f"{exit_price:.4f}",
                        'pnl_pct': pnl_pct,
                        'rr': f"1:{actual_r:.1f}" if pnl_amt > 0 else '0',
                        'rr_achieved': float(rr_achieved),
                        'actual_r': float(actual_r),
                        'ai': 'ONAYLA' if current_trade['score'] >= 70 else 'GECTI',
                        'reasons': ', '.join(current_trade['reasons']),
                        'setup_type': current_trade['setup_type'],
                        'kill_zone': current_trade['kill_zone'],
                        'regime': current_trade.get('regime', 'NEUTRAL'),
                        'strategy': self.trail_strategy
                    })
                    self.equity_curve['labels'].append(t.strftime('%m-%d %H:%M'))
                    self.equity_curve['data'].append(self.rm.balance)
                    current_trade = None
                continue
            
            # --- CONFIRMATION CANDLE KONTROL ---
            if pending_signal:
                # Bir onceki mumda sinyal cikmisti, bu mum confirmation
                p = pending_signal
                confirmed = False
                if p['direction'] == 'LONG':
                    confirmed = row['Close'] > row['Open']  # Yesil mum
                    entry = float(row['Close'])
                else:
                    confirmed = row['Close'] < row['Open']  # Kirmizi mum
                    entry = float(row['Close'])
                
                if confirmed:
                    atr = float(row.get('ATR_14', entry * 0.005))
                    if pd.isna(atr): atr = entry * 0.005
                    
                    regime_risk = regime_rules.get('risk', self.rm.get_risk_pct())
                    risk = self.rm.balance * min(regime_risk, self.rm.get_risk_pct())
                    
                    # Strateji fonksiyonu ile SL/TP/be_trigger/partial_tp hesapla
                    sl, tp, be_trigger, partial_tp = self.trail_fn(entry, atr, p['direction'])
                    rr_ratio = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 3.0
                    reward = risk * rr_ratio
                    
                    current_trade = {
                        'direction': p['direction'],
                        'entry': entry,
                        'sl': sl,
                        'original_sl': sl,
                        'tp': tp,
                        'be_trigger': be_trigger,
                        'partial_tp': partial_tp,
                        'partial_hit': False,
                        'be_locked': False,
                        'risk': risk,
                        'reward': reward,
                        'entry_bal': self.rm.balance,
                        'score': p['score'],
                        'reasons': p['reasons'],
                        'setup_type': p['setup_type'],
                        'kill_zone': p['kill_zone'],
                        'regime': last_regime,
                        'max_fav_excursion': 0.0
                    }
                
                pending_signal = None
                continue
            
            # --- REGIME FILTRESI ---
            if not regime_rules.get('trade', True):
                continue
                
            can_trade, msg = self.rm.can_trade_today()
            if not can_trade: continue
            
            kz = is_kill_zone(t)
            if not kz: continue
            
            # Match Bias & Struct with STRICT LOOK-AHEAD PREVENTION
            # A 1-hour candle starting at 09:30 finishes at 10:30. At 10:05, the 09:30 candle isn't closed yet!
            b_match = self.df_bias[self.df_bias.index + pd.Timedelta(hours=1) <= t]
            s_match = self.df_struct[self.df_struct.index + pd.Timedelta(minutes=15) <= t]
            if len(b_match) < 2 or len(s_match) < 2: continue
            
            b_row = b_match.iloc[-1]
            s_row = s_match.iloc[-1]
            
            bias = "BULLISH" if b_row['Close'] > b_row.get('EMA_200', 0) else "BEARISH"
            
            # Performance Optimization: Use truncated slices instead of growing O(N^2) dataframes
            slice_length = 300 
            sig_up_to_amd = self.df_signal.iloc[max(0, i-slice_length):i+1]
            try:
                amd_res = detect_amd_phases_v2(sig_up_to_amd)
            except:
                amd_res = None
            amd_bull = amd_res if amd_res and amd_res['direction'] == 'LONG' else None
            amd_bear = amd_res if amd_res and amd_res['direction'] == 'SHORT' else None
            
            # Turtle Soup v2 (lookback 20 requires at least 40 bars for safety)
            sig_up_to_ts = self.df_signal.iloc[max(0, i-60):i+1]
            ts_res = find_turtle_soup_v2(sig_up_to_ts, lookback=20)
            valid_ts_index = len(sig_up_to_ts) - 3
            ts_bull_list = [x for x in ts_res if x['direction'] == 'LONG' and x['index'] >= valid_ts_index]
            ts_bear_list = [x for x in ts_res if x['direction'] == 'SHORT' and x['index'] >= valid_ts_index]
            ts_bull = ts_bull_list[-1] if ts_bull_list else None
            ts_bear = ts_bear_list[-1] if ts_bear_list else None
            
            # OB v2
            sig_up_to_ob = self.df_signal.iloc[max(0, i-50):i+1]
            try:
                ob_res = find_order_blocks_v2(sig_up_to_ob, lookback=min(len(sig_up_to_ob)-1, 50))
            except:
                ob_res = []
            ob_bull_list = [x for x in ob_res if x['type'] == 'BULLISH_OB']
            ob_bear_list = [x for x in ob_res if x['type'] == 'BEARISH_OB']
            ob_bull = ob_bull_list[-1] if ob_bull_list else None
            ob_bear = ob_bear_list[-1] if ob_bear_list else None
            
            # IPDA: check against daily data up to this bar
            ipda_hit = None
            if hasattr(self, 'df_daily') and not self.df_daily.empty:
                t_naive = pd.Timestamp(t).tz_localize(None) if pd.Timestamp(t).tzinfo else pd.Timestamp(t)
                daily_up_to = self.df_daily[self.df_daily.index <= t_naive]
                sig_up_to_ipda = self.df_signal.iloc[max(0, i-60):i+1]
                ipda_hit = find_ipda_v2(daily_up_to, sig_up_to_ipda)
            ipda_bull = ipda_hit if ipda_hit and ipda_hit['direction'] == 'LONG' else None
            ipda_bear = ipda_hit if ipda_hit and ipda_hit['direction'] == 'SHORT' else None

            # SMT: compare last 10 bars of signal TF with correlated asset
            smt_bull = None
            smt_bear = None
            if hasattr(self, 'df_smt') and not self.df_smt.empty:
                smt_up_to = self.df_smt[self.df_smt.index <= t].tail(10)
                sig_up_to_smt = self.df_signal.iloc[max(0, i-10):i+1]
                if len(smt_up_to) >= 5 and len(sig_up_to_smt) >= 5:
                    smt_result = find_smt_divergence(sig_up_to_smt, smt_up_to, self.ticker, 'QQQ')
                    if smt_result:
                        if smt_result['direction'] == 'BULLISH': smt_bull = smt_result
                        if smt_result['direction'] == 'BEARISH': smt_bear = smt_result

            # Score
            b_sc, b_rs, _b_pos = calculate_signal_score(
                bias=bias,
                bos=row.get('BOS_Bull', False) or s_row.get('BOS_Bull', False),
                ote=row.get('OTE_Bull', False),
                asr=row.get('ASR_Break_Bull', False),
                ifvg=row.get('iFVG_Bull', False),
                breaker=row.get('Breaker_Bull', False),
                kill_zone=True,
                direction='BULLISH',
                turtle_soup_v2=ts_bull,
                amd_v2=amd_bull,
                ipda_v2=ipda_bull,
                smt_v2=smt_bull,
                active_ob_v2=ob_bull,
                current_fvg=row.get('FVG_Bull', False)
            )

            s_sc, s_rs, _s_pos = calculate_signal_score(
                bias=bias,
                bos=row.get('BOS_Bear', False) or s_row.get('BOS_Bear', False),
                ote=row.get('OTE_Bear', False),
                asr=row.get('ASR_Break_Bear', False),
                ifvg=row.get('iFVG_Bear', False),
                breaker=row.get('Breaker_Bear', False),
                kill_zone=True,
                direction='BEARISH',
                turtle_soup_v2=ts_bear,
                amd_v2=amd_bear,
                ipda_v2=ipda_bear,
                smt_v2=smt_bear,
                active_ob_v2=ob_bear,
                current_fvg=row.get('FVG_Bear', False)
            )
            
            direction = None
            score = 0
            reasons = []
            setup_type = "Normal"
            min_score = regime_rules.get('min_score', 50)
            
            # Silver Bullet Check
            is_sb_time = False
            try:
                est_time = t.tz_convert('America/New_York')
                if est_time.hour == 10 or (est_time.hour == 9 and est_time.minute >= 50):
                    is_sb_time = True
            except:
                pass
                
            sb_direction = None
            if is_sb_time:
                body = abs(row['Close'] - row['Open'])
                atr_val = row.get('ATR_14', 0)
                displacement = body > (atr_val * 1.5) if atr_val > 0 else False
                
                if row.get('Sweep_Bull', False) and row.get('FVG_Bull', False) and displacement:
                    sb_direction = "LONG"
                elif row.get('Sweep_Bear', False) and row.get('FVG_Bear', False) and displacement:
                    sb_direction = "SHORT"
            
            if sb_direction == "LONG":
                direction = "LONG"
                score = 95
                reasons = ["SILVER_BULLET", "Liq Sweep", "FVG", "Displacement"]
                setup_type = "Silver Bullet"
            elif sb_direction == "SHORT":
                direction = "SHORT"
                score = 95
                reasons = ["SILVER_BULLET", "Liq Sweep", "FVG", "Displacement"]
                setup_type = "Silver Bullet"
            else:
                if b_sc >= min_score and b_sc >= s_sc:
                    direction = "LONG"
                    score = b_sc
                    reasons = b_rs
                elif s_sc >= min_score and s_sc > b_sc:
                    direction = "SHORT"
                    score = s_sc
                    reasons = s_rs
                    
                if direction:
                    reasons_str = ' '.join(reasons)
                    if "TURTLE SOUP" in reasons_str: setup_type = "Turtle Soup"
                    elif "SMT Div" in reasons_str: setup_type = "SMT Divergence"
                    elif "AMD Setup" in reasons_str: setup_type = "AMD Setup"
                    elif "IPDA Level" in reasons_str: setup_type = "IPDA Level"
                    elif "Liq Sweep" in reasons_str: setup_type = "Liquidity Sweep"
                    elif "FVG" in reasons_str: setup_type = "FVG"
                    elif "OB" in reasons_str: setup_type = "OB"
                    else: setup_type = "Other"
            
            # Regime yon filtresi
            only_dir = regime_rules.get('only_direction', None)
            if only_dir and direction:
                if only_dir == 'LONG' and direction == 'SHORT': direction = None
                elif only_dir == 'SHORT' and direction == 'LONG': direction = None
                
            if direction:
                # Confirmation candle: sinyali BEKLET, bir sonraki mumda onayla
                pending_signal = {
                    'direction': direction,
                    'score': score,
                    'reasons': reasons,
                    'setup_type': setup_type,
                    'kill_zone': kz if not is_sb_time else 'SILVER_BULLET'
                }
                
        rep = self.rm.get_report_data()
        daily_returns = list(self.rm.daily_pnl_history.values())
        sharpe = 0.0
        if len(daily_returns) > 1 and np.std(daily_returns) > 0:
            sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)
            
        # Compile new metrics
        count_rr_2 = len([t for t in self.trades if t.get('rr_achieved', 0) >= 2.0])
        count_rr_3 = len([t for t in self.trades if t.get('rr_achieved', 0) >= 3.0])
        avg_rr = np.mean([t.get('actual_r', 0) for t in self.trades]) if self.trades else 0
        
        setup_stats = {}
        kz_stats = {}
        for tr in self.trades:
            st = tr.get('setup_type', 'Other')
            if st not in setup_stats: setup_stats[st] = {'win':0, 'total':0}
            setup_stats[st]['total'] += 1
            if tr.get('actual_r', 0) > 0: setup_stats[st]['win'] += 1
            
            kz = tr.get('kill_zone', 'Other')
            if kz not in kz_stats: kz_stats[kz] = {'win':0, 'total':0}
            kz_stats[kz]['total'] += 1
            if tr.get('actual_r', 0) > 0: kz_stats[kz]['win'] += 1
            
        best_setup = max(setup_stats.keys(), key=lambda k: setup_stats[k]['win'] / setup_stats[k]['total'] if setup_stats[k]['total']>0 else 0) if setup_stats else "N/A"
            
        return {
            "metrics": {
                "net_pnl": rep['net_pnl'],
                "win_rate": rep['win_rate'],
                "total_trades": rep['total_trades'],
                "max_drawdown": rep['max_drawdown'],
                "best_day_pnl": rep['best_day_pnl'],
                "sharpe_ratio": float(sharpe),
                "best_setup": best_setup,
                "avg_rr_realized": float(avg_rr),
                "trades_hit_1_2": count_rr_2,
                "trades_hit_1_3": count_rr_3,
                "kz_stats": kz_stats,
                "setup_stats": setup_stats
            },
            "equity": self.equity_curve,
            "trades": sorted(self.trades, key=lambda x: x['date'], reverse=True)
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

    print(f"\n{ticker} verileri indiriliyor ({period})...")
    # Base backtest ile verileri bir kere alalim
    base_bt = ICTBacktest(ticker, period, balance)
    base_bt.load_data()
    print(f"Veri hazir. {len(base_bt.df_signal)} bar bulundu. Stratejiler test ediliyor...")

    for strategy_key, label in STRATEGY_LABELS.items():
        # Ayni veriyi paylasarak backtest objesi olustur
        bt = ICTBacktest(ticker, period, balance, trail_strategy=strategy_key)
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
    print("\n" + "="*60)
    print("EURUSD=X TESTI (30 Gn)")
    print("="*60)
    run_strategy_comparison('EURUSD=X', '30d', 10000)
