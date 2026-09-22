# 补丁应用方式（中文说明）

这里的 `reference-*.patch` 是从核对时的 iStoreOS 文件到交付 overlay 的可读差异，不需要再次执行 `patch`。包含中文用途说明，不是 ImmortalWrt 内核补丁队列。

实际移植由 `scripts/manage.py adapt` 自动完成：

1. 检查当前源码确实提供 `Build/pine64-img`、`Build/boot-script`、`BuildImage` 和 RK3568 U-Boot 基类。
2. 在构建调用前插入独立设备包含文件与 U-Boot 定义，避免依赖固定行号。
3. 复制经过核对的 overlay。已经存在且内容相同的文件允许重复执行；不同内容一律报错，防止覆盖未来官方支持。
4. 把本次生成的构建接口差异保存为 `build-logs/generated-adaptation.patch`，便于审核。
5. 执行 `make defconfig` 并审计，再由正常的内核/U-Boot 编译验证设备树和镜像。

这是对已知接口变化的检查与适配机制，不是能够自动推理任意未来内核 API 的程序。未来 master 改变接口、DT bindings、内核驱动或包依赖时，失败日志必须用于更新移植，不能通过模糊打补丁、删除配置、关闭校验和来冒充兼容。
