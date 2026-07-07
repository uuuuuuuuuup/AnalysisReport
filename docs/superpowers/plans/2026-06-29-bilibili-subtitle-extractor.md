# B站批量字幕提取器优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 B 站批量字幕提取器增加“无字幕视频立即跳过”和“收集后设置处理范围”两个功能。

**Architecture：** 保持现有 `popup/content/background/injected` 四层架构不变；无字幕判定下沉到 `injected.js`，由 `background.js` 快速切下一个视频；范围选择放在 `popup.js/html/css` 中，在启动前对收集列表做切片。

**Tech Stack：** Chrome Extension Manifest V3、原生 JavaScript、CSS。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `/Users/apple/Downloads/bilibili-subtitle-extractor/injected.js` | 页面主世界脚本，自动点击字幕按钮并拦截字幕请求；本次新增无字幕立即上报。 |
| `/Users/apple/Downloads/bilibili-subtitle-extractor/background.js` | Service Worker 管理批量队列；本次新增对 `no_subtitle` 的快速跳过。 |
| `/Users/apple/Downloads/bilibili-subtitle-extractor/popup.html` | 弹出面板 HTML；本次新增范围输入区。 |
| `/Users/apple/Downloads/bilibili-subtitle-extractor/popup.js` | 弹出面板逻辑；本次新增范围校验/切片、跳过数展示。 |
| `/Users/apple/Downloads/bilibili-subtitle-extractor/popup.css` | 弹出面板样式；本次新增范围输入区样式。 |

---

## Task 1: `injected.js` 增加无字幕立即上报

**Files:**
- Modify: `/Users/apple/Downloads/bilibili-subtitle-extractor/injected.js`

- [ ] **Step 1: 在文件顶部增加 `reported` 标记**

在 `let hasDownloaded = false;` 下一行添加：

```javascript
let reported = false;
```

- [ ] **Step 2: 修改 `reportDone` 函数，设置 `reported` 标记**

将现有函数替换为：

```javascript
function reportDone(ok, error) {
    if (reported) return;
    reported = true;
    window.postMessage({
        type: 'BILI_SUBTITLE_BATCH_DONE',
        ok: ok,
        error: error || '',
        bv: getBV(),
        title: getVideoTitle(),
        batchId: BATCH_ID
    }, '*');
}
```

- [ ] **Step 3: 修改 60 秒超时保护，避免重复上报**

将：

```javascript
setTimeout(() => {
    if (!hasDownloaded) {
        console.warn('⏰ 字幕提取超时');
        reportDone(false, 'timeout');
    }
}, 60000);
```

改为：

```javascript
setTimeout(() => {
    if (!hasDownloaded && !reported) {
        console.warn('⏰ 字幕提取超时');
        reportDone(false, 'timeout');
    }
}, 60000);
```

- [ ] **Step 4: 修改 `autoTriggerSubtitle`，无字幕时立即返回并上报**

将 `autoTriggerSubtitle` 函数整体替换为：

```javascript
async function autoTriggerSubtitle() {
    console.log('🤖 自动触发字幕加载...');

    // 等待播放器区域出现
    const videoArea = await waitForElement(() => {
        return document.querySelector('.bpx-player-container') ||
               document.querySelector('.player-container') ||
               document.querySelector('#bilibili-player');
    }, 15000);

    if (!videoArea) {
        console.warn('⚠️ 未找到播放器区域');
        return false;
    }

    // 触发控制栏显示
    videoArea.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
    videoArea.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    await sleep(800);

    // 等待并找字幕按钮
    const subtitleBtn = await waitForElement(() => {
        return document.querySelector('.bpx-player-ctrl-subtitle') ||
               document.querySelector('.player-ctrl-subtitle') ||
               document.querySelector('[aria-label*="字幕"]') ||
               document.querySelector('[text="字幕"]');
    }, 15000);

    if (!subtitleBtn) {
        console.warn('⚠️ 未找到字幕按钮，判定为无字幕');
        reportDone(false, 'no_subtitle');
        return false;
    }

    console.log('✅ 找到字幕按钮');

    // 先 hover，再 click，确保菜单展开
    subtitleBtn.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    subtitleBtn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    await sleep(400);
    subtitleBtn.click();
    await sleep(800);

    // 等待中文选项出现
    const chineseOption = await waitForElement(() => {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const text = (el.textContent || '').trim();
            if ((text === '中文' ||
                 text.includes('中文（自动生成）') ||
                 text.includes('中文(自动生成)') ||
                 text.includes('AI 生成')) &&
                el.getBoundingClientRect().width > 0 &&
                el.getBoundingClientRect().height > 0) {
                return el;
            }
        }
        return null;
    }, 10000);

    if (chineseOption) {
        console.log('✅ 自动点击中文字幕');
        chineseOption.click();
        return true;
    }

    console.log('💡 未找到中文选项，判定为无字幕');
    reportDone(false, 'no_subtitle');
    return false;
}
```

- [ ] **Step 5: 验证改动**

检查点：
- 文件顶部有 `let reported = false;`。
- `reportDone` 第一行判断 `if (reported) return;` 并设置 `reported = true;`。
- 超时保护判断条件包含 `&& !reported`。
- `autoTriggerSubtitle` 在“找不到字幕按钮”和“未找到中文选项”两个分支都调用了 `reportDone(false, 'no_subtitle')`。

- [ ] **Step 6: 提交**

```bash
cd /Users/apple/Downloads/bilibili-subtitle-extractor
git add injected.js
git commit -m "feat(injected): 无字幕视频立即上报 no_subtitle，避免等待超时"
```

---

## Task 2: `background.js` 对 `no_subtitle` 快速跳过

**Files:**
- Modify: `/Users/apple/Downloads/bilibili-subtitle-extractor/background.js`

- [ ] **Step 1: 修改 `handleSubtitleCaptured` 函数**

将现有函数整体替换为：

```javascript
async function handleSubtitleCaptured(result) {
    const data = await chrome.storage.local.get(STORAGE_KEY);
    const batch = data[STORAGE_KEY];
    if (!batch || batch.status !== 'running') return;

    const idx = batch.currentIndex;
    if (idx >= 0 && idx < batch.queue.length) {
        batch.queue[idx].done = true;
        batch.queue[idx].ok = result.ok;
        batch.queue[idx].error = result.error || '';
    }

    await chrome.storage.local.set({ [STORAGE_KEY]: batch });

    // 无字幕时快速跳过，成功时多等一下下载触发
    const isNoSubtitle = !result.ok && result.error === 'no_subtitle';
    await sleep(result.ok ? 2500 : (isNoSubtitle ? 500 : 1000));

    // 处理下一个
    await openNextVideo(idx + 1);
}
```

- [ ] **Step 2: 验证改动**

检查点：
- 新增 `const isNoSubtitle = !result.ok && result.error === 'no_subtitle';`。
- `sleep` 参数为 `result.ok ? 2500 : (isNoSubtitle ? 500 : 1000)`。

- [ ] **Step 3: 提交**

```bash
cd /Users/apple/Downloads/bilibili-subtitle-extractor
git add background.js
git commit -m "feat(background): 收到 no_subtitle 时快速跳过无字幕视频"
```

---

## Task 3: `popup.html` 增加范围输入区

**Files:**
- Modify: `/Users/apple/Downloads/bilibili-subtitle-extractor/popup.html`

- [ ] **Step 1: 在 `collectResult` 和 `btnStart` 之间插入范围面板**

将：

```html
            <button id="btnCollect">收集本页视频</button>
            <div id="collectResult" class="result"></div>
            <button id="btnStart" class="btn-primary" disabled>开始批量提取字幕</button>
```

改为：

```html
            <button id="btnCollect">收集本页视频</button>
            <div id="collectResult" class="result"></div>

            <div id="rangePanel" class="range-panel" style="display:none;">
                <div class="label">处理范围（包含首尾）</div>
                <div class="range-inputs">
                    <input type="number" id="rangeStart" min="1" value="1">
                    <span>到</span>
                    <input type="number" id="rangeEnd" min="1" value="1">
                </div>
                <div class="hint">1 表示第 1 个视频</div>
            </div>

            <button id="btnStart" class="btn-primary" disabled>开始批量提取字幕</button>
```

- [ ] **Step 2: 验证改动**

检查点：
- `rangePanel` 默认 `style="display:none;"`。
- 包含 `rangeStart`、`rangeEnd` 两个 `number` 输入框。

- [ ] **Step 3: 提交**

```bash
cd /Users/apple/Downloads/bilibili-subtitle-extractor
git add popup.html
git commit -m "feat(popup): 增加范围选择输入区"
```

---

## Task 4: `popup.js` 增加范围校验、切片和跳过数展示

**Files:**
- Modify: `/Users/apple/Downloads/bilibili-subtitle-extractor/popup.js`

- [ ] **Step 1: 获取 DOM 引用**

在 `let currentTabId = null;` 和 `let collectedList = [];` 之后添加：

```javascript
    const rangePanel = document.getElementById('rangePanel');
    const rangeStart = document.getElementById('rangeStart');
    const rangeEnd = document.getElementById('rangeEnd');
```

- [ ] **Step 2: 在收集成功后显示范围面板并设置默认值**

将 `btnCollect` 的事件监听中：

```javascript
            collectedList = res.list || [];
            collectResult.textContent = `共收集到 ${collectedList.length} 个视频`;
            if (collectedList.length > 0) {
                btnStart.disabled = false;
            }
```

改为：

```javascript
            collectedList = res.list || [];
            collectResult.textContent = `共收集到 ${collectedList.length} 个视频`;
            if (collectedList.length > 0) {
                btnStart.disabled = false;
                rangePanel.style.display = 'block';
                rangeStart.value = 1;
                rangeStart.max = collectedList.length;
                rangeEnd.value = collectedList.length;
                rangeEnd.max = collectedList.length;
            } else {
                rangePanel.style.display = 'none';
            }
```

- [ ] **Step 3: 在 `btnStart` 点击时校验并切片**

将 `btnStart` 的事件监听整体替换为：

```javascript
    btnStart.addEventListener('click', () => {
        if (collectedList.length === 0) return;

        let start = parseInt(rangeStart.value, 10);
        let end = parseInt(rangeEnd.value, 10);
        const total = collectedList.length;

        if (!Number.isFinite(start) || start < 1) start = 1;
        if (!Number.isFinite(end) || end < 1) end = total;
        if (start > total) start = total;
        if (end > total) end = total;
        if (start > end) {
            const tmp = start;
            start = end;
            end = tmp;
        }

        const queue = collectedList.slice(start - 1, end);
        if (queue.length === 0) {
            setGlobalStatus('范围无效，未选择任何视频', 'error');
            return;
        }

        btnStart.disabled = true;
        btnStart.textContent = '启动中...';

        chrome.runtime.sendMessage({
            action: 'startBatch',
            queue: queue
        }, (res) => {
            if (!res || !res.ok) {
                setGlobalStatus('启动失败：' + (res?.error || ''), 'error');
                btnStart.disabled = false;
                btnStart.textContent = '开始批量提取字幕';
                return;
            }

            batchPanel.style.display = 'block';
            setGlobalStatus('批量任务已启动', 'success');
            startPolling();
        });
    });
```

- [ ] **Step 4: 修改进度展示，增加跳过数**

将 `updateBatchUI` 函数整体替换为：

```javascript
    function updateBatchUI(batch) {
        const total = batch.queue.length;
        const done = batch.queue.filter(item => item.done).length;
        const skipped = batch.queue.filter(item => item.done && item.error === 'no_subtitle').length;
        const percent = total > 0 ? (done / total * 100) : 0;

        progressFill.style.width = percent + '%';

        let currentTitle = '';
        if (batch.currentIndex >= 0 && batch.currentIndex < total) {
            currentTitle = batch.queue[batch.currentIndex].title || batch.queue[batch.currentIndex].bv;
        }

        batchStatus.textContent = `进度：${done}/${total} | 跳过 ${skipped} 个 | 当前：${currentTitle || '准备中'}`;
    }
```

- [ ] **Step 5: 验证改动**

检查点：
- 文件开头获取了 `rangePanel`、`rangeStart`、`rangeEnd`。
- 收集成功后显示 `rangePanel` 并设置 `min/max/value`。
- `btnStart` 点击时校验范围、自动修正越界/逆序、切片后发送。
- `updateBatchUI` 计算 `skipped` 并显示在进度文案中。

- [ ] **Step 6: 提交**

```bash
cd /Users/apple/Downloads/bilibili-subtitle-extractor
git add popup.js
git commit -m "feat(popup): 支持设置处理范围并在进度中显示跳过数"
```

---

## Task 5: `popup.css` 增加范围面板样式

**Files:**
- Modify: `/Users/apple/Downloads/bilibili-subtitle-extractor/popup.css`

- [ ] **Step 1: 在文件末尾追加样式**

```css
.range-panel {
    margin: 10px 0;
    padding: 10px;
    background: #f9f9f9;
    border-radius: 8px;
    font-size: 13px;
}

.range-panel .label {
    margin-bottom: 6px;
    color: #333;
}

.range-inputs {
    display: flex;
    align-items: center;
    gap: 8px;
}

.range-inputs input {
    width: 60px;
    padding: 6px;
    border: 1px solid #ddd;
    border-radius: 4px;
    text-align: center;
    font-size: 13px;
}

.range-panel .hint {
    margin-top: 6px;
    font-size: 11px;
    color: #888;
}
```

- [ ] **Step 2: 验证改动**

检查点：
- 新样式不影响原有 `.label` 样式（`.range-panel .label` 是限定选择器）。
- 输入框宽度适中、居中对齐。

- [ ] **Step 3: 提交**

```bash
cd /Users/apple/Downloads/bilibili-subtitle-extractor
git add popup.css
git commit -m "style(popup): 增加范围输入区样式"
```

---

## Task 6: 手动验证

**Files:**
- N/A

- [ ] **Step 1: 刷新扩展**

1. 打开 Chrome `chrome://extensions/`。
2. 找到“B站批量字幕提取器”。
3. 点击刷新按钮。

- [ ] **Step 2: 验证范围选择**

1. 打开一个 UP 主空间搜索页，例如 `https://space.bilibili.com/322005137/search?keyword=直播`。
2. 点击扩展图标，点击“收集本页视频”。
3. 预期：弹出面板显示 `共收集到 N 个视频`，并出现“处理范围”输入框，默认 `1` 到 `N`。
4. 修改为 `10` 到 `15`，点击“开始批量提取字幕”。
5. 预期：后台只打开第 10 到第 15 个视频（共 6 个）。

- [ ] **Step 3: 验证无字幕跳过**

1. 在批量队列中确保包含至少一个已知没有字幕的视频。
2. 预期：该视频打开后，很快就跳到下一个，不会卡住 60 秒。
3. 进度文案预期：`进度：X/Y | 跳过 Z 个 | 当前：...`

- [ ] **Step 4: 验证边界非法输入**

1. 重新收集视频。
2. 尝试输入：`开始=20，结束=5`（假设总数 ≥20）。
3. 预期：自动交换为 5 到 20，处理第 5 到第 20 个视频。
4. 尝试输入：`开始=0，结束=999`。
5. 预期：自动修正为 `1` 到 `N`。

- [ ] **Step 5: 验证正常有字幕视频**

1. 选择一段包含已知有字幕视频的范围。
2. 预期：字幕文件正常下载，进度正常推进，任务完成后批量标签页关闭。

---

## 自我审查

| 需求 | 覆盖任务 |
|---|---|
| 无字幕视频立即跳过 | Task 1（检测并上报）、Task 2（快速跳过） |
| 收集后设置 start/end 范围 | Task 3（UI）、Task 4（校验切片） |
| 范围包含边界 | Task 4 使用 `slice(start - 1, end)` |
| 进度显示跳过数 | Task 4 `updateBatchUI` |
| 样式保持统一 | Task 5 |
| 手动验证 | Task 6 |

无占位符，所有改动均给出完整代码。
