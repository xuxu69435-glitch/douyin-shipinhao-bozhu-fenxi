# 接入模型 API 与真实测试


## 使用 ChatGPT 套餐（0.1.2 起）

在 **模型与采集设置 → 模型接入方式** 选择 **使用 ChatGPT 套餐（官方授权登录）**，点击 **使用 ChatGPT 登录**。在系统浏览器完成登录，核对应用名称 Douyin Analyst，并授权使用套餐用量。返回桌面后选择账户返回的可用模型，点击 **保存并测试所选模型**。

此方式无需填写 OPENAI_API_KEY；使用授权账户的套餐额度，额度与模型可用性以官方页面及账户实际返回为准。**管理套餐用量** 打开官方设置。它不是把周额度兑换成可转让 API Key，也不会在失败时改用已有 API 密钥。

登录凭据存于应用数据目录的 `chatgpt` 子目录，使用 Windows DPAPI 保护。不要复制或提交该目录。只有收到完整模型响应、通过结构和证据校验才算测试通过。尚未登录不等于套餐不可用。

套餐通道目前不支持输出 token 上限参数；本程序限制请求次数、输入、接收文本长度和超时，不承诺费用硬上限。本地 Whisper 仍须独立准备权重。实现与验证见 [套餐接入记录](research/chatgpt-plan.md)。

## 使用 API Key

启动 Douyin Analyst，打开左侧 **模型与采集设置**，填写：

| 页面字段 | 统一配置名 | 应填写的内容 |
| --- | --- | --- |
| API 基础地址 | OPENAI_BASE_URL | 服务商提供的基础地址，例如 `https://你的服务/v1` |
| 模型名称 | OPENAI_MODEL | 服务商控制台提供的实际模型 ID |
| API 密钥 | OPENAI_API_KEY | 自己的 API Key |

基础地址不要包含 `/chat/completions`。程序会请求 `OPENAI_BASE_URL + /chat/completions`。仅允许 HTTPS 或本机 HTTP；不将密钥放入 URL。

选择支持 Chat Completions、`response_format: {"type":"json_object"}` 和 `max_tokens` 的服务及模型。本程序在 JSON 格式之外继续做 Pydantic 和字幕证据 ID 校验。JSON mode 本身不保证业务 schema 或内容事实正确，参见 [官方 JSON 输出说明](https://developers.openai.com/api/docs/guides/structured-outputs)。

点击 **保存并测试所选模型**：只发送一句示例字幕，检查网络、模型返回、结构及引用格式，产生少量 API 用量；不会采集抖音、下载 Whisper 权重或把连接测试保存成真实视频分析。

配置保存后对新建或恢复任务生效，无需重启。运行中任务持有自己的配置快照，修改配置前需暂停或完成当前任务。

## 密钥与数据位置

页面底部显示实际数据目录。Windows 正常安装默认是 `%LOCALAPPDATA%\com.douyinanalyst.desktop`。

- `model-settings.json`：本机设置。Windows API 密钥用 DPAPI 加密，绑定当前 Windows 用户，页面不回显。
- `analyst.sqlite3`：任务、字幕、版本化分析、报告及分析运行记录。
- `media`：复制导入的本地视频及已下载媒体。
- Whisper 权重：由 faster-whisper 使用自己的缓存，或使用页面填写的已有模型目录；不打进安装包。

原始视频保留在用户选择的位置，导入时另外复制到应用数据目录，避免移动原文件后证据失效。字幕会发送给配置的模型服务；报告和字幕结果保留在本机。

## 建议测试顺序

1. 选择套餐授权或 API Key，并测试所选模型，确认结构和证据格式通过。
2. 填写本地语音模型名（默认 small）或已有模型目录。首次使用模型名时需下载权重；本地语音识别不使用上述文字模型 API。
3. 在任务中心点击 **选择本地视频分析**，选择一段自己有权处理、包含清晰语音的视频。检查任务状态、字幕时间、摘要与证据，试用 SRT/VTT 导出。
4. 确认本机安装 Microsoft Edge；展开 **抖音采集设置**，选择 **浏览器采集（打开普通 Edge）**，开启 **启用真实抖音采集** 并保存。按 [Cookie 获取与导入](douyin-cookie.md) 在本机粘贴并加密保存登录状态，也兼容单行文本文件。出现登录或验证时在打开的 Edge 窗口自行完成；程序不自动读取浏览器 Cookie。
5. 在任务中心粘贴分享文本，点击“检测此链接的采集能力（不调用模型）”；可导出最新 JSON 结果。分别测试作品链接、分享文本及主页。R0 仍须证明真实作者、第二页不同作品 ID、真实视频下载与 FFprobe 成功，不能用本地视频或测试替身替代。
6. 主页任务选择 10 或 30 条，核对成功/失败/无语音数量、停止原因、主题比例、报告到字幕定位，以及 Markdown/JSON 导出。

真实样本验证用于评价识别、转写、分析质量及平台成功率。博主本人身份未核实的表达仍不直接归因，主营业务证据不足时保持不推断。

## 命令行入口

未使用页面保存配置时，也支持同一组环境变量：

```powershell
$env:OPENAI_BASE_URL = 'https://你的服务/v1'
$env:OPENAI_MODEL = '服务商提供的模型ID'
$env:OPENAI_API_KEY = '仅在本机填入密钥'
.\backend\.venv\Scripts\python.exe .\scripts\analyze_local_video.py 'E:\你的视频.mp4'
```

已保存的本机设置优先于环境变量；命令行默认与桌面使用同一数据目录，也可传入 `--data-dir` 指定独立测试目录。不要把实际环境变量或配置文件提交到 Git。

真实 R0 采集探针仍为 `scripts/live_douyin_probe.py`，其主页、作品链接、Cookie 文件和媒体目录参数见 README 与调研记录。
