# 龙佰集团(002601)关键指标计算

import json

# 基础数据
current_price = 16.56  # 当前股价(元)
current_market_cap = 394.4  # 当前市值(亿元)
rf = 1.77  # 十年期国债收益率(%)

# 2025年财务数据(单位:亿元)
revenue_2025 = 259.88
net_profit_2025 = 12.45  # 归母净利润
adjusted_net_profit_2025 = 11.70  # 扣非净利润
ocf_2025 = 39.66  # 经营现金流
fcf_2025 = 37.20  # 自由现金流
total_assets_2025 = 644.25
shareholders_equity_2025 = 273.52
cash_2025 = 91.27  # 现金及等价物
long_term_debt_2025 = 123.12  # 长期借款
roe_2025 = 5.47  # ROE(%)

# 股息数据
dividend_yield_ttm = 3.354  # 股息率TTM(%)
dividend_2025 = 14.23  # 2025年分红总额(亿元,包括两次分红)

# 计算关键指标
# 1. 广义净现金
broad_cash = cash_2025  # 广义现金(假设无短期投资)
interest_bearing_debt = long_term_debt_2025  # 有息负债(简化,实际应包括短期借款)
broad_net_cash = broad_cash - interest_bearing_debt

# 2. 支付率
payout_ratio = (dividend_2025 / net_profit_2025) * 100

# 3. 门槛值(A股)
threshold = max(3.5, rf + 2)

# 4. Owner Earnings估算
owner_earnings_2025 = fcf_2025

# 5. 粗算穿透回报率
dividend_tax_rate = 0  # A股长期持有免税
repurchase_2025 = 2.336  # 亿元

rough_return = (owner_earnings_2025 * (payout_ratio/100) * (1 - dividend_tax_rate) + repurchase_2025) / current_market_cap * 100

print('='*80)
print('龙佰集团(002601)关键指标计算')
print('='*80)
print(f'当前股价: {current_price}元')
print(f'当前市值: {current_market_cap}亿元')
print(f'十年期国债收益率: {rf}%')
print(f'门槛值(A股): {threshold}%')
print()
print('2025年财务数据:')
print(f'营业收入: {revenue_2025}亿元')
print(f'归母净利润: {net_profit_2025}亿元')
print(f'扣非净利润: {adjusted_net_profit_2025}亿元')
print(f'经营现金流: {ocf_2025}亿元')
print(f'自由现金流: {fcf_2025}亿元')
print(f'ROE: {roe_2025}%')
print()
print('现金与负债:')
print(f'广义现金: {broad_cash}亿元')
print(f'有息负债: {interest_bearing_debt}亿元')
print(f'广义净现金: {broad_net_cash}亿元')
print(f'广义净现金/市值: {broad_net_cash/current_market_cap*100:.2f}%')
print()
print('分配情况:')
print(f'2025年分红总额: {dividend_2025}亿元')
print(f'支付率: {payout_ratio:.2f}%')
print(f'股息率TTM: {dividend_yield_ttm}%')
print(f'2025年回购金额: {repurchase_2025}亿元')
print()
print('回报率计算:')
print(f'Owner Earnings(使用FCF): {owner_earnings_2025}亿元')
print(f'粗算穿透回报率: {rough_return:.2f}%')
print(f'vs门槛值: {rough_return - threshold:.2f}pct')
print('='*80)

# 保存计算结果
result = {
    'current_price': current_price,
    'current_market_cap': current_market_cap,
    'rf': rf,
    'threshold': threshold,
    'revenue_2025': revenue_2025,
    'net_profit_2025': net_profit_2025,
    'adjusted_net_profit_2025': adjusted_net_profit_2025,
    'ocf_2025': ocf_2025,
    'fcf_2025': fcf_2025,
    'roe_2025': roe_2025,
    'broad_cash': broad_cash,
    'interest_bearing_debt': interest_bearing_debt,
    'broad_net_cash': broad_net_cash,
    'payout_ratio': payout_ratio,
    'dividend_yield_ttm': dividend_yield_ttm,
    'dividend_2025': dividend_2025,
    'repurchase_2025': repurchase_2025,
    'owner_earnings_2025': owner_earnings_2025,
    'rough_return': rough_return
}

with open('稳健投资策略分析报告/002601/calculation_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print('\n计算结果已保存')
