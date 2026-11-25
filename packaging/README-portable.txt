gtav-asset-repair 0.7.1
======================

Texture and ped repair for GTA V.
Pure-Python core: no Python install, no CodeWalker, no OpenIV, no .NET.


Quick start
-----------

Double-click gtav-asset-repair.exe. There is no installer and nothing is written
to the registry. The unzipped folder can live anywhere (non-ASCII paths are
fine), but keep the structure intact — the exe needs the _internal folder next
to it.


Five pages
----------

1. Normal maps (DDS)
   Turn a badge diffuse into a tangent-space normal map. Strength, blur and
   alpha weight are adjustable.

2. Textures (YTD)
   Batch-shrink the long edge of the textures inside .ytd files
   (1024 / 1536 / 2048), optionally rebuilding full mip chains as well.

3. Mip check (DDS/YTD)
   Find textures whose mip chain is too short and rebuild them on request.
   Less shimmer at a distance.

4. Ped repair (YMT)
   Check that the .ymt declares the drawables the .ydd actually has. Fixes blank
   wardrobe entries and crashes on spawn.

5. Defrag (RPF)
   Rebuild an RPF archive: lay the resources out contiguously, rewrite the
   directory table, and hand the space left by deleted files back to the disk.
   Textures are not re-compressed and resource contents are untouched.


Safety
------

* .bak backups are kept by default. Test in game first, delete them after.
* Back up the original files before the first run on a given pack.
* RPFs with encrypted children (common in vanilla dlc) are skipped
  automatically and counted in the report — they are never half-written.
* Large archives (3 GB and up) take tens of seconds; the progress bar shows it.


Feedback
--------

https://github.com/wokken198/gtav-asset-repair/issues


================================================================


gtav-asset-repair 0.7.1
======================

GTA V 的贴图与 PED 修复工具。
纯 Python 内核：不需要安装 Python，不需要 CodeWalker，不需要 OpenIV，不需要 .NET。


快速开始
--------

双击 gtav-asset-repair.exe 即可，没有安装程序，也不用写注册表。
解压后的整个文件夹可以放在任意位置（含中文路径），但请保持文件夹结构完整
（exe 需要旁边的 _internal 目录）。


五个功能
--------

1. 法线生成 (DDS)
   从车标等漫反射贴图生成法线贴图；可调强度、模糊、Alpha 权重。

2. 纹理压缩 (YTD)
   批量缩小 .ytd 里的贴图长边（1024 / 1536 / 2048），并可选补满 mip 链。

3. MIP 检查 (DDS/YTD)
   找出 mip 链不完整的贴图，按需重建，减少远处闪烁。

4. PED 修复 (YMT)
   检查 .ymt 声明的 drawable 数与 .ydd 实际内容是否一致，
   修掉换装菜单空白、随机换装崩溃这类问题。

5. Defragment (RPF)
   重建 RPF 归档：把有效资源连续排布、重写目录表、把删文件后
   残留在包内的空洞还给磁盘。不重新压缩贴图，不改资源内容。


安全须知
--------

* 默认保留 .bak 备份。改完请进游戏验证，再删除 .bak。
* 处理前请先备份原始文件——第一次用在某个包上时尤其如此。
* 子包加密的 RPF（游戏原版 dlc 常见）会被自动跳过，
  并在报告里说明跳过了几个，不会写坏它们。
* 大型归档（3 GB 级）需要几十秒，进度条会显示进度。


反馈
----

https://github.com/wokken198/gtav-asset-repair/issues
