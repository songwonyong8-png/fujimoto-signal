"""Offline unit tests for F v4 reverse exit order, timing and accounting."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import backtest_f_v4 as f


class ReverseExitTests(unittest.TestCase):
    def market(self, n=260, price=100.):
        dates=pd.date_range('2021-01-01',periods=n,freq='B')
        p=pd.DataFrame({'open':np.full(n,price),'close':np.full(n,price),
                        'high':np.full(n,price+2),'low':np.full(n,price-2),
                        'volume':np.full(n,1000.)},index=dates)
        sig=pd.DataFrame(False,index=dates,
                         columns=['stage1','stage2','cloud','cloud_vp',
                                  'macd_death','cloud_breakdown','rsi_failure'])
        sig['macd_bullish']=True
        return p,sig

    def runit(self,p,sig,variant='F4_cloud_reverse',end=None):
        a,t,orders=f.run_reverse_variant(p,sig,'test',p.index[0],
                                          p.index[-1] if end is None else p.index[end],
                                          'SYNTH',variant)
        return a,t,orders

    def filled_three(self,sig):
        sig.iloc[90,sig.columns.get_loc('stage1')]=True
        sig.iloc[93,sig.columns.get_loc('stage2')]=True
        sig.iloc[99,sig.columns.get_loc('cloud')]=True
        sig.iloc[99,sig.columns.get_loc('cloud_vp')]=True

    def test_stage_weights_exact_and_no_same_bar_fill(self):
        p,s=self.market();self.filled_three(s)
        a,t,o=self.runit(p,s)
        buys=[x for x in o if x['side']=='BUY']
        self.assertEqual([x['stage'] for x in buys],[1,2,3])
        self.assertEqual([x['date'] for x in buys],
                         [str(p.index[k].date()) for k in (91,94,100)])
        self.assertTrue(np.allclose([x['initial_capital_weight'] for x in buys],
                                    [1/9,2/9,6/9]))
        self.assertAlmostEqual(buys[-1]['cash_after'],0.,places=10)

    def test_cloud_loss_sells_only_6_then_macd_sells_remaining_3(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[105],'cloud_breakdown']=True
        s.loc[p.index[110],'macd_death']=True
        a,t,o=self.runit(p,s)
        sells=[x for x in o if x['side']=='SELL']
        self.assertEqual([x['stage'] for x in sells],[3,2,1])
        self.assertEqual([x['date'] for x in sells],
                         [str(p.index[k].date()) for k in (106,111,111)])
        self.assertEqual([x['reason'] for x in sells],
                         ['CLOUD_BOTTOM_BREAK','MACD_DEAD_CROSS','MACD_DEAD_CROSS'])
        self.assertEqual(t[0]['status'],'CLOSED')
        self.assertEqual(a['completed_trades'],1)
        self.assertEqual(a['stage3_sells'],1)

    def test_macd_death_first_sells_3_2_1_in_one_open(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[105],'macd_death']=True
        a,t,o=self.runit(p,s)
        sells=[x for x in o if x['side']=='SELL']
        self.assertEqual([x['stage'] for x in sells],[3,2,1])
        self.assertEqual(len({x['date'] for x in sells}),1)
        self.assertEqual(sells[0]['date'],str(p.index[106].date()))
        self.assertEqual(t[0]['status'],'CLOSED')

    def test_stage_1_only_rsi_failure_closes_1(self):
        p,s=self.market();s.loc[p.index[90],'stage1']=True
        s.loc[p.index[105],'rsi_failure']=True
        a,t,o=self.runit(p,s)
        self.assertEqual([(x['side'],x['stage']) for x in o],
                         [('BUY',1),('SELL',1)])
        self.assertEqual(t[0]['status'],'CLOSED')

    def test_stage_2_macd_death_liquidates_both(self):
        p,s=self.market();s.loc[p.index[90],'stage1']=True
        s.loc[p.index[93],'stage2']=True
        s.loc[p.index[105],'macd_death']=True
        a,t,o=self.runit(p,s)
        self.assertEqual([x['stage'] for x in o if x['side']=='SELL'],[2,1])
        self.assertEqual(a['stage3_sells'],0)

    def test_rsi_failure_with_all_lots_liquidates_3_2_1(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[105],'rsi_failure']=True
        a,t,o=self.runit(p,s)
        self.assertEqual([x['stage'] for x in o if x['side']=='SELL'],[3,2,1])

    def test_no_hardcoded_40_day_exit_and_open_is_not_closed_win(self):
        p,s=self.market();self.filled_three(s)
        a,t,o=self.runit(p,s)
        self.assertEqual(len([x for x in o if x['side']=='SELL']),0)
        self.assertEqual(t[0]['status'],'OPEN_MTM')
        self.assertGreater(t[0]['calendar_bars_held'],150)
        self.assertEqual(a['completed_trades'],0)
        self.assertEqual(a['open_trades'],1)
        self.assertIsNone(a['winning_fraction'])

    def test_cloud_sell_does_not_allow_rebuy_in_same_campaign(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[105],'cloud_breakdown']=True
        s.loc[p.index[120],'cloud']=True
        a,t,o=self.runit(p,s)
        self.assertEqual(a['stage3_buys'],1)
        self.assertEqual(a['stage3_sells'],1)
        self.assertEqual(t[0]['status'],'OPEN_MTM')

    def test_stage3_entry_unchanged_even_if_current_macd_flag_is_false(self):
        # No additional entry filter vs v3: only a NEW dead cross exits.
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[99],'macd_bullish']=False
        a,t,o=self.runit(p,s)
        self.assertEqual([x['stage'] for x in o if x['side']=='BUY'],[1,2,3])

    def test_cloud_vp_ignores_cloud_without_vp_confirmation(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[99],'cloud_vp']=False
        a,t,o=self.runit(p,s,variant='F4_cloud_vp_reverse')
        self.assertEqual([x['stage'] for x in o if x['side']=='BUY'],[1,2])

    def test_trading_at_next_open_and_gap_is_not_filled_at_signal_close(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[105],'cloud_breakdown']=True
        p.loc[p.index[106],'open']=82.
        a,t,o=self.runit(p,s)
        stage3_sale=[x for x in o if x['side']=='SELL' and x['stage']==3][0]
        self.assertEqual(stage3_sale['price'],82.)
        self.assertEqual(stage3_sale['date'],str(p.index[106].date()))

    def test_no_buy_on_last_signal_day(self):
        p,s=self.market(n=103)
        s.loc[p.index[-1],'stage1']=True
        a,t,o=self.runit(p,s)
        self.assertEqual(len(o),0)
        self.assertEqual(a['cumulative_return'],0.)

    def test_short_history_entry_not_blocked_by_fixed_40_day_window(self):
        p,s=self.market(n=102)
        s.loc[p.index[82],'stage1']=True
        a,t,o=self.runit(p,s)
        self.assertEqual(len(o),1)
        self.assertEqual(t[0]['status'],'OPEN_MTM')

    def test_macd_stage2_must_follow_rsi_signal_and_fit_20_day_limit(self):
        p,s=self.market()
        s.loc[p.index[89],'stage2']=True
        s.loc[p.index[90],'stage1']=True
        s.loc[p.index[112],'stage2']=True
        a,t,o=self.runit(p,s)
        self.assertEqual([x['stage'] for x in o if x['side']=='BUY'],[1])

    def test_risk_exit_takes_priority_over_stage3_entry(self):
        p,s=self.market();self.filled_three(s)
        s.loc[p.index[99],'macd_death']=True
        a,t,o=self.runit(p,s)
        self.assertEqual([x['stage'] for x in o if x['side']=='BUY'],[1,2])
        self.assertEqual([x['stage'] for x in o if x['side']=='SELL'],[2,1])

    def test_no_future_indicator_values(self):
        n=250
        rng=np.random.default_rng(7)
        close=100+np.cumsum(rng.normal(size=n))
        idx=pd.date_range('2021-01-01',periods=n,freq='B')
        p=pd.DataFrame({'open':close,'close':close,'high':close+1,'low':close-1,
                        'volume':np.full(n,1000.)},index=idx)
        a=f.extended_indicators(p)
        q=p.copy();q.iloc[-1,q.columns.get_loc('close')]=2000.
        b=f.extended_indicators(q)
        pd.testing.assert_frame_equal(a.iloc[:-1],b.iloc[:-1])

    def test_frozen_top50_still_does_not_use_marketcap_api(self):
        with mock.patch.object(f.v3.yf,'Ticker',side_effect=AssertionError('metadata request')):
            rows,_=f.v3.top50_candidates()
        self.assertEqual(len(rows),50)


if __name__=='__main__':
    unittest.main()
