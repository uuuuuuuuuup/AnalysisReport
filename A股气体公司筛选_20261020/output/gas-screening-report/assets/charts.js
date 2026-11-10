// assets/charts.js — A股气体公司筛选报告图表
// 数据截至2026-10-20，与报告正文/data目录一致
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim() || '#0e5c58';
  var accent2 = style.getPropertyValue('--accent2').trim() || '#b25a2b';
  var ink = style.getPropertyValue('--ink').trim() || '#1b2430';
  var muted = style.getPropertyValue('--muted').trim() || '#5d6570';
  var rule = style.getPropertyValue('--rule').trim() || '#d9d9d0';
  var bg2 = style.getPropertyValue('--bg2').trim() || '#eeeee7';
  var bad = '#a13a2a';
  var palette = [accent, accent2, muted, accent + '99', accent2 + '99'];

  var baseTooltip = { trigger: 'item', appendToBody: true, textStyle: { fontSize: 12 } };
  var axisCommon = {
    axisLine: { lineStyle: { color: rule } },
    axisLabel: { color: muted, fontSize: 11 },
    splitLine: { lineStyle: { color: rule, opacity: 0.5 } }
  };

  /* ---------- 图1 · PE(TTM)估值分布 ---------- */
  var el1 = document.getElementById('chart-pe');
  if (el1) {
    var c1 = echarts.init(el1, null, { renderer: 'svg' });
    // [名称, PE, 类型] 亏损公司不显示
    var peData = [
      ['凯美特气', 255.2, 'S'], ['中船特气', 158.6, 'S'], ['和远气体', 154.5, 'E'],
      ['三孚股份', 86.4, 'C'], ['金宏气体', 84.4, 'E'], ['广钢气体', 82.7, 'K'],
      ['侨源股份', 81.2, 'E'], ['华特气体', 85.8, 'S'], ['南大光电', 80.2, 'S'],
      ['蜀道装备', 59.8, 'D'], ['冰轮环境', 47.9, 'D'], ['雅克科技', 44.6, 'C'],
      ['多氟多', 44.7, 'C'], ['昊华科技', 28.0, 'C'], ['杭氧股份', 23.9, 'E'],
      ['巨化股份', 18.2, 'C'], ['中泰股份', 12.7, 'D'], ['九丰能源', 12.3, 'C']
    ];
    peData.sort(function (a, b) { return b[1] - a[1]; });
    var typeColor = { S: accent, K: accent2, E: muted, D: ink, C: '#8a5a34' };
    c1.setOption({
      animation: false,
      tooltip: Object.assign({}, baseTooltip, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var p = ps[0];
          return p.name + '<br/>PE(TTM): <b>' + p.value + 'x</b><br/>类型: ' + p.data.type;
        }
      }),
      grid: { left: 90, right: 40, top: 30, bottom: 40 },
      xAxis: Object.assign({}, axisCommon, { type: 'value', name: 'PE(TTM)', nameTextStyle: { color: muted }, axisLabel: { color: muted, fontSize: 11 } }),
      yAxis: Object.assign({}, axisCommon, { type: 'category', data: peData.map(function (d) { return d[0]; }), splitLine: { show: false } }),
      series: [{
        type: 'bar',
        data: peData.map(function (d) {
          return { value: d[1], type: d[2], itemStyle: { color: typeColor[d[2]] } };
        }),
        label: { show: true, position: 'right', color: muted, fontSize: 10, formatter: '{c}x' },
        barMaxWidth: 16
      }],
      graphic: [{
        type: 'group', right: 10, top: 0,
        children: [
          { type: 'rect', shape: { width: 10, height: 10, r: 2 }, style: { fill: accent }, left: 0, top: 4 },
          { type: 'text', style: { text: 'S特气  ', fill: muted, fontSize: 10 }, left: 14, top: 0 },
          { type: 'rect', shape: { width: 10, height: 10, r: 2 }, style: { fill: accent2 }, left: 62, top: 4 },
          { type: 'text', style: { text: 'K电子大宗  ', fill: muted, fontSize: 10 }, left: 76, top: 0 },
          { type: 'rect', shape: { width: 10, height: 10, r: 2 }, style: { fill: muted }, left: 146, top: 4 },
          { type: 'text', style: { text: 'E零售  ', fill: muted, fontSize: 10 }, left: 160, top: 0 },
          { type: 'rect', shape: { width: 10, height: 10, r: 2 }, style: { fill: ink }, left: 200, top: 4 },
          { type: 'text', style: { text: 'D设备  ', fill: muted, fontSize: 10 }, left: 214, top: 0 },
          { type: 'rect', shape: { width: 10, height: 10, r: 2 }, style: { fill: '#8a5a34' }, left: 258, top: 4 },
          { type: 'text', style: { text: 'C平台', fill: muted, fontSize: 10 }, left: 272, top: 0 }
        ]
      }]
    });
    window.addEventListener('resize', function () { c1.resize(); });
  }

  /* ---------- 快筛表排序 ---------- */
  var tbl = document.getElementById('screen-table');
  if (tbl) {
    var tbody = tbl.querySelector('tbody');
    var headers = tbl.querySelectorAll('th.sortable');
    headers.forEach(function (th, idx) {
      th.addEventListener('click', function () {
        var isNum = th.classList.contains('num');
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
        var cur = th.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
        headers.forEach(function (h) { h.removeAttribute('data-dir'); });
        th.setAttribute('data-dir', cur);
        function parse(row) {
          var t = row.children[idx].textContent.trim();
          if (isNum) {
            var v = parseFloat(t.replace(/[^0-9.\-]/g, ''));
            return isNaN(v) ? -Infinity : v;
          }
          return t;
        }
        rows.sort(function (a, b) {
          var va = parse(a), vb = parse(b);
          var r = (typeof va === 'string') ? va.localeCompare(vb, 'zh') : va - vb;
          return cur === 'asc' ? r : -r;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  }

  /* ---------- 图2 · 评分热力图 ---------- */
  var el2 = document.getElementById('chart-heat');
  if (el2) {
    var c2 = echarts.init(el2, null, { renderer: 'svg' });
    var rows = [
      ['中船特气 S', 25.0, 13.0, 17.0, 13.0, 11.5, 2.0, 81.5],
      ['杭氧股份 E+D', 17.0, 14.0, 15.0, 13.0, 11.0, 6.0, 76.0],
      ['广钢气体 K+R', 22.0, 12.0, 13.0, 13.0, 10.5, 2.0, 72.5],
      ['南大光电 S', 18.0, 11.0, 17.0, 11.0, 12.0, 3.0, 72.0],
      ['华特气体 S', 25.0, 11.0, 15.0, 7.5, 9.0, 2.0, 69.5],
      ['昊华科技 C*', 16.0, 10.0, 16.0, 12.0, 10.0, 5.0, 69.0],
      ['巨化股份 C*', 15.0, 12.0, 17.0, 8.0, 10.0, 6.0, 68.0],
      ['雅克科技 C*', 20.0, 11.0, 15.0, 8.4, 8.0, 4.0, 63.4],
      ['九丰能源 C*', 10.0, 10.0, 17.0, 8.0, 10.0, 7.0, 62.0],
      ['侨源股份 E', 13.0, 13.0, 17.0, 4.0, 11.0, 2.0, 57.0],
      ['金宏气体 E', 15.0, 11.0, 13.0, 11.0, 11.0, 3.0, 51.4],
      ['凯美特气 S', 14.0, 9.0, 16.0, 9.0, 6.0, 1.0, 46.8]
    ];
    var cols = ['壁垒D1', '成本D2', '财务D3', '成长D4', '风险治理D5', '估值催化D6', '总分'];
    var heatData = [];
    rows.forEach(function (r, yi) {
      cols.forEach(function (_, xi) { heatData.push([xi, yi, r[xi + 1]]); });
    });
    // 列满分用于归一着色
    var maxScore = [25, 15, 20, 15, 15, 10, 100];
    c2.setOption({
      animation: false,
      tooltip: Object.assign({}, baseTooltip, {
        formatter: function (p) {
          return rows[p.value[1]][0] + ' · ' + cols[p.value[0]] + '<br/>得分: <b>' + p.value[2] +
            '</b> / ' + maxScore[p.value[0]];
        }
      }),
      grid: { left: 110, right: 90, top: 40, bottom: 60 },
      xAxis: { type: 'category', data: cols, axisLine: { lineStyle: { color: rule } }, axisLabel: { color: muted, fontSize: 11 }, splitArea: { show: false } },
      yAxis: { type: 'category', data: rows.map(function (r) { return r[0]; }), axisLine: { lineStyle: { color: rule } }, axisLabel: { color: ink, fontSize: 11 }, splitArea: { show: false } },
      visualMap: {
        min: 0, max: 1, calculable: false, orient: 'vertical', right: 0, top: 'center',
        textStyle: { color: muted, fontSize: 10 },
        formatter: function (v) { return (v * 100).toFixed(0) + '%满分'; },
        inRange: { color: [bg2, accent2, accent] },
        outOfRange: { color: 'transparent' }
      },
      series: [{
        type: 'heatmap',
        data: heatData,
        label: { show: true, color: ink, fontSize: 10, formatter: function (p) { return p.value[2]; } },
        itemStyle: { borderColor: '#fff', borderWidth: 2 }
      }]
    });
    window.addEventListener('resize', function () { c2.resize(); });
  }

  /* ---------- 图3 · 风险矩阵气泡图 ---------- */
  var el3 = document.getElementById('chart-bubble');
  if (el3) {
    var c3 = echarts.init(el3, null, { renderer: 'svg' });
    var bubble = [
      { n: '中船特气', x: 25.0, y: 17.0, z: 72, t: 'S' },
      { n: '华特气体', x: 25.0, y: 15.0, z: 47, t: 'S' },
      { n: '南大光电', x: 18.0, y: 17.0, z: 44, t: 'S' },
      { n: '凯美特气', x: 14.0, y: 16.0, z: 82, t: 'S' },
      { n: '广钢气体', x: 22.0, y: 13.0, z: 71, t: 'K' },
      { n: '金宏气体', x: 15.0, y: 13.0, z: 46, t: 'E' },
      { n: '杭氧股份', x: 17.0, y: 15.0, z: 3, t: 'E' },
      { n: '侨源股份', x: 13.0, y: 17.0, z: 70, t: 'E' },
      { n: '昊华科技', x: 16.0, y: 16.0, z: 15, t: 'C' },
      { n: '雅克科技', x: 20.0, y: 15.0, z: 30, t: 'C' },
      { n: '巨化股份', x: 15.0, y: 17.0, z: 5, t: 'C' },
      { n: '九丰能源', x: 10.0, y: 17.0, z: 3, t: 'C' }
    ];
    var seriesMap = {};
    bubble.forEach(function (d) {
      if (!seriesMap[d.t]) seriesMap[d.t] = [];
      seriesMap[d.t].push(d);
    });
    var tName = { S: 'S特气认证', K: 'K电子大宗', E: 'E区域零售', C: 'C平台' };
    var series3 = Object.keys(seriesMap).map(function (t) {
      return {
        name: tName[t], type: 'scatter',
        data: seriesMap[t].map(function (d) {
          return { value: [d.x, d.y], name: d.n, z: d.z, t: t };
        }),
        symbolSize: function (v, p) { return 10 + p.data.z * 0.55; },
        itemStyle: { color: typeColorC(t), opacity: 0.78, borderColor: '#fff', borderWidth: 1 },
        label: { show: true, position: 'top', color: ink, fontSize: 10, formatter: function (p) { return p.data.name; } }
      };
    });
    function typeColorC(t) { return { S: accent, K: accent2, E: muted, C: '#8a5a34' }[t]; }
    c3.setOption({
      animation: false,
      tooltip: Object.assign({}, baseTooltip, {
        formatter: function (p) {
          return '<b>' + p.data.name + '</b>（' + tName[p.data.t] + '）<br/>壁垒分: ' + p.value[0] +
            '<br/>财务质量分: ' + p.value[1] + '<br/>题材溢价: ' + p.data.z + '%';
        }
      }),
      legend: { top: 0, textStyle: { color: muted, fontSize: 11 } },
      grid: { left: 50, right: 40, top: 40, bottom: 50 },
      xAxis: Object.assign({}, axisCommon, { type: 'value', name: '稀缺壁垒分(D1,满分25)', nameTextStyle: { color: muted, fontSize: 10 }, min: 8, max: 27 }),
      yAxis: Object.assign({}, axisCommon, { type: 'value', name: '财务质量分(D3,满分20)', nameTextStyle: { color: muted, fontSize: 10 }, min: 12, max: 18.5 }),
      series: series3
    });
    window.addEventListener('resize', function () { c3.resize(); });
  }

  /* ---------- 图4 · 认证矩阵 ---------- */
  var el4 = document.getElementById('chart-cert');
  if (el4) {
    var c4 = echarts.init(el4, null, { renderer: 'svg' });
    var certCols = ['ASML/Cymer', 'GIGAPHOTON', 'Coherent', '头部晶圆厂放量', '全球份额型', 'on-site长约'];
    var certRows = [
      ['华特气体', 2, 2, 0, 2, 0, 0],
      ['凯美特气', 1, 1, 1, 0, 0, 0],
      ['中船特气', 0, 0, 0, 2, 2, 0],
      ['南大光电', 0, 0, 0, 2, 2, 0],
      ['金宏气体', 0, 0, 0, 2, 0, 1],
      ['雅克科技', 0, 0, 0, 2, 2, 0],
      ['广钢气体', 0, 0, 0, 2, 0, 2],
      ['昊华科技', 0, 0, 0, 1, 0, 0],
      ['巨化股份', 0, 0, 0, 1, 0, 0]
    ];
    var certData = [];
    certRows.forEach(function (r, yi) {
      certCols.forEach(function (_, xi) { certData.push([xi, yi, r[xi + 1]]); });
    });
    var certLabel = { 0: '—', 1: '弱', 2: '放量' };
    c4.setOption({
      animation: false,
      tooltip: Object.assign({}, baseTooltip, {
        formatter: function (p) {
          return '<b>' + certRows[p.value[1]][0] + '</b> × ' + certCols[p.value[0]] + '<br/>状态: ' +
            (p.value[2] === 2 ? '已认证放量' : p.value[2] === 1 ? '证据弱/导入中' : '无公开证据');
        }
      }),
      grid: { left: 100, right: 70, top: 40, bottom: 60 },
      xAxis: { type: 'category', data: certCols, axisLine: { lineStyle: { color: rule } }, axisLabel: { color: muted, fontSize: 11 }, splitArea: { show: false } },
      yAxis: { type: 'category', data: certRows.map(function (r) { return r[0]; }), axisLine: { lineStyle: { color: rule } }, axisLabel: { color: ink, fontSize: 11 }, splitArea: { show: false } },
      visualMap: {
        min: 0, max: 2, calculable: false, orient: 'vertical', right: 0, top: 'center',
        textStyle: { color: muted, fontSize: 10 },
        inRange: { color: [bg2, accent2, accent] },
        outOfRange: { color: 'transparent' }
      },
      series: [{
        type: 'heatmap',
        data: certData,
        label: { show: true, color: ink, fontSize: 10, formatter: function (p) { return certLabel[p.value[2]]; } },
        itemStyle: { borderColor: '#fff', borderWidth: 2 }
      }]
    });
    window.addEventListener('resize', function () { c4.resize(); });
  }

  /* ---------- 图5 · 分品类毛利率 ---------- */
  var el5 = document.getElementById('chart-gm');
  if (el5) {
    var c5 = echarts.init(el5, null, { renderer: 'svg' });
    var gmRows = [
      ['南大光电(S)', 39.6, 40.6], ['侨源股份(E)', 36.8, 35.9], ['凯美特气(S)', 33.7, 31.1],
      ['华特气体(S)', 30.9, 30.1], ['金宏气体(E)', 29.7, 27.0], ['中船特气(S)', 28.9, 31.8],
      ['广钢气体(K)', 26.9, null], ['杭氧股份(E)', 21.0, 21.0], ['和远气体(E)', 18.9, 20.6]
    ];
    c5.setOption({
      animation: false,
      tooltip: Object.assign({}, baseTooltip, { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: function (v) { return v == null ? '—' : v + '%'; } }),
      legend: { top: 0, textStyle: { color: muted, fontSize: 11 } },
      grid: { left: 50, right: 30, top: 40, bottom: 70 },
      xAxis: Object.assign({}, axisCommon, { type: 'category', data: gmRows.map(function (r) { return r[0]; }), axisLabel: { color: muted, fontSize: 10, rotate: 30 }, splitLine: { show: false } }),
      yAxis: Object.assign({}, axisCommon, { type: 'value', name: '毛利率%', nameTextStyle: { color: muted } }),
      series: [
        { name: 'FY2025', type: 'bar', data: gmRows.map(function (r) { return r[1]; }), itemStyle: { color: accent }, barMaxWidth: 18 },
        { name: '2026H1', type: 'bar', data: gmRows.map(function (r) { return r[2]; }), itemStyle: { color: accent2 }, barMaxWidth: 18 }
      ]
    });
    window.addEventListener('resize', function () { c5.resize(); });
  }

  /* ---------- 图6 · 击球锚 ---------- */
  var el6 = document.getElementById('chart-anchor');
  if (el6) {
    var c6 = echarts.init(el6, null, { renderer: 'svg' });
    var anchors = [
      ['中船特气\n(当前153.81)', 45.0, 60.0, 95.0, 153.81],
      ['广钢气体\n(当前26.99)', 15.0, 22.0, 30.0, 26.99],
      ['杭氧股份\n(当前25.28)', 21.2, 25.3, 31.8, 25.28],
      ['巨化股份\n(当前29.53)', 25.0, 30.0, 37.0, 29.53],
      ['中泰股份\n(当前14.68)', 14.0, 17.6, 26.0, 14.68]
    ];
    c6.setOption({
      animation: false,
      tooltip: Object.assign({}, baseTooltip, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var a = anchors[ps[0].dataIndex];
          return '<b>' + a[0].replace('\n', ' ') + '</b><br/>保守: ' + a[1] + ' / 中性: ' + a[2] +
            ' / 乐观: ' + a[3] + '<br/>当前价: <b>' + a[4] + '</b>';
        }
      }),
      legend: { top: 0, textStyle: { color: muted, fontSize: 11 } },
      grid: { left: 90, right: 60, top: 40, bottom: 30 },
      xAxis: Object.assign({}, axisCommon, { type: 'value', name: '元/股', nameTextStyle: { color: muted }, axisLabel: { color: muted, fontSize: 11, formatter: function (v) { return v; } } }),
      yAxis: Object.assign({}, axisCommon, { type: 'category', data: anchors.map(function (a) { return a[0]; }), splitLine: { show: false } }),
      series: [
        { name: '保守锚', type: 'bar', stack: 'a', data: anchors.map(function (a) { return a[1]; }), itemStyle: { color: bg2 }, barMaxWidth: 20, label: { show: true, position: 'insideLeft', color: muted, fontSize: 9, formatter: function (p) { return p.value; } } },
        { name: '中性区间', type: 'bar', stack: 'a', data: anchors.map(function (a) { return +(a[2] - a[1]).toFixed(1); }), itemStyle: { color: accent2 + '88' } },
        { name: '乐观区间', type: 'bar', stack: 'a', data: anchors.map(function (a) { return +(a[3] - a[2]).toFixed(1); }), itemStyle: { color: accent + '88' } },
        {
          name: '当前价', type: 'scatter',
          data: anchors.map(function (a, i) { return [a[4], i]; }),
          symbol: 'diamond', symbolSize: 14, itemStyle: { color: bad },
          label: { show: true, position: 'right', color: bad, fontSize: 10, fontWeight: 700, formatter: function (p) { return p.value[0]; } }
        }
      ]
    });
    window.addEventListener('resize', function () { c6.resize(); });
  }
})();
