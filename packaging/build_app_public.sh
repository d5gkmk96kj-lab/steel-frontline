#!/bin/bash
# 把《钢铁战线》打包成**独立 .app**（自带 Python + Qt，零依赖）
#
# 公开版：**不含任何音乐**（版权干净，可自由分发）。
# 与完整版的唯一区别就是 --add-data music 那一步 —— 建立空的 music/ 目录，
# 游戏第一次运行时会把用户自己的歌复制/读取到这里。
#
# 关键：用 --paths 让 core/ui/qt 作为真正的模块编入 PYZ。
#       绝不能用 --add-data 塞源码 —— 那会破坏包内导入
#       （表现为 No module named '__future__'）。
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
NAME="${SF_NAME:-钢铁战线公开版}"

# 从 core/version.py 读取版本（唯一来源，避免多处写死）
VER_JSON=$(python3 - <<'PYEOF'
import sys, json
sys.path.insert(0, ".")
try:
    from core import version as V
    print(json.dumps({"short": V.macos_version_string(),
                      "build": V.macos_build_string(),
                      "label": V.VERSION_LABEL,
                      "bundle": V.BUNDLE_ID,
                      "bundle_public": V.BUNDLE_ID_PUBLIC}))
except Exception:
    print(json.dumps({"short": "0.0", "build": "0.0.0",
                      "label": "dev", "bundle": "local.steelfrontline.game",
                      "bundle_public": "local.steelfrontline.game.public"}))
PYEOF
)
VER_SHORT=$(echo "$VER_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['short'])")
VER_BUILD=$(echo "$VER_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['build'])")
VER_LABEL=$(echo "$VER_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['label'])")
echo "  版本: v$VER_LABEL ($VER_SHORT build $VER_BUILD)"
case "$NAME" in
  *公开*) BUNDLE_ID=$(echo "$VER_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['bundle_public'])") ;;
  *)      BUNDLE_ID=$(echo "$VER_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['bundle'])") ;;
esac
echo "  Bundle ID: $BUNDLE_ID"


echo "=== 1. 图标 ==="
python3 packaging/make_icon.py
ICONSET="packaging/icon.iconset"
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512 1024; do
  sips -z $s $s packaging/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1
done
cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
iconutil -c icns "$ICONSET" -o packaging/icon.icns
echo "  就绪"

echo "=== 2. 清理 ==="
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
rm -rf "build_dist_public" "dist_public" *.spec

echo "=== 2.5 准备空音乐目录（公开版不带歌）==="
rm -rf packaging/_empty_music
mkdir -p packaging/_empty_music
cat > packaging/_empty_music/README.txt <<'TXT'
这个目录是放背景音乐的地方。

把 mp3 / ogg / m4a / wav 等音频文件放进来，命名成 music1、music2、music3……
游戏会从 music1 开始播，放完自动随机下一首，一直循环。

详细教程见游戏目录下的「游戏教程.md」。
TXT
echo "  空 music/ 就绪（仅说明文件）"

# 公开版用温和文案（作弊提示不带人身攻击）
# 作弊提示风格：写进包内文件（运行时可读），而不是只设环境变量 ——
# 用户双击 .app 时没有环境变量，只靠它会被静默降级。
echo "mild" > "$ROOT/cheat_flavor.txt"
echo "  作弊提示风格: mild"

echo "=== 3. PyInstaller（--paths 真实模块分析）==="
pyinstaller \
  --noconfirm --clean --windowed \
  --distpath "dist_public" \
  --workpath "build_dist_public" \
  --name "$NAME" \
  --icon packaging/icon.icns \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --paths "$ROOT" \
  --add-data "$ROOT/packaging/_empty_music:music" \
  --add-data "$ROOT/locales:locales" \
  --add-data "$ROOT/tips.txt:." \
  --add-data "$ROOT/cheat_flavor.txt:." \
  --hidden-import core.cards --hidden-import core.engine --hidden-import core.run \
  --hidden-import core.audio --hidden-import core.cheats --hidden-import core.events \
  --hidden-import core.enemies --hidden-import core.relics \
  --hidden-import ui.app --hidden-import ui.theme --hidden-import ui.console \
  --hidden-import ui.widgets --hidden-import ui.screens --hidden-import ui.art \
  --hidden-import ui.battle_view --hidden-import ui.map_view \
  --hidden-import qt.qapp --hidden-import qt.qconsole --hidden-import qt.qbattle \
  --hidden-import qt.qscreens --hidden-import qt.qmap --hidden-import qt.qwidgets \
  --hidden-import qt.qtheme \
  --hidden-import qt.qdeckbuild --hidden-import qt.qversus --hidden-import qt.qlobby \
  --hidden-import core.versus --hidden-import core.deckbuild --hidden-import core.netplay \
  --hidden-import PyQt6.QtWidgets --hidden-import PyQt6.QtGui \
  --hidden-import PyQt6.QtCore --hidden-import PyQt6.QtMultimedia \
  --collect-submodules PyQt6.QtMultimedia \
  packaging/app_entry.py

echo "=== 3.5 写入版本号到 Info.plist ==="
PLIST="dist_public/$NAME.app/Contents/Info.plist"
if [ -f "$PLIST" ]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER_SHORT" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VER_SHORT" "$PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VER_BUILD" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VER_BUILD" "$PLIST"
  # 让 Finder 的「显示简介」也显示版本
  /usr/libexec/PlistBuddy -c "Add :CFBundleGetInfoString string v$VER_LABEL" "$PLIST" 2>/dev/null || true
  echo "  已写入: $VER_SHORT / build $VER_BUILD"
  /usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$PLIST" 2>/dev/null | sed 's/^/    CFBundleShortVersionString: /'
else
  echo "  ⚠️ 找不到 $PLIST"
fi

echo "=== 4. 结果 ==="
APP="dist_public/$NAME.app"
if [ ! -d "$APP" ]; then echo "打包失败"; exit 1; fi
du -sh "$APP"
echo
echo "  自检（跑 4 秒看是否存活）："
"$APP/Contents/MacOS/$NAME" >/tmp/app_selftest.log 2>&1 &
PID=$!
sleep 4
if kill -0 $PID 2>/dev/null; then
  echo "    ✅ 启动成功"
  kill $PID 2>/dev/null
else
  echo "    ❌ 启动失败，日志："
  tail -25 /tmp/app_selftest.log
  exit 1
fi
