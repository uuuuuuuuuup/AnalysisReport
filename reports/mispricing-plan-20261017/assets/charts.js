// assets/charts.js — 老登股错杀作战计划
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // ---------- Chart: 漏斗预期规模 ----------
  var funnelEl = document.getElementById('chart-funnel');
  if (funnelEl && window.echarts) {
    var funnel = echarts.init(funnelEl, null, { renderer: 'svg' });
    funnel.setOption({
      animation: false,
      tooltip: {
        trigger: 'item',
        appendToBody: true,
        formatter: function(p) {
          return p.name + '<br>预期数量：' + p.data.range;
        }
      },
      series: [{
        name: '漏斗预期规模',
        type: 'funnel',
        left: '6%',
        right: '6%',
        top: 10,
        bottom: 10,
        minSize: '10%',
        maxSize: '100%',
        sort: 'descending',
        gap: 4,
        label: {
          show: true,
          position: 'inside',
          fontSize: 13,
          fontWeight: 600,
          formatter: function(p) { return p.name + '  ' + p.data.range; }
        },
        labelLine: { show: false },
        itemStyle: { borderColor: bg2, borderWidth: 2 },
        emphasis: { label: { fontSize: 14 } },
        data: [
          { name: '全市场 A 股', value: 5400, range: '约 5,400 只', label: { color: ink }, itemStyle: { color: rule } },
          { name: '剔除科技链后', value: 4000, range: '约 4,000 只', label: { color: '#fff' }, itemStyle: { color: muted } },
          { name: '分位初筛', value: 115, range: '80–150 只', label: { color: '#fff' }, itemStyle: { color: accent } },
          { name: '行业收窄个体', value: 30, range: '20–40 只', label: { color: '#fff' }, itemStyle: { color: accent2 } },
          { name: '猎物档', value: 5, range: '0–10 只（零候选合法）', label: { color: '#fff' }, itemStyle: { color: accent2 } }
        ]
      }]
    });
    window.addEventListener('resize', function() { funnel.resize(); });
  }

  // ---------- Mermaid ----------
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: true,
      theme: 'neutral',
      securityLevel: 'loose',
      flowchart: { htmlLabels: true, curve: 'basis' }
    });
  }
})();
