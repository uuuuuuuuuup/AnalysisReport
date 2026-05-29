(async () => {
  // ==================== 配置 ====================
  const REQUEST_DELAY = 1200; // 请求间隔(ms)，避免触发限流
  const UP_MID = location.pathname.match(/\/(\d+)/)?.[1] || '1039025435'; // 自动从URL提取UP主ID

  // ==================== MD5 实现 ====================
  const md5 = (() => {
    function md5cycle(x, k) {
      let a = x[0], b = x[1], c = x[2], d = x[3];
      a = ff(a, b, c, d, k[0], 7, -680876936);
      d = ff(d, a, b, c, k[1], 12, -389564586);
      c = ff(c, d, a, b, k[2], 17, 606105819);
      b = ff(b, c, d, a, k[3], 22, -1044525330);
      a = ff(a, b, c, d, k[4], 7, -176418897);
      d = ff(d, a, b, c, k[5], 12, 1200080426);
      c = ff(c, d, a, b, k[6], 17, -1473231341);
      b = ff(b, c, d, a, k[7], 22, -45705983);
      a = ff(a, b, c, d, k[8], 7, 1770035416);
      d = ff(d, a, b, c, k[9], 12, -1958414417);
      c = ff(c, d, a, b, k[10], 17, -42063);
      b = ff(b, c, d, a, k[11], 22, -1990404162);
      a = ff(a, b, c, d, k[12], 7, 1804603682);
      d = ff(d, a, b, c, k[13], 12, -40341101);
      c = ff(c, d, a, b, k[14], 17, -1502002290);
      b = ff(b, c, d, a, k[15], 22, 1236535329);
      a = gg(a, b, c, d, k[1], 5, -165796510);
      d = gg(d, a, b, c, k[6], 9, -1069501632);
      c = gg(c, d, a, b, k[11], 14, 643717713);
      b = gg(b, c, d, a, k[0], 20, -373897302);
      a = gg(a, b, c, d, k[5], 5, -701558691);
      d = gg(d, a, b, c, k[10], 9, 38016083);
      c = gg(c, d, a, b, k[15], 14, -660478335);
      b = gg(b, c, d, a, k[4], 20, -405537848);
      a = gg(a, b, c, d, k[9], 5, 568446438);
      d = gg(d, a, b, c, k[14], 9, -1019803690);
      c = gg(c, d, a, b, k[3], 14, -187363961);
      b = gg(b, c, d, a, k[8], 20, 1163531501);
      a = gg(a, b, c, d, k[13], 5, -1444681467);
      d = gg(d, a, b, c, k[2], 9, -51403784);
      c = gg(c, d, a, b, k[7], 14, 1735328473);
      b = gg(b, c, d, a, k[12], 20, -1926607734);
      a = hh(a, b, c, d, k[5], 4, -378558);
      d = hh(d, a, b, c, k[8], 11, -2022574463);
      c = hh(c, d, a, b, k[11], 16, 1839030562);
      b = hh(b, c, d, a, k[14], 23, -35309556);
      a = hh(a, b, c, d, k[1], 4, -1530992060);
      d = hh(d, a, b, c, k[4], 11, 1272893353);
      c = hh(c, d, a, b, k[7], 16, -155497632);
      b = hh(b, c, d, a, k[10], 23, -1094730640);
      a = hh(a, b, c, d, k[13], 4, 681279174);
      d = hh(d, a, b, c, k[0], 11, -358537222);
      c = hh(c, d, a, b, k[3], 16, -722521979);
      b = hh(b, c, d, a, k[6], 23, 76029189);
      a = hh(a, b, c, d, k[9], 4, -640364487);
      d = hh(d, a, b, c, k[12], 11, -421815835);
      c = hh(c, d, a, b, k[15], 16, 530742520);
      b = hh(b, c, d, a, k[2], 23, -995338651);
      a = ii(a, b, c, d, k[0], 6, -198630844);
      d = ii(d, a, b, c, k[7], 10, 1126891415);
      c = ii(c, d, a, b, k[14], 15, -1416354905);
      b = ii(b, c, d, a, k[5], 21, -57434055);
      a = ii(a, b, c, d, k[12], 6, 1700485571);
      d = ii(d, a, b, c, k[3], 10, -1894986606);
      c = ii(c, d, a, b, k[10], 15, -1051523);
      b = ii(b, c, d, a, k[1], 21, -2054922799);
      a = ii(a, b, c, d, k[8], 6, 1873313359);
      d = ii(d, a, b, c, k[15], 10, -30611744);
      c = ii(c, d, a, b, k[6], 15, -1560198380);
      b = ii(b, c, d, a, k[13], 21, 1309151649);
      a = ii(a, b, c, d, k[4], 6, -145523070);
      d = ii(d, a, b, c, k[11], 10, -1120210379);
      c = ii(c, d, a, b, k[2], 15, 718787259);
      b = ii(b, c, d, a, k[9], 21, -343485551);
      x[0] = add32(a, x[0]);
      x[1] = add32(b, x[1]);
      x[2] = add32(c, x[2]);
      x[3] = add32(d, x[3]);
    }
    function cmn(q, a, b, x, s, t) {
      a = add32(add32(a, q), add32(x, t));
      return add32((a << s) | (a >>> (32 - s)), b);
    }
    function ff(a, b, c, d, x, s, t) { return cmn((b & c) | ((~b) & d), a, b, x, s, t); }
    function gg(a, b, c, d, x, s, t) { return cmn((b & d) | (c & (~d)), a, b, x, s, t); }
    function hh(a, b, c, d, x, s, t) { return cmn(b ^ c ^ d, a, b, x, s, t); }
    function ii(a, b, c, d, x, s, t) { return cmn(c ^ (b | (~d)), a, b, x, s, t); }
    function add32(a, b) { return (a + b) & 0xFFFFFFFF; }
    function md5blk(s) {
      const md5blks = [];
      for (let i = 0; i < 64; i += 4)
        md5blks[i >> 2] = s.charCodeAt(i) + (s.charCodeAt(i+1) << 8) + (s.charCodeAt(i+2) << 16) + (s.charCodeAt(i+3) << 24);
      return md5blks;
    }
    const hex_chr = '0123456789abcdef';
    function rhex(n) {
      let s = '';
      for (let j = 0; j < 4; j++)
        s += hex_chr[(n >> (j * 8 + 4)) & 0x0F] + hex_chr[(n >> (j * 8)) & 0x0F];
      return s;
    }
    function hex(x) { return x.map(rhex).join(''); }
    return function(str) {
      // UTF-8编码
      str = unescape(encodeURIComponent(str));
      const n = str.length;
      let state = [1732584193, -271733879, -1732584194, 271733878];
      let i;
      for (i = 64; i <= n; i += 64)
        md5cycle(state, md5blk(str.substring(i - 64, i)));
      str = str.substring(i - 64);
      const tail = new Array(16).fill(0);
      for (i = 0; i < str.length; i++)
        tail[i >> 2] |= str.charCodeAt(i) << ((i % 4) << 3);
      tail[i >> 2] |= 0x80 << ((i % 4) << 3);
      if (i > 55) { md5cycle(state, tail); tail.fill(0); }
      tail[14] = n * 8;
      md5cycle(state, tail);
      return hex(state);
    };
  })();

  // ==================== WBI 签名 ====================
  const MIXIN_KEY_ENC_TAB = [
    46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,
    27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,16,
    55,37,36,7,20,59,44,40,11,25,30,52,21,57,54,6,
    48,24,1,22,26,51,34,17,4,0,13,56,52,27,6,48
  ];

  function getMixinKey(raw) {
    let result = '';
    for (let i = 0; i < 32; i++) result += raw[MIXIN_KEY_ENC_TAB[i]];
    return result;
  }

  function signWbi(params, imgKey, subKey) {
    const mixinKey = getMixinKey(imgKey + subKey);
    params = { ...params, wts: Math.floor(Date.now() / 1000) };
    // 过滤特殊字符
    const filteredParams = {};
    for (const k in params) {
      const v = String(params[k]);
      if (/[!'()*]/.test(v)) continue;
      filteredParams[k] = v;
    }
    const query = Object.keys(filteredParams).sort().map(k =>
      encodeURIComponent(k) + '=' + encodeURIComponent(filteredParams[k])
    ).join('&');
    params.w_rid = md5(query + mixinKey);
    return params;
  }

  // ==================== 工具函数 ====================
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  async function fetchJSON(url, extraHeaders = {}) {
    const resp = await fetch(url, {
      credentials: 'include',
      headers: {
        'Referer': 'https://www.bilibili.com',
        ...extraHeaders
      }
    });
    const json = await resp.json();
    if (json.code !== 0) throw new Error('API错误[' + json.code + ']: ' + (json.message || ''));
    return json.data;
  }

  // ==================== API 调用 ====================
  async function getWbiKeys() {
    const data = await fetchJSON('https://api.bilibili.com/x/web-interface/nav');
    const imgKey = data.wbi_img.img_url.split('/').pop().split('.')[0];
    const subKey = data.wbi_img.sub_url.split('/').pop().split('.')[0];
    return { imgKey, subKey };
  }

  async function getAllVideos(imgKey, subKey) {
    const videos = [];
    let page = 1;
    while (true) {
      const params = signWbi({ mid: UP_MID, pn: page, ps: 30, order: 'pubdate' }, imgKey, subKey);
      const qs = new URLSearchParams(params).toString();
      const data = await fetchJSON(
        'https://api.bilibili.com/x/space/wbi/arc/search?' + qs,
        { 'Referer': 'https://space.bilibili.com/' + UP_MID + '/' }
      );
      const list = data.list.vlist;
      for (const v of list) videos.push({ bvid: v.bvid, title: v.title });
      const total = data.page.count;
      console.log('  📄 第' + page + '页: ' + list.length + '个 (累计' + videos.length + '/' + total + ')');
      if (page * 30 >= total) break;
      page++;
      await sleep(REQUEST_DELAY);
    }
    return videos;
  }

  async function getVideoCid(bvid) {
    const data = await fetchJSON(`https://api.bilibili.com/x/web-interface/view?bvid=${bvid}`);
    // 如果有多P，返回所有分P的cid
    return data.pages.map(p => ({ cid: p.cid, part: p.part }));
  }

  async function getSubtitleUrls(bvid, cid, imgKey, subKey) {
    const params = signWbi({ bvid: bvid, cid: cid }, imgKey, subKey);
    const qs = new URLSearchParams(params).toString();
    const data = await fetchJSON('https://api.bilibili.com/x/player/wbi/v2?' + qs);
    return data.subtitle?.subtitles || [];
  }

  async function downloadSubtitle(url) {
    if (url.startsWith('//')) url = 'https:' + url;
    const resp = await fetch(url);
    const json = await resp.json();
    // 返回带时间戳的字幕和纯文本
    const withTime = json.body.map(item => ({
      from: +item.from.toFixed(2),
      to: +item.to.toFixed(2),
      content: item.content
    }));
    const plainText = json.body.map(item => item.content).join('\n');
    return { withTime, plainText };
  }

  // ==================== 主流程 ====================
  console.log('%c🚀 B站字幕批量抓取脚本启动', 'font-size:16px;font-weight:bold;color:#00a1d6');
  console.log(`🎯 UP主ID: ${UP_MID}`);

  // Step 1: 获取WBI密钥
  console.log('🔑 正在获取WBI密钥...');
  let imgKey, subKey;
  try {
    ({ imgKey, subKey } = await getWbiKeys());
    console.log('✅ WBI密钥获取成功');
  } catch (e) {
    console.error('❌ 获取WBI密钥失败，请确认已登录B站:', e.message);
    return;
  }

  // Step 2: 获取视频列表
  console.log('📋 正在获取视频列表...');
  let videos;
  try {
    videos = await getAllVideos(imgKey, subKey);
    console.log(`✅ 共获取到 ${videos.length} 个视频\n`);
  } catch (e) {
    console.error('❌ 获取视频列表失败:', e.message);
    return;
  }

  // Step 3: 逐个获取字幕
  const results = [];
  let successCount = 0, noSubCount = 0, errorCount = 0;
  const startTime = Date.now();

  for (let i = 0; i < videos.length; i++) {
    const v = videos[i];
    const pct = ((i + 1) / videos.length * 100).toFixed(1);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(0);
    console.log(`🎬 [${i+1}/${videos.length}] (${pct}%, ${elapsed}s) ${v.title}`);

    try {
      // 获取cid（可能有多个分P）
      const pages = await getVideoCid(v.bvid);
      await sleep(600);

      const allSubtitles = [];
      for (const page of pages) {
        const subs = await getSubtitleUrls(v.bvid, page.cid, imgKey, subKey);
        await sleep(600);

        if (subs.length === 0) continue;

        for (const sub of subs) {
          try {
            const subtitleData = await downloadSubtitle(sub.subtitle_url);
            allSubtitles.push({
              part: pages.length > 1 ? page.part : undefined,
              lang: sub.lang_doc,
              lang_code: sub.lang,
              is_ai: sub.type === 1,
              text: subtitleData.plainText,
              detail: subtitleData.withTime
            });
            await sleep(400);
          } catch (e2) {
            console.log(`  ⚠️ 字幕下载失败: ${e2.message}`);
          }
        }
      }

      if (allSubtitles.length === 0) {
        noSubCount++;
        console.log('  ⚠️ 无字幕');
        results.push({ bvid: v.bvid, title: v.title, subtitle: null });
      } else {
        successCount++;
        console.log(`  ✅ ${allSubtitles.length}条字幕`);
        results.push({ bvid: v.bvid, title: v.title, subtitles: allSubtitles });
      }
    } catch (e) {
      errorCount++;
      console.log(`  ❌ 错误: ${e.message}`);
      results.push({ bvid: v.bvid, title: v.title, error: e.message });
    }
  }

  // ==================== 输出结果 ====================
  const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log('\n' + '%c📊 抓取完成！', 'font-size:14px;font-weight:bold;color:#00a1d6');
  console.log(`⏱️ 总耗时: ${totalTime}s`);
  console.log(`✅ 成功: ${successCount} | ⚠️ 无字幕: ${noSubCount} | ❌ 失败: ${errorCount}`);
  console.log('💾 结果已保存至 window.__bilibiliSubtitles');

  // 存入全局变量，方便后续操作
  window.__bilibiliSubtitles = results;

  // 自动下载JSON文件
  const jsonStr = JSON.stringify(results, null, 2);
  const blob = new Blob([jsonStr], { type: 'application/json' });
  const dlUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = dlUrl;
  a.download = `bilibili_${UP_MID}_subtitles.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(dlUrl);
  console.log('📁 JSON文件已自动下载');

  // 额外生成纯文本版
  const textLines = results.filter(r => r.subtitles).map(r => {
    const header = `========== ${r.title} (${r.bvid}) ==========`;
    const body = r.subtitles.map(s => {
      const tag = s.is_ai ? '[AI字幕]' : '[手动字幕]';
      const partTag = s.part ? ` [${s.part}]` : '';
      return `${tag}${partTag} ${s.lang}\n${s.text}`;
    }).join('\n\n');
    return header + '\n' + body;
  }).join('\n\n\n');

  const textBlob = new Blob([textLines], { type: 'text/plain;charset=utf-8' });
  const textDlUrl = URL.createObjectURL(textBlob);
  const a2 = document.createElement('a');
  a2.href = textDlUrl;
  a2.download = `bilibili_${UP_MID}_subtitles.txt`;
  document.body.appendChild(a2);
  a2.click();
  document.body.removeChild(a2);
  URL.revokeObjectURL(textDlUrl);
  console.log('📄 纯文本文件已自动下载');
})();
