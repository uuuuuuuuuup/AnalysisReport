(function BiliDynamicScraper() {

  var HOST_UID = '1039025435';
  var API_BASE = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space';
  var DELAY_MS = 1200;
  var MAX_PAGES = 200;

  function sleep(ms) {
    return new Promise(function(resolve) { setTimeout(resolve, ms); });
  }

  function formatTimestamp(ts) {
    if (!ts) return '';
    var d = new Date(ts * 1000);
    return d.toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit'
    });
  }

  function extractText(mod) {
    if (!mod) return '';
    var parts = [];

    if (mod.desc && mod.desc.text) {
      parts.push(mod.desc.text);
    }

    if (mod.desc && mod.desc.rich_text_nodes) {
      var richParts = [];
      var nodes = mod.desc.rich_text_nodes;
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (n.type === 'RICH_TEXT_NODE_TYPE_EMOJI') {
          richParts.push('[表情]');
        } else {
          richParts.push(n.text || '');
        }
      }
      var richText = richParts.join('');
      if (richText.length > (mod.desc.text || '').length) {
        parts[0] = richText;
      }
    }

    if (mod.major) {
      if (mod.major.archive) {
        if (mod.major.archive.title) parts.push('[视频标题] ' + mod.major.archive.title);
        if (mod.major.archive.desc) parts.push('[视频描述] ' + mod.major.archive.desc);
      }
      if (mod.major.opus) {
        if (mod.major.opus.title) parts.push('[文章标题] ' + mod.major.opus.title);
        if (mod.major.opus.summary && mod.major.opus.summary.text) {
          parts.push(mod.major.opus.summary.text);
        }
        if (mod.major.opus.paragraphs) {
          var paras = mod.major.opus.paragraphs;
          for (var j = 0; j < paras.length; j++) {
            if (paras[j].text && paras[j].text.nodes) {
              var pnodes = paras[j].text.nodes;
              for (var k = 0; k < pnodes.length; k++) {
                if (pnodes[k].word && pnodes[k].word.words) {
                  parts.push(pnodes[k].word.words);
                }
              }
            }
          }
        }
      }
    }

    return parts.filter(Boolean).join('\n');
  }

  function extractImages(mod) {
    if (!mod) return [];
    var images = [];

    if (mod.major && mod.major.draw && mod.major.draw.items) {
      var items = mod.major.draw.items;
      for (var i = 0; i < items.length; i++) {
        images.push({
          src: items[i].src,
          width: items[i].width,
          height: items[i].height,
          type: 'draw'
        });
      }
    }

    if (mod.major && mod.major.opus && mod.major.opus.pics) {
      var pics = mod.major.opus.pics;
      for (var j = 0; j < pics.length; j++) {
        images.push({
          src: pics[j].url,
          width: pics[j].width,
          height: pics[j].height,
          type: 'opus'
        });
      }
    }

    if (mod.major && mod.major.opus && mod.major.opus.paragraphs) {
      var paras = mod.major.opus.paragraphs;
      for (var p = 0; p < paras.length; p++) {
        if (paras[p].pic && paras[p].pic.pics) {
          var ppics = paras[p].pic.pics;
          for (var q = 0; q < ppics.length; q++) {
            images.push({
              src: ppics[q].url,
              width: ppics[q].width,
              height: ppics[q].height,
              type: 'opus_paragraph'
            });
          }
        }
      }
    }

    return images;
  }

  function parseDynamicItem(item) {
    if (!item) return null;
    var basic = item.basic || {};
    var modules = item.modules || {};
    var author = modules.module_author || {};
    var dynamic = modules.module_dynamic || {};
    var stat = modules.module_stat || {};
    var type = item.type || '';

    var textContent = extractText(dynamic);
    var isCharging = false;
    if (textContent.indexOf('充电专属') !== -1 || textContent.indexOf('包月充电') !== -1) {
      isCharging = true;
    }

    var likeCount = 0;
    var repostCount = 0;
    var commentCount = 0;
    if (stat.like) likeCount = stat.like.count || 0;
    if (stat.repost) repostCount = stat.repost.count || 0;
    if (stat.comment) commentCount = stat.comment.count || 0;

    var result = {
      dynamic_id: basic.rid_str || item.id_str || '',
      dynamic_type: type,
      author: author.name || '',
      author_uid: author.mid || '',
      publish_time: formatTimestamp(author.ts || basic.rid_ts),
      timestamp: author.ts || basic.rid_ts || 0,
      text: textContent,
      images: extractImages(dynamic),
      stats: { like: likeCount, repost: repostCount, comment: commentCount },
      is_charging: isCharging
    };

    return result;
  }

  async function main() {
    console.log('[BiliScraper] 开始抓取 UP主 (UID: ' + HOST_UID + ') 的动态...');
    var allDynamics = [];
    var offset = '';
    var pageNum = 0;
    var hasMore = true;

    while (hasMore && pageNum < MAX_PAGES) {
      pageNum++;
      var url = API_BASE + '?host_mid=' + HOST_UID + '&offset=' + encodeURIComponent(offset) + '&features=itemOpusStyle,opusBigCover,opusVote';

      console.log('[BiliScraper] 正在抓取第 ' + pageNum + ' 页...');

      try {
        var resp = await fetch(url, {
          credentials: 'include',
          headers: { 'Accept': 'application/json' }
        });

        if (!resp.ok) {
          console.error('[BiliScraper] 请求失败，HTTP状态: ' + resp.status);
          break;
        }

        var data = await resp.json();

        if (data.code !== 0) {
          console.error('[BiliScraper] API返回错误: code=' + data.code + ', message=' + data.message);
          if (data.code === -352) {
            console.warn('[BiliScraper] 触发风控，等待5秒后重试...');
            await sleep(5000);
            pageNum--;
            continue;
          }
          break;
        }

        var items = (data.data && data.data.items) || [];
        if (items.length === 0) {
          console.log('[BiliScraper] 本页无数据，抓取结束');
          break;
        }

        for (var i = 0; i < items.length; i++) {
          var parsed = parseDynamicItem(items[i]);
          if (parsed) allDynamics.push(parsed);
        }

        console.log('[BiliScraper] 第 ' + pageNum + ' 页获取 ' + items.length + ' 条动态，累计 ' + allDynamics.length + ' 条');

        hasMore = (data.data && data.data.has_more) || false;
        offset = (data.data && data.data.offset) || '';

        if (hasMore) await sleep(DELAY_MS);

      } catch (err) {
        console.error('[BiliScraper] 请求异常:', err);
        await sleep(3000);
        continue;
      }
    }

    console.log('[BiliScraper] 抓取完成！共获取 ' + allDynamics.length + ' 条动态');

    allDynamics.sort(function(a, b) { return b.timestamp - a.timestamp; });

    var totalImages = 0;
    var chargingCount = 0;
    for (var i = 0; i < allDynamics.length; i++) {
      totalImages += allDynamics[i].images.length;
      if (allDynamics[i].is_charging) chargingCount++;
    }
    console.log('[BiliScraper] 统计: ' + totalImages + ' 张图片, ' + chargingCount + ' 条充电专属动态');

    // 保存JSON
    var jsonData = {
      scraper_info: {
        uid: HOST_UID,
        scrape_time: new Date().toLocaleString('zh-CN'),
        total_count: allDynamics.length,
        total_images: totalImages,
        charging_count: chargingCount
      },
      dynamics: allDynamics
    };

    var jsonBlob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' });
    var jsonUrl = URL.createObjectURL(jsonBlob);
    var jsonA = document.createElement('a');
    jsonA.href = jsonUrl;
    jsonA.download = 'bilibili_dynamic_' + HOST_UID + '_' + Date.now() + '.json';
    jsonA.click();
    URL.revokeObjectURL(jsonUrl);
    console.log('[BiliScraper] JSON数据文件已下载');

    // 保存Markdown
    var mdLines = [];
    mdLines.push('# B站UP主动态备份\n');
    mdLines.push('- UID: ' + HOST_UID);
    mdLines.push('- 抓取时间: ' + new Date().toLocaleString('zh-CN'));
    mdLines.push('- 动态总数: ' + allDynamics.length);
    mdLines.push('- 图片总数: ' + totalImages);
    mdLines.push('\n---\n');

    for (var j = 0; j < allDynamics.length; j++) {
      var d = allDynamics[j];
      mdLines.push('## ' + d.publish_time);
      mdLines.push('> 类型: ' + d.dynamic_type + ' | 点赞: ' + d.stats.like + ' | 转发: ' + d.stats.repost + ' | 评论: ' + d.stats.comment + '\n');
      if (d.text) mdLines.push(d.text + '\n');
      if (d.images.length > 0) {
        mdLines.push('**图片 (' + d.images.length + ' 张):​**\n');
        for (var k = 0; k < d.images.length; k++) {
          mdLines.push('- 图片: ' + d.images[k].src + ' (' + d.images[k].width + 'x' + d.images[k].height + ')');
        }
        mdLines.push('');
      }
      mdLines.push('---\n');
    }

    var mdBlob = new Blob([mdLines.join('\n')], { type: 'text/markdown;charset=utf-8' });
    var mdUrl = URL.createObjectURL(mdBlob);
    var mdA = document.createElement('a');
    mdA.href = mdUrl;
    mdA.download = 'bilibili_dynamic_' + HOST_UID + '_' + Date.now() + '.md';
    mdA.click();
    URL.revokeObjectURL(mdUrl);
    console.log('[BiliScraper] Markdown文件已下载');

    // 保存图片索引
    var allImageUrls = [];
    for (var m = 0; m < allDynamics.length; m++) {
      var dd = allDynamics[m];
      for (var n = 0; n < dd.images.length; n++) {
        var img = dd.images[n];
        var ext = img.src.split('.').pop().split('?')[0] || 'jpg';
        allImageUrls.push({
          index: allImageUrls.length,
          url: img.src,
          dynamic_id: dd.dynamic_id,
          filename: 'img_' + dd.dynamic_id + '_' + n + '.' + ext
        });
      }
    }

    if (allImageUrls.length > 0) {
      var imgJsonBlob = new Blob([JSON.stringify(allImageUrls, null, 2)], { type: 'application/json' });
      var imgJsonUrl = URL.createObjectURL(imgJsonBlob);
      var imgA = document.createElement('a');
      imgA.href = imgJsonUrl;
      imgA.download = 'bilibili_images_index_' + HOST_UID + '_' + Date.now() + '.json';
      imgA.click();
      URL.revokeObjectURL(imgJsonUrl);
      console.log('[BiliScraper] 图片索引文件已下载');

      // 逐张下载图片
      var downloadedCount = 0;
      var failedCount = 0;

      for (var p = 0; p < allImageUrls.length; p++) {
        var imgItem = allImageUrls[p];
        try {
          var imgResp = await fetch(imgItem.url, { credentials: 'include' });
          if (imgResp.ok) {
            var imgBlobData = await imgResp.blob();
            var blobUrl = URL.createObjectURL(imgBlobData);
            var a2 = document.createElement('a');
            a2.href = blobUrl;
            a2.download = imgItem.filename;
            a2.click();
            URL.revokeObjectURL(blobUrl);
            downloadedCount++;
          } else {
            failedCount++;
            console.warn('[BiliScraper] 图片下载失败 (' + imgItem.filename + '): HTTP ' + imgResp.status);
          }
        } catch (e) {
          failedCount++;
          console.warn('[BiliScraper] 图片下载异常: ' + imgItem.filename, e);
        }

        await sleep(200);

        if ((downloadedCount + failedCount) % 50 === 0 && (downloadedCount + failedCount) > 0) {
          console.log('[BiliScraper] 图片进度: ' + (downloadedCount + failedCount) + '/' + allImageUrls.length + ' (成功' + downloadedCount + ', 失败' + failedCount + ')');
        }
      }

      console.log('[BiliScraper] 图片下载完成: 成功' + downloadedCount + ', 失败' + failedCount);
    }

    console.log('\n========================================');
    console.log('[BiliScraper] 全部完成！');
    console.log('  动态总数: ' + allDynamics.length);
    console.log('  图片总数: ' + totalImages);
    console.log('  已下载文件:');
    console.log('    1. JSON数据文件 (含完整结构化数据)');
    console.log('    2. Markdown可读文件');
    console.log('    3. 图片索引文件');
    console.log('    4. 图片文件 (逐张下载)');
    console.log('========================================\n');

    return jsonData;
  }

  return main();

})();
