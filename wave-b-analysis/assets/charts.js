// assets/charts.js — 报告图表（数据来自 chart-data.js，全部为K线/两融原始数据实算）
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var D = window.CHART_DATA;

  function mk(id, opt) {
    var el = document.getElementById(id);
    if (!el || typeof echarts === 'undefined') return null;
    var c = echarts.init(el, null, { renderer: 'svg' });
    c.setOption(opt);
    window.addEventListener('resize', function () { c.resize(); });
    return c;
  }
  var baseAxis = {
    axisLine: { lineStyle: { color: rule } },
    axisLabel: { color: muted, fontSize: 10 },
    axisTick: { show: false }
  };

  /* ---------- 图1 归一化走势 ---------- */
  mk('chart-norm', {
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function (v) { return v + '（顶点=100）'; } },
    legend: { top: 0, textStyle: { color: ink, fontSize: 12 }, itemWidth: 18 },
    grid: { left: 46, right: 20, top: 36, bottom: 46 },
    xAxis: Object.assign({ type: 'category', data: D.normKC.map(function (d) { return d[0]; }) }, baseAxis),
    yAxis: Object.assign({ type: 'value', scale: true, splitLine: { lineStyle: { color: rule } } }, baseAxis),
    series: [
      {
        name: '科创50（顶2255.25）', type: 'line', showSymbol: false, data: D.normKC,
        lineStyle: { color: accent, width: 2 }, itemStyle: { color: accent },
        markPoint: {
          symbolSize: 44, label: { color: '#fff', fontSize: 10 },
          data: [{ type: 'min', name: '低点' }], itemStyle: { color: accent }
        },
        markLine: {
          silent: true, symbol: 'none', lineStyle: { color: muted, type: 'dashed', width: 1 },
          label: { color: muted, fontSize: 10, formatter: '最大回撤 -44.6%' },
          data: [{ yAxis: 55.4 }]
        }
      },
      {
        name: '创业板指（顶4380.41）', type: 'line', showSymbol: false, data: D.normCY,
        lineStyle: { color: accent2, width: 2 }, itemStyle: { color: accent2 }
      }
    ]
  });

  /* ---------- 图2 RSI ---------- */
  mk('chart-rsi', {
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true },
    legend: { top: 0, textStyle: { color: ink, fontSize: 12 }, itemWidth: 18 },
    grid: { left: 40, right: 20, top: 36, bottom: 46 },
    xAxis: Object.assign({ type: 'category', data: D.rsiKC.map(function (d) { return d[0]; }) }, baseAxis),
    yAxis: Object.assign({
      type: 'value', min: 0, max: 100, interval: 25,
      splitLine: { lineStyle: { color: rule } }
    }, baseAxis),
    series: [
      {
        name: '科创50 RSI14', type: 'line', showSymbol: false, data: D.rsiKC,
        lineStyle: { color: accent, width: 1.8 }, itemStyle: { color: accent }
      },
      {
        name: '创业板指 RSI14', type: 'line', showSymbol: false, data: D.rsiCY,
        lineStyle: { color: accent2, width: 1.8 }, itemStyle: { color: accent2 }
      },
      {
        name: '超卖线', type: 'line', data: [], markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: muted, type: 'dashed', width: 1 },
          label: { formatter: '30 超卖线', color: muted, fontSize: 10 },
          data: [{ yAxis: 30 }]
        }
      }
    ]
  });

  /* ---------- 图3 融资余额 ---------- */
  mk('chart-margin', {
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function (v) { return v + ' 亿元'; } },
    grid: { left: 66, right: 30, top: 40, bottom: 46 },
    xAxis: Object.assign({ type: 'category', data: D.margin.map(function (d) { return d[0]; }) }, baseAxis),
    yAxis: Object.assign({
      type: 'value', min: 23000, max: 26600,
      splitLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 10, formatter: function (v) { return v / 10000 + '万亿'; } }
    }, baseAxis),
    series: [{
      name: '融资余额', type: 'line', showSymbol: false, data: D.margin.map(function (d) { return d[1]; }),
      lineStyle: { color: accent, width: 2.2 }, itemStyle: { color: accent },
      areaStyle: { color: accent + '14' },
      markPoint: {
        symbolSize: 46, label: { color: '#fff', fontSize: 10 },
        data: [
          { coord: ['2026-09-22', 26263.4], value: '峰值\n26263', itemStyle: { color: accent2 } },
          { coord: ['2026-10-27', 23809.7], value: '23810\n-9.3%', itemStyle: { color: accent } }
        ]
      },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: muted, type: 'dashed', width: 1 },
        label: { color: muted, fontSize: 10 },
        data: [
          { yAxis: 23000, label: { formatter: '23,000 否决阈值' } },
          { coord: ['2026-10-09', 25300.5], label: { formatter: '10-09 起 13 日连降', position: 'insideEndTop' } }
        ]
      }
    }]
  });

  /* ---------- 图4 三情景目标区（双面板） ---------- */
  var futDates = ['2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-09'];
  function panel(idx, data, scenes, yname, min, max) {
    return {
      xAxisIndex: idx, yAxisIndex: idx,
      type: 'line', showSymbol: false,
      data: data.concat(futDates.map(function () { return null; })),
      lineStyle: { color: idx === 0 ? accent : accent2, width: 2 },
      itemStyle: { color: idx === 0 ? accent : accent2 },
      markArea: {
        silent: true,
        data: scenes.map(function (s) {
          return [
            { xAxis: futDates[0], yAxis: s[1], itemStyle: { color: s[3] }, label: { show: true, position: 'insideTopRight', color: s[4], fontSize: 10, formatter: s[0] + ' ' + s[1] + '–' + s[2] } },
            { xAxis: futDates[futDates.length - 1], yAxis: s[2] }
          ];
        })
      },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: muted, type: 'dashed', width: 1 },
        label: { color: muted, fontSize: 10 },
        data: [
          { yAxis: scenes[3][1], label: { formatter: scenes[3][0] } },
          { yAxis: scenes[3][2], label: { formatter: '' } }
        ]
      }
    };
  }
  // 科创50: 保守1350-1420 中性1450-1520 乐观1550-1610 支撑1249.01/二次探底1150-1200
  var scKC = [
    ['乐观', 1550, 1610, accent + '26', accent],
    ['中性', 1450, 1520, accent2 + '30', accent2],
    ['保守', 1350, 1420, muted + '22', muted],
    ['支撑 1249.01', 1249, 1250, accent, accent]
  ];
  // 创业板: 保守2820-2890 中性2950-3050 乐观3100-3215 支撑2494.22
  var scCY = [
    ['乐观', 3100, 3215, accent + '26', accent],
    ['中性', 2950, 3050, accent2 + '30', accent2],
    ['保守', 2820, 2890, muted + '22', muted],
    ['支撑 2494.22', 2494, 2495, accent, accent]
  ];
  var allX = D.kc120.map(function (d) { return d[0]; }).concat(futDates);
  mk('chart-scenario', {
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    title: [
      { text: '科创50（000688）', left: 50, top: 4, textStyle: { color: ink, fontSize: 13, fontWeight: 600 } },
      { text: '创业板指（399006）', left: 50, top: '54%', textStyle: { color: ink, fontSize: 13, fontWeight: 600 } }
    ],
    grid: [
      { left: 60, right: 110, top: 34, height: '30%' },
      { left: 60, right: 110, top: '59%', height: '30%' }
    ],
    xAxis: [
      Object.assign({ type: 'category', data: allX, gridIndex: 0 }, baseAxis),
      Object.assign({ type: 'category', data: allX, gridIndex: 1 }, baseAxis)
    ],
    yAxis: [
      Object.assign({ type: 'value', min: 1150, max: 2350, gridIndex: 0, name: '', splitLine: { lineStyle: { color: rule } } }, baseAxis),
      Object.assign({ type: 'value', min: 2350, max: 4450, gridIndex: 1, name: '', splitLine: { lineStyle: { color: rule } } }, baseAxis)
    ],
    series: [
      panel(0, D.kc120, scKC),
      panel(1, D.cy120, scCY)
    ]
  });
})();
