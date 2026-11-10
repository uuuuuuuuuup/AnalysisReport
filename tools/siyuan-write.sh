#!/usr/bin/env bash
# siyuan-write.sh — 写入思源文档并立即刷新索引
#
# 为什么需要它：`siyuan-sisyphus fs write` 走的是 /api/file/putFile，
# 即把 .sy 文件直接写盘，绕过了内核索引。结果：文件是新的，但 SQL/全文
# 搜索/反向链接都是旧的 —— 只能手动「重建索引」（全库，很重）。
# 本脚本在写完后就地只重建这一个文档的索引（约 15ms，实测）。
#
# 用法:
#   tools/siyuan-write.sh "/投资研究/…/文档名" /tmp/draft.md
#   tools/siyuan-write.sh "/投资研究/…/文档名" /tmp/draft.md --create
#   tools/siyuan-write.sh --reindex-only "/投资研究/…/文档名"
#
# 选项:
#   --create       文档不存在时创建（默认要求文档已存在）
#   --reindex-only 只刷新索引，不写内容
#   --quiet        只输出错误
#
# 环境变量:
#   SIYUAN_API_URL / SIYUAN_TOKEN  覆盖 CLI 配置

set -euo pipefail

CONFIG="${SIYUAN_SISYPHUS_CONFIG:-$HOME/.siyuan-sisyphus/config.json}"

die() { printf '错误: %s\n' "$*" >&2; exit 1; }

# ---- 解析参数 ----------------------------------------------------------
CREATE=0
REINDEX_ONLY=0
QUIET=0
POSITIONAL=()
for arg in "$@"; do
  case "$arg" in
    --create)       CREATE=1 ;;
    --reindex-only) REINDEX_ONLY=1 ;;
    --quiet)        QUIET=1 ;;
    -h|--help)      sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              POSITIONAL+=("$arg") ;;
  esac
done

HPATH="${POSITIONAL[0]:-}"
[ -n "$HPATH" ] || die "缺少文档路径。用法: $0 \"/笔记本/目录/文档\" <markdown文件>"

if [ "$REINDEX_ONLY" -eq 0 ]; then
  MD_FILE="${POSITIONAL[1]:-}"
  [ -n "$MD_FILE" ] || die "缺少 markdown 文件。用法: $0 \"$HPATH\" /tmp/draft.md"
  [ -f "$MD_FILE" ] || die "markdown 文件不存在: $MD_FILE"
fi

# ---- 解析地址与 token --------------------------------------------------
if [ -n "${SIYUAN_API_URL:-}" ]; then
  API_URL="$SIYUAN_API_URL"
else
  API_URL=$(python3 -c "
import json,os,sys
p=os.environ.get('CONFIG','')
try:
    c=json.load(open(p))
    pr=c.get('profiles',{}).get(c.get('currentProfile',''),{})
    print(pr.get('apiUrl','http://127.0.0.1:6806'))
except Exception:
    print('http://127.0.0.1:6806')
" CONFIG="$CONFIG")
fi

if [ -n "${SIYUAN_TOKEN:-}" ]; then
  TOKEN="$SIYUAN_TOKEN"
else
  TOKEN=$(python3 -c "
import json,os
try:
    c=json.load(open(os.environ['CONFIG']))
    pr=c.get('profiles',{}).get(c.get('currentProfile',''),{})
    print(pr.get('token',''))
except Exception:
    print('')
" CONFIG="$CONFIG")
fi
[ -n "$TOKEN" ] || die "未找到 API token（检查 $CONFIG 或设置 SIYUAN_TOKEN）"

# ---- 调用内核 API ------------------------------------------------------
api() { # api <endpoint> <json>
  curl -sf -X POST "$API_URL/api/$1" \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$2"
}

# 由 hpath 解析文档 ID：取 hpath 的目录部分 + 末段作为相对路径
resolve_doc_id() {
  local hpath="$1"
  local parent name
  parent=$(dirname "$hpath")
  name=$(basename "$hpath")

  # 笔记本 = hpath 第一段
  local nb_name
  nb_name=$(printf '%s' "$hpath" | sed 's#^/##' | cut -d/ -f1)

  local nb_id
  nb_id=$(api "notebook/lsNotebooks" '{}' | python3 -c "
import sys,json
target=sys.argv[1]
for n in json.load(sys.stdin).get('data',{}).get('notebooks',[]):
    if n['name']==target:
        print(n['id']); break
" "$nb_name")
  [ -n "$nb_id" ] || die "找不到笔记本: $nb_name"

  local inner="${parent#/$nb_name}"
  api "filetree/getIDsByHPath" \
    "$(python3 -c "import json,sys;print(json.dumps({'notebook':sys.argv[1],'path':sys.argv[2]}))" "$nb_id" "$inner")" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin).get('data') or []
print(d[0] if d else '')
"
}

# ---- 1. 写内容 ---------------------------------------------------------
if [ "$REINDEX_ONLY" -eq 0 ]; then
  WRITE_ARGS=(fs write --path "$HPATH" --overwrite true --markdown "$(cat "$MD_FILE")")
  [ "$CREATE" -eq 1 ] && WRITE_ARGS+=(--create)
  if [ "$QUIET" -eq 1 ]; then
    siyuan-sisyphus "${WRITE_ARGS[@]}" >/dev/null
  else
    siyuan-sisyphus "${WRITE_ARGS[@]}"
  fi
fi

# ---- 2. 解析存储路径 ---------------------------------------------------
DOC_ID=$(resolve_doc_id "$HPATH")
[ -n "$DOC_ID" ] || die "写入后仍解析不到文档 ID: $HPATH"

SY_PATH=$(api "filetree/getPathByID" \
  "$(python3 -c "import json,sys;print(json.dumps({'id':sys.argv[1]}))" "$DOC_ID")" \
  | python3 -c "import sys,json;print((json.load(sys.stdin).get('data') or {}).get('path',''))")
[ -n "$SY_PATH" ] || die "解析不到 .sy 存储路径 (doc id=$DOC_ID)"

# ---- 3. 只重建这个文档的索引（关键步骤）--------------------------------
api "filetree/upsertIndexes" \
  "$(python3 -c "import json,sys;print(json.dumps({'paths':[sys.argv[1]]}))" "$SY_PATH")" >/dev/null

# ---- 4. 让已打开的编辑器重载 -------------------------------------------
api "ui/reloadProtyle" \
  "$(python3 -c "import json,sys;print(json.dumps({'id':sys.argv[1]}))" "$DOC_ID")" >/dev/null

[ "$QUIET" -eq 1 ] || printf '✓ 已写入并重建索引  doc=%s\n' "$DOC_ID"
