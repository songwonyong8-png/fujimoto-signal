"""Offline deterministic v5 tests. No Yahoo downloads or network needed."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import backtest_f_v5 as f


class F5IndependentLotExitTests(unittest.TestCase):
    def market(self, n=260, price=100.):
        idx = pd.date_range('2021-01-01', periods=n, freq='B')
        prices = pd.DataFrame({
            'open': np.full(n, price), 'close': np.full(n, price),
            'high': np.full(n, price+2), 'low': np.full(n, price-2),
            'volume': np.full(n, 1000.)}, index=idx)
        signals = pd.DataFrame(False, index=idx, columns=[
            'stage1', 'stage2', 'cloud', 'cloud_vp', 'macd_death',
            'cloud_breakdown', 'cloud_top_breakdown', 'rsi_failure'])
        return prices, signals

    def complete_entries(self, s):
        s.loc[s.index[90], 'stage1'] = True
        s.loc[s.index[93], 'stage2'] = True
        s.loc[s.index[99], ['cloud', 'cloud_vp']] = True

    def runit(self, p, s, model='A', profile='cloud', first=None, last=None):
        return f.run_signal_lot_variant(
            p, s, 'synthetic', p.index[0] if first is None else first,
            p.index[-1] if last is None else last, 'MOCK', model, profile)

    def orders(self, orders, side):
        return [x for x in orders if x['side'] == side]

    def test_all_entry_weights_and_dates_unchanged(self):
        p, s = self.market(); self.complete_entries(s)
        _, _, orders = self.runit(p, s)
        b = self.orders(orders, 'BUY')
        self.assertEqual([x['stage'] for x in b], [1,2,3])
        self.assertEqual([x['date'] for x in b],
                         [str(p.index[i].date()) for i in (91, 94, 100)])
        np.testing.assert_allclose([x['initial_capital_weight'] for x in b], [1/9,2/9,6/9])
        self.assertAlmostEqual(b[-1]['cash_after'], 0., places=9)

    def test_v5_a_each_signal_sells_only_matching_lot(self):
        p, s = self.market(); self.complete_entries(s)
        s.loc[p.index[105], 'macd_death'] = True
        s.loc[p.index[110], 'rsi_failure'] = True
        s.loc[p.index[115], 'cloud_breakdown'] = True
        a, trades, fills = self.runit(p, s)
        sells = self.orders(fills, 'SELL')
        self.assertEqual([x['stage'] for x in sells], [2,1,3])
        self.assertEqual([x['date'] for x in sells],
                         [str(p.index[i].date()) for i in (106,111,116)])
        self.assertEqual(a['completed_trades'],1)
        self.assertEqual(trades[0]['status'],'CLOSED')

    def test_v5_a_macd_does_not_sell_3_or_1(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'macd_death']=True
        a,trades,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[2])
        self.assertEqual(trades[0]['status'],'OPEN_MTM')
        self.assertEqual(a['stage1_sells'],0)
        self.assertEqual(a['stage3_sells'],0)

    def test_v5_a_rsi_does_not_sell_2_or_3(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'rsi_failure']=True
        a,trades,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[1])
        self.assertEqual(a['open_trades'],1)

    def test_v5_a_cloud_bottom_only_sells_3(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'cloud_breakdown']=True
        a,_,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[3])
        self.assertEqual(a['stage2_sells'],0)

    def test_v5_b_macd_sells_3_and_2_not_1(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'macd_death']=True
        a,_,fills=self.runit(p,s,model='B')
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[3,2])
        self.assertEqual(a['stage1_sells'],0)

    def test_v5_b_rsi_sells_all_lots(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'rsi_failure']=True
        a,_,fills=self.runit(p,s,model='B')
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[3,2,1])
        self.assertEqual(a['completed_trades'],1)

    def test_v5_b_cloud_sell_only_stage3(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'cloud_breakdown']=True
        a,_,fills=self.runit(p,s,model='B')
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[3])
        self.assertEqual(a['open_trades'],1)

    def test_v5_c_cloud_top_break_sells_3_early(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'cloud_top_breakdown']=True
        a,_,fills=self.runit(p,s,model='C')
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[3])
        self.assertEqual(self.orders(fills,'SELL')[0]['reason'],'CLOUD_TOP_BREAK')
        _,_,a_fills=self.runit(p,s,model='A')
        self.assertEqual(len(self.orders(a_fills,'SELL')),0)

    def test_no_cloud_top_exit_if_only_bottom_mode(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'cloud_top_breakdown']=True
        _,_,fills=self.runit(p,s,model='B')
        self.assertFalse(self.orders(fills,'SELL'))

    def test_simultaneous_signals_independent_sells_all_lots(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],['rsi_failure','macd_death','cloud_breakdown']]=True
        a,_,fills=self.runit(p,s,model='A')
        sells=self.orders(fills,'SELL')
        self.assertEqual([x['stage'] for x in sells],[3,2,1])
        self.assertEqual(len({x['date'] for x in sells}),1)
        self.assertEqual(a['completed_trades'],1)

    def test_cloud_vp_requires_vp_confirmation(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[99],'cloud_vp']=False
        a,_,fills=self.runit(p,s,model='A',profile='cloud_vp')
        self.assertEqual([x['stage'] for x in self.orders(fills,'BUY')],[1,2])
        self.assertEqual(a['stage3_buys'],0)

    def test_exit_cannot_sell_unowned_lot(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[105],['cloud_breakdown','macd_death']]=True
        a,_,fills=self.runit(p,s)
        self.assertFalse(self.orders(fills,'SELL'))
        self.assertEqual(a['open_trades'],1)

    def test_rsi_stage1_only_can_close_by_itself(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[105],'rsi_failure']=True
        a,_,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'SELL')],[1])
        self.assertEqual(a['completed_trades'],1)

    def test_rsi_exit_prevents_later_stage2_purchase(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[92],'rsi_failure']=True
        s.loc[p.index[94],'stage2']=True
        a,_,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'BUY')],[1])
        self.assertEqual(a['stage2_buys'],0)

    def test_macd_exit_prevents_later_stage3_purchase(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[96],'macd_death']=True
        a,_,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'BUY')],[1,2])
        self.assertEqual(a['stage3_buys'],0)

    def test_never_rebuy_sold_lot_within_same_campaign(self):
        p,s=self.market(); self.complete_entries(s)
        s.loc[p.index[105],'cloud_breakdown']=True
        s.loc[p.index[120],'cloud']=True
        a,_,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'BUY')],[1,2,3])
        self.assertEqual(a['stage3_buys'],1)

    def test_no_forced_40_session_sell_and_open_not_a_win(self):
        p,s=self.market(); self.complete_entries(s)
        a,t,fills=self.runit(p,s)
        self.assertFalse(self.orders(fills,'SELL'))
        self.assertEqual(t[0]['status'],'OPEN_MTM')
        self.assertGreater(t[0]['calendar_bars_held'],150)
        self.assertEqual(a['completed_trades'],0)
        self.assertIsNone(a['winning_fraction'])

    def test_fee_per_side_math_when_closed(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[105],'rsi_failure']=True
        a,t,fills=self.runit(p,s)
        # initial budget 1/9. One buy and one sell at 100 each, fee both sides.
        expected=1-(1/9)+ (1/9)*(1-f.FEE)/(1+f.FEE)
        self.assertAlmostEqual(a['cumulative_return'],expected-1,places=10)
        self.assertAlmostEqual(t[0]['return'],expected-1,places=10)

    def test_next_open_gap_applies_to_fill_and_not_signal_close(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[105],'rsi_failure']=True
        p.loc[p.index[106],'open']=80.
        _,_,fills=self.runit(p,s)
        sale=self.orders(fills,'SELL')[0]
        self.assertAlmostEqual(sale['price'],80.)
        self.assertEqual(sale['date'],str(p.index[106].date()))

    def test_dates_limit_forward_exit_orders(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[105],'rsi_failure']=True
        a,t,fills=self.runit(p,s,last=p.index[105])
        self.assertEqual(a['open_trades'],1)
        self.assertFalse(self.orders(fills,'SELL'))

    def test_stage_2_window_20_bar_limit(self):
        p,s=self.market(); s.loc[p.index[90],'stage1']=True
        s.loc[p.index[111],'stage2']=True
        a,_,fills=self.runit(p,s)
        self.assertEqual([x['stage'] for x in self.orders(fills,'BUY')],[1])

    def test_invalid_model_and_stages_are_rejected(self):
        with self.assertRaises(ValueError):
            f.sell_stages('bad',{1},False,False,False)
        with self.assertRaises(ValueError):
            f.sell_stages('A',{1,4},False,False,False)
        with self.assertRaises(ValueError):
            f.strategy_id('A','bad')

    def test_pair_cohort_greedy_nonoverlap_and_complete_horizon(self):
        p,s=self.market(n=260)
        for k in (90,95,155,210,250):
            s.loc[p.index[k],'stage1']=True
        anchors=f.cohort_starts(s,0,len(p)-1,40)
        self.assertEqual(anchors,[90,155,210])

    def test_paired_4_models_have_identical_anchor_and_evaluation_date(self):
        p,s=self.market(n=190); self.complete_entries(s)
        s.loc[p.index[110],'macd_death']=True
        s.loc[p.index[115],'rsi_failure']=True
        s.loc[p.index[120],'cloud_breakdown']=True
        # Divergent exit prices make the paired strategy's cash flows measurable.
        p.loc[p.index[116], 'open'] = 85.
        cohort=f.paired_comparison(p,s,'synthetic',p.index[0],p.index[-1],
                                    'MOCK',horizons=(40,))
        self.assertEqual(len(cohort),2)  # cloud and cloud_vp
        self.assertEqual({x['first_signal'] for x in cohort},{str(p.index[90].date())})
        self.assertEqual({x['evaluation_date'] for x in cohort},{str(p.index[130].date())})
        # F4 exits all on MACD; A maintains lots until each separate invalidation.
        self.assertNotEqual(cohort[0]['f4_return'],cohort[0]['v5a_return'])
        self.assertAlmostEqual(cohort[0]['v5a_minus_f4'],
                               cohort[0]['v5a_return']-cohort[0]['f4_return'])

    def test_paired_masks_later_rsi_signals_to_prevent_reentry(self):
        p,s=self.market(n=180);self.complete_entries(s)
        s.loc[p.index[105],'rsi_failure']=True
        s.loc[p.index[120],'stage1']=True
        s.loc[p.index[130],'rsi_failure']=True
        pairs=f.paired_comparison(p,s,'synthetic',p.index[0],p.index[-1],
                                   'MOCK',horizons=(60,))
        self.assertEqual(len(pairs),2)
        self.assertEqual(pairs[0]['first_signal'],str(p.index[90].date()))

    def test_no_future_data_changes_indicators_past(self):
        n=310;idx=pd.date_range('2020-01-01',periods=n,freq='B')
        close=np.linspace(100,150,n)
        p=pd.DataFrame({'open':close,'high':close+2,'low':close-2,
                        'close':close,'volume':np.full(n,1000)},index=idx)
        a=f.extended_indicators(p)
        altered=p.copy();altered.iloc[-1,altered.columns.get_loc('close')]=2000
        b=f.extended_indicators(altered)
        pd.testing.assert_frame_equal(a.iloc[:-1],b.iloc[:-1])

    def test_strategy_keeps_existing_f3_top50_without_yahoo_cap_calls(self):
        with mock.patch.object(f.v3.yf,'Ticker',side_effect=AssertionError('API must not be called')):
            top,_=f.v3.top50_candidates()
        self.assertEqual(len(top),50)


if __name__ == '__main__':
    unittest.main()
