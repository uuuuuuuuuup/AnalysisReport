<template>
  <div class="max-w-6xl mx-auto px-6 py-12">
    <!-- 页面标题 -->
    <div class="mb-10">
      <p class="font-mono text-[13px] tracking-[0.22em] uppercase text-signal mb-3">Stock Register · {{ total }} Issues</p>
      <h1 class="text-3xl font-extrabold uppercase tracking-[-0.015em] text-ink">投资标的列表</h1>
      <p class="text-ink-soft mt-3 text-lg max-w-xl" v-if="filteredStocks.length !== total">
        当前筛选 {{ filteredStocks.length }} 只标的 · 第 {{ (currentPage - 1) * pageSize + 1 }}-{{ Math.min(currentPage * pageSize, filteredStocks.length) }} 条
      </p>
    </div>

    <!-- 筛选 + 搜索 -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
      <FilterBar :selected="activeFilter" :options="filterOptions" @select="setFilter" />
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索名称或代码..."
        class="px-4 py-2 font-mono text-sm border-2 border-rule bg-paper-raised text-ink placeholder:text-ink-muted/50 focus:outline-none focus:border-signal transition-colors w-full sm:w-60"
      />
    </div>

    <!-- 表格 -->
    <div class="border-2 border-rule bg-paper-raised">
      <StockTable :stocks="pagedStocks" />
    </div>

    <!-- 分页 -->
    <Pagination :current="currentPage" :totalPages="totalPages" @change="currentPage = $event" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import FilterBar from '../components/FilterBar.vue'
import StockTable from '../components/StockTable.vue'
import Pagination from '../components/Pagination.vue'

const stocksData = ref([])
const activeFilter = ref('all')
const searchQuery = ref('')
const currentPage = ref(1)
const pageSize = 25

onMounted(async () => {
  try {
    const resp = await fetch('./data/stocks.json')
    const data = await resp.json()
    stocksData.value = data.items
  } catch (e) {
    console.error('加载数据失败:', e)
  }
})

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

const total = computed(() => stocksData.value.length)

const filteredStocks = computed(() => {
  let result = stocksData.value
  if (activeFilter.value !== 'all') {
    result = result.filter(s => s.classification.rating === activeFilter.value)
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    result = result.filter(s =>
      (s.company && s.company.toLowerCase().includes(q)) ||
      s.symbol.toLowerCase().includes(q)
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
