<template>
  <div class="prose-content" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

marked.setOptions({ breaks: false, gfm: true })

const props = defineProps({ markdown: { type: String, required: true } })
const html = computed(() => marked.parse(props.markdown))
</script>

<style scoped>
.prose-content {
  font-family: var(--font-body);
  line-height: 1.7;
  color: var(--color-ink);
  font-size: 16px;
}
.prose-content :deep(h1) {
  font-family: var(--font-heading);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: -0.015em;
  font-size: 1.75rem;
  margin-top: 0;
  margin-bottom: 1.2rem;
  padding-bottom: 0.9rem;
  border-bottom: 2px solid var(--color-rule);
}
.prose-content :deep(h2) {
  font-family: var(--font-heading);
  font-weight: 800;
  text-transform: uppercase;
  font-size: 1.2rem;
  letter-spacing: -0.01em;
  margin-top: 2.2em;
  margin-bottom: 0.8em;
  padding-top: 0.9em;
  border-top: 2px solid var(--color-rule);
}
.prose-content :deep(h3) {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 1.05rem;
  margin-top: 1.6em;
  margin-bottom: 0.5em;
  color: var(--color-ink);
}
.prose-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  margin: 1.4rem 0;
}
.prose-content :deep(th) {
  text-align: left;
  font-weight: 500;
  font-size: 0.68rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--color-ink-soft);
  border-bottom: 2px solid var(--color-rule);
  padding: 0 10px 8px 0;
}
.prose-content :deep(th:last-child) {
  padding-right: 0;
}
.prose-content :deep(td) {
  padding: 8px 10px 8px 0;
  border-bottom: 1px solid var(--color-glacier);
  color: var(--color-ink);
}
.prose-content :deep(td:last-child) {
  padding-right: 0;
}
.prose-content :deep(blockquote) {
  border-left: 4px solid var(--color-signal);
  padding: 4px 0 4px 20px;
  margin: 1.4em 0;
  font-style: italic;
  color: var(--color-ink-soft);
  font-size: 1.05em;
}
.prose-content :deep(strong) {
  font-weight: 700;
  color: var(--color-ink);
}
.prose-content :deep(hr) {
  border: none;
  border-top: 2px solid var(--color-rule);
  margin: 2.2em 0;
}
.prose-content :deep(ul), .prose-content :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.75rem 0;
}
.prose-content :deep(li) {
  margin: 0.25rem 0;
}
.prose-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.82em;
  background: var(--color-glacier-soft);
  padding: 0.12em 0.4em;
  border: 1px solid var(--color-glacier);
  color: var(--color-ink);
}
.prose-content :deep(a) {
  color: var(--color-signal);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.prose-content :deep(p) {
  color: var(--color-ink);
}
</style>
