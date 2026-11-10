// assets/charts.js — 老登股错杀挖掘 v2（全市场脚本初筛版）
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var amber = style.getPropertyValue('--amber').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var DATA = window.LAODENG_DATA || [];

  var TIER_COLOR = {
    '准猎物': accent2,
    '拐点跟踪': amber,
    '观察': muted,
    '高位收息': '#6b7fa0',
    '待判': '#9a9384',
    '禁区': accent
  };

  // ---------- Chart A: 核心矩阵图 (X=10年价格分位, Y=财务质量OCF/NI) ----------
  var mEl = document.getElementById('chart-matrix');
  if (mEl && window.echarts && DATA.length) {
    var m = echarts.init(mEl, null, { renderer: 'svg' });
    var series = {};
    DATA.forEach(function(d) {
      if (d.pctl === null || d.ocf === null) return;
      var t = d.tier;
      if (!series[t]) series[t] = [];
      var ocfClamped = Math.max(-3, Math.min(6, d.ocf));
      series[t].push({
        name: d.name,
        value: [d.pctl, ocfClamped, d.cap, d.ocf, d.code],
        itemStyle: { color: TIER_COLOR[t] || muted, opacity: 0.85 }
      });
    });
    var order = ['准猎物', '拐点跟踪', '观察', '高位收息', '禁区'];
    var seriesArr = order.filter(function(t) { return series[t]; }).map(function(t) {
      return {
        name: t,
        type: 'scatter',
        data: series[t],
        symbolSize: function(v) {
          var cap = v[2] || 100;
          return Math.max(9, Math.min(42, Math.sqrt(cap) * 0.9));
        },
        emphasis: { focus: 'series', label: { show: true, formatter: function(p) { return p.name; }, position: 'top', color: ink, fontWeight: 600 } },
        label: { show: true, formatter: function(p) { return p.name; }, position: 'top', fontSize: 9, color: muted },
        labelLayout: { hideOverlap: true }
      };
    });
    m.setOption({
      animation: false,
      legend: { top: 0, data: order.filter(function(t) { return series[t]; }), textStyle: { color: ink } },
      tooltip: {
        appendToBody: true,
        formatter: function(p) {
          var v = p.value;
          return '<b>' + p.name + '</b> (' + v[4] + ')<br>档位: ' + p.seriesName +
                 '<br>10年价格分位: ' + v[0] + '%<br>OCF/NI(3年): ' + v[3] +
                 '<br>市值: ' + (v[2] || '?') + '亿';
        }
      },
      grid: { left: 60, right: 30, top: 50, bottom: 50 },
      xAxis: {
        name: '10年价格分位（%）→ 越左越低估', nameLocation: 'middle', nameGap: 32,
        nameTextStyle: { color: muted, fontSize: 11 },
        min: 0, max: 100, type: 'value',
        axisLabel: { color: muted, formatter: '{value}%' },
        splitLine: { lineStyle: { color: rule } }
      },
      yAxis: {
        name: '财务质量 OCF/NI（3年累计）→ 越高越健康', nameLocation: 'middle', nameGap: 42,
        nameTextStyle: { color: muted, fontSize: 11 },
        min: -3, max: 6, type: 'value',
        axisLabel: { color: muted },
        splitLine: { lineStyle: { color: rule } }
      },
      series: seriesArr.concat([{
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: accent2, type: 'dashed', width: 1.2 },
          label: { formatter: 'OCF/NI=0.7 质量线', color: accent2, fontSize: 10, position: 'insideEndTop' },
          data: [{ yAxis: 0.7 }]
        },
        data: []
      }, {
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: accent2, type: 'dashed', width: 1.2 },
          label: { formatter: '分位40% 低估线', color: accent2, fontSize: 10, position: 'insideEndTop' },
          data: [{ xAxis: 40 }]
        },
        data: []
      }])
    });
    window.addEventListener('resize', function() { m.resize(); });
  }

  // ---------- Chart B: 漏斗 ----------
  var fEl = document.getElementById('chart-funnel');
  if (fEl && window.echarts) {
    var f = echarts.init(fEl, null, { renderer: 'svg' });
    f.setOption({
      animation: false,
      tooltip: { trigger: 'item', appendToBody: true, formatter: function(p) { return p.name + '<br>' + p.data.range; } },
      series: [{
        type: 'funnel', left: '5%', right: '5%', top: 10, bottom: 10,
        minSize: '14%', maxSize: '100%', sort: 'descending', gap: 4,
        label: { show: true, position: 'inside', fontSize: 13, fontWeight: 600,
          formatter: function(p) { return p.name + '  ' + p.data.range; } },
        labelLine: { show: false },
        itemStyle: { borderColor: bg2, borderWidth: 2 },
        data: [
          { name: '全市场', value: 5577, range: '5,577 只（问财直连全量拉取·零截断）', label: { color: ink }, itemStyle: { color: rule } },
          { name: '行业+市值过滤后', value: 3400, range: '约 3,400 只', label: { color: '#fff' }, itemStyle: { color: muted } },
          { name: '低估+错杀双条件', value: 147, range: '147 只 → 价格分位≤40% 再剔 89 只', label: { color: ink }, itemStyle: { color: '#c9c2b2' } },
          { name: '候选池', value: 58, range: '58 只（脚本精筛·含分位/OCF/NI）', label: { color: '#fff' }, itemStyle: { color: amber } },
          { name: '准猎物档', value: 9, range: '9 只（扫描6 + 关注池3：顺丰/心脉/艾力斯）', label: { color: '#fff' }, itemStyle: { color: accent2 } }
        ]
      }]
    });
    window.addEventListener('resize', function() { f.resize(); });
  }

  // ---------- Chart C: 五档分布 ----------
  var bEl = document.getElementById('chart-tiers');
  if (bEl && window.echarts && DATA.length) {
    var cnt = {};
    DATA.forEach(function(d) { cnt[d.tier] = (cnt[d.tier] || 0) + 1; });
    var order2 = ['准猎物', '拐点跟踪', '观察', '高位收息', '禁区'];
    var b = echarts.init(bEl, null, { renderer: 'svg' });
    b.setOption({
      animation: false,
      tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 30, top: 10, bottom: 8, containLabel: true },
      xAxis: { type: 'value', minInterval: 1, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      yAxis: { type: 'category', data: order2.slice().reverse(), axisLabel: { color: ink }, axisLine: { lineStyle: { color: rule } }, axisTick: { show: false } },
      series: [{
        type: 'bar', barWidth: '55%',
        label: { show: true, position: 'right', color: ink, fontWeight: 600 },
        data: order2.slice().reverse().map(function(t) {
          return { value: cnt[t] || 0, itemStyle: { color: TIER_COLOR[t] || muted } };
        })
      }]
    });
    window.addEventListener('resize', function() { b.resize(); });
  }

  // ---------- Chart D: 高低分位对照条形（双组对照） ----------
  var pEl = document.getElementById('chart-pctl-compare');
  if (pEl && window.echarts && DATA.length) {
    var sorted = DATA.filter(function(d) { return d.pctl !== null; })
      .sort(function(a, b) { return a.pctl - b.pctl; });
    var p = echarts.init(pEl, null, { renderer: 'svg' });
    p.setOption({
      animation: false,
      tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' },
        formatter: function(ps) { var d = ps[0]; var item = sorted[d.dataIndex];
          return '<b>' + item.name + '</b><br>分位: ' + item.pctl + '%<br>OCF/NI: ' + (item.ocf === null ? '--' : item.ocf) + '<br>档位: ' + item.verdict; } },
      grid: { left: 8, right: 30, top: 10, bottom: 8, containLabel: true },
      xAxis: { type: 'value', max: 100, axisLabel: { color: muted, formatter: '{value}%' }, splitLine: { lineStyle: { color: rule } } },
      yAxis: { type: 'category', data: sorted.map(function(d) { return d.name; }), axisLabel: { color: ink, fontSize: 10 }, axisTick: { show: false }, axisLine: { lineStyle: { color: rule } } },
      series: [{
        type: 'bar', barWidth: '70%',
        data: sorted.map(function(d) {
          return { value: d.pctl, itemStyle: { color: TIER_COLOR[d.tier] || muted } };
        })
      }]
    });
    p.setOption({});
    window.addEventListener('resize', function() { p.resize(); });
  }
})();

// ---------- Chart E: 关注池分位分布（独立于主矩阵） ----------
(function() {
  var style2 = getComputedStyle(document.documentElement);
  var a2 = style2.getPropertyValue('--accent2').trim();
  var am = style2.getPropertyValue('--amber').trim();
  var mt = style2.getPropertyValue('--muted').trim();
  var rl = style2.getPropertyValue('--rule').trim();
  var ik = style2.getPropertyValue('--ink').trim();
  var blue = '#6b7fa0';
  var rd = style2.getPropertyValue('--accent').trim();

  var el = document.getElementById('chart-watchlist');
  if (!el || !window.echarts) return;
  var DATA = (window.LAODENG_DATA || []).filter(function(d) { return d.src === '关注池'; });
  if (!DATA.length) return;

  var sorted = DATA.filter(function(d) { return d.pctl !== null; })
    .sort(function(a, b) { return a.pctl - b.pctl; });

  function colorOf(t) {
    if (t === '准猎物') return a2;
    if (t === '拐点跟踪') return am;
    if (t === '禁区') return rd;
    if (t === '高位收息') return blue;
    return mt;
  }

  var c = echarts.init(el, null, { renderer: 'svg' });
  c.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' },
      formatter: function(ps) {
        var d = sorted[ps[0].dataIndex];
        return '<b>' + d.name + '</b> (' + d.code + ')<br>分位: ' + d.pctl + '%<br>PB: ' + (d.pb || '--') +
               '<br>OCF/NI: ' + (d.ocf === null ? '--' : d.ocf) + '<br>判定: ' + d.verdict;
      } },
    grid: { left: 8, right: 40, top: 10, bottom: 8, containLabel: true },
    xAxis: { type: 'value', max: 100, axisLabel: { color: mt, formatter: '{value}%' }, splitLine: { lineStyle: { color: rl } } },
    yAxis: { type: 'category', data: sorted.map(function(d) { return d.name; }),
      axisLabel: { color: ik, fontSize: 9.5 }, axisTick: { show: false }, axisLine: { lineStyle: { color: rl } } },
    series: [{
      type: 'bar', barWidth: '72%',
      data: sorted.map(function(d) {
        return { value: d.pctl, itemStyle: { color: colorOf(d.tier) } };
      })
    }]
  });
  window.addEventListener('resize', function() { c.resize(); });
})();
