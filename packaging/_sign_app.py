#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 .app 做一次干净的 ad-hoc 签名。

为什么需要这一步
----------------
PyInstaller 自己做的 ad-hoc 签名是**坏的**。`codesign --verify` 报：

    code has no resources but signature indicates they must be present

后果很严重：macOS 无法识别这是一个「完整但未签名」的 App，于是
**系统设置 → 隐私与安全性里不显示「仍要打开」按钮**，用户在新机器上
完全打不开（用户实际遇到的问题）。

为什么重签一开始也失败
----------------------
`.app` 内很多**目录**（各种 .framework，以及 .app 根目录本身）带着
`com.apple.FinderInfo`，codesign 会报：

    resource fork, Finder information, or similar detritus not allowed

坑点（都踩过）：
  * `xattr -cr` 清不掉**目录**上的属性，声称成功但实际还在
  * `removexattr(2)` 系统调用对目录也静默失败
  * 必须对**每一个路径（含目录和符号链接）逐个 `xattr -c`**，然后
    **立刻**签名 —— 中间不要跑别的命令

用法： python3 packaging/_sign_app.py /path/to/Foo.app
"""
from __future__ import annotations

import os
import subprocess
import sys

# 会阻止签名的扩展属性
BAD_ATTRS = ("com.apple.FinderInfo", "com.apple.fileprovider.fpfs#P",
             "com.apple.quarantine", "com.apple.ResourceFork")


def _all_paths(app: str) -> list:
    """列出 .app 内所有路径（含目录本身与符号链接）。"""
    out = [app]
    for root, dirs, files in os.walk(app):
        for n in dirs + files:
            out.append(os.path.join(root, n))
    return out


def strip_xattrs(app: str) -> int:
    """逐个路径清扩展属性。返回处理后仍有问题的路径数。"""
    # 先删 ._ 与 .DS_Store（它们本身就是 resource fork）
    for root, dirs, files in os.walk(app, topdown=False):
        for name in list(files) + list(dirs):
            if name.startswith("._") or name == ".DS_Store":
                try:
                    os.remove(os.path.join(root, name))
                except Exception:
                    pass

    for p in _all_paths(app):
        # -c 清全部；-s 作用于符号链接本身而不是目标
        for flag in ("-c", "-cs"):
            try:
                subprocess.run(["xattr", flag, p], capture_output=True,
                               timeout=10)
            except Exception:
                pass

    # 复查：还有没有阻止签名的属性
    left = 0
    for p in _all_paths(app):
        try:
            names = subprocess.run(["xattr", p], capture_output=True,
                                   text=True, timeout=10).stdout
        except Exception:
            continue
        if any(b in names for b in BAD_ATTRS):
            left += 1
    return left


def _needs_tempdir(app: str) -> bool:
    """项目在 ~/Documents 下时，系统的文件同步服务会**不断把
    com.apple.FinderInfo 加回来**，导致签名永远失败。
    这种情况下必须挪到 /tmp 去签，签完再拷回来。"""
    real = os.path.realpath(app)
    home = os.path.expanduser("~")
    for d in ("Documents", "Desktop", "Downloads"):
        if real.startswith(os.path.join(home, d) + os.sep):
            return True
    return False


def sign_in_tempdir(app: str) -> bool:
    """把 .app 复制到 /tmp，在那里签名，再拷回来。"""
    import shutil
    import tempfile
    app = os.path.abspath(app)
    tmp = tempfile.mkdtemp(prefix="sf_sign_")
    tmp_app = os.path.join(tmp, os.path.basename(app))
    try:
        # ditto 能完整保留目录结构与权限
        subprocess.run(["ditto", app, tmp_app], check=True)
        ok = _sign_here(tmp_app)
        if not ok:
            return False
        # 签好的包拷回去（先删旧的，避免残留被拒的文件）
        backup = app + ".unsigned"
        try:
            if os.path.exists(backup):
                shutil.rmtree(backup, ignore_errors=True)
            os.rename(app, backup)
        except Exception:
            backup = None
        try:
            subprocess.run(["ditto", tmp_app, app], check=True)
        except Exception:
            if backup and os.path.exists(backup):
                os.rename(backup, app)      # 失败就还原
            return False
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        return True
    except Exception as exc:
        print("  临时目录签名失败: %r" % (exc,))
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _sign_here(app: str) -> bool:
    """在当前目录直接清属性并签名（通用实现）。"""
    left = strip_xattrs(app)
    if left:
        print("  ⚠️ 还有 %d 个路径带阻止签名的属性" % left)
    else:
        print("  扩展属性已清理干净")

    # 清完立刻签，中间不要跑别的命令
    r = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app],
                       capture_output=True, text=True)
    err = (r.stderr or "").strip()
    if err and "replacing existing signature" not in err:
        print("  codesign: %s" % err.splitlines()[0][:120])

    v = subprocess.run(["codesign", "--verify", "--deep", "--strict", app],
                       capture_output=True, text=True)
    if v.returncode == 0:
        return True
    print("  验证输出: %s" % (v.stderr or "").strip()[:160])
    return False


def sign(app: str) -> bool:
    """对外入口：必要时自动挪到 /tmp 去签。"""
    if not os.path.isdir(app):
        print("  找不到 %s" % app)
        return False
    if _needs_tempdir(app):
        print("  （当前目录有文件同步服务，会不断加回 FinderInfo）")
        print("  -> 改在 /tmp 里签名，签完再拷回来")
        return sign_in_tempdir(app)
    return _sign_here(app)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    app = sys.argv[1]
    if sign(app):
        print("  ✅ 签名有效（ad-hoc）")
        print("     -> Gatekeeper 会认成「完整但未签名」，")
        print("        系统设置 → 隐私与安全性 里会出现「仍要打开」")
        return 0
    print("  ⚠️ 签名验证未通过 —— 用户可能无法通过「仍要打开」放行")
    return 1


if __name__ == "__main__":
    sys.exit(main())
