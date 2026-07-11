/**
 * 评论区功能模块
 * 管理股票分析报告的评论功能
 */

const CommentsModule = (function() {
    // 存储键名前缀
    const STORAGE_PREFIX = 'turtle_report_comments_';
    
    // 当前评论数据
    let currentComments = [];
    
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
     * 加载评论数据
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     */
    function loadComments(stockCode, modelName) {
        const key = getStorageKey(stockCode, modelName);
        const data = StorageUtils.get(key);
        currentComments = data || [];
        return currentComments;
    }
    
    /**
     * 保存评论数据
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     */
    function saveComments(stockCode, modelName) {
        const key = getStorageKey(stockCode, modelName);
        StorageUtils.set(key, currentComments);
    }
    
    /**
     * 添加评论
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} content - 评论内容
     * @param {string} author - 作者名
     * @returns {object} 新评论对象
     */
    function addComment(stockCode, modelName, content, author = '匿名用户') {
        const comment = {
            id: StorageUtils.generateId(),
            stockCode,
            modelName,
            content: content.trim(),
            author: author.trim() || '匿名用户',
            timestamp: Date.now(),
            replies: [],
            isEdited: false
        };
        
        currentComments.unshift(comment); // 添加到开头
        saveComments(stockCode, modelName);
        
        return comment;
    }
    
    /**
     * 获取所有评论
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @returns {Array} 评论数组
     */
    function getComments(stockCode, modelName) {
        loadComments(stockCode, modelName);
        return currentComments;
    }
    
    /**
     * 获取评论数量
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @returns {number} 评论数量
     */
    function getCommentCount(stockCode, modelName) {
        loadComments(stockCode, modelName);
        return currentComments.length;
    }
    
    /**
     * 删除评论
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} commentId - 评论 ID
     * @returns {boolean} 是否成功删除
     */
    function deleteComment(stockCode, modelName, commentId) {
        loadComments(stockCode, modelName);
        const index = currentComments.findIndex(c => c.id === commentId);
        
        if (index !== -1) {
            currentComments.splice(index, 1);
            saveComments(stockCode, modelName);
            return true;
        }
        
        return false;
    }
    
    /**
     * 添加回复
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} commentId - 评论 ID
     * @param {string} content - 回复内容
     * @param {string} author - 回复者
     * @param {string} parentAuthor - 被回复者（可选）
     * @returns {object} 回复对象
     */
    function addReply(stockCode, modelName, commentId, content, author = '匿名用户', parentAuthor = null) {
        loadComments(stockCode, modelName);
        
        const comment = currentComments.find(c => c.id === commentId);
        if (!comment) {
            return null;
        }
        
        const reply = {
            id: StorageUtils.generateId(),
            content: content.trim(),
            author: author.trim() || '匿名用户',
            timestamp: Date.now(),
            parentAuthor,
            isEdited: false
        };
        
        comment.replies.push(reply);
        saveComments(stockCode, modelName);
        
        return reply;
    }
    
    /**
     * 删除回复
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} commentId - 评论 ID
     * @param {string} replyId - 回复 ID
     * @returns {boolean} 是否成功删除
     */
    function deleteReply(stockCode, modelName, commentId, replyId) {
        loadComments(stockCode, modelName);
        
        const comment = currentComments.find(c => c.id === commentId);
        if (!comment) {
            return false;
        }
        
        const index = comment.replies.findIndex(r => r.id === replyId);
        if (index !== -1) {
            comment.replies.splice(index, 1);
            saveComments(stockCode, modelName);
            return true;
        }
        
        return false;
    }
    
    /**
     * 编辑评论
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     * @param {string} commentId - 评论 ID
     * @param {string} newContent - 新内容
     * @returns {boolean} 是否成功更新
     */
    function editComment(stockCode, modelName, commentId, newContent) {
        loadComments(stockCode, modelName);
        
        const comment = currentComments.find(c => c.id === commentId);
        if (!comment) {
            return false;
        }
        
        comment.content = newContent.trim();
        comment.isEdited = true;
        saveComments(stockCode, modelName);
        
        return true;
    }
    
    /**
     * 清空所有评论
     * @param {string} stockCode - 股票代码
     * @param {string} modelName - 模型名称
     */
    function clearComments(stockCode, modelName) {
        const key = getStorageKey(stockCode, modelName);
        StorageUtils.remove(key);
        currentComments = [];
    }
    
    // 公开接口
    return {
        loadComments,
        saveComments,
        addComment,
        getComments,
        getCommentCount,
        deleteComment,
        addReply,
        deleteReply,
        editComment,
        clearComments
    };
})();

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CommentsModule;
}
