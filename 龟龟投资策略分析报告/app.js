/**
 * 龟龟投资策略报告 - 应用逻辑
 * 功能：报告加载、搜索、视图切换、收藏管理
 */

// ============================================
// 全局状态
// ============================================
const state = {
    reports: [],
    favorites: JSON.parse(localStorage.getItem('favorites') || '[]'),
    currentView: 'dashboard',
    currentFilter: 'all',
    currentSort: 'date-desc',
    searchQuery: '',
    selectedReport: null,
    sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true'
};

// ============================================
// 报告数据定义
// ============================================
const reportData = [
    { code: '000002', name: '万科 A', file: '000002/万科 A_000002_分析报告.md', rating: 'exclude' },
    { code: '000538', name: '云南白药', file: '000538/云南白药_000538_分析报告.md', rating: 'good' },
    { code: '000568', name: '泸州老窖', file: '000568/泸州老窖_000568_分析报告.md', rating: 'good' },
    { code: '000858', name: '五粮液', file: '000858/五粮液_000858_分析报告.md', rating: 'good' },
    { code: '000895', name: '双汇发展', file: '000895/双汇发展_000895_分析报告.md', rating: 'good' },
    { code: '001914', name: '招商积余', file: '001914/招商积余_001914_分析报告.md', rating: 'warning' },
    { code: '001965', name: '招商公路', file: '001965/招商公路_001965_分析报告.md', rating: 'good' },
    { code: '001979', name: '招商蛇口', file: '001979/招商蛇口_001979_分析报告.md', rating: 'warning' },
    { code: '002027', name: '分众传媒', file: '002027/分众传媒_002027_分析报告.md', rating: 'good' },
    { code: '002304', name: '洋河股份', file: '002304/洋河股份_002304_分析报告.md', rating: 'good' },
    { code: '002352', name: '顺丰控股', file: '002352/顺丰控股_002352_分析报告.md', rating: 'warning' },
    { code: '002507', name: '涪陵榨菜', file: '002507/涪陵榨菜_002507_分析报告.md', rating: 'good' },
    { code: '002568', name: '百润股份', file: '002568/百润股份_002568_分析报告.md', rating: 'warning' },
    { code: '002991', name: '甘源食品', file: '002991/甘源食品_002991_分析报告.md', rating: 'good' },
    { code: '300015', name: '爱尔眼科', file: '300015/爱尔眼科_300015_分析报告.md', rating: 'warning' },
    { code: '300058', name: '蓝色光标', file: '300058/蓝色光标_300058_分析报告.md', rating: 'exclude' },
    { code: '300146', name: '汤臣倍健', file: '300146/汤臣倍健_300146_分析报告.md', rating: 'good' },
    { code: '300760', name: '迈瑞医疗', file: '300760/迈瑞医疗_300760_分析报告.md', rating: 'good' },
    { code: '300896', name: '爱美客', file: '300896/爱美客_300896_分析报告.md', rating: 'warning' },
    { code: '300979', name: '华利集团', file: '300979/华利集团_300979_分析报告.md', rating: 'good' },
    { code: '600009', name: '上海机场', file: '600009/上海机场_600009_分析报告.md', rating: 'warning' },
    { code: '600048', name: '保利发展', file: '600048/保利发展_600048_分析报告.md', rating: 'warning' },
    { code: '600132', name: '重庆啤酒', file: '600132/重庆啤酒_600132_分析报告.md', rating: 'good' },
    { code: '600519', name: '贵州茅台', file: '600519/贵州茅台_600519_分析报告.md', rating: 'good' },
    { code: '600600', name: '青岛啤酒', file: '600600/青岛啤酒_600600_分析报告.md', rating: 'good' },
    { code: '600887', name: '伊利股份', file: '600887/伊利股份_600887_分析报告.md', rating: 'good' },
    { code: '600900', name: '长江电力', file: '600900/长江电力_600900_分析报告.md', rating: 'good' },
    { code: '600941', name: '中国移动', file: '600941/中国移动_600941_分析报告.md', rating: 'good' },
    { code: '601728', name: '中国电信', file: '601728/中国电信_601728_分析报告.md', rating: 'good' },
    { code: '603288', name: '海天味业', file: '603288/海天味业_603288_分析报告.md', rating: 'good' },
    { code: '688036', name: '传音控股', file: '688036/传音控股_688036_分析报告.md', rating: 'good' },
    { code: '688363', name: '华熙生物', file: '688363/华熙生物_688363_分析报告.md', rating: 'warning' }
];

// 报告元数据缓存
const reportMetaCache = new Map();

// ============================================
// 工具函数
// ============================================

/**
 * 获取评级显示信息
 */
function getRatingInfo(rating) {
    const map = {
        good: { label: '优秀', emoji: '✅', class: 'good' },
        warning: { label: '警告', emoji: '⚠️', class: 'warning' },
        exclude: { label: '排除', emoji: '❌', class: 'exclude' }
    };
    return map[rating] || map.warning;
}

/**
 * 编码文件路径（处理空格等特殊字符）
 * 本地文件和 GitHub Pages 都使用相对路径
 */
function encodeFilePath(filePath) {
    // 将路径按 / 分割，对每一部分进行编码，然后重新组合
    return filePath.split('/').map(part => encodeURIComponent(part)).join('/');
}

/**
 * 解析报告元数据
 */
async function parseReportMeta(report) {
    if (reportMetaCache.has(report.code)) {
        return reportMetaCache.get(report.code);
    }

    try {
        const encodedPath = encodeFilePath(report.file);
        const response = await fetch(encodedPath);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const content = await response.text();
        
        // 提取价格
        const priceMatch = content.match(/当前股价[：:]\s*([\d,\.]+)\s*元/);
        const price = priceMatch ? priceMatch[1] : '--';
        
        // 提取日期
        const dateMatch = content.match(/分析日期[：:]\s*(\d{4}-\d{2}-\d{2})/);
        const date = dateMatch ? dateMatch[1] : '2026-03-12';
        
        // 提取摘要
        const summaryMatch = content.match(/核心结论[\s\S]*?(?=###|##|$)/);
        let summary = '';
        if (summaryMatch) {
            summary = summaryMatch[0]
                .replace(/[#*]/g, '')
                .replace(/\n+/g, ' ')
                .trim()
                .slice(0, 100) + '...';
        }
        
        // 提取标签
        const tags = [];
        if (content.includes('护城河极深')) tags.push('护城河深');
        if (content.includes('现金流极佳')) tags.push('现金流好');
        if (content.includes('毛利率')) {
            const marginMatch = content.match(/毛利率[:：]\s*(\d+)%/);
            if (marginMatch) tags.push(`毛利率${marginMatch[1]}%`);
        }
        
        const meta = { price, date, summary, tags: tags.slice(0, 3) };
        reportMetaCache.set(report.code, meta);
        return meta;
    } catch (error) {
        console.error(`解析报告 ${report.code} 失败:`, error);
        return { price: '--', date: '2026-03-12', summary: '', tags: [] };
    }
}

/**
 * 绘制评级分布图
 */
function drawRatingChart() {
    const canvas = document.getElementById('ratingChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const radius = Math.min(centerX, centerY) - 20;
    
    // 统计数据
    const stats = {
        good: state.reports.filter(r => r.rating === 'good').length,
        warning: state.reports.filter(r => r.rating === 'warning').length,
        exclude: state.reports.filter(r => r.rating === 'exclude').length
    };
    const total = state.reports.length;
    
    // 颜色
    const colors = {
        good: '#10b981',
        warning: '#f59e0b',
        exclude: '#ef4444'
    };
    
    // 绘制环形图
    let startAngle = -Math.PI / 2;
    
    Object.entries(stats).forEach(([key, value]) => {
        if (value === 0) return;
        
        const angle = (value / total) * Math.PI * 2;
        
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, startAngle, startAngle + angle);
        ctx.arc(centerX, centerY, radius * 0.6, startAngle + angle, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = colors[key];
        ctx.fill();
        
        startAngle += angle;
    });
    
    // 中心文字
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 32px Inter';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total.toString(), centerX, centerY - 8);
    
    ctx.font = '12px Inter';
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.fillText('报告总数', centerX, centerY + 16);
}

// ============================================
// 视图渲染
// ============================================

/**
 * 渲染报告卡片
 */
function createReportCard(report, meta) {
    const rating = getRatingInfo(report.rating);

    return `
        <div class="report-card" data-code="${report.code}" data-rating="${report.rating}">
            <div class="card-header">
                <span class="card-code">${report.code}</span>
            </div>
            <h4 class="card-title">${report.name}</h4>
            <p class="card-summary">${meta.summary || '基于龟龟投资策略框架的深度分析报告'}</p>
            <div class="card-footer">
                <span class="card-date">${meta.date}</span>
                <svg class="card-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
            </div>
        </div>
    `;
}

/**
 * 渲染报告列表项
 */
function createReportListItem(report, meta) {
    return `
        <div class="report-list-item" data-code="${report.code}" data-rating="${report.rating}">
            <div class="list-info">
                <h4>${report.name}</h4>
                <div class="list-meta">
                    <span class="list-code">${report.code}</span>
                    <span>${meta.date}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * 更新统计数据
 */
function updateStats() {
    const total = state.reports.length;
    const good = state.reports.filter(r => r.rating === 'good').length;
    const exclude = state.reports.filter(r => r.rating === 'exclude').length;
    
    document.getElementById('totalReports').textContent = total;
    document.getElementById('goodReports').textContent = good;
    document.getElementById('heroTotal').textContent = total;
    document.getElementById('heroGood').textContent = good;
    document.getElementById('heroExclude').textContent = exclude;
}

/**
 * 渲染最近报告
 */
async function renderRecentReports() {
    const container = document.getElementById('recentReports');
    const recentReports = state.reports.slice(0, 6);
    
    const cards = await Promise.all(
        recentReports.map(async report => {
            const meta = await parseReportMeta(report);
            return createReportCard(report, meta);
        })
    );
    
    container.innerHTML = cards.join('');
    
    // 绑定点击事件
    container.querySelectorAll('.report-card').forEach(card => {
        card.addEventListener('click', () => {
            const code = card.dataset.code;
            showReportDetail(code);
        });
    });
}

/**
 * 渲染报告列表
 */
async function renderReportList() {
    const container = document.getElementById('reportList');
    
    // 过滤
    let filtered = state.reports;
    if (state.currentFilter !== 'all') {
        filtered = filtered.filter(r => r.rating === state.currentFilter);
    }
    
    // 搜索
    if (state.searchQuery) {
        const query = state.searchQuery.toLowerCase();
        filtered = filtered.filter(r => 
            r.code.includes(query) || 
            r.name.toLowerCase().includes(query)
        );
    }
    
    // 排序
    filtered = [...filtered].sort((a, b) => {
        switch (state.currentSort) {
            case 'code':
                return a.code.localeCompare(b.code);
            case 'name':
                return a.name.localeCompare(b.name);
            default:
                return 0;
        }
    });
    
    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <h3>没有找到报告</h3>
                <p>尝试调整筛选条件或搜索关键词</p>
            </div>
        `;
        return;
    }
    
    const items = await Promise.all(
        filtered.map(async report => {
            const meta = await parseReportMeta(report);
            return createReportListItem(report, meta);
        })
    );
    
    container.innerHTML = items.join('');
    
    // 绑定点击事件
    container.querySelectorAll('.report-list-item').forEach(item => {
        item.addEventListener('click', () => {
            const code = item.dataset.code;
            showReportDetail(code);
        });
    });
}

/**
 * 渲染收藏列表
 */
async function renderFavorites() {
    const container = document.getElementById('favoritesGrid');
    const emptyState = document.getElementById('favoritesEmpty');
    
    if (state.favorites.length === 0) {
        container.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    container.style.display = 'grid';
    
    const favoriteReports = state.reports.filter(r => state.favorites.includes(r.code));
    
    const cards = await Promise.all(
        favoriteReports.map(async report => {
            const meta = await parseReportMeta(report);
            return createReportCard(report, meta);
        })
    );
    
    container.innerHTML = cards.join('');
    
    // 绑定点击事件
    container.querySelectorAll('.report-card').forEach(card => {
        card.addEventListener('click', () => {
            const code = card.dataset.code;
            showReportDetail(code);
        });
    });
}

/**
 * 显示报告详情
 */
async function showReportDetail(code) {
    const report = state.reports.find(r => r.code === code);
    if (!report) return;
    
    state.selectedReport = report;
    
    // 加载报告内容
    try {
        const encodedPath = encodeFilePath(report.file);
        const response = await fetch(encodedPath);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const content = await response.text();
        
        // 解析元数据
        const meta = await parseReportMeta(report);
        
        // 更新详情页信息
        document.getElementById('detailCode').textContent = report.code;
        document.getElementById('detailName').textContent = report.name;

        // 标签
        const tagsHtml = meta.tags.map(tag => `<span class="stock-tag">${tag}</span>`).join('');
        document.getElementById('detailTags').innerHTML = tagsHtml || '<span class="stock-tag">价值投资</span>';
        
        // 渲染 Markdown
        document.getElementById('markdownContent').innerHTML = marked.parse(content);
        
        // 生成目录
        generateTOC();
        
        // 更新收藏按钮状态
        updateFavoriteButton();
        
        // 更新下载链接
        document.getElementById('downloadBtn').href = encodedPath;
        document.getElementById('downloadBtn').download = `${report.name}_${report.code}_分析报告.md`;
        
        // 切换到详情视图
        switchView('detail');
        
    } catch (error) {
        console.error('加载报告失败:', error);
        alert('报告加载失败，请稍后重试');
    }
}

/**
 * 生成目录
 */
function generateTOC() {
    const headings = document.querySelectorAll('.markdown-body h2, .markdown-body h3');
    const tocNav = document.getElementById('tocNav');
    
    let html = '';
    headings.forEach((heading, index) => {
        const id = `section-${index}`;
        heading.id = id;
        
        const level = heading.tagName === 'H2' ? 'toc-h2' : 'toc-h3';
        const indent = heading.tagName === 'H3' ? 'style="padding-left: 1rem;"' : '';
        
        html += `<a href="#${id}" class="${level}" ${indent}>${heading.textContent}</a>`;
    });
    
    tocNav.innerHTML = html || '<p style="color: var(--primary-400); font-size: 0.875rem;">暂无目录</p>';
    
    // 绑定点击事件
    tocNav.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = link.getAttribute('href').slice(1);
            const target = document.getElementById(targetId);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
}

/**
 * 更新收藏按钮状态
 */
function updateFavoriteButton() {
    const btn = document.getElementById('favoriteBtn');
    const isFavorited = state.favorites.includes(state.selectedReport.code);
    
    if (isFavorited) {
        btn.classList.add('active');
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
        `;
    } else {
        btn.classList.remove('active');
        btn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
        `;
    }
}

/**
 * 切换收藏状态
 */
function toggleFavorite() {
    if (!state.selectedReport) return;
    
    const code = state.selectedReport.code;
    const index = state.favorites.indexOf(code);
    
    if (index > -1) {
        state.favorites.splice(index, 1);
    } else {
        state.favorites.push(code);
    }
    
    localStorage.setItem('favorites', JSON.stringify(state.favorites));
    updateFavoriteButton();
}

/**
 * 切换视图
 */
function switchView(viewName) {
    state.currentView = viewName;
    
    // 更新导航状态
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewName);
    });
    
    // 更新视图显示
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    
    const viewMap = {
        dashboard: 'dashboardView',
        reports: 'reportsView',
        favorites: 'favoritesView',
        about: 'aboutView',
        detail: 'detailView'
    };
    
    const targetView = document.getElementById(viewMap[viewName]);
    if (targetView) {
        targetView.classList.add('active');
    }
    
    // 更新页面标题
    const titleMap = {
        dashboard: '总览',
        reports: '报告列表',
        favorites: '收藏',
        about: '关于',
        detail: state.selectedReport?.name || '报告详情'
    };
    document.getElementById('pageTitle').textContent = titleMap[viewName];
    
    // 特殊处理
    if (viewName === 'favorites') {
        renderFavorites();
    } else if (viewName === 'dashboard') {
        setTimeout(drawRatingChart, 100);
    }
}

// ============================================
// 搜索功能
// ============================================

const searchModal = document.getElementById('searchModal');
const modalSearchInput = document.getElementById('modalSearchInput');
const searchResults = document.getElementById('searchResults');

/**
 * 打开搜索弹窗
 */
function openSearch() {
    searchModal.classList.add('active');
    modalSearchInput.focus();
    renderSearchResults('');
}

/**
 * 关闭搜索弹窗
 */
function closeSearch() {
    searchModal.classList.remove('active');
    modalSearchInput.value = '';
}

/**
 * 渲染搜索结果
 */
async function renderSearchResults(query) {
    let results = state.reports;
    
    if (query) {
        const lowerQuery = query.toLowerCase();
        results = results.filter(r => 
            r.code.includes(lowerQuery) || 
            r.name.toLowerCase().includes(lowerQuery)
        );
    }
    
    if (results.length === 0) {
        searchResults.innerHTML = '<div class="search-empty">没有找到匹配的报告</div>';
        return;
    }
    
    const items = await Promise.all(
        results.slice(0, 8).map(async report => {
            const meta = await parseReportMeta(report);
            const rating = getRatingInfo(report.rating);
            
            return `
                <div class="search-result-item" data-code="${report.code}">
                    <div class="search-result-rating ${rating.class}">${rating.emoji}</div>
                    <div class="search-result-info">
                        <div class="search-result-title">${report.name}</div>
                        <div class="search-result-meta">${report.code} · ${meta.price}元</div>
                    </div>
                </div>
            `;
        })
    );
    
    searchResults.innerHTML = items.join('');
    
    // 绑定点击事件
    searchResults.querySelectorAll('.search-result-item').forEach(item => {
        item.addEventListener('click', () => {
            const code = item.dataset.code;
            closeSearch();
            showReportDetail(code);
        });
    });
}

// ============================================
// 事件绑定
// ============================================

function initEventListeners() {
    // 侧边栏切换
    document.getElementById('sidebarToggle').addEventListener('click', () => {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        state.sidebarCollapsed = sidebar.classList.contains('collapsed');
        localStorage.setItem('sidebarCollapsed', state.sidebarCollapsed);
    });
    
    // 移动端菜单
    document.getElementById('mobileMenuBtn').addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('mobile-open');
    });
    
    // 导航点击
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.dataset.view;
            switchView(view);
            
            // 关闭移动端菜单
            document.getElementById('sidebar').classList.remove('mobile-open');
        });
    });
    
    // 筛选按钮
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.currentFilter = btn.dataset.filter;
            renderReportList();
        });
    });
    
    // 排序选择
    document.getElementById('sortSelect').addEventListener('change', (e) => {
        state.currentSort = e.target.value;
        renderReportList();
    });
    
    // 返回按钮
    document.getElementById('backBtn').addEventListener('click', () => {
        switchView('reports');
    });
    
    // 收藏按钮
    document.getElementById('favoriteBtn').addEventListener('click', toggleFavorite);
    
    // 搜索框
    document.getElementById('searchInput').addEventListener('focus', openSearch);
    
    // 搜索弹窗
    modalSearchInput.addEventListener('input', (e) => {
        renderSearchResults(e.target.value);
    });
    
    searchModal.addEventListener('click', (e) => {
        if (e.target === searchModal) {
            closeSearch();
        }
    });
    
    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
        // Cmd/Ctrl + K 打开搜索
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            openSearch();
        }
        
        // ESC 关闭搜索
        if (e.key === 'Escape' && searchModal.classList.contains('active')) {
            closeSearch();
        }
    });
    
    // 查看全部链接
    document.querySelectorAll('.view-all').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            switchView(link.dataset.view);
        });
    });
}

// ============================================
// 初始化
// ============================================

async function init() {
    // 初始化报告数据
    state.reports = reportData.map(r => ({ ...r }));
    
    // 恢复侧边栏状态
    if (state.sidebarCollapsed) {
        document.getElementById('sidebar').classList.add('collapsed');
    }
    
    // 绑定事件
    initEventListeners();
    
    // 更新统计
    updateStats();
    
    // 渲染初始视图
    await renderRecentReports();
    await renderReportList();
    
    // 绘制图表
    setTimeout(drawRatingChart, 100);
    
    console.log('龟龟投资策略报告库已加载');
}

// 启动应用
document.addEventListener('DOMContentLoaded', init);
