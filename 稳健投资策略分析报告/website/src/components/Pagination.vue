<template>
  <div v-if="totalPages > 1" class="flex items-center justify-center gap-1.5 mt-10">
    <button
      @click="$emit('change', current - 1)"
      :disabled="current <= 1"
      class="px-3 py-1.5 font-mono text-xs tracking-[0.1em] uppercase border-2 border-rule text-ink-soft hover:bg-ink hover:text-paper hover:border-ink transition-colors disabled:opacity-20 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-ink-soft disabled:hover:border-rule"
    >
      ← 上一页
    </button>
    <template v-for="p in visiblePages" :key="p">
      <span v-if="p === '...'" class="px-1.5 text-ink-muted font-mono text-xs">...</span>
      <button
        v-else
        @click="$emit('change', p)"
        class="w-9 h-9 font-mono text-sm transition-colors border-2"
        :class="p === current
          ? 'bg-signal text-paper border-signal'
          : 'text-ink-soft border-rule hover:bg-ink hover:text-paper hover:border-ink'"
      >
        {{ p }}
      </button>
    </template>
    <button
      @click="$emit('change', current + 1)"
      :disabled="current >= totalPages"
      class="px-3 py-1.5 font-mono text-xs tracking-[0.1em] uppercase border-2 border-rule text-ink-soft hover:bg-ink hover:text-paper hover:border-ink transition-colors disabled:opacity-20 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-ink-soft disabled:hover:border-rule"
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
