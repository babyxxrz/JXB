# 一帧检测结果（张鹏源发布, 朱玉贺的分拣闭环订阅; 见技术设计文档 7.2）
string frame_id          # 帧唯一标识（任务完成后必须重新检测, 禁止复用旧帧）
int64 captured_at_ms     # Unix 时间戳, ms（图像超过 1s 未用于生成任务则重新采集）
int32 image_width_px     # 图像宽, px
int32 image_height_px    # 图像高, px
Detection[] detections   # 目标数组; 无目标返回空数组
