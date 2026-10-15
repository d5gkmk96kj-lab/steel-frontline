@echo off
REM ==========================================================================
REM  钢铁战线 Steel Frontline — Windows Rework 构建脚本
REM
REM  在 **Windows 机器**上双击运行即可（或在 Git Bash / CMD 里跑）。
REM
REM  前置要求：
REM     1. Python 3.9+（安装时勾选 "Add Python to PATH"）
REM     2. pip install pyinstaller PyQt6
REM
REM  产出：
REM     dist_win\钢铁战线WindowsRework\钢铁战线WindowsRework.exe
REM     packaging\钢铁战线WindowsRework-<版本>-安装包.zip
REM
REM  注意：PyInstaller **不支持交叉编译** —— 这个脚本只能在 Windows 上跑。
REM ==========================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

cd /d "%~dp0.."
echo ==============================================
echo  钢铁战线 Windows Rework 构建
echo ==============================================
echo.

REM ---- 0. 找 Python ----
set PY=
where python >nul 2>&1 && set PY=python
if "%PY%"=="" ( where py >nul 2>&1 && set PY=py )
if "%PY%"=="" (
    echo [错误] 没找到 Python。
    echo        请安装 Python 3.9+，安装时务必勾选 "Add Python to PATH"。
    echo        下载： https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
echo [1/6] Python: %PY%
%PY% --version

REM ---- 1. 检查依赖 ----
%PY% -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [2/6] 缺少 PyInstaller，正在安装...
    %PY% -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败。试试手动跑：
        echo        %PY% -m pip install pyinstaller
        pause
        exit /b 1
    )
) else (
    echo [2/6] PyInstaller 已安装
)

%PY% -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [3/6] 缺少 PyQt6，正在安装（约 50 MB，第一次会慢）...
    %PY% -m pip install --upgrade PyQt6
    if errorlevel 1 (
        echo [错误] PyQt6 安装失败。试试手动跑：
        echo        %PY% -m pip install PyQt6
        pause
        exit /b 1
    )
) else (
    echo [3/6] PyQt6 已安装
)

REM ---- 2. 生成图标 ----
echo.
echo [4/6] 生成图标...
%PY% packaging\make_icon.py
if errorlevel 1 (
    echo [警告] 图标生成失败，会用默认图标继续
)

REM ---- 3. 打包 ----
echo.
echo [5/6] 打包中（约 3-8 分钟，请耐心等）...
echo.

set NAME=钢铁战线WindowsRework
set DIST=dist_win
set WORK=build_win

if exist "%DIST%" rmdir /s /q "%DIST%"
if exist "%WORK%" rmdir /s /q "%WORK%"

%PY% -m PyInstaller ^
  --noconfirm --clean --windowed ^
  --name "%NAME%" ^
  --distpath "%DIST%" ^
  --workpath "%WORK%" ^
  --specpath "%WORK%" ^
  --paths . ^
  --hidden-import core ^
  --hidden-import core.run ^
  --hidden-import core.cards ^
  --hidden-import core.enemies ^
  --hidden-import core.engine ^
  --hidden-import core.versus ^
  --hidden-import core.netplay ^
  --hidden-import core.saves ^
  --hidden-import core.session ^
  --hidden-import core.reconnect ^
  --hidden-import core.relay_client ^
  --hidden-import core.updater ^
  --hidden-import core.cleanup ^
  --hidden-import core.tips ^
  --hidden-import core.audio ^
  --hidden-import core.i18n ^
  --hidden-import core.version ^
  --hidden-import core.cheats ^
  --hidden-import core.deckbuild ^
  --hidden-import qt ^
  --hidden-import qt.qapp ^
  --hidden-import qt.qscreens ^
  --hidden-import qt.qbattle ^
  --hidden-import qt.qversus ^
  --hidden-import qt.qlobby ^
  --hidden-import qt.qdeckbuild ^
  --hidden-import qt.qsave ^
  --hidden-import qt.qupdate ^
  --hidden-import qt.qcleanup ^
  --hidden-import qt.qconsole ^
  --hidden-import qt.qfx ^
  --hidden-import qt.qmap ^
  --hidden-import qt.qtheme ^
  --hidden-import qt.qwidgets ^
  --add-data "locales;locales" ^
  --add-data "tips.txt;." ^
  --icon "packaging\icon.ico" ^
  packaging\app_entry.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败。看看上面的报错信息。
    pause
    exit /b 1
)

set APP=%DIST%\%NAME%\%NAME%.exe
if not exist "%APP%" (
    echo [错误] 没找到生成的 exe：%APP%
    pause
    exit /b 1
)

REM ---- 4. 组装发布包 ----
echo.
echo [6/6] 组装发布包...

for /f "delims=" %%v in ('%PY% -c "import sys;sys.path.insert(0,'.');from core import version as V;print(V.VERSION)"') do set VER=%%v
set OUT=packaging\%NAME%-%VER%-安装包

if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"

REM 主程序（整个目录都要带上 _internal）
xcopy /e /i /q "%DIST%\%NAME%" "%OUT%\%NAME%" >nul

REM 说明文件
if exist "tips.txt" copy /y "tips.txt" "%OUT%\tips.txt" >nul
if exist "README.md" copy /y "README.md" "%OUT%\游戏教程.md" >nul
mkdir "%OUT%\music" 2>nul
mkdir "%OUT%\data" 2>nul

(
echo ⚠️ 本游戏全部由 AI（DeepSeek-V4.1-Flash）生成 ⚠️
echo    代码、卡牌、美术、文案、翻译、测试全部由 AI 完成。
echo    未经专业团队打磨，可能存在 Bug。反馈请到项目 Wiki。
echo    ————————————————————————————————————————
echo.
echo 钢铁战线 Steel Frontline — Windows Rework
echo 版本：%VER%
echo.
echo 怎么玩：
echo   1. 双击 %NAME%.exe
echo   2. 如果 Windows 弹出「已保护你的电脑」：
echo        点「更多信息」→「仍要运行」
echo      （因为本软件没有购买微软的数字签名证书，这是正常现象）
echo   3. 存档位置：%%APPDATA%%\钢铁战线\data\
echo.
echo 加音乐：
echo   把音乐文件放进 music\ 文件夹，命名 music1.mp3 / music2.ogg ...
echo.
echo 更新：
echo   启动后会自动检查更新，也可以在「设置」里手动检查。
echo.
) > "%OUT%\使用说明.txt"

echo 正在压缩...
powershell -NoProfile -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath '%OUT%.zip' -Force" >nul 2>&1

echo.
echo ==============================================
echo  构建完成
echo ==============================================
echo.
echo  可执行文件: %APP%
echo  发布包:     %OUT%.zip
echo.
echo  下一步：
echo   1. 双击 %APP% 测试一下能不能跑
echo   2. 把 %OUT%.zip 上传到 GitHub Releases
echo.
pause
endlocal
