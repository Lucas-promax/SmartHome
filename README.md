# SmartHome 智能家居控制台

SmartHome 是一个前后端分离的智能家居管理项目，提供设备控制、环境状态监测、摄像头预览、AI 视觉识别和智能助手等功能，支持通过串口连接 Arduino 家居主控板及独立的 OV7670 摄像头板。

## 主要功能

- 查看家居状态，控制灯光、风扇、主门和车库门。
- 支持 USB 摄像头及 OV7670 摄像头，提供目标检测和人脸识别功能。
- 管理人员信息与人脸门禁授权，查看数据分析、系统日志和告警设置。
- 通过兼容 OpenAI 接口的智能助手查询系统状态并调用设备控制等工具。

## 技术与目录

- `frontend/`：Vue 3、Vite、Element Plus 和 ECharts 构建的管理界面。
- `backend/`：Python FastAPI 后端，使用 SQLite 存储数据，集成 OpenCV、YOLO、InsightFace 和串口通信。
- `start.ps1` / `start.cmd`：Windows 下的前后端启动入口。

## Windows 启动

在项目根目录执行以下命令，准备 Python 虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd --prefix frontend install
.\start.ps1
```

启动后访问前端 `http://127.0.0.1:3001`，后端 API 文档位于 `http://127.0.0.1:8000/docs`。也可运行 `start.cmd` 启动服务。

硬件连接和智能助手参数可在界面中配置；视觉识别所需模型需另外放置于 `backend/models/`。本地数据库、模型和运行数据不纳入版本控制。
