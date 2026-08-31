# Windows SlowFetch

这是一个受 Linux 版 fastfetch 启发、为 Windows 设计的系统信息展示脚本。它会在终端中输出当前系统的概览信息，并在必要时把图片徽标按字符方式渲染到右侧。

它的代码入口为 `slowfetch.py`，实际功能包括：

- 收集 Windows 系统基本信息
- 读取主机、CPU、GPU、内存、磁盘、电池等信息
- 显示桌面与终端相关信息
- 支持从图片目录加载徽标并渲染为彩色终端图案
- 支持自定义展示结构与参数配置

---

## 1. 快速开始

环境要求：Windows 10/11，Python 3.8+。

建议安装 Pillow，以便更稳定地渲染图片徽标：

```bat
pip install pillow
```

随后运行：

```bat
python slowfetch.py
```

首次运行时，脚本会自动创建：

- `logos/` 目录
- `slowfetch.conf` 配置文件
- `README.txt` 说明文件

默认会尝试读取 `logos/logo.png`，若不存在则自动选择 `logos/` 目录中的第一张支持格式图片。

---

## 2. 功能概览

这个脚本本质上是一个“终端系统信息看板”，其核心能力包括：

1. 系统信息采集
   - OS、主机名、内核、启动时间、运行时间
   - CPU、GPU、内存、swap、磁盘、电池
   - Shell、桌面环境、窗口管理器、主题、终端类型
   - 语言环境和当前系统时间

2. 图片徽标渲染
   - 读取 `logos/` 中的图片
   - 自动按终端宽度缩放
   - 用 ANSI 颜色和 Unicode 半块字符 `▀` 组合显示
   - 通过缓存减少重复渲染

3. 配置与自定义
   - 通过 `slowfetch.conf` 配置默认图片、宽度和低内存模式
   - 通过命令行覆盖配置
   - 使用 `--structure` 自定义展示顺序和标签

4. 终端兼容
   - Windows 控制台颜色启用逻辑
   - `--no-color` 可关闭颜色与图片渲染
   - `--debug` 可输出详细日志

---

## 3. 配置文件说明

脚本会生成默认配置：

```ini
[slowfetch]
# 徽标图片路径（相对或绝对）
logo_image = logos/logo.png
# 徽标显示宽度（字符数）
logo_width = 40
# 低内存模式（限制最大高度）
low_memory = false
```

### 参数说明

- `logo_image`：指定徽标图片路径；若为空或文件不存在，则从 `logos/` 自动找第一张图
- `logo_width`：控制徽标显示宽度
- `low_memory`：启用低内存模式，降低图片渲染高度，减少内存占用

---

## 4. 命令行参数

```bat
python slowfetch.py
python slowfetch.py --logo "D:\my_logo.png"
python slowfetch.py --width 30
python slowfetch.py --structure "OS:OS,Host,,Uptime:Uptime"
python slowfetch.py --low-memory
python slowfetch.py --no-color
python slowfetch.py --color
python slowfetch.py --debug
python slowfetch.py --help
```

### 参数含义

- `--logo`：临时指定徽标图片
- `--width`：覆盖默认徽标宽度
- `--structure`：自定义展示模块和顺序
- `--low-memory`：触发更保守的图像高度计算
- `--no-color`：关闭 ANSI 颜色输出，通常也会关闭图片渲染
- `--color`：强制启用颜色输出
- `--debug`：打印调试日志
- `--help`：显示脚本说明文档

---

## 5. 图片徽标功能

### 支持的图片格式

脚本会扫描 `logos/` 目录下的图片文件，并接受这些扩展名：

- `.png`
- `.jpg`
- `.jpeg`
- `.bmp`
- `.gif`
- `.webp`
- `.tif`
- `.tiff`

### 渲染方式

代码里使用的是：

- `PIL.Image` 读取图片
- 按目标宽度和低内存模式重新计算高度
- 缩放后按像素逐行生成字符
- 使用 ANSI 真彩颜色和 Unicode 半块 `▀` 组合，形成类似“像素徽标”的效果

### 缓存机制

脚本会在项目目录下创建 `.cache/`，把已渲染图片缓存为 `pkl` 文件，避免重复计算。缓存键包含：

- 图片路径
- 宽度
- 内存模式
- 文件修改时间
- 文件大小

如果没有安装 Pillow，脚本会记录警告并返回空的徽标结果；也就是说，图片渲染依赖 Pillow，而不是完全零依赖。

---

## 6. 信息模块与实际数据来源

以下是脚本中实际存在的模块，按代码中的 `mod_*` 函数列出：

| 模块名 | 代码函数 | 实际作用 |
| --- | --- | --- |
| OS | `mod_os()` | 返回 `Microsoft Windows + platform.version()` |
| Host | `mod_host()` | 通过 `wmi.Win32_ComputerSystem` 获取制造商和型号 |
| Kernel | `mod_kernel()` | 返回系统内核版本 |
| Uptime | `mod_uptime()` | 用 `psutil.boot_time()` 计算运行时长 |
| Packages | `mod_packages()` | 检测是否存在 `choco / scoop / winget` |
| Shell | `mod_shell()` | 读取 `ComSpec`，识别 PowerShell / cmd |
| Resolution | `mod_resolution()` | 读取屏幕分辨率 |
| DE | `mod_de()` | 固定返回 `Windows Explorer` |
| WM | `mod_wm()` | 固定返回 `DWM` |
| WM Theme | `mod_wm_theme()` | 从注册表读取深浅色主题 |
| Icons | `mod_icons()` | 固定返回 `Windows` |
| Terminal | `mod_terminal()` | 判断 `TERM_PROGRAM` / `WT_SESSION` / ConHost |
| CPU | `mod_cpu()` | 读取 CPU 名称和核心数 |
| GPU | `mod_gpu()` | 读取显卡信息，优先 WMI，降级注册表 |
| Memory | `mod_memory()` | 用 `psutil.virtual_memory()` 计算占用与总量 |
| Swap | `mod_swap()` | 用 `psutil.swap_memory()` 计算虚拟内存 |
| Disk (/) | `mod_disk()` | 用 `psutil.disk_usage(os.path.abspath(os.sep))` 计算系统盘占用 |
| Battery | `mod_battery()` | 用 `psutil.sensors_battery()` 检测电量和状态 |
| Locale | `mod_locale()` | 读取系统语言/地区 |
| System Time | `mod_system_time()` | 当前时间，格式 `YYYY-MM-DD HH:MM:SS` |
| Boot Time | `mod_boot()` | 使用 `psutil.boot_time()` 计算开机时间 |

### 空值处理

如果某个模块返回空字符串，脚本在默认输出时会自动跳过该项。也就是说：

- 无电池设备不会显示电池信息
- 某些设备没有 swap 或主题信息时会自动隐藏
- 这符合“只展示有意义数据”的风格

---

## 7. 自定义结构 `--structure`

脚本支持通过 `--structure` 自定义显示顺序，语法为：

- `模块名`
- 或 `标签:模块名`
- 以逗号分隔
- 空项会输出空行
- 若输入了代码中不存在的模块名，会显示 `(未知模块 xxx)`

示例：

```bat
python slowfetch.py --structure "OS:OS,Host,,Uptime:Uptime,Memory"
```

这会生成：

- `OS: ...`
- `Host: ...`
- 空一行
- `Uptime: ...`
- `Memory: ...`

### 可用模块名

实测代码中支持的模块名包括：

```text
os host kernel uptime packages shell resolution de wm wm_theme icons terminal cpu gpu memory swap disk battery locale system_time boot
```

注意：这些名字对应代码里的 `mod_` 函数名，大小写在 `main()` 里会转成小写后查找，因此名字不区分大小写。

---

## 8. 项目结构

```text
slowfetch for windows/
├── slowfetch.py
├── slowfetch.conf
├── logos/
│   ├── README.txt
│   └── logo.png
├── .cache/
│   └── (自动生成缓存文件)
├── README.md
└── 其他资源
```

---

## 9. 与 fastfetch 的关系

它确实是“受 fastfetch 启发”的：

- 目标：展示系统信息
- 风格：终端横向布局、彩色输出
- 功能：支持自定义展示结构

但它不是 fastfetch 的完整移植版本，以下点需要注意：

- 它是单个 Python 脚本，不是 C/C++ 程序
- 它依赖 Windows API、WMI、PSUtil 和可选 Pillow
- 图片徽标是它的特色功能，而不是 fastfetch 的原生 ASCII 字符画逻辑
- 它的目标是“简洁、可读、轻量”，更偏向单机展示工具

---

## 10. 常见问题

### Q：为什么不显示图片？
A：通常是以下几种原因：

- `--no-color` 已关闭颜色输出
- 终端不支持 ANSI VT
- `logos/` 里没有可用图片
- 未安装 Pillow，导致渲染失败

### Q：为什么有些信息为空？
A：脚本中很多模块会在异常时返回空字符串，默认输出时会自动隐藏这些项。常见原因包括：

- 当前设备没有电池
- 没有安装对应工具
- 权限不足或 WMI/注册表读取失败

### Q：怎么调小徽标？
A：可以使用：

```bat
python slowfetch.py --width 20
```

或者修改 `slowfetch.conf` 里的 `logo_width`。

### Q：怎么减少内存占用？
A：使用：

```bat
python slowfetch.py --low-memory
```

或在配置文件中设置：

```ini
low_memory = true
```

---

## 11. 总结

这个脚本的核心职责并不是“做一个复杂的系统监控器”，而是：

- 读取 Windows 当前状态
- 组织为美观的终端信息栏
- 可选放入图片徽标
- 提供简单的自定义配置接口

所以它更接近于“单文件 Windows 版系统信息展示工具”，而不是完整的系统诊断/监控平台。