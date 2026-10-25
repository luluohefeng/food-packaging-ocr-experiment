# 食品包装图片 OCR 最小验证实验

通过 PaddleOCR 对食品包装图片进行文字识别，并把结果整理为统一的 JSON 文件。
本实验只验证两件事：

1. PaddleOCR 能否从包装图片中识别出文字（含中文）；
2. 识别结果能否被整理成结构清晰、可继续处理的 JSON 数据。

> **重要声明：这是一个技术验证实验，不是完整的食品包装合规检测系统。**
> 程序只做"识别文字 + 结构化保存"，不做法规匹配与合规判定，识别结果
> 不构成任何合规判断依据，也不能直接替代人工核验。

## 一、本次实验不涉及的功能

- 不做食品法规匹配、风险等级判定，不给出任何合规结论；
- 不集成 PyMuPDF / PP-StructureV3 / FastAPI / 数据库 / 大模型 / Docker；
- 不处理 PDF，只处理图片（PNG / JPG / JPEG）；
- 不提供 Web 页面或批量任务调度，一次运行处理一张图片。

## 二、环境与依赖安装

- 操作系统：Windows（macOS / Linux 同样适用，仅安装命令略有差异）
- Python：3.9 - 3.12（本项目在 **Python 3.11.7 / Windows** 上验证通过）
- 全部推理在 **CPU** 上完成，不需要 GPU

本项目已在本机 `ocr_experiment\.venv` 中创建好虚拟环境并安装依赖；如果你换机器
或虚拟环境丢失，按下面步骤重建（不会影响系统全局 Python）：

```bash
cd ocr_experiment
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

> 网络提示：默认源是官方 PyPI。若下载较慢，可加清华镜像源：
>
> ```bash
> .venv\Scripts\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

依赖版本（已实测）：

| 包 | 版本 | 作用 |
| --- | --- | --- |
| paddlepaddle | 3.3.1 | 深度学习推理框架 |
| paddleocr | 3.7.0 | OCR 模型封装（内部使用 paddlex 3.7.2） |
| Pillow | 13.0.0 | 读取图片尺寸、校验图片文件 |

### 已知问题：为什么关闭了 MKLDNN？

`main.py` 中传入了 `enable_mkldnn=False`。原因是 paddlepaddle 3.3.x 在
Windows CPU 上默认开启 MKLDNN（oneDNN）加速时，PP-OCRv5 检测模型会报
`NotImplementedError (ConvertPirAttribute2RuntimeAttribute ...)`。
关闭后推理速度稍慢，但结果一致、可稳定运行。该参数已写死在
[main.py](main.py) 的 `init_ocr_engine()` 中，无需手动设置。

### 模型下载

首次运行会自动下载 PP-OCRv5 检测/识别模型到用户目录
（`C:\Users\<你的用户名>\.paddlex\official_models\`），需要联网。
下载一次后即可离线运行。如果下载中断导致报错，删除对应模型目录后重跑即可。

## 三、项目结构

```
ocr_experiment/
├── main.py              # 主程序：识别 + 结构化保存
├── requirements.txt     # 依赖清单
├── README.md            # 本说明文档
├── .gitignore           # 忽略虚拟环境、缓存、输出与私有图片
├── samples/             # 测试图片目录（由你放入图片，不随仓库上传）
└── output/              # 运行后生成的 JSON（目录不存在时自动创建，忽略提交）
```

## 四、如何放入测试图片

把 PNG / JPG / JPEG 图片直接放到 `samples/` 目录，例如 `samples\milk.jpg`。
程序不会修改或覆盖你的原始图片（只读取、不写入）。

> 注意：`samples/` 下的图片被 `.gitignore` 排除，**不会**随仓库上传到 GitHub。
> 请自行拍摄或使用你确认可以公开的食品包装图片。如果你想分享演示图片，
> 可以替换为明确允许公开的素材（如自有产品图、公共数据集图片），并自行
> 移除 `.gitignore` 中的排除规则。

## 五、如何运行

在项目根目录 `ocr_experiment/` 下执行（使用 `--input` 指定图片，
`--output` 指定结果 JSON 路径）：

```bash
# 基本用法：识别 samples\milk.jpg，结果默认保存到 output\ocr_result.json
.venv\Scripts\python main.py --input samples\milk.jpg

# 指定输出文件
.venv\Scripts\python main.py --input samples\milk.jpg --output output\milk_result.json

# 简写参数名
.venv\Scripts\python main.py -i samples\milk.jpg -o output\milk_result.json
```

运行结束后，终端会显示识别到的文字区域数量和输出文件路径，例如：

```
[运行] 使用 paddleocr 3.7.0 识别：samples\milk.jpg
[完成] 识别到 5 个文字区域
[完成] 结果已保存：C:\...\ocr_experiment\output\ocr_result.json
```

## 六、输出 JSON 各字段含义

顶层字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `source_image` | string | 输入图片文件名（不含目录） |
| `image_width` / `image_height` | int | 原始图片的像素宽 / 高 |
| `coordinate_system` | string | 坐标约定：`image_pixel_origin_top_left`，即所有坐标都是**输入图片的像素坐标，原点在左上角**。它**不是**包装上的实际印刷尺寸（厘米/毫米），换算需要另外标定比例 |
| `ocr_engine` / `ocr_version` | string | OCR 引擎名称与实际安装的 paddleocr 版本 |
| `framework_versions` | object | 实际安装的 paddlepaddle / paddlex 版本，便于排查兼容问题 |
| `results` | array | 每个识别出的文字区域一条记录；数组为空 `[]` 表示本次未识别到任何文字 |

`results` 中每条记录的字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `text` | string | 识别出的文字 |
| `confidence` | float 或 null | 模型对**识别结果正确性**的信心（0~1）。数值越高，文字识别越可能正确。它**不是**“文字违法/违规的概率”。若 API 未返回该字段，则为 `null`（不做编造） |
| `polygon` | array 或 null | 文字区域的四边形顶点坐标，`[[x0,y0],[x1,y1],...]`，来自 API 原始返回；API 未提供时为 `null` |
| `bbox` | array 或 null | 统一矩形框 `[x0, y0, x1, y1]`（左上角、右下角）。优先取 API 直接给出的矩形；API 只给多边形时，由各顶点最小/最大横纵坐标计算外接矩形 |
| `source_image` | string | 同顶层 `source_image`，便于单条记录独立使用 |

全部坐标均为整数、单位是输入图片像素；文件以 UTF-8 保存，中文可直接阅读。

### JSON 输出示例

下面是实际运行一次得到的输出结构（节选 2 条记录，示例内容来自一张
900 x 500 的合成测试图，仅用于演示字段格式）：

```json
{
  "source_image": "sample.jpg",
  "image_width": 900,
  "image_height": 500,
  "coordinate_system": "image_pixel_origin_top_left",
  "ocr_engine": "PaddleOCR",
  "ocr_version": "3.7.0",
  "framework_versions": {
    "paddlepaddle": "3.3.1",
    "paddlex": "3.7.2"
  },
  "results": [
    {
      "text": "食品名称：纯牛奶",
      "confidence": 0.9977719187736511,
      "polygon": [[37, 43], [329, 43], [329, 87], [37, 87]],
      "bbox": [37, 43, 329, 87],
      "source_image": "sample.jpg"
    },
    {
      "text": "配料表：生牛乳",
      "confidence": 0.9972895383834839,
      "polygon": [[35, 130], [296, 128], [296, 172], [35, 174]],
      "bbox": [35, 128, 296, 174],
      "source_image": "sample.jpg"
    }
  ]
}
```

示例中的文字与数值来自真实运行结果（合成测试图）；你自己的图片产生的
`text`、坐标与置信度会不同。坐标是"识别区域在整张输入图片中的像素位置"，
与包装上真实的印刷尺寸没有直接换算关系。

## 七、如何判断程序是否运行成功

1. 终端出现 `[完成] 识别到 N 个文字区域` 和 `[完成] 结果已保存：...`；
2. 输出目录里生成了对应的 JSON 文件；
3. 用文本编辑器或任意 JSON 工具打开该文件，中文正常显示、`results` 内的
   `text` 与图片上的文字大致一致。

常见错误提示对应的含义：

| 终端提示 | 原因 |
| --- | --- |
| `输入图片不存在：...` | `--input` 路径写错或图片还没放进 `samples/` |
| `不支持的图片格式 ...` | 文件扩展名不是 png / jpg / jpeg |
| `无法读取图片文件 ...` | 文件已损坏，或并非真正的图片文件 |
| `未安装 paddleocr ...` | 虚拟环境没激活或依赖未安装，按第二章重建环境 |
| `OCR 推理失败 ...` | 多为首次模型下载中断（网络问题），删除 `~\.paddlex\official_models` 下对应目录后重跑 |
| `JSON 保存失败：...` | 输出路径无法写入（如目录不存在且无法创建、磁盘权限等） |
| `未识别到任何文字 ...` | 程序正常结束，但检测阶段没找到文字区域。**这不代表图片中一定没有文字**，常见原因见第八章 |

## 八、实验局限性

图片质量对结果影响很大，常见问题包括：

- **小字号**：包装上极小的字体（如营养成分表）可能漏检或识别错误；
- **反光/高光**：塑料包装反光区域文字可能变淡、断裂；
- **包装曲面**：圆柱瓶身、褶皱处的文字会变形，影响检测与识别；
- **复杂背景**：文字压在图案、渐变色上时容易漏检或错字；
- **艺术字体**：手写体、变体字、竖排文字的识别率明显低于横排印刷体；
- **语言混合**：中英混排整体可用，但个别字符可能混淆（如“净”与“浄”）；
- **置信度只反映“认字是否正确”**，与内容是否合规完全无关。

结论：该流程适合作为“提取包装图片中大部分印刷文字”的第一步，结果需要人工抽查，
不能直接当作最终合规依据。

## 九、下一阶段：与 PyMuPDF、PP-StructureV3 结果统一

本实验输出的 JSON 是“图片 OCR”这一路结果。后续封装完整检测系统时，建议：

1. 把所有工具的输出统一成同一套中间结构（可复用本 JSON 的字段设计）：
   - 文本：`text` + `confidence`；
   - 位置：统一转换为 `bbox [x0, y0, x1, y1]`（PyMuPDF 的页面坐标、PP-StructureV3
     的版面框坐标同样可以归一化为各自来源的像素坐标）；
   - 来源信息：`source_image` / `source_page` / `source_tool`；
2. 用 PyMuPDF 提取 PDF 中**已有**的文本层（如产品电子标签文件），
   用 PP-StructureV3 做版面分析（标题、表格、栏位）和表格结构化提取，
   用本程序处理**扫描图/照片**；
3. 融合时注意坐标系差异：PDF 页面坐标与图片像素坐标需分别标注坐标系统，
   且都需要与真实包装尺寸建立标定关系后才能做“位置对应”；
4. 在统一结构之上，再实现法规关键词匹配、风险等级判定等业务逻辑。