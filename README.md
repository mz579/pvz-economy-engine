# 🌻 末日菜园作战室：真实菜价 × 植物策略推荐系统

> 僵尸来了先别慌，看看今天土豆多少钱。毕竟末日可以不精致，但种菜不能不讲性价比。😁

PvZ Economy Engine V2.0 是一个“看起来在打僵尸，实际上认真做数据分析”的蔬菜种植推荐系统。它把北京示例数据或用户上传的任意地区菜价、植物策略属性和有限资源约束放进同一块草坪里，专门研究一个非常严肃、也非常离谱的问题：**如果末日真的来了，有限的阳光和格子到底该种什么，才能既守住脑子，又守住钱包？**

系统会采集或读取真实菜价，清洗数据，把现实蔬菜映射成植物，再计算末日性价比指数并推荐种植组合。它不能替你把僵尸赶走，但至少能阻止你在预算只有 150 阳光时，冲动消费一排三线射手。

目前项目已经跑通完整链路，数据从菜市场一路走到草坪，中途没有被僵尸吃掉：

```text
北京新发地公开价格 / 本地 CSV fallback / 用户地区 CSV
  -> crawler.py 采集与回退
  -> preprocess.py 日期、菜名、单位清洗
  -> features.py 30 日价格特征
  -> plants.csv 植物与蔬菜映射
  -> scoring.py 末日性价比指数与理由
  -> optimizer.py PuLP 整数规划 / 贪心 fallback
  -> dashboard.py -> Streamlit PvZ 风格看板
```

## 项目亮点

- **断网也能种菜**：仓库自带 1,350 条、15 种蔬菜的 CSV。网站偶尔休假没关系，菜园不会跟着停工。
- **数据来路清楚**：统一输出 `date,name,price,source`，raw 快照和来源元数据都安排明白，不让来历不明的白菜混进队伍。
- **模型会解释人话**：除了排名，还会告诉你战斗价值、价格低估程度和稳定性。推荐土豆雷不是因为它长得老实，而是因为它确实算得过账。
- **预算意识良好**：阳光、格子、攻击和防御/控制四项约束逐项检查，坚决制止“全种向日葵然后祈祷”的激进方案。
- **求解器有后路**：优先让 PuLP 当军师；CBC 临时掉线时，贪心 fallback 会顶上，主打一个队伍可以降级，草坪不能停摆。
- **美术素材很克制**：页面只用 emoji 和原创 CSS，不搬运官方素材——律师函的攻击力不在本系统建模范围内。

## 下载后直接运行

不想先研究 Git、虚拟环境和依赖关系？可以前往 [GitHub Releases](https://github.com/mz579/pvz-economy-engine/releases/latest) 下载 `portable.zip`。完整解压后：

- Windows：双击 `start_windows.bat`；
- macOS / Linux：执行 `bash start_unix.sh`；
- 第一次启动会创建 `.venv` 并安装依赖，随后浏览器自动打开页面。

发布包里的 `README_FIRST.txt` 是极简操作说明。注意一定要先完整解压，别在压缩包里直接运行——植物能破土而出，Python 环境一般不行。

## 网站界面在哪里？

这是一个运行在本机的 Streamlit Web 应用，不是需要作者一直开着服务器的公共网站。启动成功后访问：

**http://localhost:8501**

![末日菜园作战室界面](docs/screenshots/dashboard.png)

网页左侧可以选择僵尸模式、阳光和格子，也可以填写地区名称、上传当地菜价 CSV 或下载模板。默认不上传时使用北京新发地离线示例。

## 从零开始

建议使用 Python 3.10 或更高版本。Windows PowerShell 示例见下方，照着敲就行，不需要先学会种向日葵：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m src.pipeline --offline
python -m unittest discover -s tests -v
streamlit run app.py
```

macOS/Linux 只需把激活命令替换为 `source .venv/bin/activate`。浏览器默认打开 `http://localhost:8501`。如果页面顺利出现，恭喜，你已经拥有了一块不用浇水、只吃内存的电子草坪。

离线命令行推荐：

```bash
python cli.py --mode "均衡巡逻" --sun 150 --cells 20
```

命令行也可以直接分析地区 CSV：

```bash
python cli.py --csv data/templates/regional_prices_template.csv --region "成都" --sun 150 --cells 20
```

尝试在线更新北京新发地价格：

```bash
python -m src.pipeline --online
python cli.py --online --mode "尸潮来袭" --sun 200 --cells 25
```

在线请求失败、返回空数据或字段结构变化时会自动改用本地 CSV，不需要改配置。终端会明确打印实际数据来源——网站可以摆烂，程序不行。

## 数据采集与清洗

在线适配器只访问[北京新发地公开价格页面](https://www.xinfadi.com.cn/priceDetail.html)对应的数据接口，默认处理近 30 天。离线源位于 `data/fallback/vegetable_prices.csv`。

北京新发地只是默认示例，不是地区限制。页面支持上传任意地区 CSV：系统会统一清洗单位，只分析能够和植物映射表关联的蔬菜，并把缺少菜价的植物列为“本轮未参赛”。这样既能适配不同地区，又不用养一支专门追着全国菜市场网页改版跑的爬虫维修队。

基础字段契约：

| 字段 | 含义 |
|---|---|
| `date` | 日期，输出为 `YYYY-MM-DD` |
| `name` | 标准蔬菜名，别名会在清洗层统一 |
| `price` | 价格，统一为人民币元/kg；元/斤自动乘 2 |
| `source` | `xinfadi_official`、`local_csv_fallback` 或 `user_upload:地区名` |

上传模板使用 `date,name,price,unit`；也支持 `日期,品种,均价,单位` 等中文表头，以及 UTF-8、GB18030、元/kg 和元/斤。地区名称由侧栏填写，运行时记录为 `user_upload:地区名`。

`src/features.py` 按蔬菜和日期计算 7/14/30 日均价、30 日历史均价、涨跌幅、价格分位和波动率。`data/raw/` 与 `data/processed/` 中的运行产物已由 `.gitignore` 排除，确保它们只能由流水线生成。

## 植物映射

`data/plants.csv` 包含 15 种植物。核心字段为植物名、映射蔬菜、阳光成本、攻击、防御、产能、控制、特殊能力和定位；`special_tag` 与 `category` 分别用于特殊能力量化和优化器角色识别。

映射规则：

1. 优先使用直接同名作物，例如豌豆射手映射豌豆、土豆雷映射土豆、樱桃炸弹映射樱桃。
2. 无直接对应时按外形或策略用途选择代理蔬菜，例如向日葵映射产能型油菜，坚果墙映射耐储存的大白菜。
3. 映射只连接清洗后的标准菜名，不在评分时做模糊匹配。
4. 多种植物可以共享一种蔬菜价格，但 15 种植物必须全部可关联。

属性值是本项目用于比较的内部策略参数，不宣称等同于官方游戏数值。请不要拿这张表和僵尸进行线下辩论，它大概率不会听。

## 末日性价比指数

### 1. 战斗价值

攻击原始值先按当前映射表最大攻击归一到 0-10；防御、产能、控制本身是 0-10。特殊能力根据 `special_tag` 映射到 0-10：`SINGLE=4`、`SPLASH=7`、`SIGHT=7`、`SLOW=8`、`WALL=8`、`MULTI=8`、`BOMB=9`、`PRODUCE=9`、`AOE=10`。

基础权重为：攻击 35%、防御 25%、产能 20%、控制 15%、特殊能力 5%。

```text
战斗价值 = 攻击分×0.35 + 防御×0.25 + 产能×0.20 + 控制×0.15 + 特殊能力×0.05
```

“尸潮来袭”“铁桶强攻”“迷雾夜战”会对这五项基础权重应用场景倍率，再归一化为 100%；最终场景权重可在页面的“模型状态”中查看。“均衡巡逻”使用基础权重。

### 2. 市场系数

```text
历史均价 = 最近 30 条日度价格的滚动均值
价格波动率 = 最近 30 条价格的总体标准差 / 历史均价
价格低估系数 = 历史均价 / 当前价格
稳定性系数 = 1 / (1 + 价格波动率)
```

### 3. 最终指数

```text
有效阳光成本 = max(真实阳光成本, 25)
末日性价比指数 = 战斗价值 × 价格低估系数 × 稳定性系数 / 有效阳光成本
```

25 点保护值只用于避免零阳光植物除零和无限放大——否则小喷菇会凭借“不要钱”在数学世界里直接封神。组合优化仍使用 `plants.csv` 中的真实阳光成本。指数保留公式原始尺度，不额外乘 100。每一行排名都会生成由优势维度、价格位置、稳定性和有效成本组成的中文理由。

## 组合优化

这一部分请 PuLP 来当草坪军师：目标是最大化所选植物的末日性价比指数总和，决策变量是每种植物的非负整数数量。军师虽然不打僵尸，但很擅长阻止你超预算。约束为：

1. 总阳光不超过可用阳光；
2. 植物数量不超过格子数；
3. 至少包含 1 个攻击植物；
4. 至少包含 1 个防御或控制植物。

输出包括组合、数量、单株/小计评分、总阳光、总植物数、总评分、求解方式、四项约束检查和推荐摘要。

## Streamlit 页面

页面包含阳光计数器、僵尸模式、植物推荐卡片、五列草坪网格、菜价趋势、推荐指数排行、完整模型状态和推荐理由。改变僵尸模式、阳光或格子后会重新评分并求解——放心，刷新推荐的速度通常比僵尸走路快。

截图建议放在 `docs/screenshots/dashboard.png`，画面应同时覆盖侧栏参数、顶部阳光计数器、种子卡、草坪和排行图。详细采集说明见 `docs/screenshots/README.md`。

## 项目结构

```text
app.py                         # Streamlit 主入口
cli.py                         # 完整链路命令行入口
assets/style.css               # 原创 PvZ 风格主题
data/fallback/                 # 可提交、可复现的离线数据
data/raw/                      # 运行时原始快照与来源元数据
data/processed/                # 运行时清洗和特征文件
data/plants.csv                # 15 种植物映射与属性
src/crawler.py                 # 新发地采集和本地回退
src/preprocess.py              # 字段、别名、日期和单位清洗
src/features.py                # 价格特征
src/plant_mapping.py           # 映射校验与关联
src/scoring.py                 # 正式评分与解释
src/optimizer.py               # PuLP 与贪心优化
src/dashboard.py               # UI 使用的完整视图模型
tests/                         # 单元、UI 与端到端测试
```

## 验证与故障排查

```bash
python -m unittest discover -s tests -v
python -m src.pipeline --offline
python cli.py --mode "均衡巡逻" --sun 150 --cells 20
```

- `python` 找不到：使用已安装解释器的完整路径，或重新打开已激活虚拟环境的终端。
- 新发地连接失败：属于预期可恢复状态，检查终端是否显示 `local_csv_fallback`；这不是投降，是战术性读取本地文件。
- PuLP/CBC 不可用：结果中的 `method` 会显示 `greedy`，四项约束仍会被验证；军师请假，副官照常上班。
- 资源不可行：当阳光或格子不足以同时放入攻击与防御/控制植物时，页面会返回明确错误而不是伪造组合。

## V2.0 边界与声明

本版本不包含 Airflow、多地区 SaaS、复杂金融 Alpha、夏普比率、金融化回测或重型预测模型。项目是数据分析与运筹优化练习，不隶属于植物大战僵尸版权方，也不包含官方图片、音效或其他游戏素材。
