# FTP Upload - 工业设备数据采集与上传系统

从 Modbus TCP 和西门子 S7 PLC 设备采集数据，存储为 txt 文件，并通过 FTP 上传到远程服务器。

## 功能

- **Modbus TCP 采集** — pymodbus 异步客户端，支持多种数据类型
- **S7 PLC 采集** — python-snap7，支持 DB/I/Q/M 区域读写
- **定时采集** — APScheduler 调度，按设备配置间隔自动采集
- **FTP 上传** — aioftp 异步上传，支持手动/自动上传
- **Web 管理界面** — Bootstrap 5 中文界面，设备管理、采集计划、FTP 配置、日志查看

## 快速开始

```bash
# 安装依赖
uv sync

# 启动服务
uv run python main.py
```

浏览器访问 `http://localhost:8000`

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