# Adachi Mod Menu Automation

## 当前约定
这个仓库现在分成两条线：

1. GitHub Actions 只负责编译菜单 APK
2. 本地单独目录负责目标 APK 注入、回编和签名

## GitHub Actions
workflow 文件：

[`build-and-inject.yml`](/D:/QiuMo/ai/hsahc/Adachi-Mod-Menu/.github/workflows/build-and-inject.yml#L1)

现在它只做一件事：

- 编译菜单 release APK
- 上传 `menu-apk-<sha>` artifact

不会再在 GitHub 上自动注入目标 APK。

## 本地注入目录
本地专用目录已经改成：

```text
local_injection/
```

这个目录整体被 `.gitignore` 忽略，不会上传到 GitHub。

推荐结构：

```text
local_injection/
  input/
  work/
  output/
```

## 两阶段本地注入
脚本：

[`tools/inject_menu.py`](/D:/QiuMo/ai/hsahc/Adachi-Mod-Menu/tools/inject_menu.py#L1)

### 1. prepare
先反编译目标 APK，并按 `说明.txt` 的规则打好注入点。

示例：

```bash
python tools/inject_menu.py prepare ^
  --target-apk "D:/QiuMo/ai/hsahc/apps.apk" ^
  --workspace "D:/QiuMo/ai/hsahc/Adachi-Mod-Menu/local_injection/work/apps" ^
  --force
```

### 2. finalize
等你把菜单产物放进工作目录的 `payload/` 后，再回编并签名。

示例：

```bash
python tools/inject_menu.py finalize ^
  --workspace "D:/QiuMo/ai/hsahc/Adachi-Mod-Menu/local_injection/work/apps" ^
  --output-apk "D:/QiuMo/ai/hsahc/Adachi-Mod-Menu/local_injection/output/apps.injected.apk"
```

## payload 放法
### 方式 A：直接放菜单 APK

```text
payload/menu.apk
```

脚本会自动提取：
- `com/android/support` 的 smali
- `lib/<abi>/libSakuraAdachi.so`

### 方式 B：手动替换产物

```text
payload/smali/com/android/support/...
payload/smali_classes2/com/android/support/...
payload/lib/armeabi-v7a/libSakuraAdachi.so
payload/lib/arm64-v8a/libSakuraAdachi.so
```

说明：
- 目前脚本不直接吃 raw `dex`
- 如果你只有 `dex`，请先转成 `smali`，或者直接放 `menu.apk`
