# 投资报告展示网站 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `稳健投资策略分析报告/website/` 下构建一个 Vue 3 杂志风展示网站，从 200+ 份 Markdown 分析报告中自动提取数据并展示。

**Architecture:** 构建脚本 → JSON 数据 → Vue 3 SPA。构建时 Node.js 脚本扫描报告目录提取元数据与全文，生成静态 JSON。前端 Vue Router 驱动三个页面：首页表格、个股详情、汇总专题。Tailwind CSS 实现明亮杂志风排版。

**Tech Stack:** Vue 3 + Vite + Vue Router + Tailwind CSS v4 + marked

---

## 文件结构

```
website/
├── index.html                          # Vite 入口 HTML
├── package.json
├── vite.config.js
├── src/
│   ├── main.js                         # Vue 应用入口
│   ├── App.vue                         # 根组件（布局壳）
│   ├── style.css                       # Tailwind + 全局样式 + 字体
│   ├── router.js                       # 路由配置
│   ├── views/
│   │   ├── HomePage.vue                # 首页：表格 + 筛选 + 分页
│   │   ├── StockDetail.vue             # 个股详情：报告渲染
│   │   └── SummaryPage.vue             # 汇总报告列表
│   ├── components/
│   │   ├── NavBar.vue                  # 顶部导航栏
│   │   ├── FilterBar.vue               # 评级筛选按钮组
│   │   ├── StockTable.vue              # 股票数据表格
│   │   ├── Pagination.vue              # 分页组件
│   │   ├── ReportRenderer.vue          # Markdown → HTML 渲染
│   │   └── FooterBar.vue               # 页脚
│   └── utils/
│       └── classify.js                 # 评级分类逻辑
├── scripts/
│   └── build-data.js                   # 构建脚本：扫描报告 → JSON
└── public/
    └── data/                           # 构建生成（gitignore）
        ├── stocks.json
        └── summaries.json
```

---

### Task 1: 项目脚手架

**Files:**
- Create: `website/package.json`
- Create: `website/vite.config.js`
- Create: `website/index.html`
- Create: `website/src/main.js`
- Create: `website/src/App.vue`
- Create: `website/src/style.css`
- Create: `website/src/router.js`
- Create: `website/.gitignore`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "investment-report-site",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build-data": "node scripts/build-data.js",
    "build": "npm run build-data && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "marked": "^15.0.0",
    "vue": "^3.5.0",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "vite": "^6.2.0",
    "@vitejs/plugin-vue": "^5.2.0"
  }
}
```

- [ ] **Step 2: 创建 vite.config.js**

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: './',
  build: {
    outDir: 'dist',
  },
})
```

- [ ] **Step 3: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>稳健投资策略分析报告</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
</head>
<body class="font-body bg-warm">
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 4: 创建 src/main.js**

```js
import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import './style.css'

createApp(App).use(router).mount('#app')
```

- [ ] **Step 5: 创建 src/style.css**

```css
@import "tailwindcss";

@theme {
  --font-heading: "DM Sans", sans-serif;
  --font-body: "Newsreader", serif;
  --font-mono: "JetBrains Mono", monospace;
  --color-warm: #faf7f2;
  --color-warm-deep: #f0ebe0;
  --color-ink: #1c1c1c;
  --color-ink-light: #5c5c5c;
  --color-accent: #1a3a4a;
  --color-success: #2d6a4f;
  --color-warn: #b5841b;
  --color-danger: #a13d3d;
}

body {
  @apply bg-warm text-ink antialiased;
  font-family: var(--font-body);
}

h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-heading);
}
```

- [ ] **Step 6: 创建 src/App.vue**

```vue
<template>
  <div class="min-h-screen flex flex-col">
    <NavBar />
    <main class="flex-1">
      <router-view />
    </main>
    <FooterBar />
  </div>
</template>

<script setup>
import NavBar from './components/NavBar.vue'
import FooterBar from './components/FooterBar.vue'
</script>
```

- [ ] **Step 7: 创建 src/router.js**

```js
import { createRouter, createWebHashHistory } from 'vue-router'
import HomePage from './views/HomePage.vue'
import StockDetail from './views/StockDetail.vue'
import SummaryPage from './views/SummaryPage.vue'

const routes = [
  { path: '/', name: 'home', component: HomePage },
  { path: '/stock/:symbol', name: 'stock', component: StockDetail },
  { path: '/summary', name: 'summary', component: SummaryPage },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
```

- [ ] **Step 8: 创建 .gitignore**

```
node_modules/
dist/
public/data/
```

- [ ] **Step 9: 安装依赖并验证**

```bash
cd website && npm install && npm run dev
```

Expected: Vite 开发服务器启动成功，空白页面渲染。

---

### Task 2: 评级分类工具函数

**Files:**
- Create: `website/src/utils/classify.js`

- [ ] **Step 1: 创建 classify.js**

```js
const RULES = [
  {
    rating: 'build',
    label: '建仓',
    keywords: [
      '可建底仓', '可买入', '可适度配置', '建议配置',
      '高优先级观察', '中等仓位', '可逢低建仓', '建议配置',
      '可建立底仓', '可适度配置（中等仓位）',
    ],
  },
  {
    rating: 'watch',
    label: '观察',
    keywords: [
      '中优先级观察', '低优先级观察', '观察', '建议观察',
      '谨慎观察', '观察级', '低仓位观察', '低配',
    ],
  },
  {
    rating: 'avoid',
    label: '不建议',
    keywords: [
      '不建议买入', '否决', '不建议投资', '不建仓',
      '不建议', '不建仓/低优先级观察',
    ],
  },
]

/**
 * 从结论文本中提取评级
 * @param {string} text - 报告第一行结论文本
 * @returns {{ rating: string, label: string }}
 */
export function classifyConclusion(text) {
  if (!text) return { rating: 'unknown', label: '待分类' }
  // 去掉 markdown 格式符号，提取纯文本
  const clean = text
    .replace(/^[>\s#*-]*\s*/, '')
    .replace(/\*\*/g, '')
    .replace(/⚠️/g, '')
    .replace(/❌/g, '')
    .trim()
  for (const rule of RULES) {
    for (const kw of rule.keywords) {
      if (clean.includes(kw)) {
        return { rating: rule.rating, label: rule.label }
      }
    }
  }
  return { rating: 'unknown', label: '待分类' }
}

/**
 * 从报告中提取投资结论文本
 * @param {string} markdown - 完整报告内容
 * @returns {string}
 */
export function extractConclusion(markdown) {
  if (!markdown) return ''
  const lines = markdown.split('\n')
  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const line = lines[i].trim()
    // 匹配 "> **结论**" 格式的 blockquote
    if (line.startsWith('>') && line.includes('**') && line.length > 10) {
      return line
    }
    // 匹配 "## 投资结论" 后面的内容
    if (line === '## 投资结论') {
      for (let j = i + 1; j < Math.min(lines.length, i + 5); j++) {
        if (lines[j].trim().startsWith('>')) {
          return lines[j].trim()
        }
      }
    }
  }
  return ''
}

/**
 * 从报告中提取行业信息
 * @param {string} markdown - 完整报告内容
 * @returns {string}
 */
export function extractIndustry(markdown) {
  if (!markdown) return ''
  // 查找"商业质量速写"表格中的行业信息
  // 或在报告头部寻找行业关键词
  const match = markdown.match(/商业模式清晰度\s*\|\s*清晰\s*\|([^|]+)/)
  if (match) return match[1].trim()
  const metaMatch = markdown.match(/\*\*[^*]+\*\*\s*·\s*[^·]+\s*·\s*[^·]+\s*·/)
  if (metaMatch) {
    const parts = metaMatch[0].split('·').map(s => s.trim())
    // 尝试从 meta line 提取，通常不包含行业信息
  }
  return '未分类'
}
```

---

### Task 3: 构建数据脚本

**Files:**
- Create: `website/scripts/build-data.js`

- [ ] **Step 1: 创建 build-data.js**

```js
import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync, statSync } from 'fs'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const WEBSITE_DIR = resolve(__dirname, '..')
const REPORTS_DIR = resolve(WEBSITE_DIR, '..')
const DATA_DIR = join(WEBSITE_DIR, 'public', 'data')

// 评级分类
const RULES = [
  {
    rating: 'build', label: '建仓',
    keywords: ['可建底仓', '可买入', '可适度配置', '建议配置', '高优先级观察', '中等仓位', '可逢低建仓', '可建立底仓'],
  },
  {
    rating: 'watch', label: '观察',
    keywords: ['中优先级观察', '低优先级观察', '观察', '建议观察', '谨慎观察', '观察级', '低仓位观察', '低配'],
  },
  {
    rating: 'avoid', label: '不建议',
    keywords: ['不建议买入', '否决', '不建议投资', '不建仓', '不建议', '❌'],
  },
]

function classifyConclusion(text) {
  if (!text) return { rating: 'unknown', label: '待分类' }
  const clean = text.replace(/^[>\s#*-]*\s*/, '').replace(/\*\*/g, '').replace(/[⚠️❌]/g, '').trim()
  for (const rule of RULES) {
    for (const kw of rule.keywords) {
      if (clean.includes(kw)) return { rating: rule.rating, label: rule.label }
    }
  }
  return { rating: 'unknown', label: '待分类' }
}

function extractConclusion(markdown) {
  if (!markdown) return ''
  const lines = markdown.split('\n')
  // 找向前30行的 blockquote
  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const line = lines[i].trim()
    if (line.startsWith('>') && line.includes('**') && line.length > 10) return line
  }
  return ''
}

function extractPriceTarget(markdown) {
  if (!markdown) return { price: '', target: '', margin: '' }
  const priceMatch = markdown.match(/当前股价\s*\|\s*[¥HK\$\s]*([0-9,.]+)/)
  const targetMatch = markdown.match(/目标买入价\s*\|\s*\*{0,2}[¥HK\$\s]*([0-9,.]+)/)
  const marginMatch = markdown.match(/安全边际\s*\|\s*\*{0,2}\+?([0-9.-]+)\s*pct/)
  return {
    price: priceMatch ? priceMatch[1] : '',
    target: targetMatch ? targetMatch[1] : '',
    margin: marginMatch ? marginMatch[1] : '',
  }
}

function extractIndustry(markdown) {
  if (!markdown) return ''
  // 从商业质量速写表格提取
  const tableMatch = markdown.match(/商业模式清晰度\s*\|\s*清晰\s*\|\s*([^|\n]+)/)
  if (tableMatch) return tableMatch[1].trim()
  // 从 meta line 提取（如 "全国性股份制商业银行"）
  const metaMatch = markdown.match(/商业模式清晰度\s*\|\s*清晰\s*\|\s*([^|\n]+)/)
  return '其他'
}

function isStockDir(name) {
  // 排除非股票目录
  const skip = ['汇总', 'scripts', '分析报告备份', '.DS_Store']
  if (skip.includes(name)) return false
  if (name.startsWith('.')) return false
  // 排除中文名称的专题目录
  if (/^[一-鿿]{2,}$/.test(name)) return false
  return true
}

function findReportFile(dirPath) {
  try {
    const files = readdirSync(dirPath)
    // 找 *_稳健投资策略分析报告.md 文件
    const report = files.find(f => f.endsWith('_稳健投资策略分析报告.md'))
    if (report) return join(dirPath, report)
    // 备用：任何 .md 文件（排除 data_pack）
    const anyMd = files.find(f => f.endsWith('.md') && !f.startsWith('data_pack'))
    if (anyMd) return join(dirPath, anyMd)
  } catch (_) { /* ignore */ }
  return null
}

function buildStocks() {
  const dirs = readdirSync(REPORTS_DIR).filter(isStockDir)
  const stocks = []

  for (const dir of dirs) {
    const dirPath = join(REPORTS_DIR, dir)
    if (!statSync(dirPath).isDirectory()) continue

    // 读取 index.json
    const indexPath = join(dirPath, 'index.json')
    if (!existsSync(indexPath)) continue
    const index = JSON.parse(readFileSync(indexPath, 'utf-8'))

    // 读取 latest 符号链接指向的版本目录
    const latestPath = join(dirPath, 'latest')
    const versionDir = existsSync(latestPath) && statSync(latestPath).isDirectory()
      ? readdirSync(latestPath).find(f => f.match(/^\d{4}-\d{2}-\d{2}$/))
      : null

    // 找报告文件（在根目录或版本目录中）
    let reportPath = findReportFile(dirPath)
    if (!reportPath && versionDir) {
      reportPath = findReportFile(join(dirPath, versionDir))
    }

    let markdown = ''
    let conclusion = ''
    let priceTarget = { price: '', target: '', margin: '' }
    let industry = ''

    if (reportPath) {
      markdown = readFileSync(reportPath, 'utf-8')
      conclusion = extractConclusion(markdown)
      priceTarget = extractPriceTarget(markdown)
      industry = extractIndustry(markdown)
    }

    const classification = classifyConclusion(conclusion)

    stocks.push({
      symbol: index.symbol,
      company: index.company,
      latest: index.latest,
      conclusion,
      classification,
      priceTarget,
      industry,
      hasReport: !!reportPath,
      path: encodeURIComponent(index.symbol),
    })
  }

  // 按股票代码排序
  stocks.sort((a, b) => a.symbol.localeCompare(b.symbol))
  return stocks
}

function buildSummaries() {
  const summariesDir = join(REPORTS_DIR, '汇总')
  if (!existsSync(summariesDir)) return []

  const files = readdirSync(summariesDir).filter(f => f.endsWith('.md'))
  return files.map(f => {
    const content = readFileSync(join(summariesDir, f), 'utf-8')
    // 提取文档标题（第一个 # 标题）
    const titleMatch = content.match(/^#\s+(.+)$/m)
    return {
      slug: f.replace('.md', ''),
      title: titleMatch ? titleMatch[1] : f.replace('.md', ''),
      filename: f,
    }
  })
}

function main() {
  mkdirSync(DATA_DIR, { recursive: true })

  const stocks = buildStocks()
  const stocksOut = {
    generated: new Date().toISOString(),
    total: stocks.length,
    items: stocks,
  }
  writeFileSync(join(DATA_DIR, 'stocks.json'), JSON.stringify(stocksOut, null, 2), 'utf-8')
  console.log(`✓ stocks.json — ${stocks.length} 只股票`)

  // 按评级统计
  const byRating = {}
  for (const s of stocks) {
    byRating[s.classification.label] = (byRating[s.classification.label] || 0) + 1
  }
  console.log('  评级分布:', byRating)

  const summaries = buildSummaries()
  writeFileSync(join(DATA_DIR, 'summaries.json'), JSON.stringify(summaries, null, 2), 'utf-8')
  console.log(`✓ summaries.json — ${summaries.length} 份汇总报告`)
}

main()
```

- [ ] **Step 2: 运行构建脚本验证**

```bash
cd website && npm run build-data
```

Expected: 输出 stocks.json（约200+条）和 summaries.json。

- [ ] **Step 3: 检查生成的 JSON 结构**

查看 `website/public/data/stocks.json` 确保包含正确的 symbol、company、classification、priceTarget 等字段。

---

### Task 4: 顶部导航栏 NavBar

**Files:**
- Create: `website/src/components/NavBar.vue`

- [ ] **Step 1: 创建 NavBar.vue**

```vue
<template>
  <header class="border-b border-warm-deep">
    <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
      <router-link to="/" class="flex items-center gap-3 group">
        <span class="text-2xl">📊</span>
        <span class="text-lg font-heading font-semibold text-ink tracking-tight">
          稳健投资分析
        </span>
      </router-link>
      <nav class="flex items-center gap-6 text-sm font-heading text-ink-light">
        <router-link to="/" class="hover:text-ink transition-colors">标的列表</router-link>
        <router-link to="/summary" class="hover:text-ink transition-colors">汇总报告</router-link>
      </nav>
    </div>
  </header>
</template>
```

---

### Task 5: 评级筛选栏 FilterBar

**Files:**
- Create: `website/src/components/FilterBar.vue`

- [ ] **Step 1: 创建 FilterBar.vue**

```vue
<template>
  <div class="flex items-center gap-2 flex-wrap">
    <button
      v-for="opt in options"
      :key="opt.value"
      @click="$emit('select', opt.value)"
      class="px-4 py-1.5 rounded-full text-sm font-heading font-medium transition-all border"
      :class="selected === opt.value
        ? 'bg-ink text-warm border-ink'
        : 'bg-white text-ink-light border-warm-deep hover:border-ink/30'"
    >
      {{ opt.label }}
      <span v-if="opt.count !== undefined" class="ml-1 opacity-60">({{ opt.count }})</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  selected: { type: String, default: 'all' },
  options: { type: Array, required: true },
})
defineEmits(['select'])
</script>
```

---

### Task 6: 股票数据表格 StockTable + Pagination

**Files:**
- Create: `website/src/components/StockTable.vue`
- Create: `website/src/components/Pagination.vue`

- [ ] **Step 1: 创建 Pagination.vue**

```vue
<template>
  <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-8">
    <button
      @click="$emit('change', current - 1)"
      :disabled="current <= 1"
      class="px-3 py-1.5 text-sm rounded border border-warm-deep hover:bg-warm-deep transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
    >
      ← 上一页
    </button>
    <template v-for="p in visiblePages" :key="p">
      <span v-if="p === '...'" class="px-2 text-ink-light">...</span>
      <button
        v-else
        @click="$emit('change', p)"
        class="w-9 h-9 text-sm rounded transition-colors"
        :class="p === current
          ? 'bg-ink text-warm'
          : 'hover:bg-warm-deep text-ink-light'"
      >
        {{ p }}
      </button>
    </template>
    <button
      @click="$emit('change', current + 1)"
      :disabled="current >= totalPages"
      class="px-3 py-1.5 text-sm rounded border border-warm-deep hover:bg-warm-deep transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
    >
      下一页 →
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  current: { type: Number, required: true },
  totalPages: { type: Number, required: true },
})
defineEmits(['change'])

const visiblePages = computed(() => {
  const pages = []
  const total = props.totalPages
  const curr = props.current
  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    if (curr > 3) pages.push('...')
    for (let i = Math.max(2, curr - 1); i <= Math.min(total - 1, curr + 1); i++) pages.push(i)
    if (curr < total - 2) pages.push('...')
    pages.push(total)
  }
  return pages
})
</script>
```

- [ ] **Step 2: 创建 StockTable.vue**

```vue
<template>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b-2 border-ink/10 text-left">
          <th class="py-3 pr-4 font-heading font-medium text-ink-light text-xs uppercase tracking-wider">股票名称</th>
          <th class="py-3 px-3 font-heading font-medium text-ink-light text-xs uppercase tracking-wider">代码</th>
          <th class="py-3 px-3 font-heading font-medium text-ink-light text-xs uppercase tracking-wider text-right">当前价</th>
          <th class="py-3 px-3 font-heading font-medium text-ink-light text-xs uppercase tracking-wider text-right">目标价</th>
          <th class="py-3 px-3 font-heading font-medium text-ink-light text-xs uppercase tracking-wider text-right">安全边际</th>
          <th class="py-3 pl-3 font-heading font-medium text-ink-light text-xs uppercase tracking-wider">评级</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="stock in stocks"
          :key="stock.symbol"
          @click="goDetail(stock.symbol)"
          class="border-b border-ink/5 hover:bg-warm-deep/50 cursor-pointer transition-colors group"
        >
          <td class="py-3 pr-4">
            <span class="font-heading font-medium text-ink group-hover:text-accent transition-colors">
              {{ stock.company }}
            </span>
          </td>
          <td class="py-3 px-3 font-mono text-xs text-ink-light">{{ stock.symbol }}</td>
          <td class="py-3 px-3 text-right font-mono tabular-nums">{{ stock.priceTarget.price }}</td>
          <td class="py-3 px-3 text-right font-mono tabular-nums font-medium">{{ stock.priceTarget.target }}</td>
          <td class="py-3 px-3 text-right font-mono tabular-nums" :class="marginColor(stock.priceTarget.margin)">
            {{ stock.priceTarget.margin ? stock.priceTarget.margin + '%' : '—' }}
          </td>
          <td class="py-3 pl-3">
            <span class="inline-block px-2.5 py-0.5 rounded-full text-xs font-heading font-medium" :class="badgeClass(stock.classification.rating)">
              {{ stock.classification.label }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!stocks.length" class="text-center py-16 text-ink-light">
      暂无匹配的标的
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
defineProps({ stocks: { type: Array, required: true } })

function goDetail(symbol) {
  router.push({ name: 'stock', params: { symbol } })
}

function badgeClass(rating) {
  switch (rating) {
    case 'build': return 'bg-success/10 text-success'
    case 'watch': return 'bg-warn/10 text-warn'
    case 'avoid': return 'bg-danger/10 text-danger'
    default: return 'bg-gray-100 text-ink-light'
  }
}

function marginColor(margin) {
  if (!margin) return 'text-ink-light'
  const v = parseFloat(margin)
  if (v > 0) return 'text-success'
  if (v === 0) return 'text-ink-light'
  return 'text-danger'
}
</script>
```

---

### Task 7: 首页 HomePage

**Files:**
- Create: `website/src/views/HomePage.vue`

- [ ] **Step 1: 创建 HomePage.vue**

```vue
<template>
  <div class="max-w-6xl mx-auto px-6 py-12">
    <!-- 页面标题 -->
    <div class="mb-10">
      <h1 class="text-3xl font-heading font-semibold text-ink mb-2">投资标的列表</h1>
      <p class="text-ink-light">
        共 {{ filteredStocks.length }} 只标的
        <span v-if="total > 0"> · 当前显示第 {{ (currentPage - 1) * pageSize + 1 }}-{{ Math.min(currentPage * pageSize, filteredStocks.length) }} 条</span>
      </p>
    </div>

    <!-- 筛选 + 搜索 -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <FilterBar :selected="activeFilter" :options="filterOptions" @select="setFilter" />
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索股票名称或代码..."
        class="px-4 py-2 rounded-lg border border-warm-deep bg-white text-sm text-ink placeholder:text-ink-light/50 focus:outline-none focus:border-accent/40 transition-colors w-full sm:w-64 font-body"
      />
    </div>

    <!-- 表格 -->
    <div class="bg-white rounded-xl border border-warm-deep/60 overflow-hidden shadow-sm">
      <StockTable :stocks="pagedStocks" />
    </div>

    <!-- 分页 -->
    <Pagination :current="currentPage" :totalPages="totalPages" @change="currentPage = $event" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import FilterBar from '../components/FilterBar.vue'
import StockTable from '../components/StockTable.vue'
import Pagination from '../components/Pagination.vue'

const stocksData = ref([])
const activeFilter = ref('all')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = 25

// 加载数据
fetch('./data/stocks.json')
  .then(r => r.json())
  .then(d => { stocksData.value = d.items })

const filterOptions = computed(() => {
  const counts = {}
  for (const s of stocksData.value) {
    counts[s.classification.rating] = (counts[s.classification.rating] || 0) + 1
  }
  return [
    { value: 'all', label: '全部', count: stocksData.value.length },
    { value: 'build', label: '建仓', count: counts.build || 0 },
    { value: 'watch', label: '观察', count: counts.watch || 0 },
    { value: 'avoid', label: '不建议', count: counts.avoid || 0 },
    { value: 'unknown', label: '待分类', count: counts.unknown || 0 },
  ]
})

const filteredStocks = computed(() => {
  let result = stocksData.value
  if (activeFilter.value !== 'all') {
    result = result.filter(s => s.classification.rating === activeFilter.value)
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    result = result.filter(s =>
      s.company.toLowerCase().includes(q) || s.symbol.toLowerCase().includes(q)
    )
  }
  return result
})

const totalPages = computed(() => Math.ceil(filteredStocks.value.length / pageSize) || 1)

const pagedStocks = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredStocks.value.slice(start, start + pageSize)
})

function setFilter(value) {
  activeFilter.value = value
  currentPage.value = 1
}
</script>
```

---

### Task 8: 个股详情页 StockDetail + ReportRenderer

**Files:**
- Create: `website/src/views/StockDetail.vue`
- Create: `website/src/components/ReportRenderer.vue`

- [ ] **Step 1: 创建 ReportRenderer.vue**

```vue
<template>
  <div class="prose-content" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

marked.setOptions({
  breaks: false,
  gfm: true,
})

const props = defineProps({ markdown: { type: String, required: true } })
const html = computed(() => marked.parse(props.markdown))
</script>

<style scoped>
.prose-content {
  font-family: var(--font-body);
  line-height: 1.8;
  color: var(--color-ink);
}
.prose-content :deep(h1) {
  font-family: var(--font-heading);
  font-size: 1.75rem;
  font-weight: 600;
  margin-top: 2.5rem;
  margin-bottom: 1rem;
  letter-spacing: -0.02em;
}
.prose-content :deep(h2) {
  font-family: var(--font-heading);
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 2rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-warm-deep);
}
.prose-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1.25rem 0;
  font-size: 0.875rem;
}
.prose-content :deep(th) {
  text-align: left;
  padding: 0.625rem 0.75rem;
  border-bottom: 2px solid rgba(0,0,0,0.08);
  font-family: var(--font-heading);
  font-weight: 500;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-ink-light);
}
.prose-content :deep(td) {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid rgba(0,0,0,0.04);
}
.prose-content :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  padding: 0.75rem 1.25rem;
  margin: 1.25rem 0;
  background: rgba(26,58,74,0.03);
  border-radius: 0 0.5rem 0.5rem 0;
  font-style: italic;
}
.prose-content :deep(strong) {
  font-weight: 600;
  color: var(--color-ink);
}
.prose-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-warm-deep);
  margin: 2rem 0;
}
.prose-content :deep(ul), .prose-content :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.75rem 0;
}
.prose-content :deep(li) {
  margin: 0.25rem 0;
}
</style>
```

- [ ] **Step 2: 创建 StockDetail.vue**

```vue
<template>
  <div class="max-w-3xl mx-auto px-6 py-12">
    <!-- 返回链接 -->
    <router-link to="/" class="inline-flex items-center gap-1.5 text-sm text-ink-light hover:text-ink transition-colors mb-8 font-heading">
      ← 返回标的列表
    </router-link>

    <!-- 加载中 -->
    <div v-if="loading" class="text-center py-20 text-ink-light">加载中...</div>

    <!-- 报告内容 -->
    <template v-else-if="stock">
      <header class="mb-10">
        <div class="flex items-center gap-3 mb-3">
          <span class="inline-block px-3 py-0.5 rounded-full text-xs font-heading font-medium" :class="badgeClass(stock.classification.rating)">
            {{ stock.classification.label }}
          </span>
          <span class="text-sm text-ink-light font-mono">{{ stock.symbol }}</span>
        </div>
        <h1 class="text-3xl font-heading font-semibold text-ink">{{ stock.company }}</h1>
        <p v-if="stock.conclusion" class="mt-2 text-ink-light italic">{{ cleanConclusion(stock.conclusion) }}</p>
      </header>

      <!-- 指标卡片 -->
      <div v-if="stock.priceTarget.price" class="grid grid-cols-3 gap-4 mb-10">
        <div class="bg-white rounded-lg border border-warm-deep/60 p-4">
          <div class="text-xs text-ink-light uppercase tracking-wider font-heading mb-1">当前股价</div>
          <div class="text-xl font-heading font-semibold text-ink">{{ stock.priceTarget.price }}</div>
        </div>
        <div class="bg-white rounded-lg border border-warm-deep/60 p-4">
          <div class="text-xs text-ink-light uppercase tracking-wider font-heading mb-1">目标买入价</div>
          <div class="text-xl font-heading font-semibold text-ink">{{ stock.priceTarget.target }}</div>
        </div>
        <div class="bg-white rounded-lg border border-warm-deep/60 p-4">
          <div class="text-xs text-ink-light uppercase tracking-wider font-heading mb-1">安全边际</div>
          <div class="text-xl font-heading font-semibold" :class="marginColor(stock.priceTarget.margin)">
            {{ stock.priceTarget.margin ? stock.priceTarget.margin + '%' : '—' }}
          </div>
        </div>
      </div>

      <!-- 报告正文 -->
      <article v-if="markdown" class="bg-white rounded-xl border border-warm-deep/60 p-8 md:p-12 shadow-sm">
        <ReportRenderer :markdown="markdown" />
      </article>
      <div v-else class="text-center py-16 bg-white rounded-xl border border-warm-deep/60 text-ink-light">
        暂无详细报告内容
      </div>
    </template>

    <!-- 未找到 -->
    <div v-else class="text-center py-20 text-ink-light">未找到该标的</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ReportRenderer from '../components/ReportRenderer.vue'

const route = useRoute()
const stock = ref(null)
const markdown = ref('')
const loading = ref(true)

onMounted(async () => {
  const symbol = decodeURIComponent(route.params.symbol)
  try {
    // 加载元数据
    const stocksResp = await fetch('./data/stocks.json')
    const stocksData = await stocksResp.json()
    stock.value = stocksData.items.find(s => s.symbol === symbol) || null

    // 加载完整报告 Markdown
    // 报告文件路径: ../{symbol}/{公司名}_稳健投资策略分析报告.md
    // 因为 Vite 无法直接读取外部目录，我们在构建时把报告内容也打进数据中
    if (stock.value && stock.value.hasReport) {
      const reportResp = await fetch(`./data/reports/${symbol}.md`)
      if (reportResp.ok) {
        markdown.value = await reportResp.text()
      }
    }
  } catch (e) {
    console.error(e)
  }
  loading.value = false
})

function badgeClass(rating) {
  switch (rating) {
    case 'build': return 'bg-success/10 text-success'
    case 'watch': return 'bg-warn/10 text-warn'
    case 'avoid': return 'bg-danger/10 text-danger'
    default: return 'bg-gray-100 text-ink-light'
  }
}

function marginColor(margin) {
  if (!margin) return 'text-ink-light'
  const v = parseFloat(margin)
  if (v > 0) return 'text-success'
  if (v === 0) return 'text-ink-light'
  return 'text-danger'
}

function cleanConclusion(text) {
  return text.replace(/^>\s*\*\*/, '').replace(/\*\*$/, '').replace(/[*>]/g, '').trim()
}
</script>
```

- [ ] **Step 3: 更新 build-data.js，增加报告导出**

在 `build-data.js` 的 `main()` 函数中添加报告文件导出：

```js
// main() 中添加:
// 导出每份报告的 Markdown（供详情页使用）
const reportsDir = join(DATA_DIR, 'reports')
mkdirSync(reportsDir, { recursive: true })
for (const stock of stocks) {
  const dirPath = join(REPORTS_DIR, stock.path)
  const reportPath = findReportFile(dirPath)
  if (reportPath) {
    const md = readFileSync(reportPath, 'utf-8')
    writeFileSync(join(reportsDir, `${stock.symbol}.md`), md, 'utf-8')
  }
}
console.log(`✓ 报告文件已导出`)
```

---

### Task 9: 汇总页面 SummaryPage

**Files:**
- Create: `website/src/views/SummaryPage.vue`

- [ ] **Step 1: 创建 SummaryPage.vue**

```vue
<template>
  <div class="max-w-3xl mx-auto px-6 py-12">
    <router-link to="/" class="inline-flex items-center gap-1.5 text-sm text-ink-light hover:text-ink transition-colors mb-8 font-heading">
      ← 返回标的列表
    </router-link>

    <h1 class="text-3xl font-heading font-semibold text-ink mb-2">汇总报告</h1>
    <p class="text-ink-light mb-10">投资组合配置、观察列表及整体结论汇总</p>

    <div class="space-y-4">
      <router-link
        v-for="doc in summaries"
        :key="doc.slug"
        :to="`/summary/${doc.slug}`"
        class="block bg-white rounded-lg border border-warm-deep/60 p-6 hover:border-accent/30 hover:shadow-sm transition-all group"
      >
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="font-heading font-medium text-ink group-hover:text-accent transition-colors text-lg">
              {{ doc.title }}
            </h2>
          </div>
          <span class="text-ink-light text-sm flex items-center gap-1 shrink-0">
            阅读 <span class="group-hover:translate-x-0.5 transition-transform">→</span>
          </span>
        </div>
      </router-link>
    </div>

    <div v-if="!summaries.length" class="text-center py-20 text-ink-light">
      暂无汇总报告
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const summaries = ref([])

onMounted(async () => {
  try {
    const resp = await fetch('./data/summaries.json')
    summaries.value = await resp.json()
  } catch (e) {
    console.error(e)
  }
})
</script>
```

- [ ] **Step 2: 更新 router.js 添加汇总详情路由**

在 router.js 中添加：

```js
{
  path: '/summary/:slug',
  name: 'summary-detail',
  component: () => import('./views/SummaryDetail.vue'),
}
```

- [ ] **Step 3: 创建 SummaryDetail.vue**

```vue
<template>
  <div class="max-w-3xl mx-auto px-6 py-12">
    <router-link to="/summary" class="inline-flex items-center gap-1.5 text-sm text-ink-light hover:text-ink transition-colors mb-8 font-heading">
      ← 返回汇总列表
    </router-link>

    <div v-if="loading" class="text-center py-20 text-ink-light">加载中...</div>

    <article v-else-if="markdown" class="bg-white rounded-xl border border-warm-deep/60 p-8 md:p-12 shadow-sm">
      <ReportRenderer :markdown="markdown" />
    </article>

    <div v-else class="text-center py-20 text-ink-light">未找到该报告</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ReportRenderer from '../components/ReportRenderer.vue'

const route = useRoute()
const markdown = ref('')
const loading = ref(true)

onMounted(async () => {
  try {
    const resp = await fetch(`./data/summaries/${route.params.slug}.md`)
    if (resp.ok) markdown.value = await resp.text()
  } catch (e) {
    console.error(e)
  }
  loading.value = false
})
</script>
```

- [ ] **Step 4: 更新 build-data.js 导出汇总报告 Markdown**

在 `build-data.js` 的 `main()` 中添加：

```js
// 导出汇总报告 Markdown
const summariesDir2 = join(DATA_DIR, 'summaries')
mkdirSync(summariesDir2, { recursive: true })
for (const s of summaries) {
  const src = join(REPORTS_DIR, '汇总', s.filename)
  writeFileSync(join(summariesDir2, `${s.slug}.md`), readFileSync(src, 'utf-8'), 'utf-8')
}
console.log(`✓ 汇总报告已导出`)
```

---

### Task 10: 页脚 FooterBar

**Files:**
- Create: `website/src/components/FooterBar.vue`

- [ ] **Step 1: 创建 FooterBar.vue**

```vue
<template>
  <footer class="border-t border-warm-deep mt-16">
    <div class="max-w-6xl mx-auto px-6 py-8 text-center text-xs text-ink-light/60 font-body">
      稳健投资策略分析报告 · 数据基于公开财务信息与量化模型 · 仅供参考不构成投资建议
    </div>
  </footer>
</template>
```

---

### Task 11: 构建验证与样式微调

- [ ] **Step 1: 完整构建测试**

```bash
cd website && npm run build
```

Expected: 构建成功，`website/dist/` 下生成静态文件。

- [ ] **Step 2: 预览构建结果**

```bash
cd website && npx serve dist
```

检查：
- 首页表格正确渲染，评级标签颜色正确
- 筛选切换正常，搜索过滤生效
- 分页切换正常
- 点击行跳转到详情页
- 详情页 Markdown 渲染正确
- 汇总页列表正确显示

- [ ] **Step 3: 样式微调要点**

逐个检查：
- 表格列宽是否合理（股票名称应给足够空间）
- 评级标签颜色是否区分明显
- 移动端（如果有）表格水平滚动
- 报告内表格渲染（长表格、宽表格）
- 字体加载是否正确（DM Sans、Newsreader、JetBrains Mono）

---

### Task 12: GitHub Actions 部署配置

**Files:**
- Create: `.github/workflows/deploy.yml`（在仓库根目录）

- [ ] **Step 1: 创建 deploy.yml**

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [master]
    paths:
      - '稳健投资策略分析报告/**'
      - '稳健投资策略分析报告/website/**'
      - '.github/workflows/deploy.yml'

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 稳健投资策略分析报告/website
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: 稳健投资策略分析报告/website/package-lock.json
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: 稳健投资策略分析报告/website/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/deploy-pages@v4
```

---

## 构建验证清单

部署前确认：
- [ ] `npm run build-data` 生成 stocks.json、summaries.json、reports/*.md、summaries/*.md
- [ ] `npm run build` Vite 构建成功
- [ ] 首页表格显示所有标的
- [ ] 评级筛选切换正常
- [ ] 搜索过滤正常
- [ ] 分页工作正常
- [ ] 点击股票进入详情页
- [ ] 详情页 Markdown 渲染正确
- [ ] 汇总页列表和详情正常
- [ ] 返回导航链接工作正常
