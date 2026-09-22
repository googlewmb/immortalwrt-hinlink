# BBRv3 来源与验证

- 补丁来源：https://github.com/sbwml/kernel-latest-centos/blob/0dd961c204a3063010a4a2935a457cc5b34a25e5/src/0001-backport-tcp_bbr3.patch
- 固定提交：`0dd961c204a3063010a4a2935a457cc5b34a25e5`
- 交付补丁 SHA256：`4894ae7d5e0800a7540209d5bef7313ced9aaf83e64cbc389336f52b4dcdb05f`（加入中文头注释，其余内容原样保留）
- 算法上游：https://github.com/google/bbr/tree/v3
- 已在 Linux v6.18.52 原始源码涉及的 17 个文件上通过 `git apply --check`。
- 适配器仅允许 Rockchip 6.18 系列；实际 ImmortalWrt 补丁队列由 `make target/linux/prepare` 验证，失败必须停止。
- prepare 后检查 `BBR_VERSION 3`、模块版本声明和 `bbr` 注册名，禁止用 BBRv1 冒充 BBRv3。
- 包名仍是 `kmod-tcp-bbr`，sysctl 名仍是 `bbr`，不是 `bbr3`。
- 此时尚未完成全内核编译和实机测试。BBR作用于本机发出的TCP连接，不会直接改变纯转发的客户端TCP拥塞控制算法。
