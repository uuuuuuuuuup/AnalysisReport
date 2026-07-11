<template>
  <header class="border-b-2 border-rule bg-paper sticky top-0 z-50">
    <div class="max-w-6xl mx-auto px-6 flex items-center h-14 gap-8">
      <router-link to="/" class="flex items-center gap-2.5 text-ink hover:text-ink-soft transition-colors shrink-0">
        <svg class="w-6 h-6" viewBox="0 0 26 26" aria-hidden="true">
          <circle cx="13" cy="13" r="11.5" fill="none" stroke="currentColor" stroke-width="3"/>
          <path d="M13 3 L18 13 L13 23 L8 13 Z" fill="var(--color-signal)"/>
        </svg>
        <span class="font-extrabold text-lg tracking-wide whitespace-nowrap">
          稳健<em class="not-italic text-signal">投资</em>
        </span>
      </router-link>
      <nav class="flex items-center gap-1 overflow-x-auto">
        <router-link
          to="/"
          class="font-mono text-xs tracking-[0.14em] uppercase no-underline px-3 py-1.5 whitespace-nowrap hover:bg-ink hover:text-paper transition-colors"
          :class="{ 'bg-ink text-paper': $route.name === 'home' }"
        >标的列表</router-link>
        <router-link
          to="/summary"
          class="font-mono text-xs tracking-[0.14em] uppercase no-underline px-3 py-1.5 whitespace-nowrap hover:bg-ink hover:text-paper transition-colors"
          :class="{ 'bg-ink text-paper': $route.name === 'summary' || $route.name === 'summary-detail' }"
        >汇总报告</router-link>
      </nav>

      <!-- 日间/夜间切换 -->
      <button
        class="ml-auto p-2 rounded text-ink-soft hover:text-ink hover:bg-glacier-soft transition-colors"
        :title="isDark ? '切换到日间模式' : '切换到夜间模式'"
        @click="toggle"
      >
        <!-- 月亮图标（日间显示） -->
        <svg v-if="!isDark" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
        <!-- 太阳图标（夜间显示） -->
        <svg v-else class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/>
          <line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
      </button>
    </div>
  </header>
</template>

<script setup>
import { useTheme } from '../composables/useTheme.js'

const { isDark, toggle } = useTheme()
</script>
