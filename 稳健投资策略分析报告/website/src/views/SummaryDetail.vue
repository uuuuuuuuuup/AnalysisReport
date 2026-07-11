<template>
  <div class="max-w-4xl mx-auto px-6 py-12">
    <router-link to="/summary" class="inline-flex items-center gap-1.5 font-mono text-xs tracking-[0.14em] uppercase text-ink-soft hover:text-ink transition-colors mb-8">
      ← 返回汇总列表
    </router-link>

    <div v-if="loading" class="text-center py-20 text-ink-soft font-mono">加载中...</div>

    <article v-else-if="markdown" class="border-2 border-rule bg-paper-raised p-8 md:p-12">
      <ReportRenderer :markdown="markdown" />
    </article>

    <div v-else class="text-center py-20 text-ink-soft font-mono">未找到该报告</div>
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
