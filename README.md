<div align="center">

# 🔍 CathayFinder

**综合性图书检索引擎 · 11 个渠道，一口气查N本书（找 SSID / 找路径 / 找文件）**

*开箱即用 · 双击即开 · 纯本地 · 不联网 · 绝不修改你的任何文件*

[![license](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)
[![platform](https://img.shields.io/badge/platform-Windows%2010%2B-brightgreen)]()
[![version](https://img.shields.io/badge/version-v1.1.0-orange)]()

只做**精准匹配**（完整包含你输入的那串字），不做模糊搜索 —— 搜「布罗代尔」只会出真正含
「布罗代尔」的记录，不会塞给你一堆无关书。

</div>

---

## 🔗 Cathay 人文社科工具链

这是一整套给人文社科研究者用的**本地**工具：从「找到一本书」，到「把它变成能搜、能读、能引用的 PDF」，再到「在上万本书里一秒检索」——每一步一个小程序，**各自独立，只挑你用得上的那一步就行**。

| 步骤 | 工具 | 一句话 | 版本 |
|:---:|---|---|---|
| ⓪ | [CathayRepair](https://github.com/zzhjim02/CathayRepair) | PDF 打不开、一翻就崩 → 先把它抢救回来 | v1.0.0 |
| ① | [CathayPDG](https://github.com/zzhjim02/CathayPDG) | 读秀 / 超星的 PDG 压缩包 → PDF | v0.2.0 |
| ② | [CathayOCR](https://github.com/zzhjim02/CathayOCR) | 扫描件做 OCR → 能搜索、能复制的 PDF | v1.2.4 |
| ③ | [CathayRestore](https://github.com/zzhjim02/CathayRestore) | 把 OCR 出来的 TXT 写回 PDF，做成双层 | v1.0.0 |
| ④ | [CathayExtract](https://github.com/zzhjim02/CathayExtract) | 已经是双层 PDF → 直接把文字抽成 TXT | v1.2.3 |
| ⑤ | [CathayShelf](https://github.com/zzhjim02/CathayShelf) | 批量建档归位、规范命名、繁简转换 | v0.4.8 |
| **⑥** | **CathayFinder（你在这里）** | 11 个渠道查这本书在哪（找书号 / 找路径） | **v1.1.0** |
| ⑦ | [CathayHub](https://github.com/zzhjim02/CathayHub) | **索引 + 全库检索 + 浏览阅读，四合一的日常入口** | v0.3.16 |

> 🧭 **最常用的一条线**：⑥ 查到书 → ① 转成 PDF → ② 让它能搜 → ⑤ 著录归架 → ⑦ 检索、翻开。
> 每一步都能单独用，不强制串起来；整套**纯本地、不联网、不动你的原件**。

**已成历史（功能已并入后面的工具，代码还能跑）**

| 工具 | 现状 |
|---|---|
| [CathayIndex](https://github.com/zzhjim02/CathayIndex) | 已并入 ⑥ CathayFinder 的「本地文件库索引」页签，以及 ⑦ CathayHub Indexer |
| [CathayViewer](https://github.com/zzhjim02/CathayViewer) | 已并入 ⑦ CathayHub Viewer |
| [CathayReader](https://github.com/zzhjim02/CathayReader) | 已由 ⑦ CathayHub Viewer 取代 |
| [CathaySimplify](https://github.com/zzhjim02/CathaySimplify) | 已并入 ⑤ CathayShelf 的「繁简转换 / 编码规范化」 |

**🛠️ 备用小工具（不占主线，按需取用）**

| 工具 | 什么时候想到它 |
|---|---|
| [CathayDir](https://github.com/zzhjim02/CathayDir)（[📥 Releases](https://github.com/zzhjim02/CathayDir/releases/latest)） | 成批 PDF 摆在那儿，想先知道各自是**横排还是竖排**（分流做 OCR、挑引擎参数、建库前摸底）—— 每 10 页抽一页批量判，结果能存 CSV，也能直接分成「横排 / 竖排 / 未知」三个柜。判定算法借自 CathayPDG |

---

## 📦 下载

| 下载方式 | 说明 |
|:-------|:-----|
| 📥 **百度网盘（密码 2026）** ← **最新 v1.1.0，推荐** | [CathayFinder 综合性图书检索软件 1.1.0 标准版](https://pan.baidu.com/s/1pwxOiQYO6o2XVuL3oIHfpA?pwd=2026)（**程序 + 11 个渠道数据库 + CathayIndex，解压即用**，含本地文件库；不含个人网盘资料库本身） |
| 🐙 GitHub Releases | [CathayFinder v1.1.0](https://github.com/zzhjim02/CathayFinder/releases/tag/v1.1.0)（Assets：`CathayFinder-v1.1.0.exe` 单程序 43 MB ／ `CathayFinder-v1.1.0-windows-x64.zip` 完整程序包 56 MB。**都不含数据库**） |
| 💻 源码 | 本仓库源码：`py -3 -m pip install PyQt5 pypinyin zhconv` 后 `py -3 main.py` |

> ⚠️ **本仓库只放程序，不放任何数据**：`data\`（11 个渠道的数据库，约 27 GB）**不在仓库里**
> —— 请从百度网盘下载，并**与 exe 放在同一层**，否则搜不到任何结果。
>
> 📌 **两个地方的程序都是 v1.1.0，功能完全一样，区别只在数据库**：
> 网盘版自带 27 GB 数据库（解压就能搜）；GitHub 版**只有程序** —— 适合你已经有一份 `data\db\`、
> 只想换个新 exe 的情况（下 `CathayFinder-v1.1.0.exe` 覆盖旧的即可，`data` 不用动）。
> 第一次用请走网盘。链接失效请在 Issues 里说一声。

---

## 🚀 三步就会用

1. **双击 `CathayFinder.exe`**（网盘完整包里叫 `CathayFinder 综合性图书检索引擎 1.1 标准版.exe`，GitHub 版就叫 `CathayFinder.exe`，是同一个东西）
2. 搜索框里输入：书名 / 作者 / 出版社 / 编号（SSID）
3. 回车 → 左边出结果列表，点某一行 → 右下角看详情

结果上方会写明 **「命中 N 条 ｜ 已载 M 条 · K 页」**，并按渠道（百度网盘 / 读秀 / Z-Library …）
**分组连续排列**，不会出现「A 渠道、B 渠道、又回 A 渠道」。

---

## 📚 能搜什么（11 个渠道）

| 渠道 | 里面是什么 | 库文件 | 条数 |
|---|---|---|:---:|
| 本地文件库 | 你自己电脑上扫进来的文件夹 —— **直接在软件上方的「📁 本地文件库索引」页签里建**，不用另开程序 | `local_files.db` | 自建 |
| 学术信息数据库 | 个人百度网盘 + 阿里网盘的资料目录 | `baidu_pan.db` + `aliyun.db` | 586 万 + |
| 读秀 | 读秀书目（含 SSID）+ 秒传码库 | `duxiu.db` + `duxiu_md5.db` | 511 万 + 3139 万 |
| 维基共享资源 | Wikimedia Commons 书籍扫描件目录 | `wiki_lib.db` + `commons_books.db` | 338 万 + 827 万 |
| Z-Library | Z-Library 书目 | `zlib.db` | 1045 万 |
| 中国地方志 | 地方志旧志目录 | `difangzhi.db` | 1.2 万 |
| 奇点社科 | 微信群资源目录 | `qidian.db` | 5 万 |
| 游氏古籍 | 游氏古籍编目 | `youshi.db` | 46 万 |
| 维基文库 | 中文维基文库全部条目 | `zhwikisource.db` | 198 万 |
| 华中师大近史所 | 华中师范大学中国近代史研究所实体藏书 | `huazhong.db` | 2.6 千 |
| 维基百科 | 中文维基百科全部条目 | `zhwiki.db` | 807 万 |

**搜的时候不用挑库**（默认全选）；想只在某几个库里找，就改上方勾选框。

> ❓「本地文件库」怎么来的：点窗口上方的 **「📁 本地文件库索引」页签** → 选要扫的文件夹 → 建库。
> 建完不用重启，切回「🔍 检索」页签、勾上「本地文件库」就能搜。
> （这一步原来要单独开一个小工具 **CathayIndex**，v1.1.0 起已经搬进主程序了。）

---

## 每个库的数据来源文件

> 原始数据保存在本机自己的资料目录里（只读）。想重建某个库，就用那里的原始文件重跑本仓库里的建库脚本。

| 渠道 | 数据来源 |
|---|---|
| **学术信息数据库** | ① `个人百度网盘文件总目录\`（2,687 个文件）——顶层 106 个 txt/xlsx（个人资料总库、E1 国史特殊资料集、NB2 中国近代史报刊、更新文件列表等）+ 子目录 `中华古籍智慧化服务平台国家珍贵古籍书签文件（1285种）`（2,570 个 txt）、`古籍目录12658种`（4 个 csv）、`国家珍贵古籍目录1285种`（4 个文件） |
|   | ② `个人阿里网盘文件总目录\`（3 个文件）——`阿里云盘：学术信息条目检索数据库-扩展 文件目录.xlsx`（3,199 个文件路径+大小）、`…-人文与社会译丛总目.docx`（106 种书）、`… 文件目录_OCR.pdf`（与 xlsx 同一份，未重复导入） |
| **读秀** | `读秀DXID-SSID对应表-512w_catalog\`（6 个 txt，512 万行，字段 `ss_id dx_id name year pages book_number`） |
|   | `读秀秒传码检索系统\`（30 个文件，3,139 万行）——`combined_md5_01~17`、`读秀5.0/6.0秒传`、`读秀1.0-4.0全集目录.txt`（956 MB 网盘路径清单）、`读秀4.0目录.csv.txt`、`大学堂补充库书目.txt`、`疑难书库20T/40T` 等 |
| **维基共享资源** | ① `维基共享资源-数字图书馆备份项目-目录-20250620\`（603 个文件）+ 同名 `【繁转简】` 目录（同内容）<br>② `维基共享资源-总目录-20250620\`（16 个文件、**1.58 亿行 / 7.97 GB**）—— **只抽了 pdf/djvu/tif 的书刊文件**：8,278,839 条 / 3.7 GB / 建库 3.5 分钟（全量 1.58 亿行未导：抽样看 .jpg 占 69.8%、无扩展名（分类页/画廊）占 18.6%，pdf/djvu/tif 类只有 1.7%；全量入库估计要 35–55 GB（逐字加空格索引）、1.5–3 小时，且会把检索结果稀释）
| **Z-Library** | `Z-Library资源种子检索系统\`（265 个文件） |
| **中国地方志** | `中国地方志旧志目录（全1册+2册备用）【繁体+简体】…\`（3 个 xlsx） |
| **奇点社科** | `奇点社科微信群资源目录\`（4 个文件） |
| **游氏古籍** | `游氏古籍国外古籍数据库 资料编目（全1册）（微信公众号：游氏古籍）\`（1 个 html，约 43 MB） |
| **维基文库** | `中文维基文库条目名称列表zhwikisource-20250701-all-titles.txt`（55 MB）+ `【繁转简】` 版 |
| **维基百科** | `中文维基百科条目名称列表zhwiki-20250701-all-titles.txt`（168 MB）+ `【繁转简】` 版 |
| **华中师大近史所** | `华中师范大学中国近代史研究所资料室索引 2.0（纯净版）/（前后对照版）/ 2022年9月版.docx` + `…藏书与全文检索、条目检索数据库藏书书目对照.xlsx` |
| **本地文件库** | 不是外部数据：在软件上方「📁 本地文件库索引」页签里扫你自己的文件夹生成（示例库是 `E:\OCR综合` 的 3,523 个文件）。以前要靠单独的小工具 CathayIndex，v1.1.0 起已搬进主程序 |

> 其它同目录但**未**导入本工具的数据（`中国省级图书馆免费电子资源目录`（json/md）、
> `维基共享资源-总目录` 里除 pdf/djvu/tif 以外的部分）保留在原地，需要时再说。

---

## 🎯 检索规则

- **精准匹配**：按「完整包含」匹配，不做模糊/近似；错一个字就是没有
- **按字段搜**：搜索框右边下拉 —— 全部字段 / 搜书名 / 搜作者 / 搜出版者 / 搜SSID（支持只写前几位，如 `1429`）
- **每渠道先取**：单个渠道命中很少（≤5000 条）时**全部取回**；命中极多时先取 5000 条，
  顶部明细会写清：`命中 = 显示 + 同库重复 + 读秀同书合并 + 渠道上限外未取`，点「⬇ 再取更多」继续
- **读秀按 8 位 SSID 去重**（同一本书多个秒传码只显示一条，备注里写「另有 N 条同 ID 记录」）
- **读秀结果按拼音 A→Z 排序**（汉字取拼音，英文/数字按字面）
- 滚动到底自动加载更多（按钮只是手动兜底）

---

## 📖 读秀的书怎么拿到手

选中那一行 → 点右侧 **「📋 复制SSID」** → 到某宝搜索「**读秀 百度网盘共享群**」，
买任意一个群的入群资格，即可按 SSID 下载。（极少数图书可能无法下载。）

---

## 📤 导出

点 **📄 导出 CSV / Markdown / Text / HTML**：

1. 先弹「导出选项」→ 勾你要哪些字段（渠道 / 书名 / 文件名 / 目录 / 作者 / 出版者 / 年份 / ISBN / SSID / 页数 / 备注）
2. 再选保存位置

导出的是**去重、排序后的全部结果**（不受屏幕「每渠道 5000 条」的限制；宽泛词可能较慢、文件较大）。

---

## 🗂 想停用某个库 / 换台机器

- **停用**：把该渠道的 `.db`（连同同名 `.db-wal`、`.db-shm`）改名或移走 → 重启软件 →
  该渠道自动置灰并跳过（想装回来，放回去点「🔄 检测数据库」即可）
- **换机器**：整个文件夹（exe + `data\`）一起拷，约 27 GB；或给 `data\` 建个目录联接
  （`mklink /J`），exe 放哪都行

---

## 🛠 自己打包 EXE

```bat
py -3 -m pip install PyQt5 pypinyin zhconv pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name CathayFinder --icon app.ico --add-data "app.ico;." ^
    --collect-all pypinyin --collect-all zhconv ^
    --distpath dist --workpath build --specpath . main.py
```

> ⚠️ **`--name` 绝不能与源码包同名**：源码包叫 `cathayfinder`（Windows 大小写不敏感），
> 若 `--name cathayfinder` 或把 `--distpath` 指到源码包那一层，PyInstaller 会把整个源码包删掉。
> 本仓库还带了 `fab.py` + `发版.bat` + `发布流程.md`，一键出 exe + SHA256 + 发行说明。

---

## 📁 目录结构

```
main.py                      入口
CathayFinder.spec            打包配置（onefile）
fab.py / 发版.bat            一键发版（打包 + SHA256 + 发行说明）
发布流程.md                  发版清单
requirements.txt             依赖（PyQt5 / pypinyin / zhconv）
LICENSE                      GPL-3.0
cathayfinder\
  ├─ config.py               路径 / 渠道优先级 / 颜色
  ├─ data\db_manager.py      渠道 → 数据库文件对应表（一个渠道可挂多个库）
  ├─ search\engine.py        FTS5 检索引擎（精准匹配 / 字段检索 / 去重 / 排序 / 计数）
  └─ ui\app_gui.py           界面（结果表 / 详情面板 / 导出）
```

---

## ❓ FAQ

**搜不到结果？** ① 关键词是否打错（不模糊匹配，错一个字就是没有）；② 上面勾选框里相关的库是否打勾；
③ `data\db\` 里的 `.db` 是否还在。

**结果里有的行没有书名？** 那是网盘目录 / 秒传码库的记录，库里本来只有文件名或编号，属正常。

**exe 一闪就没？** 确认 exe 与 `data\` 在同一层，别把 exe 单独拷到别处运行。

**为什么有的库搜出来很少？** 该库本身的 FTS 索引只覆盖书名/作者/出版者等列，例如按 ISBN 搜时
多数库不建 ISBN 索引 —— 按书名/作者检索最稳。

---

## 📝 更新日志

- **v1.1.0**（2026-10-03）：**CathayIndex 搬进主程序**，一套东西一个窗口搞定
  - 新增 **「📁 本地文件库索引」页签**：原来建「本地文件库」得单独开 CathayIndex 那个小程序，
    现在就在 Finder 里做 —— 选目录 → 建库（全量 / 增量） → 建完**不用重启**，
    切回「🔍 检索」页签勾上「本地文件库」直接搜
  - **结果行上直接能操作**：点一行看详情的同时，那一行就有「📂 打开所在文件夹」「📋 复制SSID」按钮，
    不用再去右下角找
  - **导出可以挑字段**：11 个字段想导哪几个勾哪几个（只要书名+SSID 也行），不再每次全给
  - **导出不再被屏幕截断**：导出永远取全部结果（不受每渠道显示上限限制），读秀按 8 位 SSID 去重、按拼音 A→Z 排序
  - 命中明细写清楚三笔账：`命中 = 显示 + 同库重复 + 读秀同书合并 + 渠道上限外未取`，
    想知道有没有漏点「⬇ 再取更多」
  - 完整性自检：公开版跑通 11 渠道、字段检索、读秀去重/拼音排序、导出去重、缺库置灰等一整套
- **v1.0.0**（2026-09-20）：首个版本 —— 11 渠道精准检索、按字段搜、渠道分组连续、
  命中/已载/页数三笔账、读秀 SSID 去重 + 拼音排序 + 复制 SSID、详情面板「打开所在文件夹 / 打开网页」、
  可选字段导出全部结果、缺库自动置灰跳过、本地文件库渠道、单文件 exe（免安装）

---

## ⚖️ 免责声明与法律定位

CathayFinder 是一个纯信息索引与检索工具。

本软件的功能仅限于：

- 读取用户本地的元数据文件（如读秀 SSID 对应表、网盘文件目录、维基共享资源目录等）；
- 对上述元数据进行全文索引与检索；
- 向用户展示检索结果，包括书名、作者、ISBN、SSID、以及用户本地或外部渠道中可能存在的存储位置信息。

本软件不提供、不存储、不分发任何受版权保护的内容。

- 本软件不包含任何电子书文件；
- 本软件不提供任何下载链接或下载功能；
- 本软件不代理用户执行任何获取、下载、传输行为；
- 本软件输出的所有信息，均来自用户自行提供的本地元数据文件。

**用户责任：**

用户在使用本软件时，应自行确保其获取和使用任何资料的行为符合所在国家或地区的法律法规。本软件仅提供信息指引，用户根据指引自行进行的任何操作，与本软件作者无关。

**开源目的：**

本软件开源的目的在于分享元数据索引与检索的技术实现，供学术研究和个人学习参考。本软件不鼓励、不支持、不参与任何侵犯版权的行为。

---

## English Disclaimer

### Disclaimer and Legal Positioning

CathayFinder is a pure information indexing and retrieval tool.

The software's functionality is limited to:

- Reading user-provided local metadata files (e.g., Duxiu SSID mapping tables, cloud storage file lists, Wikimedia Commons catalogs);
- Building full-text indexes over such metadata;
- Displaying search results to the user, including book title, author, ISBN, SSID, and possible storage locations in the user's local or external channels.

This software does not provide, store, or distribute any copyrighted content.

- It contains no ebook files;
- It provides no download links or download functionality;
- It does not perform any acquisition, download, or transfer actions on behalf of the user;
- All output information originates solely from metadata files provided by the user.

**User Responsibility:**

Users are solely responsible for ensuring that their use of any materials complies with the laws and regulations of their jurisdiction. This software provides information guidance only. Any actions taken by users based on such guidance are unrelated to the software author.

**Open Source Purpose:**

This software is open-sourced to share the technical implementation of metadata indexing and retrieval for academic research and personal study. It does not encourage, support, or participate in any copyright-infringing activities.

---

## 📄 许可

[GPL-3.0](LICENSE) © Cathay 人文社科工具链
