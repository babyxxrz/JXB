# 已用环境与依赖边界

实测Notebook使用开发板 /root/miniconda3/bin/python（Python 3.9）；本交付未取得完整pip freeze和板端CANN版本，不提供未经验证的一键升级requirements。
需要课程已有环境：ais_bench、aclruntime、torch、torchvision、opencv-python、numpy、PyYAML、pycocotools、tqdm、IPython/Jupyter。
Notebook页面兼容问题通过将Pygments 2.3.1更新至2.15.1修复；notebook 6.5.2、nbconvert 7.2.5、jupyterlab-pygments 0.2.2来自当时pip show截图。
不要直接用PC pip安装的torch替换开发板配套版本。Pygments离线wheel不是模型交付必需附件。

最终冻结环境前，在实际可运行的开发板终端执行 `python -m pip freeze > requirements-board-observed.txt`，并记录Python、CANN/驱动版本后归档。
本版本InferSession的finalize会结束底层全局环境。Notebook复用会话，不逐轮finalize；完成工作后关闭内核。
