/**
 * LocalStorage 工具模块
 * 提供统一的 LocalStorage 操作接口
 */

const StorageUtils = {
    /**
     * 从 LocalStorage 获取数据
     * @param {string} key - 存储键名
     * @returns {any} 解析后的数据，如果不存在则返回 null
     */
    get(key) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : null;
        } catch (error) {
            console.error(`从 LocalStorage 读取数据失败：${key}`, error);
            return null;
        }
    },

    /**
     * 向 LocalStorage 存储数据
     * @param {string} key - 存储键名
     * @param {any} value - 要存储的值
     * @returns {boolean} 是否成功
     */
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (error) {
            console.error(`向 LocalStorage 存储数据失败：${key}`, error);
            return false;
        }
    },

    /**
     * 从 LocalStorage 删除数据
     * @param {string} key - 存储键名
     */
    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch (error) {
            console.error(`从 LocalStorage 删除数据失败：${key}`, error);
        }
    },

    /**
     * 清空 LocalStorage
     */
    clear() {
        try {
            localStorage.clear();
        } catch (error) {
            console.error('清空 LocalStorage 失败', error);
        }
    },

    /**
     * 生成唯一 ID
     * @returns {string} 唯一 ID
     */
    generateId() {
        return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    },

    /**
     * 格式化相对时间
     * @param {number} timestamp - 时间戳
     * @returns {string} 相对时间描述
     */
    formatRelativeTime(timestamp) {
        const now = Date.now();
        const diff = now - timestamp;
        
        const minute = 60 * 1000;
        const hour = 60 * minute;
        const day = 24 * hour;
        const week = 7 * day;
        const month = 30 * day;
        const year = 365 * day;
        
        if (diff < minute) {
            return '刚刚';
        } else if (diff < hour) {
            const minutes = Math.floor(diff / minute);
            return `${minutes}分钟前`;
        } else if (diff < day) {
            const hours = Math.floor(diff / hour);
            return `${hours}小时前`;
        } else if (diff < week) {
            const days = Math.floor(diff / day);
            return `${days}天前`;
        } else if (diff < month) {
            const weeks = Math.floor(diff / week);
            return `${weeks}周前`;
        } else if (diff < year) {
            const months = Math.floor(diff / month);
            return `${months}个月前`;
        } else {
            const years = Math.floor(diff / year);
            return `${years}年前`;
        }
    },

    /**
     * 获取存储使用情况
     * @returns {object} 存储使用信息
     */
    getStorageInfo() {
        let totalSize = 0;
        let itemCount = 0;
        
        for (let key in localStorage) {
            if (localStorage.hasOwnProperty(key)) {
                const value = localStorage.getItem(key);
                totalSize += (key.length + value.length) * 2; // UTF-16 编码
                itemCount++;
            }
        }
        
        return {
            totalSize: (totalSize / 1024).toFixed(2), // KB
            itemCount,
            usagePercent: ((totalSize / (5 * 1024 * 1024)) * 100).toFixed(2) // 假设 5MB 限制
        };
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StorageUtils;
}
