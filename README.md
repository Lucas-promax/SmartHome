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

运行所需的 YOLO `.pt` 和 `buffalo_l/*.onnx` 模型通过 Git LFS 纳入版本控制。安装 Git LFS 后，在克隆或拉取项目时执行以下命令，获取完整权重：

```powershell
git lfs install
git lfs pull
```

在项目根目录执行以下命令，准备 Python 虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd --prefix frontend install
.\start.ps1
```

启动后访问前端 `http://127.0.0.1:3001`，后端 API 文档位于 `http://127.0.0.1:8000/docs`。也可运行 `start.cmd` 启动服务。

硬件连接和智能助手参数可在界面中配置；视觉识别模型位于 `backend/models/`。旧权重、训练中间产物、本地数据库和运行数据不纳入版本控制。

## OrangePi AIpro 部署

前端静态资源与 FastAPI 后端均运行在板子上，由 `backend/deploy_app.py` 提供服务；PC 只需 SSH 和浏览器。部署前端时以 `VITE_API_BASE_URL=/api` 构建，再将 `frontend/dist/` 连同后端上传到板子。板子无需运行 Node.js。

当前部署位置为 `/home/HwHiAiUser/SmartHome/deploy/current`，Python 环境复用 `/home/HwHiAiUser/SmartHome/conda_envs/backend`。ARM 依赖见 `backend/requirements-orangepi.txt`，启动脚本为 `deploy/orangepi/run.sh`；通过 CANN 环境和 `SMARTHOME_VISION_BACKEND=om` 使用板上已有的 Ascend `.om` 模型，人脸识别使用 ONNX Runtime。

自定义 YOLO 模型以当前 `backend/models/best.pt` 为源，导出固定输入 `1×3×640×640` 的 ONNX，再用 ATC 为 `Ascend310B4` 编译为 `best.om`。更新 `.pt` 后必须重新转换 `.om`；板上 `deployment-manifest.json` 记录本次部署的模型来源和 SHA-256。人脸识别目前使用 ONNX Runtime 的 CPU 执行器。

服务只监听板子的 `127.0.0.1:8000`，在 PC 上执行：

```powershell
ssh -N -L 3001:127.0.0.1:8000 orangepi
```

保持 SSH 连接后，浏览器打开 `http://localhost:3001`；API 文档为 `http://localhost:3001/docs`。关闭 SSH 只会断开显示连接，板上服务继续运行。

也可在 PC 上运行带连接保活和断线重连的脚本（Ctrl+C 退出）：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\orangepi\connect.ps1
```

两块 Arduino 都连接到板子：家居主控使用独立串口（9600 波特率），外置 OV7670 摄像头经另一块 Arduino 使用第二个串口。在硬件设置中选择主控串口，在 AI 识别页选择 OV7670 及其串口和匹配固件的波特率，两者不能使用同一串口。使用这一路摄像头时不依赖 PC 摄像头。

插在香橙派上的 USB 摄像头由后端通过 V4L2/OpenCV 采集，网页设备列表显示为“板端 USB”，默认优先选择板端摄像头。点击“开启摄像头”后即可预览、拍照并用于 AI 识别，无需电脑浏览器的摄像头权限。“本机”选项仍使用打开网页的电脑摄像头；OV7670 继续使用独立串口。各板端摄像头共用一个采集会话，切换或关闭时会释放原设备。

开机自启模板为 `deploy/orangepi/smarthome@.service`，服务以普通用户运行并附加 `dialout` 串口权限和 `video` 摄像头权限。已有部署更新模板后需执行 `sudo systemctl daemon-reload` 并重启服务，使新权限生效：

```bash
sudo systemctl status smarthome@HwHiAiUser
sudo systemctl restart smarthome@HwHiAiUser
journalctl -u smarthome@HwHiAiUser -n 100 --no-pager
```
