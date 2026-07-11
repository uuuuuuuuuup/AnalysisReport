import { ref, watch } from 'vue'

const isDark = ref(false)

// 读取 localStorage 初始化
try {
  const stored = localStorage.getItem('theme')
  if (stored === 'dark') {
    isDark.value = true
    document.documentElement.classList.add('dark')
  }
} catch {
  // localStorage 不可用时静默降级
}

// 模块级 watch —— 响应状态变化，持久化到 localStorage
watch(isDark, (val) => {
  document.documentElement.classList.toggle('dark', val)
  try {
    localStorage.setItem('theme', val ? 'dark' : 'light')
  } catch {
    // 静默降级
  }
})

export function useTheme() {
  function toggle() {
    isDark.value = !isDark.value
  }

  return { isDark, toggle }
}