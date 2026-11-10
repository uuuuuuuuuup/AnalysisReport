// assets/charts.js — 老登股错杀执行报告
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var amber = style.getPropertyValue('--amber').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // ---------- Chart 1: 执行漏斗 ----------
  var funnelEl = document.getElementById('chart-funnel');
  if (funnelEl && window.echarts) {
    var funnel = echarts.init(funnelEl, null, { renderer: 'svg' });
    funnel.setOption({
      animation: false,
      tooltip: {
        trigger: 'item',
        appendToBody: true,
        formatter: function(p) { return p.name + '<br>' + p.data.range; }
      },
      series: [{
        name: '执行漏斗',
        type: 'funnel',
        left: '6%', right: '6%', top: 10, bottom: 10,
        minSize: '12%', maxSize: '100%',
        sort: 'descending', gap: 4,
        label: {
          show: true, position: 'inside', fontSize: 13, fontWeight: 600,
          formatter: function(p) { return p.name + '  ' + p.data.range; }
        },
        labelLine: { show: false },
        itemStyle: { borderColor: bg2, borderWidth: 2 },
        data: [
          { name: '宇宙（剔除后）', value: 4000, range: '约 4,000 只', label: { color: ink }, itemStyle: { color: rule } },
          { name: '分层枚举候选池', value: 108, range: '108 只（26 行业组 × 双条件）', label: { color: '#fff' }, itemStyle: { color: muted } },
          { name: '个体判别', value: 71, range: '71 只（6 组并行八类判别）', label: { color: '#fff' }, itemStyle: { color: amber } },
          { name: '准猎物·观察级', value: 5, range: '5 只（汾酒/五粮液/柳工/老窖/华东医药）', label: { color: '#fff' }, itemStyle: { color: accent2 } },
          { name: '猎物档（正式）', value: 1, range: '0 只 —— 零候选合法结论', label: { color: '#fff' }, itemStyle: { color: accent } }
        ]
      }]
    });
    window.addEventListener('resize', function() { funnel.resize(); });
  }

  // ---------- Chart 2: 五档分布 ----------
  var barEl = document.getElementById('chart-tiers');
  if (barEl && window.echarts) {
    var bar = echarts.init(barEl, null, { renderer: 'svg' });
    bar.setOption({
      animation: false,
      tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
      grid: { left: 8, right: 24, top: 12, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value', minInterval: 1,
        axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } }
      },
      yAxis: {
        type: 'category',
        data: ['禁区档', '观察/边缘', '拐点跟踪', '准猎物·观察级', '猎物档'],
        axisLabel: { color: ink }, axisLine: { lineStyle: { color: rule } }, axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        barWidth: '58%',
        label: { show: true, position: 'right', color: ink, fontWeight: 600 },
        data: [
          { value: 28, itemStyle: { color: accent } },
          { value: 16, itemStyle: { color: muted } },
          { value: 22, itemStyle: { color: amber } },
          { value: 5, itemStyle: { color: accent2 } },
          { value: 0, itemStyle: { color: accent2 } }
        ]
      }]
    });
    window.addEventListener('resize', function() { bar.resize(); });
  }
})();
