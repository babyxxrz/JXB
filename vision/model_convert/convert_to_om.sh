#!/usr/bin/env bash
# ============================================================
# convert_to_om.sh — ONNX → OM(昇腾 .om)转换脚本
# 执行位置: Atlas 200I DK A2(需已安装 CANN 工具链)
# 用法:     bash convert_to_om.sh [onnx文件路径]
# 默认:     ./models/ 下第一个 .onnx
# 转换前:   先跑 python verify_onnx.py <onnx> 核对输入名与 shape
# ============================================================
set -e

# ---------- 0. 环境(路径按实机 CANN 安装位置调整) ----------
source /usr/local/Ascend/ascend-toolkit/set_env.sh

# ---------- 1. 转换参数(每换一个模型核对这里) ----------
ONNX_FILE="${1:-$(ls models/*.onnx 2>/dev/null | head -1)}"
[ -n "$ONNX_FILE" ] || { echo "未找到 ONNX 文件,用法: bash convert_to_om.sh <onnx路径>"; exit 1; }

MODEL_NAME="$(basename "$ONNX_FILE" .onnx)"
SOC_VERSION="Ascend310B1"          # Atlas 200I DK A2 芯片;用 npu-smi info 确认
INPUT_NAME="images"                # 必须与 verify_onnx.py 打印的输入名一致
INPUT_SHAPE="1,3,640,640"          # NCHW;必须与训练输入分辨率一致
OUTPUT_DIR="om"
AIPP_CFG=""                        # 可选: 留空 = 预处理全在 CPU 侧做(最简单)
# PRECISION 可选: force_fp16(ATC默认) / allow_fp32_to_fp16(推荐,精度更稳) / must_keep_origin_dtype
PRECISION="allow_fp32_to_fp16"

# ---------- 2. 转换 ----------
mkdir -p "$OUTPUT_DIR"
echo "==> 转换 $ONNX_FILE -> $OUTPUT_DIR/$MODEL_NAME.om (soc=$SOC_VERSION)"

atc --model="$ONNX_FILE" \
    --framework=5 \
    --output="$OUTPUT_DIR/$MODEL_NAME" \
    --soc_version="$SOC_VERSION" \
    --input_shape="$INPUT_NAME:$INPUT_SHAPE" \
    --precision_mode="$PRECISION" \
    $( [ -n "$AIPP_CFG" ] && echo "--insert_op_conf=$AIPP_CFG" ) \
    --log=info

echo ""
echo "==> 转换完成,产物:"
ls -lh "$OUTPUT_DIR/$MODEL_NAME.om"

echo ""
echo "==> 后续步骤:"
echo "  1. 运行最小推理 demo(下一步编写 detect_service 后):
       python detect_service/demo_detect.py --model om/$MODEL_NAME.om --image 测试图.jpg"
echo "  2. 与 PyTorch 输出对拍,误差应在合理范围(第一道『转换不掉点』验证)"
echo "  3. 把转换命令快照填入 docs/model_release_record.md"
echo ""
echo "==> 转换失败排查顺序:"
echo "  1. 看 atc 报错行,常见: 算子不支持 / shape 不匹配 / soc 版本错"
echo "  2. 算子不支持 -> 让杨泽改导出方式(去掉 NMS/后处理),或 onnx-simplifier 简化"
echo "  3. shape 不匹配 -> 核对 verify_onnx.py 打印的输入名与 INPUT_NAME 是否一致"
echo "  4. soc 版本错 -> 在板子上执行 npu-smi info 查看真实芯片型号"
