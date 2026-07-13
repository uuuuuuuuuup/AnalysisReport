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
    </div>
  </header>
</template>
