# gtav-asset-repair 用户手册

**作者附言：** 这个工具是我一周内完成的，每天实现一项功能。目前我不再新增功能，除非出现会
导致程序崩溃的严重问题。

如果本工具对你有帮助，非常欢迎附上仓库链接：<https://github.com/wokken198/gtav-asset-repair>
许可证要求必须保留版权声明；附上链接只是友好致谢，并非强制要求。

本手册面向解压后就想动手的人。英文版见 [README.md](README.md)。

不需要 Python、不需要安装、不需要管理员权限，也**不需要任何外部工具**——读写归档全部由
内置引擎完成。

---

## 1. 快速开始

1. **整个文件夹解压。** 不要单独把 `gtav-asset-repair.exe` 拖出来——它需要旁边的
   `_internal` 文件夹。
2. 双击 `gtav-asset-repair.exe`（被 Windows 拦了就双击 `Run.bat`）。
3. 在左侧选页面。语言与主题在右上角切换，窗口会记住。

---

## 2. 各页面做什么

| 页面 | 做什么 | 写到哪里 |
|---|---|---|
| **法线贴图 (DDS)** | 从车标/徽章 `.dds` 生成切线空间法线图 | `<输入目录>\normals\…_n.dds` |
| **贴图 (YTD)** — *分析* | 只读归档头，估算能省多少 | 仅报告区 |
| **贴图 (YTD)** — *压缩* | 缩放 `.ytd` 内的贴图 | 源文件旁 `<name>_lite.ytd` 与 `_lite_report.txt` |
| **MIP 检查 (YTD/DDS)** — *检查* | 列出 mip 链不完整的贴图 | 报告表格 |
| **MIP 检查** — *修复所选* | 重建完整 mip 链 | `<name>_fullmips.ytd`（或原地，保留 `.bak`） |
| **Ped 修复 (YMT)** — *检查* | 把每个 `.ymt` 与对应 `.ydd` 对照 | 仅报告区 |
| **Ped 修复** — *修复所选* | 修复被勾选的 ped 的 `.ymt` | 重写 `.ymt`，保留 `.bak` |
| **碎片整理 (RPF)** | 把压缩释放的空间还给磁盘 | 重写 `.rpf`，保留 `.bak` |
| **Gen8→9 转换** | 把 Legacy 资产重写成 Enhanced 布局 | 输出目录下镜像目录树 |

---

## 3. 各页面用法

### 3.1 法线贴图

1. `添加文件` 或 `添加文件夹`。
2. 调整 **强度**（浮雕深度）、**模糊**（平滑度）、**Alpha 权重**（alpha 轮廓算多少高度）。
   工具栏的 `?` 解释每一项并给出原版取值范围。
3. `生成`。

输出写在源文件旁的 `normals` 子目录里；已存在的 `*_n.dds` 会被跳过。

### 3.2 贴图 (YTD)

1. `添加 YTD`。
2. 选择长边上限（1024 / 1536 / 2048）。
3. 三选一：
   - **方案 1 · 吸附到档位** —— 长边吸附到下方最近的档位。
   - **方案 2 · 封顶** —— 超限的才缩小，更小的不动。安全默认值。
   - **方案 3 · 换格式** —— 封顶 + 换格式（未压缩 → DXT5，不透明 DXT5 → DXT1）。
     文件更小，但**务必进游戏验证**。
4. `分析` 只算不写；`压缩` 写出 `<name>_lite.ytd` 与一份简报。

1024 像素以下、`script_rt_*` 渲染目标、法线图与高光图一律不换格式。

### 3.3 MIP 检查

`检查` 列出 mip 链不完整的贴图。链条偏短的贴图远看会闪烁、出现摩尔纹。

勾选目标行后按 `修复所选`。筛选菜单可以全选、只选大问题，或跳过头发/alpha。

### 3.4 Ped 修复

添加存放 `.ydd` + `.ymt` 配对的文件夹。`检查` 会把每个 ped 标成绿色（drawable 与贴图数量
都对得上）或红色（`.ymt` 声明的部件比 `.ydd` 多）。红色行自动勾选，点行可取消。
`修复所选` 只动被勾选的行，并保留 `.bak`。

修复后的 ped 会被重新读一遍再报成功，写坏了会报出来，不会留下坏文件。

### 3.5 碎片整理 (RPF)

添加你改过的 `.rpf`，按 `碎片整理`。文件会被重写、回收空洞，并保留 `.bak`。压缩之后尤其
有用：归档里没有空洞时，游戏和 FiveM 的读取更快。

### 3.6 Gen8→9 转换

1. 选**输入文件夹**（你的 Legacy mod，例如某个车辆或 ped 包）。
2. 选**输出文件夹**。留空则写到源目录同级的 `<输入>-gen9`。
3. 按 **转换**。报告区逐行显示结果；**停止** 在文件之间中断，已写出的文件保留。

**转换什么**

| 类型 | 处理方式 |
|---|---|
| `.ytd` | 按 gen9 布局重建：新分页表、gen9 贴图描述符、保留 `script_rt_*` 渲染目标标志 |
| `.ydd` | 重建：gen9 drawable 布局，Sollumz 风格的包保留 legacy 结构 VFT |
| `.yft` | 重建：gen9 fragment 运行时表、gen9 材质默认值、octants 按原样保留 |
| `.ymt` / `.yld` | 逐字节复制（两代格式相同） |
| 其他 | 记为跳过，不写文件 |

**三条须知**

- **整套一起转。** 一辆车通常是三个文件——`car.yft`、`car_hi.yft`、`car.ytd`。只转
  `car.yft` 会让半辆车停在 Legacy 布局里，刹车卡钳、方向盘会在游戏里乱飞。
- **已经是 gen9 的文件会跳过**，所以重复运行是安全的。
- **没有体积上限。** 转换后的 fragment 段没有硬上限：34 MB 的系统段也能正常加载。

转换是按 gen9 结构完整重建，所以 `script_rt_*` 渲染目标标志能原样保住——这个标志一旦丢了，
车能刷出，但仪表盘渲染目标随后失败，几秒后崩溃。

13 MB 的车身文件约 10 秒，一辆车（车身、`_hi`、贴图）约 20 秒。

---

## 4. 命令行

同样的引擎，适合批量处理：

```
gtav-asset-repair normals <src> [--out DIR] [--strength 4.5] [--blur 1.2]
gtav-asset-repair lite <ytd…> [--mode cap|tier|agg] [--cap 1024] [--inplace]
gtav-asset-repair mips check <ytd|dds…>
gtav-asset-repair mips fix   <ytd…> [--out DIR | --inplace]
gtav-asset-repair ped check <folder|ydd|ymt…> [--json report.json]
gtav-asset-repair ped fix   <folder…> [--apply]
gtav-asset-repair ytd list  <ytd…> [--legacy]
gtav-asset-repair scale     <dds…> --out DIR --long-edge 1536
gtav-asset-repair audit     <ped.ymt.xml> [--json report.json]
gtav-asset-repair pack      --xml a.ytd.xml --build DIR --out a.ytd
gtav-asset-repair gen8to9   <src> [dst] [--dry-run] [--json]
```

多数命令支持 `--json` 输出机器可读结果；`--work DIR` 把所有默认输出收进一个目录。

---

## 5. 备份与回滚

任何重写你文件的命令，第一次都会在旁边留一份 `.bak`（`foo.ytd` → `foo.ytd.bak`）。已存在
的 `.bak` 不会被覆盖，所以第一份就是原件。

回滚：删掉被重写的文件，把 `foo.ytd.bak` 改名回 `foo.ytd`。界面左下角长期显示这条提示。

---

## 6. 排错

**`WinError 5` / 拒绝访问。** 目录只读，或文件被别的工具占用（OpenIV、CodeWalker、正在
运行的游戏）。关掉工具，或把文件拷到可写目录。桌面根目录常被 Windows 自身保护——换一个
你能写的目录。

**双击 exe 没反应。** 要么你把 exe 单独拿出来了（重新解压，保持文件夹结构），要么被
Windows SmartScreen 拦了。右键 exe → *更多信息* → *仍要运行*，或直接用包里的 `Run.bat`。

**转完的车一刷出就崩。** 确认这辆车目录里的 `.ytd` 也一起转了，并且这个 `.ytd` 里若有
`script_rt_*` 贴图，必须由本工具这类会保留渲染目标标志的转换器处理。

**只有刹车卡钳 / 方向盘乱飞。** 只转了主 `.yft`，`_hi.yft` 还是 Legacy 格式。整包三个文件
一起转。

**Ped 修复后还是红的。** 修复后的 `.ymt` 没能通过回读确认，所以没有保留。

**MIP 检查几乎标出 mod 里所有贴图。** 很多 mod 本来就只有一层 mip。标出来是对的，要不要修
由你决定。

**某些文件的压缩幅度很小。** 1000 像素以下的贴图、`script_rt_*`、法线图与高光图是故意跳过
的，报告里会写明原因。

---

## 7. 反馈

报错与提问：<https://github.com/wokken198/gtav-asset-repair/issues>

请附上文件类型、页面或命令，以及日志面板最后几行——通常一眼就能定位。

MIT 许可。不包含任何游戏资产；所有输入都来自你自己的安装。
