#!/bin/bash
# 视频批量压缩脚本 — 拖入视频文件即可自动压缩
# 用法：
#   1. 直接拖文件：./compress.sh video1.mp4 video2.mp4
#   2. 压缩整个文件夹：./compress.sh /path/to/folder
#   3. 不带参数：压缩当前目录下所有视频

OUTPUT_DIR="compressed"
CRF=23          # 质量：18(高)~28(低)，23是平衡点
MAX_WIDTH=1280  # 横屏最大宽度
MAX_HEIGHT=720  # 横屏最大高度

# 检查 ffmpeg
if ! command -v ffmpeg &>/dev/null; then
  echo "❌ 需要先安装 ffmpeg：brew install ffmpeg"
  exit 1
fi

# 收集所有视频文件
FILES=()
if [ $# -eq 0 ]; then
  # 无参数：当前目录
  for f in *.mp4 *.mov *.avi *.mkv *.MP4 *.MOV; do
    [ -f "$f" ] && FILES+=("$f")
  done
else
  for arg in "$@"; do
    if [ -d "$arg" ]; then
      while IFS= read -r -d '' f; do
        FILES+=("$f")
      done < <(find "$arg" -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.avi" -o -iname "*.mkv" \) -print0)
    elif [ -f "$arg" ]; then
      FILES+=("$arg")
    fi
  done
fi

if [ ${#FILES[@]} -eq 0 ]; then
  echo "❌ 没有找到视频文件"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "📦 找到 ${#FILES[@]} 个视频，开始压缩..."
echo ""

SUCCESS=0
for f in "${FILES[@]}"; do
  BASENAME=$(basename "$f")
  NAME="${BASENAME%.*}"
  OUTFILE="$OUTPUT_DIR/${NAME}.mp4"

  # 获取原始尺寸判断横竖屏
  W=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$f" 2>/dev/null)
  H=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$f" 2>/dev/null)
  ORIG_SIZE=$(du -m "$f" | cut -f1)

  if [ -n "$W" ] && [ -n "$H" ] && [ "$W" -lt "$H" ]; then
    # 竖屏：宽高互换限制
    SCALE="scale='min($MAX_HEIGHT,iw)':'min($MAX_WIDTH,ih)':force_original_aspect_ratio=decrease"
  else
    SCALE="scale='min($MAX_WIDTH,iw)':'min($MAX_HEIGHT,ih)':force_original_aspect_ratio=decrease"
  fi

  echo "🎬 $BASENAME (${W}x${H}, ${ORIG_SIZE}MB)"

  ffmpeg -i "$f" \
    -vf "$SCALE" \
    -c:v libx264 -crf $CRF -preset medium \
    -c:a aac -b:a 128k \
    -movflags +faststart \
    -y "$OUTFILE" 2>/dev/null

  if [ $? -eq 0 ]; then
    NEW_SIZE=$(du -m "$OUTFILE" | cut -f1)
    echo "   ✅ → ${NAME}.mp4 (${NEW_SIZE}MB, 压缩率 $((100 - NEW_SIZE * 100 / ORIG_SIZE))%)"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "   ❌ 压缩失败"
  fi
done

echo ""
echo "🎉 完成！${SUCCESS}/${#FILES[@]} 个视频已压缩到 ./$OUTPUT_DIR/"
