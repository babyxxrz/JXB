# -*- coding: utf-8 -*-
"""
acl_engine.py — PyACL 推理引擎封装(仅在 Atlas 200I DK A2 上可用)

职责: 加载 .om 模型,提供 infer([np.ndarray]) -> list[np.ndarray]。
      开发者机(Windows)上 import acl 会失败,属正常现象——
      本地单测请用 tests/ 里的 FakeEngine。

注意: PyACL 各函数名随 CANN 版本略有出入,若个别函数报 AttributeError,
      对照板子上 /usr/local/Ascend 下的官方 sample 微调即可。
"""

import numpy as np

try:
    import acl
    _HAS_ACL = True
except ImportError:
    acl = None
    _HAS_ACL = False


class AclEngine:
    def __init__(self, model_path: str, device_id: int = 0):
        if not _HAS_ACL:
            raise RuntimeError(
                "未找到 PyACL(import acl 失败)。本类只能在 Atlas 200I DK A2 上使用;"
                "开发机请用 FakeEngine 单测(见 tests/)。")
        self.model_path = model_path
        self.device_id = device_id
        self.model_id = None
        self.model_desc = None
        self.context = None
        self.stream = None
        self._init_acl()
        self._load_model()
        print(f"[AclEngine] 已加载模型: {model_path}")

    # -----------------------------------------------------------
    # 初始化与加载
    # -----------------------------------------------------------
    def _init_acl(self):
        self._check(acl.init(), "acl.init")
        self._check(acl.rt.set_device(self.device_id), "acl.rt.set_device")
        self.context, ret = acl.rt.create_context(self.device_id)
        self._check(ret, "acl.rt.create_context")
        self.stream, ret = acl.rt.create_stream()
        self._check(ret, "acl.rt.create_stream")

    def _load_model(self):
        self.model_id, ret = acl.mdl.load_from_file(self.model_path)
        self._check(ret, "acl.mdl.load_from_file")
        self.model_desc = acl.mdl.create_desc()
        self._check(acl.mdl.get_desc(self.model_desc, self.model_id), "acl.mdl.get_desc")

    @staticmethod
    def _check(ret, step: str):
        if ret != 0:
            raise RuntimeError(f"{step} 失败,返回码 {ret}(0x{ret & 0xFFFFFFFF:08x})")

    # -----------------------------------------------------------
    # 推理主入口
    # -----------------------------------------------------------
    def infer(self, inputs):
        """
        inputs: list[np.ndarray] 或单个 np.ndarray,float32 连续内存,
                形状与模型输入一致(预处理见 processing.preprocess)。
        返回:   list[np.ndarray],按模型输出顺序。
        """
        if not isinstance(inputs, (list, tuple)):
            inputs = [inputs]

        input_dataset = output_dataset = None
        in_bufs = []    # (data_buffer, 设备内存) 用于统一释放
        out_bufs = []
        try:
            input_dataset, ret = acl.mdl.create_dataset()
            self._check(ret, "acl.mdl.create_dataset(in)")
            output_dataset, ret = acl.mdl.create_dataset()
            self._check(ret, "acl.mdl.create_dataset(out)")

            # ---- 输入搬运: host numpy -> device ----
            for arr in inputs:
                arr = np.ascontiguousarray(arr, dtype=np.float32)
                nbytes = arr.nbytes
                data_buf, dev_buf = self._copy_in(arr, nbytes)
                in_bufs.append((data_buf, dev_buf))
                ret = acl.mdl.add_dataset_buffer(input_dataset, data_buf)
                self._check(ret, "acl.mdl.add_dataset_buffer(in)")

            # ---- 输出缓冲: 按模型输出数量与字节大小分配 ----
            out_info = []  # (dev_buf, size, dims)
            num_out = acl.mdl.get_num_outputs(self.model_desc)
            for i in range(num_out):
                size = acl.mdl.get_output_size(self.model_desc, i)
                dev_buf, ret = acl.rt.malloc(size, acl.ACL_MEM_MALLOC_NORMAL_ONLY)
                self._check(ret, f"acl.rt.malloc(out{i})")
                data_buf, ret = acl.mdl.create_data_buffer(dev_buf, size)
                self._check(ret, f"acl.mdl.create_data_buffer(out{i})")
                ret = acl.mdl.add_dataset_buffer(output_dataset, data_buf)
                self._check(ret, f"acl.mdl.add_dataset_buffer(out{i})")
                dims = acl.mdl.get_output_dims(self.model_desc, i)["dims"]
                out_bufs.append((data_buf, dev_buf))
                out_info.append((dev_buf, size, dims))

            # ---- 执行 ----
            self._check(acl.mdl.execute(self.model_id, input_dataset,
                                        output_dataset, self.stream),
                        "acl.mdl.execute")
            self._check(acl.rt.synchronize_stream(self.stream),
                        "acl.rt.synchronize_stream")

            # ---- 输出搬运: device -> host numpy ----
            outputs = []
            for dev_buf, size, dims in out_info:
                host = np.zeros(size, dtype=np.uint8)
                host_ptr = acl.util.numpy_to_ptr(host)
                ret = acl.rt.memcpy(host_ptr, size, dev_buf, size,
                                    acl.ACL_MEMCPY_DEVICE_TO_HOST)
                self._check(ret, "acl.rt.memcpy(D2H)")
                arr = host.view(np.float32).reshape(dims)
                outputs.append(arr.copy())
            return outputs

        finally:
            for data_buf, dev_buf in in_bufs + out_bufs:
                self._try_free(dev_buf)
                self._try_destroy_buffer(data_buf)
            if input_dataset is not None:
                self._try_destroy_dataset(input_dataset)
            if output_dataset is not None:
                self._try_destroy_dataset(output_dataset)

    def _copy_in(self, arr, nbytes):
        ptr = acl.util.numpy_to_ptr(arr)
        dev_buf, ret = acl.rt.malloc(nbytes, acl.ACL_MEM_MALLOC_NORMAL_ONLY)
        self._check(ret, "acl.rt.malloc(in)")
        ret = acl.rt.memcpy(dev_buf, nbytes, ptr, nbytes,
                            acl.ACL_MEMCPY_HOST_TO_DEVICE)
        self._check(ret, "acl.rt.memcpy(H2D)")
        data_buf, ret = acl.mdl.create_data_buffer(dev_buf, nbytes)
        self._check(ret, "acl.mdl.create_data_buffer(in)")
        return data_buf, dev_buf

    # -----------------------------------------------------------
    # 资源释放(容错: 释放失败不影响推理流程)
    # -----------------------------------------------------------
    @staticmethod
    def _try_free(dev_buf):
        try:
            acl.rt.free(dev_buf)
        except Exception:
            pass

    @staticmethod
    def _try_destroy_buffer(data_buf):
        try:
            acl.mdl.destroy_data_buffer(data_buf)
        except Exception:
            pass

    @staticmethod
    def _try_destroy_dataset(dataset):
        try:
            acl.mdl.destroy_dataset(dataset)
        except Exception:
            pass

    def destroy(self):
        for name, fn in (
            ("acl.rt.destroy_stream", lambda: acl.rt.destroy_stream(self.stream)),
            ("acl.mdl.unload", lambda: acl.mdl.unload(self.model_id)),
            ("acl.mdl.destroy_desc", lambda: acl.mdl.destroy_desc(self.model_desc)),
            ("acl.rt.destroy_context", lambda: acl.rt.destroy_context(self.context)),
            ("acl.rt.reset_device", lambda: acl.rt.reset_device(self.device_id)),
            ("acl.finalize", lambda: acl.finalize()),
        ):
            try:
                fn()
            except Exception:
                pass

    def __del__(self):
        if _HAS_ACL and self.model_id is not None:
            self.destroy()
