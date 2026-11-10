# ChatGPT 套餐接入记录

核对日期：2026-11-10。采用官方 Sign in with ChatGPT 的本地应用授权流程。历史 API 赠送活动与该流程分开：本实现不领取、兑换或转售额度，也不需要 Platform API Key。

## 0.1.5 配置与真实批量验收

保留桌面“模型与采集设置 → 模型接入方式 → 使用 ChatGPT 套餐”及账户可用模型选择；兼容 API Key 仍为独立选项。实际保存的配置决定后续分析通道，套餐请求失败不切换到 API Key。

原抖音作品已完成真实字幕和套餐分析；随后 10 条真实主页样本经源码 SingleWorker 完成 10/10 分析，580 段字幕、351 处单视频引用重验，10 次模型请求全部来自 `chatgpt_plan`，模型 `gpt-6.1-sol`，未读取或使用 API Key。两条暂停时已落库结果在恢复后版本及请求次数保持不变。见 [批量记录](../testing/real-profile-10-chatgpt-0.1.5.json)、[暂停恢复及导出复核](../testing/real-profile-resume-chatgpt-0.1.5.json)。

真实批量入口及配置说明见 [接入说明](../api-setup.md)。测试数据独立保存，凭据仍在原软件的加密目录；不复制或提交授权。30 条整批、人工语义质量和界面中播放尚待验收，实际报告的相近领域标签归并仍需改进。

## 采用的实现

| 项目 | 固定版本或 commit | 许可证 | 采用文件和能力 |
| --- | --- | --- | --- |
| openai/sign-in-with-chatgpt-devkit | `0a36fefeb913055c8c7a1a29b63d82b96b2e841a`，`@siwc/local` 0.1.0 | DevKit Noncommercial License v1.0 | `packages/local/src/{index,oauth,storage,models,responses,errors,types}.ts`，及对应测试；PKCE/OIDC、动态注册、主机标识、刷新轮换、加密存储接口、模型列表、流式 Responses 完成判断 |
| Node.js | 22.20.0 Windows x64 | MIT 及随附第三方声明 | 本地登录/请求桥接运行时；安装包内附完整上游 LICENSE |
| jose / openai / proper-lockfile | 6.1.0 / 7.21.0 / 4.1.2 | MIT / Apache-2.0 / MIT | 上游 SDK 的签名校验、HTTP/SSE 和跨进程文件锁；传递依赖以 auth-helper/package-lock.json 为准 |

上游文件保持原样，保留独立许可；应用适配在 `auth-helper/main.mjs` 和 `backend/app/chatgpt_plan.py`。非商用个人学习实验符合本轮用途，不能据此宣称可直接商用分发。未采用完整 Electron 示例或其字体/品牌资源。依赖通知随打包资源分发。

## 接口边界

- Tauri → 认证 FastAPI API → Python 私有管道 → 官方 Node SDK。Node 辅助进程仅处理登录与模型请求，不运行任务调度或额外业务 Worker。
- 浏览器授权由用户完成；不读取现有聊天或其他应用的登录凭据。账户、注册和令牌由 SDK 存于应用独立目录，使用 Windows DPAPI 加密；令牌不进入前端、命令参数或日志。
- 仅向公开 `https://api.openai.com/v1/models` 和 `/responses` 发送模型请求。SDK处理刷新与 OIDC 校验；未完成的流和额度失败不保存为成功分析。
- 模型菜单取自账户实际返回的可见模型，不假定某个套餐必有固定模型。套餐通道与 API Key 通道显式选择；不会失败后改用另一个通道。
- 套餐请求固定 `store:false`、`stream:true`，以 instructions 提供约束，不发送不支持的 max_output_tokens、temperature 或 previous_response_id。
- 保留最多 5 个字幕分段、最多 12 次请求的固定分析 harness；套餐请求不自动重试，单次 90 秒、接收文本最多 32768 字符。该字符限制是本地停止条件，不能替代服务端输出 token 或费用硬上限。SDK当前未向桥接返回实际用量，运行记录明确 `usage_reported:false`；用量管理打开 ChatGPT 官方页面。
- 本地 Whisper 继续负责语音识别；套餐通道不用于音频转写。LangGraph Agent 仍暂缓。

## 验证与限制

- 官方 SDK 测试：56 通过，1 项 Unix 文件权限测试在 Windows 跳过；使用合成凭据和网络替身，不代表真实账户已授权。
- 应用回归覆盖：套餐模式不解密已有 API Key、保存时保留密文、子进程环境不继承模型密钥或 Node 注入参数、无账户时请求拒绝、非法字幕引用拒绝、额度失败不回退至 API。
- 真实官方账户授权、可见模型列表和 GPT-6.1-Sol 完整 Responses 请求已通过；文字样本为合成输入，原 API Key 密文保持一致，见 testing/chatgpt-plan-0.1.2.json。
- 合成语音 MP4 的真实 FFmpeg、Whisper small CPU int8、套餐模型分析与证据落库链路通过，得到 4 段有效时间戳字幕。该结果不证明真实抖音获取或真实博主分析质量，见 testing/real-asr-0.1.2.json。
- 真实连接测试发现领域为空时不应编造类别，已统一规范为“未分类”，并提高提示版本。安装版最终验证结果见 testing/windows-update-0.1.2.md。

## 官方依据

- [本地开源应用的 ChatGPT 套餐接入](https://developers.openai.com/siwc/token-sharing-open-source)
- [官方 DevKit 集成示例](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)
- [模型列表与完成推理](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [预览限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
- [用户说明与套餐用量](https://learn.chatgpt.com/docs/sign-in-with-chatgpt)
