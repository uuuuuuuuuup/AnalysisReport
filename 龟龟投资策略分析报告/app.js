/**
 * 龟龟投资策略报告 - 应用逻辑
 * 功能：报告加载、模型分类、搜索、视图切换、收藏管理
 */

// ============================================
// 全局状态
// ============================================
const state = {
    reports: [],
    models: [],
    currentModel: 'all',
    favorites: JSON.parse(localStorage.getItem('favorites') || '[]'),
    currentView: 'dashboard',
    currentFilter: 'all',
    currentSort: 'date-desc',
    searchQuery: '',
    selectedReport: null,
    sidebarCollapsed: localStorage.getItem('sidebarCollapsed') === 'true'
};

// ============================================
// 报告数据定义 - 支持多模型
// ============================================
const reportData = [
    // Qwen3.5-Plus 模型
    { code: '000002', name: '万科 A', file: 'Qwen3.5-Plus/000002/万科 A_000002_分析报告.md', rating: 'exclude', model: 'Qwen3.5-Plus' },
    { code: '000538', name: '云南白药', file: 'Qwen3.5-Plus/000538/云南白药_000538_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '000568', name: '泸州老窖', file: 'Qwen3.5-Plus/000568/泸州老窖_000568_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '000858', name: '五粮液', file: 'Qwen3.5-Plus/000858/五粮液_000858_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '000895', name: '双汇发展', file: 'Qwen3.5-Plus/000895/双汇发展_000895_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '001914', name: '招商积余', file: 'Qwen3.5-Plus/001914/招商积余_001914_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '001965', name: '招商公路', file: 'Qwen3.5-Plus/001965/招商公路_001965_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '001979', name: '招商蛇口', file: 'Qwen3.5-Plus/001979/招商蛇口_001979_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '002027', name: '分众传媒', file: 'Qwen3.5-Plus/002027/分众传媒_002027_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '002304', name: '洋河股份', file: 'Qwen3.5-Plus/002304/洋河股份_002304_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '002352', name: '顺丰控股', file: 'Qwen3.5-Plus/002352/顺丰控股_002352_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '002507', name: '涪陵榨菜', file: 'Qwen3.5-Plus/002507/涪陵榨菜_002507_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '002568', name: '百润股份', file: 'Qwen3.5-Plus/002568/百润股份_002568_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '002991', name: '甘源食品', file: 'Qwen3.5-Plus/002991/甘源食品_002991_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '300058', name: '蓝色光标', file: 'Qwen3.5-Plus/300058/蓝色光标_300058_分析报告.md', rating: 'exclude', model: 'Qwen3.5-Plus' },
    { code: '300146', name: '汤臣倍健', file: 'Qwen3.5-Plus/300146/汤臣倍健_300146_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '300760', name: '迈瑞医疗', file: 'Qwen3.5-Plus/300760/迈瑞医疗_300760_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '300896', name: '爱美客', file: 'Qwen3.5-Plus/300896/爱美客_300896_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '300979', name: '华利集团', file: 'Qwen3.5-Plus/300979/华利集团_300979_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '600009', name: '上海机场', file: 'Qwen3.5-Plus/600009/上海机场_600009_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '600048', name: '保利发展', file: 'Qwen3.5-Plus/600048/保利发展_600048_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    { code: '600132', name: '重庆啤酒', file: 'Qwen3.5-Plus/600132/重庆啤酒_600132_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '600519', name: '贵州茅台', file: 'Qwen3.5-Plus/600519/贵州茅台_600519_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '600600', name: '青岛啤酒', file: 'Qwen3.5-Plus/600600/青岛啤酒_600600_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '600887', name: '伊利股份', file: 'Qwen3.5-Plus/600887/伊利股份_600887_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '600900', name: '长江电力', file: 'Qwen3.5-Plus/600900/长江电力_600900_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '600941', name: '中国移动', file: 'Qwen3.5-Plus/600941/中国移动_600941_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '601728', name: '中国电信', file: 'Qwen3.5-Plus/601728/中国电信_601728_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '603288', name: '海天味业', file: 'Qwen3.5-Plus/603288/海天味业_603288_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '688036', name: '传音控股', file: 'Qwen3.5-Plus/688036/传音控股_688036_分析报告.md', rating: 'good', model: 'Qwen3.5-Plus' },
    { code: '688363', name: '华熙生物', file: 'Qwen3.5-Plus/688363/华熙生物_688363_分析报告.md', rating: 'warning', model: 'Qwen3.5-Plus' },
    
    // GLM5 模型
    { code: '000002', name: '万科 A', file: 'GLM5/000002/万科A_000002_分析报告.md', rating: 'exclude', model: 'GLM5' },
    { code: '000538', name: '云南白药', file: 'GLM5/000538/云南白药_000538_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '000568', name: '泸州老窖', file: 'GLM5/000568/泸州老窖_000568_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '000858', name: '五粮液', file: 'GLM5/000858/五粮液_000858_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '000895', name: '双汇发展', file: 'GLM5/000895/双汇发展_000895_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '001914', name: '招商积余', file: 'GLM5/001914/招商积余_001914_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '001965', name: '招商公路', file: 'GLM5/001965/招商公路_001965_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '001979', name: '招商蛇口', file: 'GLM5/001979/招商蛇口_001979_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002027', name: '分众传媒', file: 'GLM5/002027/分众传媒_002027_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '002304', name: '洋河股份', file: 'GLM5/002304/洋河股份_002304_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '002352', name: '顺丰控股', file: 'GLM5/002352/顺丰控股_002352_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002507', name: '涪陵榨菜', file: 'GLM5/002507/涪陵榨菜_002507_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '002568', name: '百润股份', file: 'GLM5/002568/百润股份_002568_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002991', name: '甘源食品', file: 'GLM5/002991/甘源食品_002991_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '300015', name: '爱尔眼科', file: 'GLM5/300015/爱尔眼科_300015_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300146', name: '汤臣倍健', file: 'GLM5/300146/汤臣倍健_300146_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '300760', name: '迈瑞医疗', file: 'GLM5/300760/迈瑞医疗_300760_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '300896', name: '爱美客', file: 'GLM5/300896/爱美客_300896_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300979', name: '华利集团', file: 'GLM5/300979/华利集团_300979_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600009', name: '上海机场', file: 'GLM5/600009/上海机场_600009_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600048', name: '保利发展', file: 'GLM5/600048/保利发展_600048_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600132', name: '重庆啤酒', file: 'GLM5/600132/重庆啤酒_600132_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600519', name: '贵州茅台', file: 'GLM5/600519/贵州茅台_600519_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600600', name: '青岛啤酒', file: 'GLM5/600600/青岛啤酒_600600_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600887', name: '伊利股份', file: 'GLM5/600887/伊利股份_600887_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600900', name: '长江电力', file: 'GLM5/600900/长江电力_600900_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600941', name: '中国移动', file: 'GLM5/600941/中国移动_600941_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '601728', name: '中国电信', file: 'GLM5/601728/中国电信_601728_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '603288', name: '海天味业', file: 'GLM5/603288/海天味业_603288_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '688036', name: '传音控股', file: 'GLM5/688036/传音控股_688036_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '688363', name: '华熙生物', file: 'GLM5/688363/华熙生物_688363_分析报告.md', rating: 'warning', model: 'GLM5' },
    
    // GLM5 新增报告 (2026-03-12)
    { code: '000333', name: '美的集团', file: 'GLM5/000333/美的集团_000333_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '000423', name: '东阿阿胶', file: 'GLM5/000423/东阿阿胶_000423_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '000429', name: '粤高速A', file: 'GLM5/000429/粤高速A_000429_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000848', name: '承德露露', file: 'GLM5/000848/承德露露_000848_分析报告.md', rating: 'exclude', model: 'GLM5' },
    { code: '002690', name: '美亚光电', file: 'GLM5/002690/美亚光电_002690_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300627', name: '华测导航', file: 'GLM5/300627/华测导航_300627_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300628', name: '亿联网络', file: 'GLM5/300628/亿联网络_300628_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '300866', name: '安克创新', file: 'GLM5/300866/安克创新_300866_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '301061', name: '匠心家居', file: 'GLM5/301061/匠心家居_301061_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600018', name: '上港集团', file: 'GLM5/600018/上港集团_600018_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600025', name: '华能水电', file: 'GLM5/600025/华能水电_600025_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600036', name: '招商银行', file: 'GLM5/600036/招商银行_600036_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600066', name: '宇通客车', file: 'GLM5/600066/宇通客车_600066_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600276', name: '恒瑞医药', file: 'GLM5/600276/恒瑞医药_600276_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600674', name: '川投能源', file: 'GLM5/600674/川投能源_600674_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600885', name: '宏发股份', file: 'GLM5/600885/宏发股份_600885_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601298', name: '青岛港', file: 'GLM5/601298/青岛港_601298_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '603129', name: '春风动力', file: 'GLM5/603129/春风动力_603129_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603259', name: '药明康德', file: 'GLM5/603259/药明康德_603259_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '688334', name: '西高院', file: 'GLM5/688334/西高院_688334_分析报告.md', rating: 'warning', model: 'GLM5' },
    
    // GLM5 新增报告 (2026-03-13) - Git 未跟踪文件
    { code: '000063', name: '中兴通讯', file: 'GLM5/000063/中兴通讯_000063_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000100', name: 'TCL 科技', file: 'GLM5/000100/TCL 科技_000100_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000401', name: '冀东水泥', file: 'GLM5/000401/冀东水泥_000401_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000513', name: '丽珠集团', file: 'GLM5/000513/丽珠集团_000513_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000596', name: '古井贡酒', file: 'GLM5/000596/古井贡酒_000596_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '000625', name: '长安汽车', file: 'GLM5/000625/长安汽车_000625_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000661', name: '长春高新', file: 'GLM5/000661/长春高新_000661_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000725', name: '京东方 A', file: 'GLM5/000725/京东方A_000725_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000786', name: '北新建材', file: 'GLM5/000786/北新建材_000786_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '000876', name: '新希望', file: 'GLM5/000876/新希望_000876_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '001289', name: '龙源电力', file: 'GLM5/001289/龙源电力_001289_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002241', name: '歌尔股份', file: 'GLM5/002241/歌尔股份_002241_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002311', name: '海大集团', file: 'GLM5/002311/海大集团_002311_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002327', name: '富安娜', file: 'GLM5/002327/富安娜_002327_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002415', name: '海康威视', file: 'GLM5/002415/海康威视_002415_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002459', name: '晶澳科技', file: 'GLM5/002459/晶澳科技_002459_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002475', name: '立讯精密', file: 'GLM5/002475/立讯精密_002475_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002557', name: '洽洽食品', file: 'GLM5/002557/洽洽食品_002557_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002572', name: '索菲亚', file: 'GLM5/002572/索菲亚_002572_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002594', name: '比亚迪', file: 'GLM5/002594/比亚迪_002594_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002714', name: '牧原股份', file: 'GLM5/002714/牧原股份_002714_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '002867', name: '周大生', file: 'GLM5/002867/周大生_002867_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '003000', name: '劲仔食品', file: 'GLM5/003000/劲仔食品_003000_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300347', name: '泰格医药', file: 'GLM5/300347/泰格医药_300347_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300413', name: '芒果超媒', file: 'GLM5/300413/芒果超媒_300413_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300498', name: '温氏股份', file: 'GLM5/300498/温氏股份_300498_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300759', name: '康龙化成', file: 'GLM5/300759/康龙化成_300759_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '300782', name: '卓胜微', file: 'GLM5/300782/卓胜微_300782_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600050', name: '中国联通', file: 'GLM5/600050/中国联通_600050_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600061', name: '国投资本', file: 'GLM5/600061/国投资本_600061_分析报告.md', rating: 'exclude', model: 'GLM5' },
    { code: '600085', name: '同仁堂', file: 'GLM5/600085/同仁堂_600085_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600196', name: '复星医药', file: 'GLM5/600196/复星医药_600196_分析报告.md', rating: 'exclude', model: 'GLM5' },
    { code: '600332', name: '白云山', file: 'GLM5/600332/白云山_600332_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600398', name: '海澜之家', file: 'GLM5/600398/海澜之家_600398_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600436', name: '片仔癀', file: 'GLM5/600436/片仔癀_600436_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600438', name: '通威股份', file: 'GLM5/600438/通威股份_600438_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600566', name: '济川药业', file: 'GLM5/600566/济川药业_600566_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600585', name: '海螺水泥', file: 'GLM5/600585/海螺水泥_600585_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600690', name: '海尔智家', file: 'GLM5/600690/海尔智家_600690_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600763', name: '通策医疗', file: 'GLM5/600763/通策医疗_600763_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600809', name: '山西汾酒', file: 'GLM5/600809/山西汾酒_600809_分析报告.md', rating: 'good', model: 'GLM5' },
    { code: '600872', name: '中炬高新', file: 'GLM5/600872/中炬高新_600872_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '600905', name: '三峡能源', file: 'GLM5/600905/三峡能源_600905_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601006', name: '大秦铁路', file: 'GLM5/601006/大秦铁路_601006_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601012', name: '隆基绿能', file: 'GLM5/601012/隆基绿能_601012_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601186', name: '中国铁建', file: 'GLM5/601186/中国铁建_601186_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601390', name: '中国中铁', file: 'GLM5/601390/中国中铁_601390_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601607', name: '上海医药', file: 'GLM5/601607/上海医药_601607_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601618', name: '中国中冶', file: 'GLM5/601618/中国中冶_601618_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601633', name: '长城汽车', file: 'GLM5/601633/长城汽车_601633_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601816', name: '京沪高铁', file: 'GLM5/601816/京沪高铁_601816_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601865', name: '福莱特', file: 'GLM5/601865/福莱特_601865_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '601888', name: '中国中免', file: 'GLM5/601888/中国中免_601888_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603027', name: '千禾味业', file: 'GLM5/603027/千禾味业_603027_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603345', name: '安井食品', file: 'GLM5/603345/安井食品_603345_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603369', name: '今世缘', file: 'GLM5/603369/今世缘_603369_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603605', name: '珀莱雅', file: 'GLM5/603605/珀莱雅_603605_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603806', name: '福斯特', file: 'GLM5/603806/福斯特_603806_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '603833', name: '欧派家居', file: 'GLM5/603833/欧派家居_603833_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '605499', name: '东鹏饮料', file: 'GLM5/605499/东鹏饮料_605499_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '688169', name: '石头科技', file: 'GLM5/688169/石头科技_688169_分析报告.md', rating: 'warning', model: 'GLM5' },
    { code: '688271', name: '联影医疗', file: 'GLM5/688271/联影医疗_688271_分析报告.md', rating: 'warning', model: 'GLM5' }
];

// 模型配置
const modelConfig = {
    'Qwen3.5-Plus': { name: 'Qwen3.5-Plus', icon: '🤖', color: '#10b981' },
    'GLM5': { name: 'GLM5', icon: '🧠', color: '#8b5cf6' }
};

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
 * 获取模型信息
 */
function getModelInfo(model) {
    return modelConfig[model] || { name: model, icon: '🤖', color: '#6b7280' };
}

/**
 * 编码文件路径（处理空格等特殊字符）
 */
function encodeFilePath(filePath) {
    return filePath.split('/').map(part => encodeURIComponent(part)).join('/');
}

/**
 * 解析报告元数据
 */
async function parseReportMeta(report) {
    const cacheKey = `${report.model}-${report.code}`;
    if (reportMetaCache.has(cacheKey)) {
        return reportMetaCache.get(cacheKey);
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
        reportMetaCache.set(cacheKey, meta);
        return meta;
    } catch (error) {
        console.error(`解析报告 ${cacheKey} 失败:`, error);
        return { price: '--', date: '2026-03-12', summary: '', tags: [] };
    }
}

/**
 * 获取所有模型列表
 */
function getModels() {
    const models = new Set();
    reportData.forEach(r => models.add(r.model));
    return Array.from(models);
}

/**
 * 按模型分组报告
 */
function groupReportsByModel(reports) {
    const grouped = {};
    reports.forEach(report => {
        if (!grouped[report.model]) {
            grouped[report.model] = [];
        }
        grouped[report.model].push(report);
    });
    return grouped;
}

/**
 * 获取某股票的所有模型分析
 */
function getReportsByCode(code) {
    return reportData.filter(r => r.code === code);
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

    // 检查 canvas 尺寸是否有效
    if (rect.width <= 0 || rect.height <= 0) {
        console.warn('Canvas 尺寸无效，跳过绘制');
        return;
    }

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    // 确保半径不为负数，设置最小值
    const radius = Math.max(10, Math.min(centerX, centerY) - 20);

    // 统计数据
    const reports = state.currentModel === 'all'
        ? state.reports
        : state.reports.filter(r => r.model === state.currentModel);

    const stats = {
        good: reports.filter(r => r.rating === 'good').length,
        warning: reports.filter(r => r.rating === 'warning').length,
        exclude: reports.filter(r => r.rating === 'exclude').length
    };
    const total = reports.length;

    // 如果没有数据，显示空状态
    if (total === 0) {
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '14px Inter';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('暂无数据', centerX, centerY);
        return;
    }

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
// 模型选择器
// ============================================

function initModelSelector() {
    const modelSelectBtn = document.getElementById('modelSelectBtn');
    const modelDropdown = document.getElementById('modelDropdown');
    
    // 生成模型选项
    const models = getModels();
    models.forEach(model => {
        const config = getModelInfo(model);
        const count = reportData.filter(r => r.model === model).length;
        
        const option = document.createElement('div');
        option.className = 'model-option';
        option.dataset.model = model;
        option.innerHTML = `
            <span class="model-option-icon">${config.icon}</span>
            <span class="model-option-name">${config.name}</span>
            <span class="model-option-count">${count}</span>
        `;
        option.addEventListener('click', () => selectModel(model));
        modelDropdown.appendChild(option);
    });
    
    // 更新全部模型数量
    document.getElementById('allModelCount').textContent = reportData.length;
    
    // 切换下拉菜单
    modelSelectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        modelDropdown.classList.toggle('active');
        
        // 在移动端，将下拉框定位到底部
        if (window.innerWidth <= 768) {
            modelDropdown.style.position = 'fixed';
            modelDropdown.style.top = 'auto';
            modelDropdown.style.left = 'var(--space-4)';
            modelDropdown.style.right = 'var(--space-4)';
            modelDropdown.style.bottom = 'var(--space-4)';
            modelDropdown.style.maxHeight = '60vh';
            modelDropdown.style.overflowY = 'auto';
            modelDropdown.style.webkitOverflowScrolling = 'touch';
        }
    });
    
    // 点击外部关闭
    document.addEventListener('click', (e) => {
        // 检查点击是否在下拉框内
        if (!modelDropdown.contains(e.target) && !modelSelectBtn.contains(e.target)) {
            modelDropdown.classList.remove('active');
        }
    });
    
    // 移动端点击下拉框内部不关闭
    modelDropdown.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

function selectModel(model) {
    state.currentModel = model;
    
    // 更新按钮显示
    const config = model === 'all' 
        ? { name: '全部模型', icon: '🌐' }
        : getModelInfo(model);
    document.getElementById('currentModelName').textContent = config.name;
    document.querySelector('.model-icon').textContent = config.icon;
    
    // 更新选项状态
    document.querySelectorAll('.model-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.model === model);
    });
    
    // 更新 Hero 文本
    const heroModelText = document.getElementById('heroModelText');
    if (heroModelText) {
        heroModelText.textContent = model === 'all' 
            ? '多模型智能分析'
            : `${config.name} 分析结果`;
    }
    
    // 刷新视图
    updateStats();
    renderRecentReports();
    renderReportList();
    drawRatingChart();
}

// ============================================
// 视图渲染
// ============================================

/**
 * 渲染报告卡片
 */
function createReportCard(report, meta) {
    const modelInfo = getModelInfo(report.model);
    
    return `
        <div class="report-card" data-code="${report.code}" data-model="${report.model}" data-rating="${report.rating}">
            <div class="card-header">
                <span class="card-code">${report.code}</span>
                <span class="card-model" style="background: ${modelInfo.color}20; color: ${modelInfo.color}">
                    ${modelInfo.icon} ${modelInfo.name}
                </span>
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
    const modelInfo = getModelInfo(report.model);
    const rating = getRatingInfo(report.rating);
    
    return `
        <div class="report-list-item" data-code="${report.code}" data-model="${report.model}" data-rating="${report.rating}">
            <div class="list-rating ${rating.class}">${rating.emoji}</div>
            <div class="list-info">
                <h4>${report.name}</h4>
                <div class="list-meta">
                    <span class="list-code">${report.code}</span>
                    <span class="list-model" style="color: ${modelInfo.color}">
                        ${modelInfo.icon} ${modelInfo.name}
                    </span>
                    <span>${meta.date}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * 渲染模型统计卡片
 */
function renderModelStats() {
    const container = document.getElementById('modelStatsGrid');
    if (!container) return;
    
    const models = getModels();
    const grouped = groupReportsByModel(reportData);
    
    let html = '';
    
    // 添加"全部模型"卡片
    const allStats = {
        good: reportData.filter(r => r.rating === 'good').length,
        warning: reportData.filter(r => r.rating === 'warning').length,
        exclude: reportData.filter(r => r.rating === 'exclude').length
    };
    
    html += `
        <div class="model-stat-card ${state.currentModel === 'all' ? 'active' : ''}" data-model="all">
            <div class="model-stat-header">
                <span class="model-stat-icon">🌐</span>
                <span class="model-stat-name">全部模型</span>
            </div>
            <div class="model-stat-count">${reportData.length}</div>
            <div class="model-stat-breakdown">
                <span class="breakdown-item good">${allStats.good}</span>
                <span class="breakdown-item warning">${allStats.warning}</span>
                <span class="breakdown-item exclude">${allStats.exclude}</span>
            </div>
        </div>
    `;
    
    // 添加各模型卡片
    models.forEach(model => {
        const config = getModelInfo(model);
        const reports = grouped[model] || [];
        const stats = {
            good: reports.filter(r => r.rating === 'good').length,
            warning: reports.filter(r => r.rating === 'warning').length,
            exclude: reports.filter(r => r.rating === 'exclude').length
        };
        
        html += `
            <div class="model-stat-card ${state.currentModel === model ? 'active' : ''}" data-model="${model}">
                <div class="model-stat-header">
                    <span class="model-stat-icon">${config.icon}</span>
                    <span class="model-stat-name">${config.name}</span>
                </div>
                <div class="model-stat-count">${reports.length}</div>
                <div class="model-stat-breakdown">
                    <span class="breakdown-item good">${stats.good}</span>
                    <span class="breakdown-item warning">${stats.warning}</span>
                    <span class="breakdown-item exclude">${stats.exclude}</span>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
    
    // 绑定点击事件
    container.querySelectorAll('.model-stat-card').forEach(card => {
        card.addEventListener('click', () => {
            selectModel(card.dataset.model);
        });
    });
}

/**
 * 更新统计数据
 */
function updateStats() {
    const reports = state.currentModel === 'all' 
        ? state.reports 
        : state.reports.filter(r => r.model === state.currentModel);
    
    const total = reports.length;
    const good = reports.filter(r => r.rating === 'good').length;
    const exclude = reports.filter(r => r.rating === 'exclude').length;
    const models = getModels().length;
    
    document.getElementById('totalReports').textContent = total;
    document.getElementById('modelCount').textContent = models;
    document.getElementById('heroTotal').textContent = total;
    document.getElementById('heroGood').textContent = good;
    document.getElementById('heroExclude').textContent = exclude;
    
    // 更新模型统计卡片
    renderModelStats();
}

/**
 * 渲染最近报告
 */
async function renderRecentReports() {
    const container = document.getElementById('recentReports');
    
    let reports = state.currentModel === 'all'
        ? state.reports
        : state.reports.filter(r => r.model === state.currentModel);
    
    const recentReports = reports.slice(0, 6);
    
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
            const model = card.dataset.model;
            showReportDetail(code, model);
        });
    });
}

/**
 * 渲染按模型分组的报告列表
 */
async function renderReportsByModel() {
    const container = document.getElementById('reportsByModel');
    const listContainer = document.getElementById('reportList');
    
    // 如果有筛选或搜索，使用列表视图
    if (state.currentFilter !== 'all' || state.searchQuery) {
        container.style.display = 'none';
        listContainer.style.display = 'flex';
        return renderReportList();
    }
    
    container.style.display = 'block';
    listContainer.style.display = 'none';
    
    // 获取要显示的模型
    let models = state.currentModel === 'all' 
        ? getModels() 
        : [state.currentModel];
    
    let html = '';
    
    for (const model of models) {
        const config = getModelInfo(model);
        const reports = state.reports.filter(r => r.model === model);
        
        if (reports.length === 0) continue;
        
        // 排序
        const sortedReports = [...reports].sort((a, b) => {
            switch (state.currentSort) {
                case 'code':
                    return a.code.localeCompare(b.code);
                case 'name':
                    return a.name.localeCompare(b.name);
                default:
                    return 0;
            }
        });
        
        const cards = await Promise.all(
            sortedReports.map(async report => {
                const meta = await parseReportMeta(report);
                return createReportCard(report, meta);
            })
        );
        
        html += `
            <div class="model-section">
                <div class="model-section-header">
                    <span class="model-section-icon" style="background: ${config.color}20; color: ${config.color}">
                        ${config.icon}
                    </span>
                    <h4 class="model-section-title">${config.name}</h4>
                    <span class="model-section-count">${reports.length} 份报告</span>
                </div>
                <div class="report-grid">
                    ${cards.join('')}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html || '<div class="empty-state"><div class="empty-icon">📭</div><h3>没有找到报告</h3></div>';
    
    // 绑定点击事件
    container.querySelectorAll('.report-card').forEach(card => {
        card.addEventListener('click', () => {
            const code = card.dataset.code;
            const model = card.dataset.model;
            showReportDetail(code, model);
        });
    });
}

/**
 * 渲染报告列表（纯列表视图）
 */
async function renderReportList() {
    const container = document.getElementById('reportList');
    
    // 过滤
    let filtered = state.currentModel === 'all'
        ? state.reports
        : state.reports.filter(r => r.model === state.currentModel);
    
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
            const model = item.dataset.model;
            showReportDetail(code, model);
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
    
    const favoriteReports = state.reports.filter(r => state.favorites.includes(`${r.model}-${r.code}`));
    
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
            const model = card.dataset.model;
            showReportDetail(code, model);
        });
    });
}

/**
 * 渲染模型对比视图
 */
async function renderComparisonView() {
    const container = document.getElementById('comparisonContent');
    
    // 获取所有被多个模型分析的股票代码
    const codeMap = {};
    state.reports.forEach(report => {
        if (!codeMap[report.code]) {
            codeMap[report.code] = [];
        }
        codeMap[report.code].push(report);
    });
    
    // 过滤出被多个模型分析的股票
    const multiModelCodes = Object.entries(codeMap)
        .filter(([_, reports]) => reports.length > 1)
        .map(([code, _]) => code);
    
    if (multiModelCodes.length === 0) {
        container.innerHTML = `
            <div class="comparison-empty">
                <div class="empty-icon">📊</div>
                <h3>暂无对比数据</h3>
                <p>目前没有股票被多个模型分析</p>
            </div>
        `;
        return;
    }
    
    // 按代码排序
    multiModelCodes.sort();
    
    let html = `
        <div class="comparison-intro">
            <p>发现 <strong>${multiModelCodes.length}</strong> 只股票被多个模型分析，点击卡片查看详细对比</p>
        </div>
        <div class="comparison-grid">
    `;
    
    for (const code of multiModelCodes) {
        const reports = codeMap[code];
        const firstReport = reports[0];
        
        // 统计各模型的评级
        const ratingCount = { good: 0, warning: 0, exclude: 0 };
        reports.forEach(r => {
            ratingCount[r.rating]++;
        });
        
        html += `
            <div class="comparison-stock-card" data-code="${code}">
                <div class="comparison-stock-header">
                    <div class="stock-info">
                        <span class="stock-code-lg">${code}</span>
                        <h4>${firstReport.name}</h4>
                    </div>
                    <div class="rating-summary">
                        <span class="rating-count good" title="优秀">${ratingCount.good}</span>
                        <span class="rating-count warning" title="警告">${ratingCount.warning}</span>
                        <span class="rating-count exclude" title="排除">${ratingCount.exclude}</span>
                    </div>
                </div>
                <div class="comparison-models">
        `;
        
        for (const report of reports) {
            const modelInfo = getModelInfo(report.model);
            const rating = getRatingInfo(report.rating);
            
            html += `
                <div class="comparison-model-item">
                    <div class="model-info-row">
                        <span class="model-icon-small">${modelInfo.icon}</span>
                        <span class="model-name-small">${modelInfo.name}</span>
                    </div>
                    <span class="rating-pill ${rating.class}">${rating.emoji} ${rating.label}</span>
                </div>
            `;
        }
        
        html += `
                </div>
                <button class="compare-btn" data-code="${code}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
                    </svg>
                    对比分析
                </button>
            </div>
        `;
    }
    
    html += '</div>';
    container.innerHTML = html;
    
    // 绑定点击事件
    container.querySelectorAll('.compare-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const code = btn.dataset.code;
            showComparisonDetail(code);
        });
    });
    
    // 卡片点击也可以进入详情
    container.querySelectorAll('.comparison-stock-card').forEach(card => {
        card.addEventListener('click', () => {
            const code = card.dataset.code;
            showComparisonDetail(code);
        });
    });
}

/**
 * 显示对比详情
 */
async function showComparisonDetail(code, model) {
    const allReports = getReportsByCode(code);
    if (allReports.length === 0) return;
    
    // 如果指定了模型，使用指定模型；否则使用第一个
    let report = model 
        ? allReports.find(r => r.model === model)
        : allReports[0];
    
    if (!report && allReports.length > 0) {
        report = allReports[0];
    }
    
    if (!report) return;
    
    // 切换到详情视图并显示对比
    state.selectedReport = report;
    state.currentComparisonCode = code;
    
    // 加载报告的内容
    try {
        const encodedPath = encodeFilePath(report.file);
        const response = await fetch(encodedPath);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const content = await response.text();
        
        const meta = await parseReportMeta(report);
        const modelInfo = getModelInfo(report.model);
        
        document.getElementById('detailCode').textContent = code;
        document.getElementById('detailName').textContent = report.name;
        
        const modelBadge = document.getElementById('detailModelBadge');
        modelBadge.textContent = `${modelInfo.icon} ${modelInfo.name}`;
        modelBadge.style.background = `${modelInfo.color}20`;
        modelBadge.style.color = modelInfo.color;
        
        const tagsHtml = meta.tags.map(tag => `<span class="stock-tag">${tag}</span>`).join('');
        document.getElementById('detailTags').innerHTML = tagsHtml || '<span class="stock-tag">价值投资</span>';
        
        document.getElementById('markdownContent').innerHTML = marked.parse(content);
        
        generateTOC();
        updateFavoriteButton();
        
        document.getElementById('downloadBtn').href = encodedPath;
        document.getElementById('downloadBtn').download = `${report.name}_${code}_分析报告.md`;
        
        // 显示模型切换和对比提示
        const modelSwitch = document.getElementById('detailModelSwitch');
        const modelSelect = document.getElementById('detailModelSelect');
        
        if (allReports.length > 1) {
            modelSwitch.style.display = 'flex';
            modelSelect.innerHTML = allReports.map(r => {
                const info = getModelInfo(r.model);
                return `<option value="${r.model}" ${r.model === report.model ? 'selected' : ''}>${info.icon} ${info.name}</option>`;
            }).join('');
            
            modelSelect.onchange = (e) => {
                showComparisonDetail(code, e.target.value);
            };
        } else {
            modelSwitch.style.display = 'none';
        }
        
        // 添加对比提示
        const comparisonNotice = document.createElement('div');
        comparisonNotice.className = 'comparison-notice';
        comparisonNotice.innerHTML = `
            <div style="padding: var(--space-4); background: var(--accent-50); border-radius: var(--radius-lg); margin-bottom: var(--space-4);">
                <strong>📊 多模型对比</strong>
                <p style="margin: var(--space-2) 0 0 0; font-size: 0.875rem; color: var(--primary-600);">
                    该股票有 ${allReports.length} 个模型的分析报告，使用上方的模型切换器查看不同模型的分析
                </p>
            </div>
        `;
        
        const existingNotice = document.querySelector('.comparison-notice');
        if (existingNotice) existingNotice.remove();
        
        document.querySelector('.detail-header').insertAdjacentElement('afterend', comparisonNotice);
        
        switchView('detail');
        
    } catch (error) {
        console.error('加载报告失败:', error);
        alert('报告加载失败，请稍后重试');
    }
}

/**
 * 更新报告导航状态
 * 根据当前筛选条件计算上一篇和下一篇报告
 */
function updateReportNavigationState(currentReport) {
    // 获取当前筛选条件下的报告列表
    let filteredReports = state.currentModel === 'all'
        ? [...state.reports]
        : state.reports.filter(r => r.model === state.currentModel);

    // 应用评级筛选
    if (state.currentFilter !== 'all') {
        filteredReports = filteredReports.filter(r => r.rating === state.currentFilter);
    }

    // 应用搜索筛选
    if (state.searchQuery) {
        const query = state.searchQuery.toLowerCase();
        filteredReports = filteredReports.filter(r =>
            r.code.includes(query) ||
            r.name.toLowerCase().includes(query)
        );
    }

    // 应用排序
    filteredReports.sort((a, b) => {
        switch (state.currentSort) {
            case 'code':
                return a.code.localeCompare(b.code);
            case 'name':
                return a.name.localeCompare(b.name);
            default:
                return 0;
        }
    });

    // 找到当前报告的索引
    const currentIndex = filteredReports.findIndex(
        r => r.code === currentReport.code && r.model === currentReport.model
    );

    // 保存导航状态
    state.navigationList = filteredReports;
    state.navigationIndex = currentIndex;

    // 更新导航按钮状态
    updateNavigationButtons();
}

/**
 * 更新导航按钮的显示状态
 */
function updateNavigationButtons() {
    const prevBtn = document.getElementById('prevReportBtn');
    const nextBtn = document.getElementById('nextReportBtn');

    if (!prevBtn || !nextBtn) return;

    const hasPrev = state.navigationIndex > 0;
    const hasNext = state.navigationIndex < state.navigationList.length - 1;

    prevBtn.disabled = !hasPrev;
    nextBtn.disabled = !hasNext;

    prevBtn.style.opacity = hasPrev ? '1' : '0.4';
    nextBtn.style.opacity = hasNext ? '1' : '0.4';
    prevBtn.style.cursor = hasPrev ? 'pointer' : 'not-allowed';
    nextBtn.style.cursor = hasNext ? 'pointer' : 'not-allowed';
}

/**
 * 导航到上一篇报告
 */
function navigateToPrevReport() {
    if (state.navigationIndex > 0) {
        const prevReport = state.navigationList[state.navigationIndex - 1];
        showReportDetail(prevReport.code, prevReport.model);
    }
}

/**
 * 导航到下一篇报告
 */
function navigateToNextReport() {
    if (state.navigationIndex < state.navigationList.length - 1) {
        const nextReport = state.navigationList[state.navigationIndex + 1];
        showReportDetail(nextReport.code, nextReport.model);
    }
}

/**
 * 显示报告详情
 */
async function showReportDetail(code, model) {
    // 获取该股票的所有模型分析
    const allReports = getReportsByCode(code);

    // 如果指定了模型，使用指定模型；否则使用第一个
    let report = model
        ? allReports.find(r => r.model === model)
        : allReports[0];

    if (!report && allReports.length > 0) {
        report = allReports[0];
    }

    if (!report) return;

    state.selectedReport = report;

    // 计算当前报告在列表中的位置，用于上一篇/下一篇导航
    updateReportNavigationState(report);
    
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
        const modelInfo = getModelInfo(report.model);
        
        // 更新详情页信息
        document.getElementById('detailCode').textContent = report.code;
        document.getElementById('detailName').textContent = report.name;
        
        // 模型标识
        const modelBadge = document.getElementById('detailModelBadge');
        modelBadge.textContent = `${modelInfo.icon} ${modelInfo.name}`;
        modelBadge.style.background = `${modelInfo.color}20`;
        modelBadge.style.color = modelInfo.color;

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
        
        // 处理多模型切换
        const modelSwitch = document.getElementById('detailModelSwitch');
        const modelSelect = document.getElementById('detailModelSelect');
        
        if (allReports.length > 1) {
            modelSwitch.style.display = 'flex';
            modelSelect.innerHTML = allReports.map(r => {
                const info = getModelInfo(r.model);
                return `<option value="${r.model}" ${r.model === report.model ? 'selected' : ''}>${info.icon} ${info.name}</option>`;
            }).join('');
            
            modelSelect.onchange = (e) => {
                showReportDetail(code, e.target.value);
            };
        } else {
            modelSwitch.style.display = 'none';
        }
        
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
    const favoriteKey = `${state.selectedReport.model}-${state.selectedReport.code}`;
    const isFavorited = state.favorites.includes(favoriteKey);
    
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
    
    const favoriteKey = `${state.selectedReport.model}-${state.selectedReport.code}`;
    const index = state.favorites.indexOf(favoriteKey);
    
    if (index > -1) {
        state.favorites.splice(index, 1);
    } else {
        state.favorites.push(favoriteKey);
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
        comparison: 'comparisonView',
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
        comparison: '模型对比',
        favorites: '收藏',
        about: '关于',
        detail: state.selectedReport?.name || '报告详情'
    };
    document.getElementById('pageTitle').textContent = titleMap[viewName];
    
    // 控制 Header 导航按钮显示/隐藏
    const headerNav = document.getElementById('headerNav');
    if (headerNav) {
        headerNav.style.display = viewName === 'detail' ? 'flex' : 'none';
    }

    // 特殊处理
    if (viewName === 'favorites') {
        renderFavorites();
    } else if (viewName === 'dashboard') {
        setTimeout(drawRatingChart, 100);
    } else if (viewName === 'reports') {
        renderReportsByModel();
    } else if (viewName === 'comparison') {
        renderComparisonView();
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
    
    // 去重 - 按股票代码分组，显示多个模型的结果
    const groupedByCode = {};
    results.forEach(r => {
        if (!groupedByCode[r.code]) {
            groupedByCode[r.code] = [];
        }
        groupedByCode[r.code].push(r);
    });
    
    const uniqueCodes = Object.keys(groupedByCode);
    
    if (uniqueCodes.length === 0) {
        searchResults.innerHTML = '<div class="search-empty">没有找到匹配的报告</div>';
        return;
    }
    
    const items = await Promise.all(
        uniqueCodes.slice(0, 8).map(async code => {
            const reports = groupedByCode[code];
            const report = reports[0];
            const meta = await parseReportMeta(report);
            const modelCount = reports.length;
            
            return `
                <div class="search-result-item" data-code="${code}">
                    <div class="search-result-info">
                        <div class="search-result-title">${report.name}</div>
                        <div class="search-result-meta">
                            ${report.code} · ${meta.price}元
                            ${modelCount > 1 ? `<span class="search-result-models">${modelCount} 个模型</span>` : ''}
                        </div>
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
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    overlay.id = 'overlay';
    document.body.appendChild(overlay);
    
    mobileMenuBtn.addEventListener('click', () => {
        sidebar.classList.toggle('mobile-open');
        overlay.classList.toggle('active');
        document.body.style.overflow = sidebar.classList.contains('mobile-open') ? 'hidden' : '';
    });
    
    // 点击遮罩层关闭菜单
    overlay.addEventListener('click', () => {
        sidebar.classList.remove('mobile-open');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    });
    
    // 移动端搜索按钮
    const mobileSearchBtn = document.getElementById('mobileSearchBtn');
    if (mobileSearchBtn) {
        mobileSearchBtn.addEventListener('click', openSearch);
    }
    
    // 导航点击
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.dataset.view;
            switchView(view);
            
            // 关闭移动端菜单和遮罩层
            const sidebar = document.getElementById('sidebar');
            const overlay = document.getElementById('overlay');
            sidebar.classList.remove('mobile-open');
            if (overlay) {
                overlay.classList.remove('active');
            }
            document.body.style.overflow = '';
        });
    });
    
    // 筛选按钮
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.currentFilter = btn.dataset.filter;
            renderReportsByModel();
        });
    });
    
    // 排序选择
    document.getElementById('sortSelect').addEventListener('change', (e) => {
        state.currentSort = e.target.value;
        renderReportsByModel();
    });
    
    // 返回按钮
    document.getElementById('backBtn').addEventListener('click', () => {
        switchView('reports');
    });

    // 上一篇/下一篇导航按钮
    document.getElementById('prevReportBtn').addEventListener('click', navigateToPrevReport);
    document.getElementById('nextReportBtn').addEventListener('click', navigateToNextReport);

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
    state.models = getModels();
    
    // 恢复侧边栏状态
    if (state.sidebarCollapsed) {
        document.getElementById('sidebar').classList.add('collapsed');
    }
    
    // 初始化模型选择器
    initModelSelector();
    
    // 绑定事件
    initEventListeners();
    
    // 更新统计
    updateStats();
    
    // 渲染初始视图
    await renderRecentReports();
    await renderReportsByModel();
    
    // 绘制图表
    setTimeout(drawRatingChart, 100);
    
    console.log('龟龟投资策略报告库已加载');
    console.log(`模型数量: ${state.models.length}`);
    console.log(`报告总数: ${state.reports.length}`);
}

// 启动应用
document.addEventListener('DOMContentLoaded', init);
