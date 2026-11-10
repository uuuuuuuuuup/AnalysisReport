// assets/charts.js — 错杀老登股扫描报告图表
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var gold = '#8A6A1B'; // B档警示色（与页面 tier-b 一致）

  // ─── 图1：扫描漏斗 ───
  var funnel = echarts.init(document.getElementById('chart-funnel'), null, { renderer: 'svg' });
  funnel.setOption({
    animation: false,
    tooltip: { trigger: 'item', appendToBody: true, formatter: '{b}: {c}' },
    series: [{
      type: 'funnel',
      left: '12%', right: '12%', top: 20, bottom: 10,
      minSize: '38%',
      label: { show: true, position: 'inside', color: '#fff', fontWeight: 600, formatter: '{b}\n{c} 只' },
      itemStyle: { borderColor: bg2, borderWidth: 2 },
      data: [
        { value: 40, name: 'L1 初筛', itemStyle: { color: accent } },
        { value: 39, name: 'L2 财务核验', itemStyle: { color: accent, opacity: 0.78 } },
        { value: 20, name: 'L3 评分诊断', itemStyle: { color: accent, opacity: 0.56 } }
      ]
    }]
  });
  window.addEventListener('resize', function() { funnel.resize(); });

  // ─── 图2：错杀矩阵（PB × 近1年跌幅） ───
  // [跌幅%, PB, 市值亿, 名称, 档位]
  var raw = [
    [-29.3, 0.34,  994, '中国交建', 'A'],
    [-34.2, 0.42, 1250, '上汽集团', 'A'],
    [-20.0, 0.30,  841, '中国铁建', 'A'],
    [-21.2, 0.33, 1065, '中国中铁', 'A'],
    [-24.6, 0.43, 3241, '浦发银行', 'A'],
    [-39.9, 1.03,  243, '郑煤机', 'A'],
    [-32.2, 0.94,  305, '长城证券', 'A'],
    [-33.3, 1.10, 1301, '中国银河', 'A'],
    [-28.3, 1.04, 1010, '国信证券', 'A'],
    [-30.9, 1.03,  282, '北新建材', 'A'],
    [-40.2, 1.26,  809, '徐工机械', 'A'],
    [-25.1, 0.88,  509, '中联重科', 'A'],
    [-20.1, 0.84,  324, '白云山', 'A'],
    [-38.8, 0.45,  243, '华菱钢铁', 'B'],
    [-40.5, 0.77,  822, '中油资本', 'B'],
    [-49.8, 1.20,  611, '华友钴业', 'B'],
    [-46.3, 0.92,  701, '长安汽车', 'B'],
    [-49.0, 1.07, 1468, '华润新能', 'B'],
    [-37.5, 0.51,  509, '广汽集团', 'C'],
    [-29.1, 0.34,  661, '保利发展', 'C']
  ];
  var tierName = { A: 'A档 疑似真错杀', B: 'B档 周期左侧', C: 'C档 价值陷阱' };
  var tierColor = { A: accent, B: gold, C: accent2 };
  function byTier(t) {
    return raw.filter(function(d) { return d[4] === t; }).map(function(d) {
      return { name: d[3], value: [d[0], d[1], d[2]] };
    });
  }
  var matrix = echarts.init(document.getElementById('chart-matrix'), null, { renderer: 'svg' });
  matrix.setOption({
    animation: false,
    tooltip: {
      appendToBody: true,
      formatter: function(p) {
        var v = p.value;
        return '<b>' + p.seriesName.replace('档 · ', '') + ' · ' + p.name + '</b><br>' +
               '近1年: ' + v[0] + '%<br>PB: ' + v[1] + '<br>市值: ' + v[2] + ' 亿';
      }
    },
    legend: { top: 0, textStyle: { color: muted }, data: Object.keys(tierName).map(function(k){ return ' ' + tierName[k]; }) },
    grid: { left: 56, right: 30, top: 42, bottom: 56 },
    xAxis: {
      name: '近1年涨跌幅 (%)', nameLocation: 'middle', nameGap: 30,
      nameTextStyle: { color: muted }, min: -55, max: -15,
      axisLabel: { color: muted, formatter: '{value}%' },
      splitLine: { lineStyle: { color: rule } },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      name: 'PB (倍)', nameTextStyle: { color: muted },
      min: 0, max: 1.5,
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: rule } }
    },
    series: ['A', 'B', 'C'].map(function(t) {
      return {
        name: ' ' + tierName[t],
        type: 'scatter',
        data: byTier(t),
        itemStyle: { color: tierColor[t], opacity: 0.82, borderColor: bg2, borderWidth: 1 },
        symbolSize: function(d) { return Math.max(12, Math.sqrt(d[2]) * 0.55); },
        label: { show: true, position: 'top', color: ink, fontSize: 10, formatter: function(p) { return p.name; } },
        labelLayout: { hideOverlap: true }
      };
    })
  });
  window.addEventListener('resize', function() { matrix.resize(); });

  // ─── 图3：行业资金净流入 Top12 ───
  var flow = echarts.init(document.getElementById('chart-flow'), null, { renderer: 'svg' });
  flow.setOption({
    animation: false,
    tooltip: { appendToBody: true, formatter: '{b}: {c} 亿元' },
    grid: { left: 90, right: 60, top: 10, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
    yAxis: {
      type: 'category', inverse: true,
      data: ['汽车制造', '机械行业', '酿酒行业', '发电设备', '飞机制造', '生物制药', '房地产', '建筑建材', '水泥行业', '交通运输', '家电行业', '农林牧渔'],
      axisLabel: { color: ink }, axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [48.1, 25.9, 16.7, 16.6, 16.5, 15.2, 14.8, 10.4, 10.2, 9.4, 8.1, 7.3],
      itemStyle: { color: accent, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: muted, formatter: '{c}' },
      barMaxWidth: 18
    }]
  });
  window.addEventListener('resize', function() { flow.resize(); });

  // ─── 图4：AI硬件龙头回撤 vs 大盘 ───
  var dd = echarts.init(document.getElementById('chart-dd'), null, { renderer: 'svg' });
  dd.setOption({
    animation: false,
    tooltip: { appendToBody: true, formatter: '{b}: {c}%' },
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: ['中际旭创', '新易盛', '寒武纪', '上证指数'],
      axisLabel: { color: ink }, axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value', max: 0, min: -60,
      axisLabel: { color: muted, formatter: '{value}%' },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: [
        { value: -52.7, itemStyle: { color: accent2 } },
        { value: -49.9, itemStyle: { color: accent2 } },
        { value: -43.5, itemStyle: { color: accent2, opacity: 0.75 } },
        { value: -12.7, itemStyle: { color: accent } }
      ],
      barMaxWidth: 52,
      label: { show: true, position: 'bottom', color: ink, fontWeight: 600, formatter: '{c}%' }
    }]
  });
  window.addEventListener('resize', function() { dd.resize(); });
})();
