# ADR-0003: 采集启用复用现有管线

## 状态

已采纳

## 背景

用户可以在上传配置中勾选「采集启用」，让寄存器纳入周期采集。需要决定如何实现这个机制。

## 决策

当 `collect_enabled=True` 时，自动将该寄存器同步到对应 PLC 设备的 `DeviceConfig.registers` 中，复用现有的 `DataPipeline` 采集管线。

## 理由

1. **复用现有逻辑**：不需要单独的采集管线，减少代码重复
2. **自动生效**：同步到 DeviceConfig 后，现有的调度器自动开始采集
3. **隔离清晰**：`collect_enabled` 控制采集，`report_enabled` 控制报文生成，互不干扰

## 后果

- 保存上传配置时需要同步更新 `config.json` 中的 DeviceConfig
- 取消采集启用时需要从 DeviceConfig 中移除对应寄存器
- 需要处理寄存器地址冲突（同一设备下不能有重复地址）
