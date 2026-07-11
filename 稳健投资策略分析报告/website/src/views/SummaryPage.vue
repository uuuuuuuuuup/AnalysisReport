<template>
  <div class="max-w-4xl mx-auto px-6 py-12">
    <router-link to="/" class="inline-flex items-center gap-1.5 font-mono text-xs tracking-[0.14em] uppercase text-ink-soft hover:text-ink transition-colors mb-8">
      ← 返回标的列表
    </router-link>

    <p class="font-mono text-[13px] tracking-[0.22em] uppercase text-signal mb-3">Investment Summaries</p>
    <h1 class="text-3xl font-extrabold uppercase tracking-[-0.015em] text-ink mb-2">汇总报告</h1>
    <p class="text-ink-soft mb-10 text-lg">投资组合配置、观察列表及整体结论汇总</p>

    <div class="space-y-0">
      <router-link
        v-for="(doc, i) in summaries"
        :key="doc.slug"
        :to="`/summary/${doc.slug}`"
        class="block bg-paper-raised border-2 border-rule p-6 hover:bg-glacier-soft/30 transition-colors group"
        :class="{ '-mt-0.5': i > 0 }"
      >
        <div class="flex items-center justify-between gap-4">
          <h2 class="font-extrabold uppercase tracking-[-0.01em] text-ink group-hover:text-signal transition-colors text-lg">
            {{ doc.title }}
          </h2>
          <span class="font-mono text-xs tracking-[0.14em] uppercase text-ink-soft group-hover:text-signal transition-colors shrink-0 flex items-center gap-1">
            阅读 <span class="group-hover:translate-x-0.5 transition-transform">→</span>
          </span>
        </div>
      </router-link>
    </div>

    <div v-if="!summaries.length" class="text-center py-20 text-ink-soft font-mono text-sm">
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
