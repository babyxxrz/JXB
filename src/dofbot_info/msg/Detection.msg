# 单个积木检测结果（detect 接口 detections 数组元素, 见技术设计文档 7.2）
string detection_id     # 检测目标唯一标识
string color            # 类别 red / yellow / blue / green
float32 confidence      # 置信度, 范围 0-1
float32 center_u_px     # 图像中心坐标 u, px（图像原点左上角, u 向右, v 向下）
float32 center_v_px     # 图像中心坐标 v, px
bool fallback           # true = 该结果来自 HSV 颜色分割兜底通道(4.5), 对应 mode=fallback
