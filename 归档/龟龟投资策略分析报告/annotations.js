/**
 * 批注功能模块
 * 管理股票分析报告的文本高亮和批注功能
 */

const AnnotationsModule = (function() {
    // 存储键名前缀
    const STORAGE_PREFIX = 'turtle_report_annotations_';
    
    // 当前批注数据
    let currentAnnotations = [];
    
    // 颜色选项
    const COLORS = {
        yellow: { bg: '#fef3c7', border: '#f59e0b', name: '黄色' },
        green: { bg: '#d1fae5', border: '#10b981', name: '绿色' },
        blue: { bg: '#dbeafe', border: '#3b82f6', name: '蓝色' },
        pink: { bg: '#fce7f3', border: '#ec4899', name: '粉色' }
    };
    
    /**
     * 获取存储键名
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @returns {string} 存储键名
     */
    function getStorageKey(stockCode, modelName) {
        return `${STORAGE_PREFIX}${stockCode}_${modelName}`;
    }
    
    /**
     * 加载批注数据
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     */
    function loadAnnotations(stockCode, modelName) {
        const key = getStorageKey(stockCode, modelName);
        const data = StorageUtils.get(key);
        currentAnnotations = data || [];
        return currentAnnotations;
    }
    
    /**
     * 保存批注数据
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     */
    function saveAnnotations(stockCode, modelName) {
        const key = getStorageKey(stockCode, modelName);
        StorageUtils.set(key, currentAnnotations);
    }
    
    /**
     * 创建批注
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} content - 批注内容
     * @param {string} highlightedText - 被高亮的文本
     * @param {string} color - 高亮颜色
     * @param {object} position - 位置信息
     * @returns {object} 新批注对象
     */
    function createAnnotation(stockCode, modelName, content, highlightedText, color = 'yellow', position = null) {
        const annotation = {
            id: StorageUtils.generateId(),
            stockCode,
            modelName,
            content: content.trim(),
            highlightedText: highlightedText.trim(),
            color,
            position,
            timestamp: Date.now(),
            isEdited: false
        };
        
        currentAnnotations.push(annotation);
        saveAnnotations(stockCode, modelName);
        
        return annotation;
    }
    
    /**
     * 获取所有批注
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @returns {Array} 批注数组
     */
    function getAnnotations(stockCode, modelName) {
        loadAnnotations(stockCode, modelName);
        return currentAnnotations;
    }
    
    /**
     * 获取批注数量
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @returns {number} 批注数量
     */
    function getAnnotationCount(stockCode, modelName) {
        loadAnnotations(stockCode, modelName);
        return currentAnnotations.length;
    }
    
    /**
     * 删除批注
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} annotationId - 批注 ID
     * @returns {boolean} 是否成功删除
     */
    function deleteAnnotation(stockCode, modelName, annotationId) {
        loadAnnotations(stockCode, modelName);
        const index = currentAnnotations.findIndex(a => a.id === annotationId);
        
        if (index !== -1) {
            currentAnnotations.splice(index, 1);
            saveAnnotations(stockCode, modelName);
            return true;
        }
        
        return false;
    }
    
    /**
     * 更新批注内容
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} annotationId - 批注 ID
     * @param {string} newContent - 新内容
     * @returns {boolean} 是否成功更新
     */
    function updateAnnotation(stockCode, modelName, annotationId, newContent) {
        loadAnnotations(stockCode, modelName);
        
        const annotation = currentAnnotations.find(a => a.id === annotationId);
        if (!annotation) {
            return false;
        }
        
        annotation.content = newContent.trim();
        annotation.isEdited = true;
        saveAnnotations(stockCode, modelName);
        
        return true;
    }
    
    /**
     * 获取颜色配置
     * @param {string} colorName - 颜色名称
     * @returns {object} 颜色配置对象
     */
    function getColorConfig(colorName) {
        return COLORS[colorName] || COLORS.yellow;
    }
    
    /**
     * 获取所有颜色选项
     * @returns {object} 所有颜色配置
     */
    function getAllColors() {
        return COLORS;
    }
    
    /**
     * 清空所有批注
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     */
    function clearAnnotations(stockCode, modelName) {
        const key = getStorageKey(stockCode, modelName);
        StorageUtils.remove(key);
        currentAnnotations = [];
    }
    
    /**
     * 根据文本内容查找批注
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} text - 文本内容
     * @returns {Array} 匹配的批注列表
     */
    function findAnnotationsByText(stockCode, modelName, text) {
        loadAnnotations(stockCode, modelName);
        return currentAnnotations.filter(a => 
            a.highlightedText.includes(text) || text.includes(a.highlightedText)
        );
    }
    
    // 公开接口
    return {
        loadAnnotations,
        saveAnnotations,
        createAnnotation,
        getAnnotations,
        getAnnotationCount,
        deleteAnnotation,
        updateAnnotation,
        getColorConfig,
        getAllColors,
        clearAnnotations,
        findAnnotationsByText
    };
})();

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AnnotationsModule;
}
