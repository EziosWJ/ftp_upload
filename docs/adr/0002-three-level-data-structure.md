# ADR-0002: 三层数据结构（系统→设备→寄存器）

## 状态

已采纳

## 背景

六大监控系统下的动态数据需要配置寄存器测点。需要决定寄存器挂在哪个层级。

## 决策

采用三层结构：系统 → 设备（DeviceWithRegisters）→ 寄存器（RegisterPoint）。

每个设备通过 `plc_device` 字段关联到一个 PLC 连接设备（DeviceConfig）。

## 理由

1. **符合实际**：一个系统下有多台设备，每台设备有自己的 PLC 和寄存器
2. **灵活连接**：同一系统下不同设备可连接不同 PLC
3. **报文聚合**：生成报文时按系统聚合所有设备的寄存器数据

## 后果

- `UploadConfig.system_devices` 使用 `dict[str, list[DeviceWithRegisters]]` 结构
- 寄存器的 `system_code` 从父级隐含，不需要在 RegisterPoint 中重复存储
