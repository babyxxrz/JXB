# -*- coding: utf-8 -*-
"""
verify_onnx.py — ONNX 合法性检查(转换 ATC 之前必跑)

用途:
  1. 校验杨泽交付的 ONNX 结构合法(onnx.checker)
  2. 打印输入/输出张量的名称与形状 —— convert_to_om.sh 里
     INPUT_NAME / INPUT_SHAPE 必须与这里打印的完全一致
  3. 打印算子清单 —— 提前发现 ATC 不支持的算子(如 NMS)

用法(在开发机或板子上均可):
  python verify_onnx.py <onnx路径>

依赖: pip install onnx
"""

import sys

import onnx


def main(onnx_path: str) -> None:
    print(f"检查文件: {onnx_path}\n")

    model = onnx.load(onnx_path)
    onnx.checker.check_model(model)
    print(f"[OK] onnx.checker 通过,opset = {model.opset_import[0].version}\n")

    print("=== 输入 ===")
    for inp in model.graph.input:
        shape = [
            (d.dim_value if d.dim_value else f"dyn({d.dim_param})")
            for d in inp.type.tensor_type.shape.dim
        ]
        print(f"  name={inp.name:16s} shape={shape}")

    print("=== 输出 ===")
    for out in model.graph.output:
        shape = [
            (d.dim_value if d.dim_value else f"dyn({d.dim_param})")
            for d in out.type.tensor_type.shape.dim
        ]
        print(f"  name={out.name:16s} shape={shape}")

    ops = sorted({node.op_type for node in model.graph.node})
    print(f"\n=== 算子清单({len(ops)} 种)===")
    print("  " + ", ".join(ops))

    # 常见坑提示
    risky = {"NonMaxSuppression", "NMS", "Einsum", "Resize"}
    found = risky & set(ops)
    if found:
        print(f"\n[警告] 含 ATC 高风险算子: {found}")
        print("  NMS/Resize 类算子常导致 ATC 转换失败。")
        print("  → 检测模型应导出【不含 NMS】的 ONNX(后处理放端侧 CPU/ACL)。")
        print("  → Resize 若失败,可尝试 onnx-simplifier 简化后再转。")
    else:
        print("\n[OK] 未发现 NMS 等高风险算子")

    print("\n下一步: 核对输入 shape 后,改 convert_to_om.sh 顶部的参数,在板子上执行转换。")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
