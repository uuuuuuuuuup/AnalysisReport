<template>
  <div class="flex items-center gap-2 flex-wrap">
    <button
      v-for="opt in options"
      :key="opt.value"
      @click="$emit('select', opt.value)"
      class="px-4 py-1.5 font-mono text-xs tracking-[0.14em] uppercase transition-all border-2"
      :class="selected === opt.value
        ? 'bg-signal text-paper border-signal'
        : 'bg-paper-raised text-ink-soft border-rule hover:bg-ink hover:text-paper hover:border-ink'"
    >
      {{ opt.label }}
      <span class="ml-1 opacity-60">({{ opt.count }})</span>
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
