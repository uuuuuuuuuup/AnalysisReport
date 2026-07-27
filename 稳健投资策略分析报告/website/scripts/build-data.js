import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync, statSync } from 'fs'
import { join, resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const WEBSITE_DIR = resolve(__dirname, '..')
const REPORTS_DIR = resolve(WEBSITE_DIR, '..')
const DATA_DIR = join(WEBSITE_DIR, 'public', 'data')

const RULES = [
  {
    rating: 'build', label: '建仓',
    keywords: ['可建底仓', '可买入', '可适度配置', '建议配置', '建议建仓', '高优先级观察', '中等仓位', '可逢低建仓', '可建立底仓', '建议持有'],
  },
  {
    rating: 'watch', label: '观察',
    keywords: ['中优先级观察', '低优先级观察', '观察', '建议观察', '谨慎观察', '观察级', '低仓位观察', '低配'],
  },
  {
    rating: 'avoid', label: '不建议',
    keywords: ['不建议买入', '否决', '不建议投资', '不建仓', '不建议', '❌'],
  },
]

function classifyConclusion(text) {
  if (!text) return { rating: 'unknown', label: '待分类' }
  const clean = text.replace(/^[>\s#*-]*\s*/, '').replace(/\*\*/g, '').replace(/[⚠️❌]/g, '').trim()
  for (const rule of RULES) {
    for (const kw of rule.keywords) {
      if (clean.includes(kw)) return { rating: rule.rating, label: rule.label }
    }
  }
  return { rating: 'unknown', label: '待分类' }
}

function extractConclusion(markdown) {
  if (!markdown) return ''
  const lines = markdown.split('\n')
  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const line = lines[i].trim()
    if (line.startsWith('>') && line.includes('**') && line.length > 10) return line
    if (line === '## 投资结论') {
      for (let j = i + 1; j < Math.min(lines.length, i + 5); j++) {
        if (lines[j].trim().startsWith('>')) return lines[j].trim()
      }
    }
  }
  return ''
}

function extractPriceTarget(markdown) {
  if (!markdown) return { price: '', target: '', margin: '' }
  // 新格式: | 当前价 / 目标买入价 / 距离目标价 | 73.69 / 106.40 / +44.3% |
  // 旧格式: | 当前股价 | ¥97.08 | ...
  const priceMatch = markdown.match(/(?:当前股价|当前价)\s*(?:\/\s*目标买入价\s*\/[^|]*)?\s*\|\s*\*{0,2}[¥HK\$\s₩]*([0-9,.]+)/)
  const targetMatch = markdown.match(/目标买入价\s*\|\s*\*{0,2}[¥HK\$\s₩元]*\s*([0-9,.]+)/)
  const marginMatch = markdown.match(/(?:修正后\s*)?安全边际\s*\|\s*\*{0,2}\+?(-?[0-9.]+)\s*pct/)
  return {
    price: priceMatch ? priceMatch[1] : '',
    target: targetMatch ? targetMatch[1] : '',
    margin: marginMatch ? marginMatch[1] : '',
  }
}

function extractIndustry(markdown) {
  if (!markdown) return ''
  const match = markdown.match(/商业模式清晰度\s*\|\s*清晰\s*\|\s*([^|\n]+)/)
  if (match) return match[1].trim()
  return '其他'
}

function isStockDir(name) {
  const skip = ['汇总', 'scripts', '分析报告备份', '.DS_Store', 'website']
  if (skip.includes(name)) return false
  if (name.startsWith('.')) return false
  if (/^[一-鿿]{2,}$/.test(name)) return false
  return true
}

function findReportFile(dirPath) {
  try {
    const files = readdirSync(dirPath)
    const report = files.find(f => f.endsWith('_稳健投资策略分析报告.md'))
    if (report) return join(dirPath, report)
    const anyMd = files.find(f => f.endsWith('.md') && !f.startsWith('data_pack') && !f.startsWith('index'))
    if (anyMd) return join(dirPath, anyMd)
  } catch (_) { /* ignore */ }
  return null
}

function buildStocks() {
  const dirs = readdirSync(REPORTS_DIR).filter(isStockDir)
  const stocks = []

  for (const dir of dirs) {
    const dirPath = join(REPORTS_DIR, dir)
    if (!statSync(dirPath).isDirectory()) continue

    const indexPath = join(dirPath, 'index.json')
    if (!existsSync(indexPath)) continue
    const index = JSON.parse(readFileSync(indexPath, 'utf-8'))

    // 优先取 latest/ 目录（最新版本）
    let reportPath = null
    const latestDir = join(dirPath, 'latest')
    if (existsSync(latestDir)) {
      reportPath = findReportFile(latestDir)
    }
    // 其次取根目录
    if (!reportPath) {
      reportPath = findReportFile(dirPath)
    }
    // 兜底：在日期版本子目录中查找
    if (!reportPath) {
      const subs = readdirSync(dirPath).filter(f => f.match(/^\d{4}-\d{2}-\d{2}$/))
      for (const sub of subs) {
        reportPath = findReportFile(join(dirPath, sub))
        if (reportPath) break
      }
    }

    let markdown = ''
    if (reportPath) {
      markdown = readFileSync(reportPath, 'utf-8')
    }

    const conclusion = extractConclusion(markdown)
    const priceTarget = extractPriceTarget(markdown)
    const industry = extractIndustry(markdown)
    const classification = classifyConclusion(conclusion)

    stocks.push({
      symbol: index.symbol,
      company: index.company,
      latest: index.latest,
      conclusion,
      classification,
      priceTarget,
      industry,
      hasReport: !!reportPath,
      path: encodeURIComponent(index.symbol),
      reportPath,
    })
  }

  stocks.sort((a, b) => a.symbol.localeCompare(b.symbol))
  return stocks
}

function buildSummaries() {
  const summariesDir = join(REPORTS_DIR, '汇总')
  if (!existsSync(summariesDir)) return []

  const files = readdirSync(summariesDir).filter(f => f.endsWith('.md'))
  return files.map(f => {
    const content = readFileSync(join(summariesDir, f), 'utf-8')
    const titleMatch = content.match(/^#\s+(.+)$/m)
    return {
      slug: f.replace('.md', ''),
      title: titleMatch ? titleMatch[1] : f.replace('.md', ''),
      filename: f,
    }
  })
}

function main() {
  mkdirSync(DATA_DIR, { recursive: true })

  const stocks = buildStocks()
  const stocksOut = {
    generated: new Date().toISOString(),
    total: stocks.length,
    items: stocks,
  }
  writeFileSync(join(DATA_DIR, 'stocks.json'), JSON.stringify(stocksOut, null, 2), 'utf-8')
  console.log(`✓ stocks.json — ${stocks.length} 只股票`)

  const byRating = {}
  for (const s of stocks) {
    byRating[s.classification.label] = (byRating[s.classification.label] || 0) + 1
  }
  console.log('  评级分布:', byRating)

  const summaries = buildSummaries()
  writeFileSync(join(DATA_DIR, 'summaries.json'), JSON.stringify(summaries, null, 2), 'utf-8')
  console.log(`✓ summaries.json — ${summaries.length} 份汇总报告`)

  // 导出每份报告的 Markdown
  const reportsDir = join(DATA_DIR, 'reports')
  mkdirSync(reportsDir, { recursive: true })
  let reportCount = 0
  for (const stock of stocks) {
    let rp = stock.reportPath
    if (!rp) {
      const dirPath = join(REPORTS_DIR, stock.path)
      rp = findReportFile(dirPath)
      if (!rp) {
        const subs = readdirSync(dirPath).filter(f => f.match(/^\d{4}-\d{2}-\d{2}$/))
        for (const sub of subs) {
          rp = findReportFile(join(dirPath, sub))
          if (rp) break
        }
      }
    }
    if (rp) {
      const md = readFileSync(rp, 'utf-8')
      writeFileSync(join(reportsDir, `${stock.symbol}.md`), md, 'utf-8')
      reportCount++
    }
  }
  console.log(`✓ 报告文件已导出 — ${reportCount} 份`)

  // 导出汇总报告 Markdown
  const summariesDir = join(DATA_DIR, 'summaries')
  mkdirSync(summariesDir, { recursive: true })
  for (const s of summaries) {
    const src = join(REPORTS_DIR, '汇总', s.filename)
    if (existsSync(src)) {
      writeFileSync(join(summariesDir, `${s.slug}.md`), readFileSync(src, 'utf-8'), 'utf-8')
    }
  }
  console.log(`✓ 汇总报告已导出 — ${summaries.length} 份`)
}

main()