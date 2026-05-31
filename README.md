# FTP Upload - 工业设备数据采集与上传系统

从 Modbus TCP 和西门子 S7 PLC 设备采集数据，存储为 txt 文件，并通过 FTP 上传到远程服务器。

## 功能

- **Modbus TCP 采集** — pymodbus 异步客户端，支持多种数据类型（UINT16/INT16/UINT32/INT32/FLOAT32/FLOAT64/BOOL）
- **S7 PLC 采集** — python-snap7，支持 DB/I/Q/M 区域读写
- **定时采集** — APScheduler 调度，按设备配置间隔自动采集
- **FTP 上传** — aioftp 异步上传，支持手动/自动上传
- **Web 管理界面** — Bootstrap 5 中文界面，设备管理、采集计划、FTP 配置、日志查看
- **设备管理** — 支持添加、编辑、删除、测试设备
- **系统信息** — 实时显示系统资源、网络状态、进程信息

## 快速开始

```bash
# 安装依赖
uv sync

# 启动服务
uv run python main.py
```

浏览器访问 `http://localhost:8000`

## 页面说明

- **首页** - 系统概览和快速操作
- **设备管理** - 添加/编辑 Modbus TCP 或 S7 设备，配置寄存器/数据区域
- **采集计划** - 管理定时采集任务
- **FTP 配置** - 配置 FTP 服务器和上传策略
- **日志查看** - 查看系统运行日志
- **系统信息** - 查看系统资源、网络状态、进程信息

## 项目结构

```
app/
├── models.py              # 数据模型
├── config.py              # 配置管理
├── server.py              # FastAPI 应用
├── scheduler.py           # 定时采集调度
├── ftp_uploader.py        # FTP 上传
├── collectors/
│   ├── base.py            # 采集器基类
│   ├── modbus_collector.py
│   └── s7_collector.py
└── web/
    ├── api.py             # REST API
    ├── routes.py          # 页面路由
    ├── templates/         # HTML 模板
    └── static/            # 静态资源
```

## 设备配置说明

### Modbus TCP
- 主机地址：PLC 的 IP 地址
- 端口：默认 502
- 从站 ID：1-247
- 寄存器：支持配置多个寄存器，填写地址、数据类型、比例、单位

### Siemens S7
- 主机地址：PLC 的 IP 地址
- 端口：默认 102
- Rack/Slot：根据 PLC 配置（通常 Rack=0, Slot=1）
- 数据区域：支持 DB/I/Q/M 区域，配置 DB 号、起始地址、大小、数据类型