<template>
  <div class="max-w-4xl mx-auto px-6 py-12">
    <router-link to="/" class="inline-flex items-center gap-1.5 font-mono text-xs tracking-[0.14em] uppercase text-ink-soft hover:text-ink transition-colors mb-8">
      ← 返回标的列表
    </router-link>

    <div v-if="loading" class="text-center py-20 text-ink-soft font-mono">加载中...</div>

    <template v-else-if="stock">
      <!-- 报告头部 -->
      <header class="border-2 border-rule bg-paper-raised mb-10">
        <div class="flex items-center justify-between gap-4 flex-wrap border-b-2 border-rule px-6 py-4">
          <div class="flex items-center gap-3">
            <span class="inline-block px-3 py-1 text-[11px] tracking-[0.18em] uppercase font-mono font-bold border-2" :class="badgeClass(stock.classification.rating)">
              {{ badgeText(stock.classification.label) }}
            </span>
            <span class="font-mono text-sm text-ink-muted tracking-[0.1em]">{{ stock.symbol }}</span>
          </div>
        </div>
        <div class="px-6 py-6">
          <h1 class="text-2xl font-extrabold uppercase tracking-[-0.01em] text-ink">{{ stock.company || stock.symbol }}</h1>
          <p v-if="stock.conclusion" class="mt-3 text-ink-soft italic">{{ cleanConclusion(stock.conclusion) }}</p>
        </div>
      </header>

      <!-- 指标卡片 -->
      <div v-if="stock.priceTarget.price" class="grid grid-cols-3 gap-0 mb-10 border-2 border-rule">
        <div class="bg-paper-raised p-5 border-r-2 border-rule">
          <div class="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-soft mb-1">当前股价</div>
          <div class="text-2xl font-bold font-mono tabular-nums text-ink">{{ stock.priceTarget.price }}</div>
        </div>
        <div class="bg-paper-raised p-5 border-r-2 border-rule">
          <div class="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-soft mb-1">目标买入价</div>
          <div class="text-2xl font-bold font-mono tabular-nums text-ink">{{ stock.priceTarget.target || '—' }}</div>
        </div>
        <div class="bg-paper-raised p-5">
          <div class="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-soft mb-1">安全边际</div>
          <div class="text-2xl font-bold font-mono tabular-nums" :class="marginColor(stock.priceTarget.margin)">
            {{ stock.priceTarget.margin ? stock.priceTarget.margin + '%' : '—' }}
          </div>
        </div>
      </div>

      <!-- 报告正文 -->
      <article v-if="markdown" class="border-2 border-rule bg-paper-raised p-8 md:p-12">
        <ReportRenderer :markdown="markdown" />
      </article>
      <div v-else class="text-center py-16 border-2 border-rule bg-paper-raised text-ink-soft font-mono text-sm">
        暂无详细报告内容
      </div>
    </template>

    <div v-else class="text-center py-20 text-ink-soft font-mono">未找到该标的</div>
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
  const symbol = route.params.symbol
  try {
    const stocksResp = await fetch('./data/stocks.json')
    const stocksData = await stocksResp.json()
    stock.value = stocksData.items.find(s => s.symbol === symbol) || null

    if (stock.value && stock.value.hasReport) {
      const reportResp = await fetch(`./data/reports/${symbol}.md`)
      if (reportResp.ok) markdown.value = await reportResp.text()
    }
  } catch (e) {
    console.error(e)
  }
  loading.value = false
})

function badgeText(label) {
  const map = { '建仓': 'BUY', '观察': 'WATCH', '不建议': 'AVOID', '待分类': '—' }
  return map[label] || label
}

function badgeClass(rating) {
  switch (rating) {
    case 'build': return 'text-success border-success bg-success-soft'
    case 'watch': return 'text-warn border-warn bg-warn-soft'
    case 'avoid': return 'text-danger border-danger bg-danger-soft'
    default: return 'text-ink-muted border-glacier bg-white/50'
  }
}

function marginColor(margin) {
  if (!margin) return 'text-ink-muted'
  const v = parseFloat(margin)
  if (v > 0) return 'text-success'
  if (v === 0) return 'text-ink-muted'
  return 'text-danger'
}

function cleanConclusion(text) {
  return text.replace(/^>\s*\*\*/, '').replace(/\*\*$/, '').replace(/[*>]/g, '').trim()
}
</script>
