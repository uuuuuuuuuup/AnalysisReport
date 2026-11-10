/* charts.js — 表格渲染与ECharts图表（数据来自 assets/data.js，口径2026-10-19） */
(function () {
  'use strict';
  var D = window.REPORT_DATA;
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var good = style.getPropertyValue('--good').trim();
  var bad = style.getPropertyValue('--bad').trim();

  function fmt(v, d) {
    if (v === null || v === undefined || v === '') return '—';
    if (typeof v === 'number') return v.toFixed(d === undefined ? 2 : d);
    return v;
  }
  function tag(cls, t) { return '<span class="tag ' + cls + '">' + t + '</span>'; }

  /* ============ 通用可排序表 ============ */
  function makeSortable(tableId, tbodyId, renderRow, sortDefault) {
    var table = document.getElementById(tableId);
    var tbody = document.getElementById(tbodyId);
    var state = { key: sortDefault.k, dir: sortDefault.dir };
    var rows = [];
    function th() { return table.querySelectorAll('thead th'); }
    function draw() {
      var sorted = rows.slice().sort(function (a, b) {
        var va = a[state.key], vb = b[state.key];
        if (typeof va === 'string' || typeof vb === 'string') {
          return String(va).localeCompare(String(vb), 'zh') * state.dir;
        }
        va = va === null || va === undefined ? -Infinity : va;
        vb = vb === null || vb === undefined ? -Infinity : vb;
        return (va - vb) * state.dir;
      });
      tbody.innerHTML = sorted.map(renderRow).join('');
      th().forEach(function (h) {
        h.classList.remove('sorted-asc', 'sorted-desc');
        if (h.dataset.k === state.key) h.classList.add(state.dir > 0 ? 'sorted-asc' : 'sorted-desc');
      });
    }
    th().forEach(function (h) {
      if (!h.dataset.k) return;
      h.addEventListener('click', function () {
        if (state.key === h.dataset.k) state.dir = -state.dir;
        else { state.key = h.dataset.k; state.dir = 1; }
        draw();
      });
    });
    return {
      setRows: function (r) { rows = r; draw(); },
      redraw: draw
    };
  }

  /* ============ 1. 64家快筛表 ============ */
  var qCtrl = makeSortable('q-table', 'q-body', function (r) {
    var cls = r.c === '601123' ? 'bad' : (r.flag ? 'warn' : '');
    return '<tr><td class="mono">' + r.c + '</td><td>' + r.n + '</td><td>' + r.t + '</td><td>' + r.b + '</td>' +
      '<td class="num">' + fmt(r.pe, 1) + '</td><td class="num">' + fmt(r.pb) + '</td><td class="num">' + fmt(r.dy) + '</td>' +
      '<td class="num">' + fmt(r.roe, 1) + '</td><td class="num">' + fmt(r.gpm, 1) + '</td>' +
      '<td class="num">' + fmt(r.dr, 1) + '</td><td class="num">' + fmt(r.ocfnp) + '</td>' +
      '<td class="num"><strong>' + fmt(r.score, 1) + '</strong></td><td>' + (r.flag ? '<span style="color:var(--bad);font-size:.78rem">' + r.flag + '</span>' : '') + '</td></tr>';
  }, { k: 'score', dir: -1 });

  function qApply() {
    var kw = document.getElementById('q-filter').value.trim();
    var ty = document.getElementById('q-type').value;
    var fl = document.getElementById('q-flag').value;
    var list = D.quick.filter(function (r) {
      if (kw && (r.c + r.n + r.b + r.t).indexOf(kw) < 0) return false;
      if (ty && r.t.indexOf(ty) < 0) return false;
      if (fl === '1' && !r.flag) return false;
      return true;
    });
    document.getElementById('q-count').textContent = '显示 ' + list.length + ' / 64 家';
    qCtrl.setRows(list);
  }
  document.getElementById('q-filter').addEventListener('input', qApply);
  document.getElementById('q-type').addEventListener('change', qApply);
  document.getElementById('q-flag').addEventListener('change', qApply);
  qApply();

  /* ============ 2. 评分表 ============ */
  var CONCL_TAG = { '核心优质': 'good', '观察': 'info', '中性': 'warn', '回避': 'bad' };
  function sRow(r) {
    return '<tr><td class="mono">' + r.c + '</td><td>' + r.n + '</td><td>' + r.b + '</td><td>' + r.cls + '</td>' +
      '<td class="num">' + r.d1 + '</td><td class="num">' + r.d2 + '</td><td class="num">' + r.d3 + '</td>' +
      '<td class="num">' + r.d4 + '</td><td class="num">' + r.d5 + '</td><td class="num">' + r.d6 + '</td>' +
      '<td class="num">' + r.total + '</td><td class="num" style="color:var(--bad)">' + r.ded + '</td>' +
      '<td class="num"><strong>' + r.adj + '</strong></td><td>' + r.conf + '</td>' +
      '<td>' + tag(CONCL_TAG[r.concl] || 'info', r.concl) + '</td></tr>';
  }
  var sCtrl = makeSortable('s-table', 's-body', sRow, { k: 'adj', dir: -1 });
  function sApply() {
    var cls = document.getElementById('s-cls').value;
    var list = D.scores.filter(function (r) { return !cls || r.cls === cls; });
    document.getElementById('s-count').textContent = '显示 ' + list.length + ' 家';
    sCtrl.setRows(list);
  }
  document.getElementById('s-cls').addEventListener('change', sApply);
  sApply();

  /* ============ 3. 核心资产表 ============ */
  var ASSET_NOTES = [
    ['601899', '紫金矿业', 'A', 'A', '金4610t/铜1.10亿吨/锂1883万吨LCE（2025年报）。卡莫阿44.20%权益产量17.3万吨@2.48%、巨龙58.16% 19.4万吨、Timok 17.2万吨、武里蒂卡58.97% 8.8t@6.95g/t；矿产金89.5t（权益75.1t）、矿产铜108.5万吨（权益88.6万吨）、锂2.55万吨LCE；AISC（紫金国际）1501美元/盎司、矿产金单位销售成本275.24元/克。扩产：巨龙二期已核准、锂2026指引12万吨、卡莫阿五期。'],
    ['603993', '洛阳钼业', 'A', 'A', 'TFM(80%)铜2957万吨@2.25%+钴329万吨@0.25%；KFM(71.25%)铜400.8万吨@1.79%+钴194.8万吨@0.87%；2025刚果金板块铜74.11万吨/钴11.75万吨；三道庄钼1.39万吨；巴西铌1.03万吨（创纪录）；IXM毛利率2.11%。板块毛利率：铜55.16%/钴63.62%。扩产：KFM技改、2026并表巴西三金矿、厄瓜多尔Cangrejos（30亿加元收购）。'],
    ['601168', '西部矿业', 'A', 'A', '玉龙铜矿58%控股（紫金22%参股；累计查明铜753.4万吨，2026-01增储）；锡铁山铅锌100%；铁矿石资源2.78亿吨、铁精粉140.5万吨；东台吉乃尔锂27%参股（不并表）。铜类收入70%+、毛利率16.89%（含冶炼）。扩产：玉龙三期推进。'],
    ['601600', '中国铝业', 'A', 'B', '铝土矿资源27.32亿吨、自产3540万吨（2025）；几内亚Boffa装船超2000万吨（权益未披露，寿命>60年）；氧化铝1735万吨（毛利率17.52%）、原铝808万吨（18.88%，含云铝29.10%并表）。边界：Toromocho属中铝集团（未核实入股份）。扩产：几内亚+华昇氧化铝。'],
    ['000975', '山金国际', 'A', 'A', '银资源8021t+金（公司口径）；青海大柴旦、玉龙矿业（银铅锌）、黑河洛克、吉林板庙子、Osino双子山（在建）、华盛金矿（停产待恢复）。克金销售成本163.69元/克（26H1）、矿产金毛利率83.81%；26H1矿产金3.26t（-12%）。大股东：山东黄金28.89%。'],
    ['600988', '赤峰黄金', 'A', 'B', '老挝Sepon（SND扩建：矿石1.315亿吨@0.81金当量）+加纳Wassa+境内五矿群；AISC：塞班1596/加纳1973美元/盎司、境内277.83元/克（口径需复核年报）；26H1金6.2t、净利17.32亿（+56.5%）。重大事项：紫金182.6亿收购中（交割≤2026-11-30）。'],
    ['600489', '中金黄金', 'A', 'B', '纱岭金矿372.06吨@2.77g/t（在建投产在即）；内蒙古矿业铜钼（乌努格吐山）；湖北三鑫；中原冶炼厂（2026拟无偿划转3家冶炼厂）。克金成本未披露（+33.9% yoy）；26H1矿产金9.14t、净利43.57亿（+61.7%）。'],
    ['600547', '山东黄金', 'A', 'B', '胶东五大矿（三山岛/焦家/新城/玲珑）+贝拉德罗50%+纳穆蒂尼（爬坡）+双子山（在建）；克金成本392.23元/克（2025）；2025探矿新增金81吨；26H1矿产金19.1t（-22.7%安监）。集团注入承诺延至2030-11；2025补税7.38亿。'],
    ['002155', '湖南黄金', 'A', 'B', '矿石量7190万吨、金137t、锑/钨10.99万吨；辰州沃溪（金锑钨）、渣滓溪锑矿、黄金洞、新龙；金分部毛利93.67%；自产锑14206吨。拟注入：天岳矿业+中南冶炼（省国资委批复）。26H1 OCF -1.1亿（存货）。'],
    ['002466', '天齐锂业', 'A', 'A', 'Greenbushes有效权益26.01%（51%TLEA×51%文菲尔德）全球最大在产锂辉石矿；SQM约22%权益法（2025投资收益6.65亿）；锂精矿FOB 384美元/吨（25Q4 IGO口径）；CGP3爬坡。2025归母仅4.63亿（周期底部）、26H1约42.4亿。'],
    ['002738', '中矿资源', 'A', 'B', 'Bikita（津巴布韦，锂矿石保有1240万吨）+Tanco（加拿大，铯镭榴石全球唯一在产）+春鹏锂业3.5万吨锂盐+Kitumba铜矿（赞比亚）。铯铷盐全球定价权；2025归母4.58亿（-40%）。缺口：Bikita精矿产量未披露。'],
    ['601958', '金钼股份', 'A', 'B', '金堆城钼矿4.12亿吨矿石@0.11%Mo+汝阳东沟4.56亿吨@0.12%；参股沙坪沟（210万吨钼金属，世界级，在建）+天池18.3%；保有钼金属227万吨；2025销量占全球钼市场约13%。成本未披露（缺口）。'],
    ['000960', '锡业股份', 'A', 'B', '个旧三大坑口+华联锌铟90.52%（都龙铟资源全球第一）；锡全球市占率27.16%第一；锡精矿自给率28.47%；26H1锡5.18万吨（+7.7%）。云锡集团32.97%已预披露减持；佤邦复产40-50%。'],
    ['600301', '华锡有色', 'A', 'B', '大厂矿田：铜坑7300万吨（占85%）+高峰+佛子冲，合计8550.62万吨/金属429.4万吨；铅锑精矿为最大毛利来源。2025铜坑6·16冒顶事故（ESG归0）；实控人将变更为中国五矿（2026-09，触发全面要约）。'],
    ['000426', '兴业银锡', 'A', 'B', '银漫矿业（5868.86万吨，10000t/d技改）+宇邦双尖子山（单体银资源亚洲第一）+大西洋锡业（摩洛哥，在建）；8家在产矿山保有>5亿吨、银2.98万吨/锡39.16万吨（白银亚洲第一）。控股股东兴业集团100%质押+破产重整2025执行完毕。'],
    ['000792', '盐湖股份', 'S', 'A', '察尔汗盐湖；KCl产量490.24万吨（2025）国内第一；蓝科锂业51.42%+4万吨一体化，碳酸锂约3.06万元/吨（推算）；钾毛利率60.71%、锂52.03%。控股股东：中国盐湖集团（五矿系12.87%，2025-01过户）。'],
    ['000408', '藏格矿业', 'S', 'A', '察尔汗铁路以东钾锂；KCl成本996元/吨（25H1披露）、碳酸锂4.31万/吨；参股巨龙铜业30.78%（2025投资收益27.82亿=净利72%）；麻米错/老挝钾矿在建。控股股东：紫金（2025年137亿入主，实控人上杭县财政局）。'],
    ['000893', '亚钾国际', 'S', 'B', '老挝甘蒙263.3km²钾盐；35km²老矿区矿石储量10.02亿吨；2025 KCl产量201万吨+，成本约1040元/吨（推算）；300万吨设计产能。无实控人；董事长2025-08被捕（个人事项）。'],
    ['600096', '云天化', 'S', 'B', '磷矿储量近8亿吨、原矿产能1450万吨/年、2025成品矿1173.75万吨；磷铵+尿素+聚甲醛一体化；26H1净利29.34亿（+6.1%），2026H1磷矿石均价1013元/吨。'],
    ['603505', '金石资源', 'S', 'B', '6座大型萤石矿山（全国龙头）+包钢金石43%（白云鄂博尾矿萤石回收）+金鄂博氟化工80万吨/年；26H1净利-28.9%（矿山停产整改/翔振竖井改造），包钢金石投资收益7576万。'],
    ['603799', '华友钴业', 'S', 'B', '印尼MHP：华越~58%+华飞51%（12万吨HPAL，2025净利12.52亿）+KNI在建；2025 MHP出货23.65万吨（约占印尼半壁）；刚果金CDM/MIKAS+Arcadia锂。26H1净利35.07亿（+29.4%）。MHP现金成本未披露。'],
    ['600111', '北方稀土', 'S', 'B', '无自有矿山——稀土精矿100%关联采购自包钢股份（2024Q4以来七连涨：19109→38769元/吨，挤压加工利润）；冶炼分离21万吨/年全球最大；磁材合金产能10万吨。26H1净利20.53亿（大幅增长）。'],
    ['601061', '中信金属', 'S', 'B', '贸易主导（铁矿石/铜精矿/铌）；权益单列：Ivanhoe 21.20%（2025末）→穿透Kamoa-Kakula约8.4%（推算）+Las Bambas 15%+26.25%包销+CBMM 5%；艾娜克无权益。26H1净利26.73亿（+84.6%）。'],
    ['600010', '包钢股份', 'S', 'B', '白云鄂博铁矿（资源量12.6/15.7亿吨口径差待统一）+尾矿坝稀土/萤石/铌；稀土精矿贡献超80%归母净利（年报结论）；2026H1扣非+218~368%（稀土精矿关联价38xxx元/吨高位）。'],
    ['600549', '厦门钨业', 'S', 'B', '钨矿山：行洛坑98.95%+阳储山+豫鹭尾矿回收，钨精矿约1.2万吨/年（自给率约20%）；拟购大湖塘（WO3 138万吨）；三大板块：钨钼/能源新材料（拖累）/稀土磁材。控股股东福建稀有稀土集团28.38%。']
  ];
  /* 数组结构转对象，便于排序 */
  var ASSETS = ASSET_NOTES.map(function (r) {
    return { c: r[0], n: r[1], cls: r[2], conf: r[3], txt: r[4] };
  });
  function aRow(r) {
    return '<tr><td class="mono">' + r.c + '</td><td>' + r.n + '</td><td style="white-space:normal;min-width:520px;font-size:.8rem;line-height:1.6">' + r.txt + '</td><td>' + r.conf + '</td></tr>';
  }
  var aCtrl = makeSortable('a-table', 'a-body', aRow, { k: 'c', dir: 1 });
  function aApply() {
    var ty = document.getElementById('a-type').value;
    var list = ASSETS.filter(function (r) { return !ty || r.cls === ty; });
    document.getElementById('a-count').textContent = '显示 ' + list.length + ' / 25 家';
    aCtrl.setRows(list);
  }
  document.getElementById('a-type').addEventListener('change', aApply);
  aApply();

  /* ============ 4. 价格锚表 ============ */
  var PRICES = [
    ['黄金', '美元/盎司', '4167.3', '2026-10-19', '2562.2', 'Kitco / COMEX月线72根 · A', '现货较5年均价+63%'],
    ['铜', '美元/吨', '14407.5', '2026-10-16', '9811（COMEX口径）≈9141（LME 2021-25均）', 'LME官网 · A', 'COMEX均价含美国关税溢价'],
    ['铝', '元/吨', '23340', '2026-10-19', 'null', '南财/沪铝主力 · B', 'SMM A00现货23260（10-16）'],
    ['锌', '元/吨', '25400', '2026-10-16', 'null', '金投网1#锌 · B', 'SMM 0#锌26445（9-30）冲突已记录'],
    ['铅', '元/吨', '16128', '2026-10-16', 'null', 'SMM 1#铅 · B', '机构区间15400-17000'],
    ['锡', '元/吨', '380500', '2026-10-19', 'null', 'Mysteel 1#锡 · B', '沪锡主力40.9-41.3万，口径差7-8%'],
    ['镍', '元/吨', '131810', '2026-10-15', 'null', '金投/沪镍主力 · B', '较SMM现货升水6.6%'],
    ['钴', '美元/吨', '39059', '2026-10-12', 'null（2025年均27.27万元/吨）', 'SMM折算 · B', '刚果金配额制重构期，慎用现货'],
    ['碳酸锂', '万元/吨', '10.1', '2026-10-19', 'null（近1年区间7.3-15.3）', '生意社 · B', '10月月跌16.5%，mid代理11.3万'],
    ['氧化镨钕', '万元/吨', '75.0', '2026-10-19', 'null', 'Mysteel · B', '9月下旬曾至75.81万'],
    ['氧化镝', '万元/吨', '145.5', '2026-10-16', 'null', '生意社 · B', '10-19 Mysteel原料123-125万，回落加速'],
    ['氧化铽', '元/千克', '6535', '2026-09-29', 'null', '中国稀土网 · B', 'vs Mysteel 5500，取协会口径'],
    ['钨（APT/精矿）', '万元/吨·标吨', 'APT 46.67 / 精矿65% 31.5', '2026-10-19', 'null', '生意社/SunSirs · B', '10月精矿自40.93万暴跌20%+'],
    ['钼精矿', '元/吨度', '5365', '2026-10-19', 'null', '钼精矿价格网 · B', '45-50%品位主流价'],
    ['氯化钾', '元/吨', '3233（进口）/3600（国产60%粉）', '2026-10-19', 'null', '生意社 · B', '月跌3.48%'],
    ['磷矿石', '元/吨', '1030', '2026-09-30', 'null', 'Chemicalbook 30%品位 · B', '敏感性区间950-1040'],
    ['铁矿石', '美元/吨', '90.3（普氏62%）', '2026-10-14', 'null', '南华引普氏 · B', '9月中旬96.65回落'],
  ];
  document.getElementById('p-body').innerHTML = PRICES.map(function (r) {
    return '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td><td class="num"><strong>' + r[2] + '</strong></td><td>' + r[3] + '</td><td>' + r[4] + '</td><td>' + r[5] + '</td><td style="white-space:normal;font-size:.78rem">' + r[6] + '</td></tr>';
  }).join('');

  /* ============ 5. P/NAV 表 ============ */
  document.getElementById('nav-body').innerHTML = D.pnav.map(function (r) {
    return '<tr><td>' + r.n + '</td><td style="white-space:normal;font-size:.78rem">' + r.scope + '</td><td class="num">' + r.nav_spot + '</td><td class="num">' + r.nav_mid + '</td><td class="num"><strong>' + r.pnav_spot + '</strong></td><td class="num">' + r.pnav_mid + '</td><td style="white-space:normal;font-size:.75rem;color:var(--muted)">' + r.assume + '</td></tr>';
  }).join('');

  /* ============ 6. 敏感性表 ============ */
  document.getElementById('sn-body').innerHTML = D.sens.map(function (r) {
    var hot = r.n.indexOf('天齐') >= 0 || (r.n.indexOf('藏格') >= 0 && r['var'].indexOf('铜') >= 0);
    return '<tr' + (hot ? ' style="background:#fdf3e7"' : '') + '><td>' + r.n + '</td><td><strong>' + r['var'] + '</strong></td><td class="num">' + r.lo + '</td><td class="num">' + r.hi + '</td><td class="num">' + r.base + '</td><td style="white-space:normal;font-size:.78rem">' + r.note + (hot ? ' <span class="tag warn">高敏感</span>' : '') + '</td></tr>';
  }).join('');

  /* ============ ECharts ============ */
  function mk(id) {
    var el = document.getElementById(id);
    if (!el || !window.echarts) return null;
    var c = echarts.init(el, null, { renderer: 'svg' });
    window.addEventListener('resize', function () { c.resize(); });
    return c;
  }
  var TOOLTIP = { appendToBody: true, confine: true };

  /* 图1：64家 PE×ROE 散点 */
  (function () {
    var c = mk('chart-quick'); if (!c) return;
    var deep = {};
    D.scores.forEach(function (s) { deep[s.c] = s.cls; });
    var groups = { A: [], S: [], rest: [] };
    D.quick.forEach(function (r) {
      var x = r.pe === null ? 45 : Math.min(r.pe, 60);
      var y = r.roe === null ? 0 : r.roe;
      if (y < -5) y = -5;
      var pt = { name: r.n, value: [x, y, r.cap || 100], code: r.c, score: r.score };
      if (deep[r.c] === 'A') groups.A.push(pt);
      else if (deep[r.c]) groups.S.push(pt);
      else groups.rest.push(pt);
    });
    function ser(name, data, color) {
      return {
        name: name, type: 'scatter', data: data,
        symbolSize: function (v) { return Math.max(6, Math.min(38, Math.sqrt(v[2]) * 0.42)); },
        itemStyle: { color: color, opacity: 0.78, borderColor: bg2, borderWidth: 1 },
        label: {
          show: true, formatter: function (p) { return p.data.code; },
          position: 'top', fontSize: 9, color: muted
        },
        emphasis: { label: { show: true, formatter: function (p) { return p.name + '\n快筛' + p.data.score; }, fontSize: 11, color: ink } }
      };
    }
    c.setOption({
      animation: false, tooltip: Object.assign({ formatter: function (p) { return p.name + '<br>PE(TTM,截断60): ' + p.value[0] + '<br>ROE: ' + p.value[1] + '%<br>市值: ' + p.value[2] + '亿'; } }, TOOLTIP),
      legend: { top: 4, textStyle: { color: muted } },
      grid: { top: 40, left: 50, right: 30, bottom: 50 },
      xAxis: { name: 'PE(TTM)，>60截断，亏损记45', nameLocation: 'middle', nameGap: 28, type: 'value', max: 62, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      yAxis: { name: 'ROE 2025(%)', type: 'value', min: -6, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      series: [ser('A类深研', groups.A, accent), ser('单列评级', groups.S, accent2), ser('未进入阶段2', groups.rest, '#b9b2a4')]
    });
  })();

  /* 图2：A类15家 总分vs调整后 */
  (function () {
    var c = mk('chart-top'); if (!c) return;
    var a = D.scores.filter(function (r) { return r.cls === 'A'; }).sort(function (x, y) { return y.adj - x.adj; });
    c.setOption({
      animation: false,
      tooltip: Object.assign({ trigger: 'axis', formatter: function (ps) { var n = ps[0].name; var s = a.filter(function (r) { return r.n === n; })[0]; return n + '<br>总分 ' + s.total + ' / 扣分 ' + s.ded + ' / 调整后 ' + s.adj + '<br>' + (s.reason || '无扣分'); } }, TOOLTIP),
      legend: { top: 4, textStyle: { color: muted } },
      grid: { top: 40, left: 60, right: 20, bottom: 80 },
      xAxis: { type: 'category', data: a.map(function (r) { return r.n; }), axisLabel: { rotate: 40, color: muted, fontSize: 11 }, axisLine: { lineStyle: { color: rule } } },
      yAxis: { type: 'value', max: 90, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      series: [
        { name: '六维总分', type: 'bar', barGap: '-100%', barWidth: 16, itemStyle: { color: '#cfd8e4', borderRadius: [3, 3, 0, 0] }, data: a.map(function (r) { return r.total; }) },
        { name: '风险调整后', type: 'bar', barWidth: 16, itemStyle: { color: accent, borderRadius: [3, 3, 0, 0] }, data: a.map(function (r) { return r.adj; }) }
      ]
    });
  })();

  /* 图3：六维热力图（A类15家） */
  (function () {
    var c = mk('chart-heat'); if (!c) return;
    var a = D.scores.filter(function (r) { return r.cls === 'A'; }).sort(function (x, y) { return y.adj - x.adj; });
    var dims = ['D1资源20', 'D2成本25', 'D3财务20', 'D4成长15', 'D5风险10', 'D6估值10'];
    var maxs = [20, 25, 20, 15, 10, 10];
    var data = [];
    a.forEach(function (r, yi) {
      [r.d1, r.d2, r.d3, r.d4, r.d5, r.d6].forEach(function (v, xi) {
        data.push([xi, yi, Math.round(v / maxs[xi] * 100)]);
      });
    });
    c.setOption({
      animation: false,
      tooltip: Object.assign({ formatter: function (p) { var r = a[p.value[1]]; var dim = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6'][p.value[0]]; return r.n + ' · ' + dim + '：' + [r.d1, r.d2, r.d3, r.d4, r.d5, r.d6][p.value[0]] + '分（标准化' + p.value[2] + '%）'; } }, TOOLTIP),
      grid: { top: 30, left: 90, right: 90, bottom: 60 },
      xAxis: { type: 'category', data: dims, splitArea: { show: false }, axisLabel: { color: muted, fontSize: 11 } },
      yAxis: { type: 'category', data: a.map(function (r) { return r.n; }), splitArea: { show: false }, axisLabel: { color: ink, fontSize: 11 } },
      visualMap: {
        min: 0, max: 100, calculable: false, orient: 'vertical', right: 8, top: 'center',
        textStyle: { color: muted },
        inRange: { color: ['#f5f2ea', '#d8b48c', accent2, accent] },
        outOfRange: { color: 'transparent' }
      },
      series: [{
        type: 'heatmap', data: data,
        label: { show: true, formatter: function (p) { return String(p.value[2]); }, color: ink, fontSize: 10 },
        itemStyle: { borderColor: bg2, borderWidth: 2 }
      }]
    });
  })();

  /* 图4：8家 现价vs三锚 */
  (function () {
    var c = mk('chart-anchors'); if (!c) return;
    var a = D.anchors;
    c.setOption({
      animation: false,
      tooltip: Object.assign({ trigger: 'axis', valueFormatter: function (v) { return fmt(v, 2) + ' 元'; } }, TOOLTIP),
      legend: { top: 4, textStyle: { color: muted } },
      grid: { top: 40, left: 55, right: 20, bottom: 70 },
      xAxis: { type: 'category', data: a.map(function (r) { return r.n; }), axisLabel: { rotate: 30, color: muted, fontSize: 11 }, axisLine: { lineStyle: { color: rule } } },
      yAxis: { type: 'value', name: '元/股', axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      series: [
        { name: '现价', type: 'bar', barWidth: 12, itemStyle: { color: ink }, data: a.map(function (r) { return r.price; }) },
        { name: '保守锚(mid×10)', type: 'bar', barWidth: 12, itemStyle: { color: '#cfd8e4' }, data: a.map(function (r) { return r.a1; }) },
        { name: '中性锚(mid×15)', type: 'bar', barWidth: 12, itemStyle: { color: accent }, data: a.map(function (r) { return r.a2; }) },
        { name: '乐观锚(run×15)', type: 'bar', barWidth: 12, itemStyle: { color: accent2 }, data: a.map(function (r) { return r.a3; }) }
      ]
    });
  })();

  /* 图5：风险矩阵气泡 */
  (function () {
    var c = mk('chart-bubble'); if (!c) return;
    var conclColor = { '核心优质': good, '观察': accent, '中性': accent2, '回避': bad };
    function ser(cls, name) {
      var pts = D.scores.filter(function (r) { return r.cls === cls && r.concl === name; }).map(function (r) {
        return {
          name: r.n, value: [r.d2, r.d1, r.cap || 120],
          meta: { adj: r.adj, ded: r.ded, concl: r.concl, bucket: r.b }
        };
      });
      return {
        name: cls + '-' + name, type: 'scatter', data: pts,
        symbolSize: function (v) { return Math.max(8, Math.min(46, Math.sqrt(v[2]) * 0.55)); },
        itemStyle: { color: conclColor[name] || muted, opacity: 0.72, borderColor: bg2, borderWidth: 1 },
        label: { show: true, formatter: function (p) { return p.name + (p.data.meta.ded < 0 ? '(' + p.data.meta.ded + ')' : ''); }, position: 'top', fontSize: 10, color: ink }
      };
    }
    var series = [];
    ['A', 'S'].forEach(function (cls) {
      ['核心优质', '观察', '中性', '回避'].forEach(function (k) {
        var s = ser(cls, k);
        if (s.data.length) series.push(s);
      });
    });
    c.setOption({
      animation: false,
      tooltip: Object.assign({ formatter: function (p) { var m = p.data.meta; return p.name + '（' + m.bucket + '）<br>成本维度D2: ' + p.value[0] + ' / 资源维度D1: ' + p.value[1] + '<br>市值≈' + p.value[2] + '亿 · 调整后' + m.adj + '分（' + m.concl + '）'; } }, TOOLTIP),
      legend: { top: 4, textStyle: { color: muted }, type: 'scroll' },
      grid: { top: 44, left: 55, right: 30, bottom: 55 },
      xAxis: { name: '成本竞争力D2（满分25）', nameLocation: 'middle', nameGap: 30, type: 'value', max: 26, min: 0, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      yAxis: { name: '资源禀赋D1（满分20）', type: 'value', max: 21, min: 0, axisLabel: { color: muted }, splitLine: { lineStyle: { color: rule } } },
      series: series
    });
  })();
})();
