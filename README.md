# 🎬 Pixelle-Video

## 📌 简介

Pixelle-Video 是一套 **AI 短视频生成** 工程：从主题或固定文案出发，串联大语言模型写稿、配图/视频、语音合成与成片合成，通过 **Streamlit Web** 或 **HTTP API** 使用。底层媒体能力大量通过 **ComfyUI 工作流**（本地或 RunningHub 等）扩展。

---

## ✨ 功能特点

- 🎞️ **端到端出片**：主题模式或固定文案模式，自动分镜、逐帧生成、拼接并可选 BGM。
- 🔀 **可替换流水线**：标准 / 自定义 / 基于素材等 Pipeline，可在核心层注册扩展。
- 🎨 **多模态服务**：LLM 文案；ComfyKit 驱动的 TTS、图像、视频类工作流；HTML 模板渲染帧画面。
- 🌐 **Web + API 双入口**：日常调参用 Web；自动化、对接其他系统用 FastAPI。
- 📦 **任务与文件**：异步生成任务查询、输出文件通过 API 静态访问路径下载。

---

## 🛠️ 技术栈


| 类别             | 技术                                                                |
| -------------- | ----------------------------------------------------------------- |
| 🐍 语言与运行时      | Python **3.11+**（见 `pyproject.toml`）                              |
| 📦 包管理         | **uv**（推荐）                                                        |
| 🖥️ Web UI     | **Streamlit**                                                     |
| ⚡ HTTP API     | **FastAPI** + **Uvicorn**                                         |
| ⚙️ 配置与模型       | **PyYAML**、**Pydantic**                                           |
| 🤖 LLM         | **OpenAI 兼容 SDK**（`openai`），支持多种兼容端点                              |
| 🎛️ ComfyUI 集成 | **ComfyKit**                                                      |
| 🎵 视频/音频处理     | **MoviePy**、**ffmpeg-python**、系统 **ffmpeg**                       |
| 🖼️ 页面渲染       | **Playwright**（Chromium 渲染 HTML 模板帧）                              |
| 🔧 其他          | **httpx**、**Pillow**、**edge-tts**、**loguru**、**beautifulsoup4** 等 |


> 💡 **说明**：`pyproject.toml` 中声明了 **fastmcp**，用于与 MCP 相关生态配合；业务主路径为上述 Web / API / ComfyKit。

---

## 📁 项目结构（注释为作用说明）

```
Pixelle-Video-main/
├── api/                      # FastAPI 应用：路由、Schema、任务队列、依赖注入
│   └── routers/              # 按领域拆分：health、llm、tts、image、content、video、tasks、files、resources、frame
├── pixelle_video/            # 核心库：配置、服务、流水线、提示词、工具函数
│   ├── config/               # 配置加载与 schema
│   ├── services/             # LLM、TTS、媒体、视频、帧处理、持久化、历史等
│   ├── pipelines/            # 标准/自定义/素材等视频生成流水线
│   ├── models/               # 分镜、进度等数据结构
│   ├── prompts/              # 各类 LLM 提示模板
│   ├── postprocess/          # 成片后处理（如数字人相关）
│   └── utils/                # 文案生成、模板、工作流等辅助逻辑
├── web/                      # Streamlit 前端
│   ├── app.py                # 多页面导航入口
│   ├── pages/                # 各页面（首页、历史等）
│   ├── components/           # 侧边栏区块：配置、内容输入、风格、输出预览等
│   ├── pipelines/            # Web 层封装的扩展流水线（图生视频、数字人、动作迁移等）
│   ├── state/                # Session 状态
│   └── i18n/                 # 国际化资源
├── workflows/                # ComfyUI 工作流 JSON（TTS、生图、生视频等）
├── templates/                # HTML 视频帧模板（static_ / image_ / video_ 等前缀）
├── bgm/                      # 背景音乐素材目录
├── output/                   # 默认成片与中间产物输出目录
├── data/                     # 运行期数据目录（视功能使用）
├── temp/                     # 临时文件
├── resources/                # 文档用静态资源、内置素材等
├── packaging/windows/        # Windows 整合包构建脚本与配置
├── docs/                     # MkDocs 文档（中英文）
├── pyproject.toml            # 项目元数据与 Python 依赖
├── config.yaml               # 运行时主配置（与代码中默认路径一致时需存在）
└── LICENSE                   # Apache-2.0
```

---

## 🚀 快速开始（Windows）

### 🪟 环境准备

1. 安装 **Python 3.11+**、**uv**、**ffmpeg**（`ffmpeg` 已加入 `PATH`）。
2. 在项目根目录执行依赖安装并启动（PowerShell 示例）：

```powershell
cd f:\Pixelle-Video-main
uv sync
uv run streamlit run web\app.py
```

1. 浏览器访问 **[http://localhost:8501](http://localhost:8501)** ，在「系统配置」中填写 LLM 与 ComfyUI / RunningHub 等，保存后再生成。

### 🔌 启动 HTTP API

```powershell
cd f:\Pixelle-Video-main
uv run python api\app.py --host 0.0.0.0 --port 8000
```

或使用：

```powershell
uv run uvicorn api.app:app --host 0.0.0.0 --port 8000
```

默认 **Swagger**：`http://localhost:8000/docs`，**ReDoc**：`http://localhost:8000/redoc`。

### 🎭 Playwright（首次渲染 HTML 帧时）

若使用依赖 Chromium 的帧渲染，需安装浏览器内核：

```powershell
uv run playwright install --with-deps chromium
```

---

## 📖 使用指南

1. ⚙️ **配置**：在 Web「系统配置」中设置 LLM（API Key、Base URL、模型名）与图像侧（本地 ComfyUI 地址或云端 Key）；与文件 `config.yaml` 保持理解一致（详见 `docs/zh/getting-started/configuration.md`）。
2. 🔄 **工作流**：在 `workflows/` 放置或选择已有 JSON；TTS / 媒体工作流名称需与界面下拉选项对应。
3. 📄 **模板**：在 `templates/` 选择 `static_*` / `image_*` / `video_*` 等 HTML 模板，分辨率与竖横屏需与输出设定匹配。
4. 🎵 **BGM**：内置或把音频放入 `bgm/` 后在界面选择。
5. 📚 **历史**：使用 Web 的 History 页面查看任务历史（若已启用持久化）。

更细步骤见：`docs/zh/getting-started/quick-start.md`、`docs/zh/user-guide/web-ui.md`。

---

## ⚙️ 核心实现

- 🧠 `**PixelleVideoCore`**（`pixelle_video/service.py`）：应用入口单例式核心，负责 `initialize()`、挂载 **LLMService**、**TTSService**、**MediaService**、**VideoService**、**FrameProcessor**、**PersistenceService**、**HistoryManager** 等，并维护 **ComfyKit** 实例与配置哈希刷新。
- 🔁 **流水线**：以 `**LinearVideoPipeline`** 为骨架（`pixelle_video/pipelines/linear.py`），`**StandardPipeline**`（`standard.py`）实现「标题 → 分镜文案 → 配图提示 → 逐帧 TTS/出图/HTML 合成片段 → 拼接 → 可选 BGM」的完整线性流程；另有 **custom**、**asset_based** 等扩展。
- ✍️ **内容生成**：`pixelle_video/utils/content_generators.py` 等与 `prompts/` 下模板配合，完成标题、口播稿、拆句、生图提示等 LLM 结构化输出。
- 🎬 **帧与成片**：`FrameHtmlService`（`frame_html.py`）使用 **Playwright** 将模板 HTML 渲染为图像序列或中间产物；**VideoService** 与 **MoviePy/ffmpeg** 负责时间轴、拼接与混音。
- 🖥️ **Web 层**：`web/app.py` 聚合页面；各 `web/pipelines/*.py` 将扩展场景接到同一套配置与进度 UI。

架构总览还可参考：`docs/zh/development/architecture.md`。

---

## 🔌 工具调用（对外能力如何落地）


| 能力                     | 调用方式                                                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 🤖 **大语言模型**           | `LLMService` 通过 **OpenAI 兼容 HTTP API** 调用（`AsyncOpenAI`），用于文案、标题、分镜提示等。                                                              |
| 🗣️ **TTS / 生图 / 生视频** | `ComfyBaseService` 子类经 **ComfyKit** 向 **ComfyUI**（或配置的 RunningHub 等远端）提交 **工作流 JSON**，由工作流内节点完成推理。                                   |
| 🖼️ **HTML 模板 → 位图**   | **Playwright** 无头 Chromium 加载 `templates/` 下 HTML，用于单帧画面导出。                                                                          |
| 🎞️ **视频编码与拼接**        | **MoviePy**、**ffmpeg-python** 及系统 **ffmpeg** 可执行文件。                                                                                  |
| 🌍 **REST 消费方**        | 任意 HTTP 客户端调用 `/api/*` 路由；Python 侧也可 `from pixelle_video import pixelle_video` 在异步上下文中直接调用核心方法（见 `pixelle_video/__init__.py` 文档字符串）。 |


---

## 📡 API 文档

- 📖 **交互式文档**：服务启动后访问 `**/docs`**（Swagger UI）或 `**/redoc**`（ReDoc）；OpenAPI JSON 默认 `**/openapi.json**`（可在 `api/config.py` 的 `APIConfig` 中调整）。
- 🏠 **根信息**：`GET /` 返回服务名、版本及各模块路径前缀摘要。
- 💚 **健康检查**：`GET /health`、`GET /version`（见 `api/routers/health.py`）。

### 📋 主要路由一览（前缀均为 `/api`，除非注明）


| 方法     | 路径                           | 说明                      |
| ------ | ---------------------------- | ----------------------- |
| POST   | `/llm/chat`                  | 💬 LLM 对话               |
| POST   | `/tts/synthesize`            | 🗣️ TTS 合成              |
| POST   | `/image/generate`            | 🖼️ 图像生成                |
| POST   | `/content/narration`         | 📝 口播/叙事内容生成            |
| POST   | `/content/image-prompt`      | ✨ 生图提示词生成               |
| POST   | `/content/title`             | 📌 标题生成                 |
| POST   | `/video/generate/sync`       | ⚡ 同步整片生成（适合较短任务）        |
| POST   | `/video/generate/async`      | ⏳ 异步整片生成，返回 `task_id`   |
| GET    | `/tasks`                     | 📋 任务列表                 |
| GET    | `/tasks/{task_id}`           | 🔍 任务状态与结果              |
| DELETE | `/tasks/{task_id}`           | 🗑️ 删除任务记录              |
| GET    | `/files/{file_path:path}`    | 📁 读取 `output` 下成品等静态文件 |
| GET    | `/resources/workflows/tts`   | 🎤 列出 TTS 工作流           |
| GET    | `/resources/workflows/media` | 🎬 列出媒体类工作流             |
| GET    | `/resources/workflows/image` | 🖼️ 列出图像工作流             |
| GET    | `/resources/templates`       | 📄 列出视频模板               |
| GET    | `/resources/bgm`             | 🎵 列出 BGM               |
| POST   | `/frame/render`              | 🖥️ 渲染单帧                |
| GET    | `/frame/template/params`     | 🎛️ 查询模板可调参数            |


中文说明与请求体示例见：`**docs/zh/reference/api-overview.md`**、`**docs/zh/user-guide/api.md**`。
