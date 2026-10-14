#!/bin/bash
# 生成《钢铁战线》公开版 DMG（不含任何音乐，版权干净可自由分发）
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
NAME="${SF_NAME:-钢铁战线公开版}"
VER_LABEL=$(python3 -c "
import sys; sys.path.insert(0,'.')
try:
    from core import version as V; print(V.VERSION_LABEL)
except Exception: print('dev')
")

APP="$ROOT/dist_public/$NAME.app"
STAGE="$ROOT/packaging/dmgstage_public"
DMG="$ROOT/packaging/${NAME}-v${VER_LABEL}-安装包.dmg"

[ -d "$APP" ] || { echo "请先运行 build_app.sh"; exit 1; }

echo "=== 组装 DMG ==="
rm -rf "$STAGE"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"

# 音乐目录留空（公开版不带歌），只放一份说明
mkdir -p "$STAGE/music" "$STAGE/data"
[ -f "$ROOT/packaging/_empty_music/README.txt" ] && \
  cp "$ROOT/packaging/_empty_music/README.txt" "$STAGE/music/README.txt"

# 拖拽安装用
ln -s /Applications "$STAGE/Applications"

# 完整教程（README）也放进 DMG，同学能直接看
[ -f "$ROOT/README.md" ] && cp "$ROOT/README.md" "$STAGE/游戏教程.md"

cat > "$STAGE/使用说明.txt" <<'TXT'
⚠️ 本游戏全部由 AI（DeepSeek-V4.1-Flash）生成 ⚠️
   代码、卡牌、美术、文案、翻译、测试全部由 AI 完成。
   未经专业团队打磨，可能存在 Bug。反馈请到项目 Wiki。
   ————————————————————————————————————————

钢铁战线 Steel Frontline
========================

【安装】
  把左边的「钢铁战线」拖进右边的「Applications」文件夹，完成。

【启动】
  打开「启动台」或「应用程序」，双击「钢铁战线」。

【首次打开提示"无法验证开发者"？】
  因为没有苹果开发者签名（签名要 $99/年），这是正常的。
  解决办法：在「应用程序」里**右键**点「钢铁战线」→ 选「打开」
            → 弹窗里再点一次「打开」。
  只需操作一次，之后双击即可正常打开。

【要装 Python 或 Qt 吗】
  完全不用。包里已自带 Python 和 Qt 图形库，
  Intel / Apple 芯片的 Mac 都能直接运行，不需要任何配置。

【关于音乐 —— 本版不含音乐】
  出于版权考虑，这个版本**没有附带任何音乐**。想加自己的歌：

  第 1 步：启动一次游戏（会自动建好音乐目录）
  第 2 步：打开  ~/Documents/钢铁战线公开版/music/
          Finder 里按 Cmd+Shift+G，粘贴 ~/Documents/钢铁战线公开版/music/
  第 3 步：把歌拷进去，命名 music1、music2、music3……（带扩展名）
          支持 mp3 / ogg / m4a / wav / aac / aiff / flac
  第 4 步：重启游戏即可

  游戏从 music1 开始播，放完自动随机下一首，一直循环。
  想按场景放不同曲子（menu/battle/map…）见「游戏教程.md」。

【存档】
  ~/Documents/钢铁战线公开版/data/

【需要联网吗】
  不需要，完全离线。

【小提示】
  游戏内任何时候按 F1 可呼出控制台（有兑换码和调试指令）。
  想正常体验就别用 :)

【局域网联机对战】
  同一 WiFi 下，一台「创建房间」把显示的 IP 念给对面，
  另一台「加入房间」填这个 IP 即可。详细教程见旁边的「游戏教程.md」。

【关于作弊】
  作弊本就可耻。控制台原本只是调试与单人测试用的。
  你自己不是房主，你就不能骗人。玩不起就别玩。
  （联机中作弊发包会被实时检测：作弊者屏幕弹红字，
    对手界面上给他挂「挂狗」标签。）
TXT

echo "=== 生成 DMG ==="
rm -f "$DMG"
hdiutil create -volname "$NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
echo
echo "=== 完成 ==="
ls -lh "$DMG"
