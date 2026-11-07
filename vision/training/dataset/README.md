# 数据集

配套附件 blocks_dataset_v001.zip 包含原始JPG/JSON、YOLO train/valid/test、测试COCO JSON。
解压后在 blocks_dataset_v001 内运行 `python configure_dataset.py`，生成基于实际解压位置的 data.local.yaml，供配套训练/评估工具读取。
prepared/data.yaml 是未经改写的历史配置，含旧Windows绝对路径，不直接使用；训练 opt.yaml 同样仅作历史记录。

split_manifest.csv 逐张记录集合、图片/标签SHA256、按字节哈希匹配的原始文件名。批次字段为空表示未知，不能自行将集合名当作采集批次。
精确哈希未匹配时不推测编号对应关系；summary.json 给出真实统计。
此数据版本固定为206张，未自动重新划分，避免改变已报告成绩的评估基础。
