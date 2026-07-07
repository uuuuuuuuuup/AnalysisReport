# B站批量字幕提取器优化设计

## 背景

`bilibili-subtitle-extractor` 是一个 Chrome 扩展，用于从 UP 主空间搜索页批量收集视频，并自动逐个打开视频页提取字幕。当前存在两个体验问题：

1. 没有字幕的视频会等待 60 秒超时后才跳到下一个。
2. 收集到视频后无法选择只处理某一段范围。

## 目标

1. 当视频没有字幕时，立即跳过，不再等待超时。
2. 在收集到视频数量后，允许用户设置 `start` 到 `end` 的处理范围（1-based，包含边界）。
3. 进度展示中单独显示被跳过的视频数量。

## 设计方案（方案一）

### 核心思路

保持现有架构不变，在 `injected.js` 里增加“无字幕立即上报”的能力；在 `popup.js/html/css` 里增加范围选择；在 `background.js` 里对 `no_subtitle` 快速处理；在 `popup.js` 里更新进度文案。

### 涉及文件

- `popup.html`
- `popup.js`
- `popup.css`
- `injected.js`
- `background.js`

### 详细改动

#### 1. `injected.js` — 无字幕立即上报

`autoTriggerSubtitle()` 返回值改为带状态：

- 找不到播放器区域 → 仍由 60 秒超时兜底。
- 找不到字幕按钮 → `reportDone(false, 'no_subtitle')`。
- 找到字幕按钮但无中文选项 → `reportDone(false, 'no_subtitle')`。

新增 `reported` 标记，防止 60 秒超时保护在已上报后再次触发。

#### 2. `background.js` — 快速跳过无字幕视频

`handleSubtitleCaptured()` 中：

- 若 `result.ok === false && result.error === 'no_subtitle'`：
  - 等待 500ms。
  - 当前队列项标记为 `done: true`、`ok: false`、`error: 'no_subtitle'`。
  - 直接打开下一个视频。
- 其他失败仍按原逻辑等待 1000ms 后继续。

#### 3. `popup.html` — 范围输入区

在 `collectResult` 与 `btnStart` 之间插入：

```html
<div id="rangePanel" style="display:none;">
  <label>范围
    <input type="number" id="rangeStart" min="1" value="1">
    到
    <input type="number" id="rangeEnd" min="1" value="1">
  </label>
  <div class="hint">包含首尾，1 表示第 1 个视频</div>
</div>
```

#### 4. `popup.js` — 范围校验、切片、进度展示

收集成功后：

- 记录完整列表。
- 显示 `rangePanel`。
- 默认 `start=1`，`end=collectedList.length`。

点击“开始批量提取字幕”时：

- 校验 `start`、`end` 为有效整数，无效则使用默认值。
- 自动 clamp 到 `[1, N]`。
- 若 `start > end` 则交换。
- 使用 `collectedList.slice(start - 1, end)` 生成子队列传给 `startBatch`。

进度更新：

- `done = batch.queue.filter(i => i.done).length`
- `skipped = batch.queue.filter(i => i.done && i.error === 'no_subtitle').length`
- 文案：`进度：8/20 | 跳过 3 个 | 当前：视频标题`

#### 5. `popup.css` — 输入框样式

为 `#rangePanel` 和输入框增加轻量样式，保持现有浅色风格。

## 数据流

1. 用户在空间页点击“收集本页视频”。
2. `content.js` 返回完整列表。
3. `popup.js` 显示总数，并展示范围输入框。
4. 用户设置范围后点击“开始批量提取字幕”。
5. `popup.js` 切片，把子队列发送给 `background.js`。
6. `background.js` 逐个打开视频页（带 `__subtitle_batch=1`）。
7. `content.js` 注入 `injected.js`。
8. `injected.js` 自动触发字幕：
   - 有字幕 → 拦截并下载，上报成功。
   - 无字幕 → 上报 `no_subtitle`。
9. `background.js` 收到结果后更新队列，继续下一个。
10. 全部完成后关闭批量标签页，`popup.js` 显示完成。

## 错误处理

| 场景 | 行为 |
|---|---|
| 输入非数字或为空 | 使用默认值 `1` 和 `N` |
| `start`/`end` 越界 | clamp 到 `[1, N]` |
| `start > end` | 自动交换 |
| 视频无字幕 | 不弹错误，计入“跳过” |

## 测试要点

- 空间页收集后，范围输入默认值为 `1` 到 `N`。
- 输入 `10` 到 `15`，实际处理第 10、11、12、13、14、15 个视频。
- 遇到无字幕视频时，不应等待 60 秒，应快速进入下一个。
- 进度文案正确显示已完成数和跳过数。
- 范围输入非法时，能自动修正或给出明确提示。

## 风险与注意事项

- B 站播放器 UI 可能变化，导致字幕按钮选择器失效。当前选择器已做多个兜底，后续如失效需同步更新。
- 无字幕判定依赖页面 DOM，若播放器加载极慢，可能先进入超时逻辑。保持 60 秒超时兜底不变。
- 范围选择仅影响本次启动的批量任务，不影响已保存的队列。
