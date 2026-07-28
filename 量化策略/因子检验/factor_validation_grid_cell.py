# %% [markdown]
# # Part 3：N × 权重 联合网格搜索
#
# **前提**：在已经跑完 `factor_validation_full.ipynb` 的**同一个 kernel** 里，
# 新增一个 cell 粘贴本文件内容并执行。不要新开 notebook 上传——那样是新 kernel，
# 拿不到 combo_panels / long_only / bench_r 等变量（这正是上次失败的原因）。

# %%
GRID_N = [16, 24, 30, 40, 50]
GRID_W = [(0.5, 0.5, 'roe50/bp50'), (0.3, 0.7, 'roe30/bp70'),
          (0.2, 0.8, 'roe20/bp80'), (0.0, 1.0, 'bp100')]

grid_rows = []
for wr, wb, wname in GRID_W:
    key = wname + ' + momExcl'
    if key in combo_panels:
        panel = combo_panels[key]
    else:
        panel = build_combo(wr, wb, exclude_mom_top=0.20)
        combo_panels[key] = panel

    for n in GRID_N:
        r, tn = long_only(panel, n_hold=n, cost_rt=COST_50W)
        if len(r) < 12:
            continue
        p = perf(r, bench_r, '%s | N=%d' % (wname, n))
        p['turnover_ann'] = round(tn.mean() * 12, 2)
        grid_rows.append(p)

grid_df = pd.DataFrame(grid_rows)
grid_df = grid_df[['portfolio', 'excess_ann', 'IR', 'excess_maxdd',
                    'win_month', 'turnover_ann', 'sharpe']]
grid_df = grid_df.sort_values('IR', ascending=False)

print('=' * 90)
print('N × 权重 联合网格  (50万成本, momExcl=20%)')
print('=' * 90)
print(grid_df.to_string(index=False))

print('\n最优 5 组 (按 IR 排序):')
print(grid_df.head(5).to_string(index=False))

grid_df.to_csv('grid_search.csv', index=False, encoding='utf-8-sig')
print('\n已导出: grid_search.csv')
