const RULES = [
  {
    rating: 'build',
    label: '建仓',
    keywords: [
      '可建底仓', '可买入', '可适度配置', '建议配置',
      '高优先级观察', '中等仓位', '可逢低建仓', '建议配置',
      '可建立底仓', '可适度配置（中等仓位）',
    ],
  },
  {
    rating: 'watch',
    label: '观察',
    keywords: [
      '中优先级观察', '低优先级观察', '观察', '建议观察',
      '谨慎观察', '观察级', '低仓位观察', '低配',
    ],
  },
  {
    rating: 'avoid',
    label: '不建议',
    keywords: [
      '不建议买入', '否决', '不建议投资', '不建仓',
      '不建议', '不建仓/低优先级观察',
    ],
  },
]

/**
 * 从结论文本中提取评级
 * @param {string} text - 报告第一行结论文本
 * @returns {{ rating: string, label: string }}
 */
export function classifyConclusion(text) {
  if (!text) return { rating: 'unknown', label: '待分类' }
  const clean = text
    .replace(/^[>\s#*-]*\s*/, '')
    .replace(/\*\*/g, '')
    .replace(/[⚠️❌]/g, '')
    .trim()
  for (const rule of RULES) {
    for (const kw of rule.keywords) {
      if (clean.includes(kw)) {
        return { rating: rule.rating, label: rule.label }
      }
    }
  }
  return { rating: 'unknown', label: '待分类' }
}

/**
 * 从报告中提取投资结论文本
 * @param {string} markdown - 完整报告内容
 * @returns {string}
 */
export function extractConclusion(markdown) {
  if (!markdown) return ''
  const lines = markdown.split('\n')
  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const line = lines[i].trim()
    if (line.startsWith('>') && line.includes('**') && line.length > 10) {
      return line
    }
    if (line === '## 投资结论') {
      for (let j = i + 1; j < Math.min(lines.length, i + 5); j++) {
        if (lines[j].trim().startsWith('>')) {
          return lines[j].trim()
        }
      }
    }
  }
  return ''
}

/**
 * 从报告中提取行业信息
 * @param {string} markdown - 完整报告内容
 * @returns {string}
 */
export function extractIndustry(markdown) {
  if (!markdown) return ''
  const match = markdown.match(/商业模式清晰度\s*\|\s*清晰\s*\|\s*([^|\n]+)/)
  if (match) return match[1].trim()
  return '其他'
}