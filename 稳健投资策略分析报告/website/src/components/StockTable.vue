<template>
  <div class="overflow-x-auto">
    <table class="w-full border-collapse font-mono text-[13.5px]">
      <thead>
        <tr>
          <th class="text-left font-medium text-[11px] tracking-[0.2em] uppercase text-ink-soft border-b-2 border-rule py-2.5 pl-5 pr-4 align-middle">股票名称</th>
          <th class="text-left font-medium text-[11px] tracking-[0.2em] uppercase text-ink-soft border-b-2 border-rule py-2.5 px-3 align-middle">代码</th>
          <th class="text-right font-medium text-[11px] tracking-[0.2em] uppercase text-ink-soft border-b-2 border-rule py-2.5 px-3 align-middle">当前价</th>
          <th class="text-right font-medium text-[11px] tracking-[0.2em] uppercase text-ink-soft border-b-2 border-rule py-2.5 px-3 align-middle">目标价</th>
          <th class="text-right font-medium text-[11px] tracking-[0.2em] uppercase text-ink-soft border-b-2 border-rule py-2.5 px-3 align-middle">安全边际</th>
          <th class="text-left font-medium text-[11px] tracking-[0.2em] uppercase text-ink-soft border-b-2 border-rule py-2.5 pl-3 pr-5 align-middle">评级</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="stock in stocks"
          :key="stock.symbol"
          @click="goDetail(stock.symbol)"
          class="cursor-pointer hover:bg-glacier-soft/50 transition-colors group"
        >
          <td class="py-3 pl-5 pr-4 border-b border-glacier font-body font-medium text-ink group-hover:text-signal transition-colors text-[15px]">
            {{ stock.company || '—' }}
          </td>
          <td class="py-3 px-3 border-b border-glacier text-xs text-ink-muted">{{ stock.symbol }}</td>
          <td class="py-3 px-3 border-b border-glacier text-right tabular-nums">{{ stock.priceTarget.price || '—' }}</td>
          <td class="py-3 px-3 border-b border-glacier text-right tabular-nums font-semibold">{{ stock.priceTarget.target || '—' }}</td>
          <td class="py-3 px-3 border-b border-glacier text-right tabular-nums font-semibold" :class="marginColor(stock.priceTarget.margin)">
            {{ stock.priceTarget.margin ? stock.priceTarget.margin + '%' : '—' }}
          </td>
          <td class="py-3 pl-3 pr-5 border-b border-glacier">
            <span class="inline-block px-2.5 py-0.5 text-[11px] tracking-[0.14em] uppercase font-mono font-semibold border" :class="badgeClass(stock.classification.rating)">
              {{ badgeText(stock.classification.label) }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!stocks.length" class="text-center py-16 text-ink-soft font-mono text-sm tracking-wider">
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
</script>
