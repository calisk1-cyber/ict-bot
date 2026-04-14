class DailyRiskManager:
    def __init__(self, initial_balance=1000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        
        self.current_date = None
        self.daily_start_balance = initial_balance
        self.daily_pnl = 0
        self.daily_trades_count = 0
        
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        
        self.daily_pnl_history = {}
        self.monthly_pnl_history = {}
        self.days_limit_hit = 0
        self.limit_hit_today = False
        
        self.max_drawdown = 0.0
        self.peak_balance = initial_balance
        
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        
        # --- SABIT LIMITLER ---
        self.DAILY_LOSS_LIMIT    = -0.02   # -%2
        self.HARD_STOP           = -0.01   # -%1'de risk yariya dus
        self.MAX_DAILY_TRADES    = 250
        self.MAX_CONSECUTIVE_L   = 3       # 3 ust uste kayip -> dur
        self.MIN_RR              = 2.0     # minimum 1:2
        self.TARGET_RR           = 3.0     # hedef 1:3
        
        # Risk override from monthly performance
        self._monthly_risk_override = None

    def update_date(self, new_date):
        if self.current_date != new_date:
            if self.current_date is not None:
                dpnl = (self.balance - self.daily_start_balance) / self.daily_start_balance * 100
                self.daily_pnl_history[self.current_date] = dpnl
            
            self.current_date = new_date
            self.daily_start_balance = self.balance
            self.daily_pnl = 0
            self.daily_trades_count = 0
            self.limit_hit_today = False
            
            # Reset consecutive losses on new day so trader isn't permanently blocked
            if self.consecutive_losses >= self.MAX_CONSECUTIVE_L:
                self.consecutive_losses = 0
            
            # Monthly performance check at month boundary
            if self.current_date is not None:
                month_key = str(new_date)[:7]  # YYYY-MM
                prev_months = sorted(self.monthly_pnl_history.keys())
                if prev_months:
                    last_month = prev_months[-1]
                    if last_month != month_key:
                        prev_pnl = self.monthly_pnl_history[last_month]
                        self._monthly_risk_override = self._monthly_performance_check(prev_pnl)
                
                # Track current month cumulative
                if month_key not in self.monthly_pnl_history:
                    self.monthly_pnl_history[month_key] = 0.0

    def _monthly_performance_check(self, monthly_pnl_pct):
        """Onceki ayin performansina gore bu ayin risk carpanini belirle."""
        if monthly_pnl_pct < -5.0:
            return 0.005   # onceki ay -%5'ten kotu -> risk yariya
        elif monthly_pnl_pct > 5.0:
            return 0.015   # onceki ay +%5'ten iyi -> risk %1.5'e cik
        else:
            return None    # normal, override yok

    def get_risk_pct(self):
        """Dinamik pozisyon boyutu."""
        daily_loss_pct = self.daily_pnl / self.daily_start_balance if self.daily_start_balance > 0 else 0
        
        # Kademeli risk azaltma
        if daily_loss_pct <= -0.015:
            return 0.0025  # -%1.5 -> micro lot
        elif daily_loss_pct <= -0.01:
            return 0.005   # -%1 -> riski yariya dus
        elif self.consecutive_losses >= 3:
            return 0       # 3 ust uste -> dur
        elif self.consecutive_losses >= 2:
            return 0.005   # 2 ust uste kayip -> kucul
        elif self.consecutive_wins >= 3:
            return min(0.015, self._monthly_risk_override or 0.015)  # 3 ust uste kazanc -> buyut
        
        # Monthly override varsa onu kullan
        if self._monthly_risk_override is not None:
            return self._monthly_risk_override
        
        return 0.01  # normal %1

    def can_trade_today(self):
        daily_loss_pct = self.daily_pnl / self.daily_start_balance if self.daily_start_balance > 0 else 0
        
        # HARD STOP: Gunluk limit -%2 asildi
        if daily_loss_pct <= self.DAILY_LOSS_LIMIT:
            self._mark_limit_hit()
            return False, "Gunluk limit -%2 asildi"
        
        # 3 ust uste kayip, bugun dur
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_L:
            self._mark_limit_hit()
            return False, "3 ust uste kayip, bugun dur"
        
        # Gunluk max islem doldu
        if self.daily_trades_count >= self.MAX_DAILY_TRADES:
            self._mark_limit_hit()
            return False, f"Gunluk {self.MAX_DAILY_TRADES} islem doldu"
        
        return True, "Onaylandi"
        
    def _mark_limit_hit(self):
        if not self.limit_hit_today:
            self.days_limit_hit += 1
            self.limit_hit_today = True

    def register_trade_result(self, pnl_amount):
        self.balance += pnl_amount
        self.daily_pnl += pnl_amount
        self.daily_trades_count += 1
        self.total_trades += 1
        
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
            
        drawdown = (self.peak_balance - self.balance) / self.peak_balance * 100
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
            
        won = pnl_amount > 0
        if won:
            self.wins += 1
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.losses += 1
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        
        # Update monthly tracking
        if self.current_date is not None:
            month_key = str(self.current_date)[:7]
            pnl_pct = (pnl_amount / self.daily_start_balance) * 100 if self.daily_start_balance > 0 else 0
            if month_key in self.monthly_pnl_history:
                self.monthly_pnl_history[month_key] += pnl_pct
            else:
                self.monthly_pnl_history[month_key] = pnl_pct

    def get_report_data(self):
        # Force save last day
        if self.current_date is not None and self.current_date not in self.daily_pnl_history:
            dpnl = (self.balance - self.daily_start_balance) / self.daily_start_balance * 100
            self.daily_pnl_history[self.current_date] = dpnl

        best_day = None
        best_day_pnl = -999
        worst_day = None
        worst_day_pnl = 999
        
        active_days = len(self.daily_pnl_history)
        avg_trades_per_day = self.total_trades / active_days if active_days > 0 else 0
        
        for d, pnl in self.daily_pnl_history.items():
            if pnl > best_day_pnl:
                best_day_pnl = pnl
                best_day = d
            if pnl < worst_day_pnl:
                worst_day_pnl = pnl
                worst_day = d
                
        win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0
        net_pnl = (self.balance - self.initial_balance) / self.initial_balance * 100
        
        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.balance,
            "net_pnl": net_pnl,
            "total_trades": self.total_trades,
            "avg_trades_day": avg_trades_per_day,
            "win_rate": win_rate,
            "max_drawdown": self.max_drawdown,
            "best_day_pnl": best_day_pnl,
            "best_day_date": best_day,
            "worst_day_pnl": worst_day_pnl,
            "worst_day_date": worst_day,
            "days_limit_hit": self.days_limit_hit,
            "monthly_pnl": self.monthly_pnl_history
        }
