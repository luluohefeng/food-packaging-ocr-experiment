# -*- coding: utf-8 -*-
"""
食品包装图片 OCR 最小验证程序（PaddleOCR 3.x）

流程：输入一张食品包装图片 -> 调用 PaddleOCR -> 整理为统一 JSON -> 保存到本地文件。

本程序只验证"识别文字 + 结构化保存"的技术可行性，不包含任何法规匹配、
风险等级判定或合规结论。识别结果不直接等同于真实包装印刷尺寸。

用法示例（在项目根目录 ocr_experiment/ 下执行）：
    .venv\\Scripts\\python main.py --input samples\\sample.jpg
    .venv\\Scripts\\python main.py --input samples\\sample.jpg --output output\\my_result.json

依赖与已知问题见 README.md。
"""

import argparse
import json
import sys
from importlib import metadata
from pathlib import Path

from PIL import Image

# 支持的输入图片格式（按扩展名判断，不区分大小写）
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg"}

# 默认输出位置：项目内 output/ocr_result.json
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "output" / "ocr_result.json"

# 使用的 PaddleOCR 模型（PP-OCRv5 系列，CPU 推理）
DET_MODEL_NAME = "PP-OCRv5_server_det"
REC_MODEL_NAME = "PP-OCRv5_server_rec"


class OcrExperimentError(Exception):
    """本程序自定义异常，message 直接面向用户展示。"""


# ---------------------------------------------------------------------------
# 参数与输入检查
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="食品包装图片 OCR 最小验证实验：识别图片文字并保存为统一 JSON。"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="输入图片路径，支持 PNG / JPG / JPEG 格式。",
    )
    parser.add_argument(
        "--output", "-o", default=str(DEFAULT_OUTPUT_PATH),
        help=f"输出 JSON 路径（默认：{DEFAULT_OUTPUT_PATH}）。相对路径基于当前工作目录。",
    )
    return parser.parse_args()


def validate_input_image(path: Path) -> Path:
    """检查输入图片是否存在、格式是否受支持、文件是否可正常读取。"""
    if not path.exists():
        raise OcrExperimentError(f"输入图片不存在：{path}")
    if not path.is_file():
        raise OcrExperimentError(f"输入路径不是文件：{path}")
    if path.suffix.lower() not in SUPPORTED_EXTS:
        raise OcrExperimentError(
            f"不支持的图片格式 {path.suffix!r}，仅支持：{', '.join(sorted(SUPPORTED_EXTS))}"
        )
    try:
        with Image.open(path) as img:
            img.verify()  # 校验文件确实是可解码的图片
    except Exception as exc:
        raise OcrExperimentError(
            f"无法读取图片文件（可能已损坏，或并非图片文件）：{path}（原因：{exc}）"
        )
    return path


def get_image_size(path: Path):
    """返回图片 (width, height)，单位为原始图片像素。"""
    with Image.open(path) as img:
        return img.size


# ---------------------------------------------------------------------------
# PaddleOCR 初始化与推理
# ---------------------------------------------------------------------------

def get_versions() -> dict:
    """读取实际安装的依赖版本；未安装的包返回 None。"""
    versions = {}
    for name in ("paddleocr", "paddlepaddle", "paddlex"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def init_ocr_engine():
    """初始化 PaddleOCR（CPU）。

    在函数内 import 依赖，这样"未安装"和"已安装但初始化失败"
    能被区分开，并给出面向用户的清晰提示。
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        raise OcrExperimentError(
            "未安装 paddleocr。请先按 README.md 创建虚拟环境并安装依赖：\n"
            "    python -m venv .venv\n"
            "    .venv\\Scripts\\python -m pip install -r requirements.txt\n"
            "（Python 需为 3.9 - 3.12，当前验证版本为 3.11.7）"
        )
    try:
        ocr = PaddleOCR(
            text_detection_model_name=DET_MODEL_NAME,
            text_recognition_model_name=REC_MODEL_NAME,
            # 以下三个开关关闭文档预处理，本次实验只需"文字检测 + 文字识别"，
            # 同时避免首次运行时额外下载方向分类/矫正模型。
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            engine="paddle_static",
            # 已知问题：paddlepaddle 3.3.x 在 Windows CPU 上默认开启 MKLDNN 加速时，
            # 推理会报 NotImplementedError（PIR 属性转换不支持），因此显式关闭。
            # 关闭后推理速度稍慢，但结果一致、可稳定运行。详见 README.md。
            enable_mkldnn=False,
        )
    except Exception as exc:
        raise OcrExperimentError(f"PaddleOCR 初始化失败：{exc}")
    return ocr


def run_ocr(ocr, image_path: Path):
    """执行 OCR 推理，返回 PaddleOCR 原始结果对象列表。"""
    try:
        # 首次运行会自动下载模型到用户目录（~/.paddlex），需要联网。
        outputs = ocr.predict(str(image_path))
    except Exception as exc:
        raise OcrExperimentError(
            f"OCR 推理失败：{exc}\n"
            "可能原因：模型下载中断（检查网络）、图片无法解码、"
            "或 paddlepaddle 版本不兼容（见 README.md 的已知问题）。"
        )
    return outputs


# ---------------------------------------------------------------------------
# 结果适配：PaddleOCR 3.x 原始结构 -> 统一 JSON 结构
# ---------------------------------------------------------------------------

def _normalize_polygon(polygon):
    """把多边形的每个顶点转成 [int, int]，保证 JSON 可序列化。失败时返回 None。"""
    try:
        return [[int(round(float(p[0]))), int(round(float(p[1])))] for p in polygon]
    except (TypeError, ValueError, IndexError):
        return None


def polygon_to_bbox(polygon):
    """由多边形各顶点的最小/最大横纵坐标计算外接矩形 [x0, y0, x1, y1]。

    注意：这里计算的是多边形在"输入图片像素坐标系"中的外接矩形，
    不代表实际包装上的印刷尺寸（需要另外标定比例才能换算）。
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return [int(round(min(xs))), int(round(min(ys))), int(round(max(xs))), int(round(max(ys)))]


def adapt_ocr_result(payload: dict, source_image: str) -> list:
    """把单个页面的 PaddleOCR 3.x 原始返回适配为统一结构。

    原始返回字段（已在 paddleocr 3.7.0 / paddlex 3.7.2 上实际验证）：
        rec_texts  : 每行识别出的文字（字符串列表）
        rec_scores : 每行文字的识别置信度（0~1 的浮点数列表）
        rec_polys  : 每个文字区域的多边形坐标（4 个顶点）
        rec_boxes  : 每个文字区域的矩形框 [x0, y0, x1, y1]
        dt_polys   : 检测阶段的多边形（rec_polys 缺失时用作备选）

    适配规则：
        - 坐标统一转为 int，保存在原始图片像素坐标系（原点左上角）。
        - bbox 优先取 API 直接给出的 rec_boxes；没有时由多边形计算外接矩形。
        - confidence 是模型对"识别结果正确性"的信心，不是文字违规的概率。
        - 某字段在原始返回中不存在时保存为 null，绝不自行编造数值。
    """
    texts = payload.get("rec_texts") or []
    scores = payload.get("rec_scores") or []
    rec_polys = payload.get("rec_polys") or []
    dt_polys = payload.get("dt_polys") or []
    rec_boxes = payload.get("rec_boxes") or []

    results = []
    for i, text in enumerate(texts):
        # confidence：API 未提供时保存 null
        confidence = None
        if i < len(scores) and scores[i] is not None:
            confidence = float(scores[i])

        # polygon：优先 rec_polys，其次 dt_polys，都没有则保存 null
        polygon = None
        if i < len(rec_polys):
            polygon = _normalize_polygon(rec_polys[i])
        elif i < len(dt_polys):
            polygon = _normalize_polygon(dt_polys[i])

        # bbox：优先 API 给出的矩形；没有时由多边形计算外接矩形
        bbox = None
        if i < len(rec_boxes) and rec_boxes[i] is not None:
            try:
                bbox = [int(round(float(v))) for v in rec_boxes[i]]
            except (TypeError, ValueError):
                bbox = None
        if bbox is None and polygon is not None:
            bbox = polygon_to_bbox(polygon)

        results.append({
            "text": str(text),
            "confidence": confidence,
            "polygon": polygon,
            "bbox": bbox,
            "source_image": source_image,
        })
    return results


def extract_page_payload(result_obj):
    """从单个 OCRResult 对象中取出原始字段字典（兼容不同版本的结构差异）。"""
    try:
        raw = result_obj.json
    except AttributeError:
        raw = result_obj
    if isinstance(raw, dict) and "res" in raw:
        return raw["res"]
    return raw if isinstance(raw, dict) else {}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    # 1. 检查输入图片（失败时快速退出，不加载模型）
    try:
        input_path = validate_input_image(Path(args.input))
    except OcrExperimentError as exc:
        print(f"[错误] {exc}")
        return 2

    # 2. 初始化 OCR 引擎
    try:
        versions = get_versions()
        ocr = init_ocr_engine()
    except OcrExperimentError as exc:
        print(f"[错误] {exc}")
        return 3
    print(f"[运行] 使用 paddleocr {versions.get('paddleocr')} 识别：{input_path}")

    # 3. OCR 推理
    try:
        outputs = run_ocr(ocr, input_path)
    except OcrExperimentError as exc:
        print(f"[错误] {exc}")
        return 4

    # 4. 适配为统一结构（保证字段类型可 JSON 序列化）
    results = []
    try:
        for out in outputs:
            results.extend(adapt_ocr_result(extract_page_payload(out), input_path.name))
    except Exception as exc:
        print(f"[错误] 解析 OCR 原始结果失败：{exc}")
        return 5

    # 5. 组装顶层 JSON 文档
    width, height = get_image_size(input_path)
    document = {
        "source_image": input_path.name,
        "image_width": width,      # 原始图片像素宽度
        "image_height": height,    # 原始图片像素高度
        "coordinate_system": "image_pixel_origin_top_left",
        "ocr_engine": "PaddleOCR",
        "ocr_version": versions.get("paddleocr"),
        "framework_versions": {
            "paddlepaddle": versions.get("paddlepaddle"),
            "paddlex": versions.get("paddlex"),
        },
        "results": results,
    }

    # 6. 保存 JSON（UTF-8，保证中文正常显示）
    output_path = Path(args.output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)  # 输出目录不存在时自动创建
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"[错误] JSON 保存失败：{exc}")
        return 6

    # 7. 终端输出摘要
    print(f"[完成] 识别到 {len(results)} 个文字区域")
    print(f"[完成] 结果已保存：{output_path.resolve()}")
    if len(results) == 0:
        print(
            "[提示] 未识别到任何文字。这不代表图片中一定没有文字，"
            "可能原因：小字号、反光、包装曲面、图案复杂等（见 README.md 局限性）。"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())