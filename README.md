# Windows SlowFetch

一款受 Linux 版 [fastfetch](https://github.com/fastfetch-cli/fastfetch) 启发的**系统信息展示工具**，专门为 Windows 设计。

它在你提供的**任意图片徽标**右侧并排显示系统信息，风格与 fastfetch / neofetch 一致。图片用 ANSI 24 位真彩色块渲染，你随时可以换成自己的图片。

## 快速开始

环境要求：Windows 10/11 + Python 3.8 及以上。

```bat
python slowfetch.py
```

首次运行会自动创建 `logos/` 文件夹和 `slowfetch.conf` 配置文件，并默认显示 `logos/logo.png` 这张 Windows 风格占位徽标。

## 自定义图片徽标（核心特性）

徽标来自图片文件，**不用改任何代码**：

1. 找到项目里的 `logos/` 文件夹；
2. 把你喜欢的图片放进去（支持 png / jpg / jpeg / bmp / gif / webp）；
3. 重新运行 `python slowfetch.py` 即可。

**替换规则**：优先使用 `slowfetch.conf` 中 `logo_image` 指定的图片；若该文件不存在，则自动使用 `logos/` 文件夹里的第一张图片。删掉旧图片、放入新图片即可换徽标。

### 徽标配置文件 `slowfetch.conf`

```ini
# logo_image: 徽标图片路径（相对本文件目录），留空则由 logos/ 目录自动选择
logo_image = logos/logo.png
# logo_width: 徽标显示宽度（终端列数），建议 30-50
logo_width = 40
```

### 命令行微调

```bat
python slowfetch.py --logo "D:\我的图片\my_logo.png"   :: 临时指定某张图片
python slowfetch.py --width 30                          :: 调整显示宽度
python slowfetch.py --no-color                          :: 关闭颜色（此时不渲染图片徽标）
```

## 显示信息模块

| 模块      | 说明                          | 数据来源                       |
| -------- | ----------------------------- | ------------------------------ |
| OS       | 系统名称与版本（含构建号/版本）| winreg + sys                   |
| Host     | 主板厂商与型号                | PowerShell (CIM)               |
| Kernel   | NT 内核版本                   | sys                            |
| Uptime   | 系统运行时间                  | ctypes GetTickCount64          |
| Packages | 检测到的包管理器数量          | choco / scoop / winget         |
| Shell    | 当前 Shell                    | 环境变量                       |
| Resolution| 屏幕分辨率                   | ctypes GetSystemMetrics        |
| DE       | 桌面环境                      | 固定值                         |
| WM       | 窗口管理器                    | 固定值 (DWM)                   |
| WM Theme | 应用主题（深/浅色）           | winreg 注册表                  |
| Icons    | 图标集                        | 固定值                         |
| Terminal | 当前终端                      | 环境变量                       |
| CPU      | CPU 型号与逻辑核心数          | CIM + 注册表                   |
| GPU      | 显卡型号（可多个）            | PowerShell (CIM)               |
| Memory   | 物理内存已用/总量             | ctypes GlobalMemoryStatusEx    |
| Swap     | 虚拟内存已用/总量             | 同上                           |
| Disk(/)  | 系统盘已用/总量               | shutil.disk_usage              |
| Battery  | 电池电量与状态（无电池隐藏）  | ctypes GetSystemPowerStatus    |
| Locale   | 系统区域                       | locale                         |

空值模块会自动隐藏（如台式机无电池时不显示 Battery），与 fastfetch 行为一致。

## 命令行选项

```
python slowfetch.py                                  # 默认输出（读取图片徽标）
python slowfetch.py --logo <图片路径>                 # 手动指定徽标图片
python slowfetch.py --width <字符数>                  # 徽标宽度（默认取配置）
python slowfetch.py --no-color                        # 禁用颜色与图片徽标
python slowfetch.py --structure 'OS,Host,,Uptime'     # 自定义显示结构
python slowfetch.py --help                            # 查看完整帮助
```

### 自定义结构（--structure）

逗号分隔的模块项，空项输出空行。项可以是 `模块名` 或 `标签:模块名`，模块名大小写不敏感：

```bat
python slowfetch.py --structure "OS:System,Host,,Uptime:Up time,Memory"
```

可用模块名：`os host kernel uptime packages shell resolution de wm wm_theme icons terminal cpu gpu memory swap disk battery locale`

## 项目结构

```
slowfetch for windows/
├── slowfetch.py        # 主程序（单一文件，可随处复制运行）
├── slowfetch.conf      # 徽标配置文件（可自行编辑）
├── logos/              # 图片徽标文件夹（放入你自己的图片即可）
│   ├── logo.png        # 默认占位徽标（可删除/替换）
│   └── README.txt      # 使用说明
└── README.md           # 本文档
```

## 图片徽标渲染说明

- **原理**：把图片降采样到终端字符网格，用“上半块”字符 + ANSI 24 位真彩色逐像素绘制，垂直分辨率比普通色块高一倍。
- **解码**：优先使用 Pillow（PIL）；未安装 PIL 时自动退回 Windows 自带 System.Drawing，无需额外依赖。
- **颜色关闭**：`--no-color` 时不会渲染图片徽标（图片本质靠颜色呈现）。

## 与 Linux fastfetch 的差异

- **语言/依赖**：原版为 C 语言，本实现为单一 Python 文件，只依赖标准库（可选 Pillow 以提升解码兼容性）。
- **数据来源**：Linux 读取 `/proc`、`/etc/os-release` 等；Windows 走 ctypes 系统 API + PowerShell CIM + 注册表。
- **徽标**：不内置 ASCII 徽标，完全使用你自己提供的图片。
- **功能范围**：保留 fastfetch 的核心信息展示与 `--structure`/`--color` 等常用选项，不包含大量耗时的扩展检测与配置系统，启动为亚秒级（图片解码为支撑，毫秒级）。

## 常见问题

**Q：显示不出图片徽标？**
A：默认需在支持真彩色的终端（Windows Terminal / Windows 11 控制台）中运行，且为彩色模式。确认 `logos/` 有图片，或 `fastfetch.conf` 的 `logo_image` 路径正确。

**Q：图片显示太大/太小/变形？**
A：用 `--width` 或配置里的 `logo_width` 调整显示宽度；高度会按图片宽高比自动缩放到约两倍字符高度，保持比例。

**Q：某些信息项为空？**
A：空值项会自动隐藏。若某项应显示但为空，多为相应查询执行超时或权限不足。