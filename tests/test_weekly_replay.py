"""Synthetic mechanics tests only; none are historical performance results."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import weekly_replay as r

CFG = dict(initial_cash_cny=100000, minimum_commission_cny=5, commission_rate=.0003,
           transfer_fee_rate=.00001, sell_stamp_rate=.0005, slippage_rate=.001,
           lot_size=100, participation_limit=.005, dividend_tax_haircut=0)

def bar(p=10, **kw):
    b=dict(open=p, high=p*1.1, low=p*.9, close=p, upper_limit=p*1.1,
           lower_limit=p*.9, suspended=False, volume_shares=1000000)
    b.update(kw); return b

def packet():
    def s(state): return dict(state=state, evidence_ids=['old'])
    return {'cutoff':'2023-11-05T23:59:00+08:00', 'industry':s('improving'),
            'companies':{k:dict(business=s('improving'), valuation=s('attractive'),
                               price_volume=s('neutral')) for k in r.SYMBOLS}}

def evidence():
    return [dict(evidence_id='old', status='verified', source_id='S1',
                 available_at='2023-11-03T18:00:00+08:00')]

class WeeklyReplayTests(unittest.TestCase):
    def test_future_evidence_filtered(self):
        rows=evidence()+[dict(evidence_id='future',status='verified',source_id='S2',available_at='2024-03-29T00:00:00+08:00')]
        self.assertEqual(len(r.eligible_evidence(rows,packet()['cutoff'])),1)
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(r.DataGap): r.aware('2023-11-05')
    def test_unknown_signal_does_not_mean_cash(self):
        p=packet();p['industry']['state']='unknown'
        with self.assertRaises(r.DataGap):r.recommend(p,evidence())
    def test_future_reference_blocked(self):
        p=packet();p['industry']['evidence_ids']=['future']
        with self.assertRaises(r.DataGap):r.recommend(p,evidence())
    def test_positive_state_allocates_eighty_percent(self):
        self.assertAlmostEqual(sum(r.recommend(packet(),evidence()).values()),.8)
    def test_single_company_impairment_can_exit(self):
        p=packet();p['companies'][r.SYMBOLS[0]]['business']['state']='impaired'
        w=r.recommend(p,evidence());self.assertEqual(w[r.SYMBOLS[0]],0);self.assertEqual(w[r.SYMBOLS[1]],.4)
    def test_industry_deterioration_exits_without_waiting_every_signal(self):
        p=packet();p['industry']['state']='deteriorating'
        self.assertEqual(sum(r.recommend(p,evidence()).values()),0)
    def test_adverse_price_volume_only_caps_position(self):
        p=packet();p['companies'][r.SYMBOLS[0]]['price_volume']['state']='adverse'
        self.assertEqual(r.recommend(p,evidence())[r.SYMBOLS[0]],.2)
    def test_changing_future_evidence_does_not_change_weights(self):
        rows=evidence()+[dict(evidence_id='later',status='verified',source_id='F',available_at='2024-01-01T00:00:00+08:00')]
        self.assertEqual(r.recommend(packet(),evidence()),r.recommend(packet(),rows))
    def test_fees(self):
        self.assertEqual(r.fees(1000,'buy',CFG),5.01)
        self.assertEqual(r.fees(1000,'sell',CFG),5.51)
    def test_buy_rounding_and_cash_constraint(self):
        cash,h,t=r.rebalance('2023-11-06',100000,{}, {'X':1}, {'X':bar()}, {'X':[1e8]*20}, CFG)
        self.assertGreaterEqual(cash,0);self.assertEqual(h['X']%100,0);self.assertLess(h['X'],10000)
    def test_sell_charges_stamp(self):
        cash,h,t=r.rebalance('2023-11-06',0,{'X':1000},{'X':0},{'X':bar()},{'X':[1e6]*20},CFG)
        self.assertEqual(h['X'],0);self.assertLess(cash,9990)
    def test_open_limit_blocks_buy(self):
        cash,h,t=r.rebalance('2023-11-06',100000,{}, {'X':.4},{'X':bar(11,upper_limit=11)}, {'X':[1e6]*20}, CFG)
        self.assertFalse(h);self.assertEqual(t[0]['status'],'blocked_at_open')
    def test_suspension_blocks_sell(self):
        cash,h,t=r.rebalance('2023-11-06',0,{'X':1000},{'X':0},{'X':bar(suspended=True)},{'X':[1e6]*20},CFG)
        self.assertEqual(h['X'],1000)
    def test_no_liquidity_window_fails(self):
        with self.assertRaises(r.DataGap):r.rebalance('2023-11-06',100000,{}, {'X':.4},{'X':bar()},{'X':[1e6]*19},CFG)
    def test_capacity_uses_previous_volume(self):
        _,h,_=r.rebalance('2023-11-06',100000,{}, {'X':.4},{'X':bar(volume_shares=1e10)},{'X':[100000]*20},CFG)
        self.assertEqual(h['X'],500)
    def test_dividend_accrues_then_pays_without_double_count(self):
        cfg=dict(CFG,slippage_rate=0,commission_rate=0,minimum_commission_cny=0,transfer_fee_rate=0,sell_stamp_rate=0)
        days=['2023-11-06','2023-11-07','2023-11-08']
        prices={(d,'X'):bar(10 if i==0 else 9) for i,d in enumerate(days)}
        dec={days[0]:dict(cutoff='2023-11-05T23:59:00+08:00',weights={'X':.1})}
        a=[dict(type='cash_dividend',symbol='X',record_date=days[0],ex_date=days[1],pay_date=days[2],cash_per_share=1)]
        out=r.simulate(days,prices,dec,a,{'X':[1e6]*20},cfg)
        self.assertEqual([x['nav'] for x in out['curve']],[100000]*3)
        self.assertEqual(out['curve'][1]['receivables'],1000)
        self.assertEqual(out['curve'][2]['receivables'],0)
    def test_unsupported_action_rejected(self):
        with self.assertRaises(r.DataGap):r.simulate(['2023-11-06'],{}, {},[{'type':'split'}],{},CFG)
    def test_future_decision_rejected(self):
        with self.assertRaises(r.DataGap):r.simulate(['2023-11-06'],{('2023-11-06','X'):bar()},
            {'2023-11-06':dict(cutoff='2023-11-06T10:00:00+08:00',weights={'X':.1})},[],{'X':[1e6]*20},CFG)
    def test_missing_bar_rejected(self):
        with self.assertRaises(r.DataGap):r.simulate(['2023-11-06'],{}, {},[],{'X':[1e6]*20},CFG)
    def test_missing_nav_not_zero_return(self):
        with self.assertRaises(r.DataGap):r.metrics([],100000)
    def test_max_drawdown(self):
        m=r.metrics([110,88,120],100)
        self.assertAlmostEqual(m['max_drawdown_pct'],-20);self.assertAlmostEqual(m['return_pct'],20)
    def test_mixed_return_basis_rejected(self):
        with self.assertRaises(r.DataGap):r.compare([110],[105],100,100,False)
    def test_excess_percentage_points_not_relative_return(self):
        m=r.compare([110],[105],100,100,True)
        self.assertAlmostEqual(m['excess_return_pp'],5);self.assertAlmostEqual(m['relative_wealth_pct'],100*(1.1/1.05-1))
    def test_actual_repository_remains_blocked(self):
        m=r.audit_readiness();self.assertEqual(m['status'],'BLOCKED');self.assertIsNone(m['performance'])

if __name__=='__main__':unittest.main()
