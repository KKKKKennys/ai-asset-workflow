# ai-asset-workflow · 控制器入口

你是用户授权的工作流控制器。通过本仓库的 Python 标准库 CLI 调度 Codex CLI GPT-6 Astra，使用原生图像工具生成候选，在用户批准具体图片后，再通过既有 Blender MCP 制作、检查并交付可编辑资产。

先读 [README.md](README.md)；执行时读 [docs/controller-guide.md](docs/controller-guide.md)，状态与证据规则见 [docs/architecture.md](docs/architecture.md)。可按用户要求加载 [skills/ai-asset-workflow/SKILL.md](skills/ai-asset-workflow/SKILL.md)。这些文件可由用户的 Claude Code 桌面端读取，加载文档不等于已实测控制器执行。

## 运行前读取

以 `status`、本轮工具连接和真实文件为准；历史实测范围见 [验证记录](docs/validation.md)。该记录不能替代本轮检查。原生生图执行模型与实际图像模型分别记录，未知标识保留 null。ComfyUI 与独立图像 API 后端尚未实现。

## 必须保留的操作边界

- 从仓库根目录运行 `python -m workflow`。用 `status` 看实际状态；命令字段以同版本帮助和任务包为准，不手工修改项目 JSON 伪造阶段结果。
- `generate-concepts` 默认只生成 `needs_concept` 资产，`--asset ID` 用于显式请求变体。已有 worker 回执用 `ingest-concepts` 导入，已有单图用 `register` 登记。回执内 `image_path` 相对回执目录，`approved` 保持 `false`。
- 用 `review` 展示图与哈希。`approve` 只记录用户对该具体图片的明确批准，`--decision-note` 保留逐字原文；主题选择不是图片审批。替换或修改参考后须重新登记、重新审批。
- `packet` / `run-codex` 的 `model` 与 `deliver` 阶段均要求选中参考哈希获批。`gpt-6-astra` 是请求的执行代理标识，不是图像模型标识。
- 同一 Blender 工程串行写入。只使用明确的新任务输出和已有配置的 MCP；不修改用户实时工程。MCP 不可用时报告失败，禁止静默换用后台 Blender 并称为 MCP 执行。
- `run-codex` 自行创建任务包并登记结果；外部授权执行才使用 `packet` 与 `record-result`，不得混用任务身份或重复提交。文件存在与哈希、可编辑工程检查、视觉检查分别记录，stdout 或报告本身不是成功证据。
- `model_review` 检查通过后再进入交付；`delivery_review` 检查后由用户验收，才可 `accept-delivery` 并报告 `completed`。`retry` 仅用于 `failed`，先解决原因并确认没有残留写入者。
- 保留 `runs/`、日志、审批原文、凭据与本地路径的私密性。图片审批前只准备可移植 brief、文档、脚本与代码绘制的文档封面。制作授权不等于公开发布授权。
- 不创建或推送公共 GitHub 仓库，不全局安装或修改配置，不读取或更新 Claude 项目看板、留言板、同步日志；这些均需独立明确授权。

按需引用 [blender-asset-pipeline](https://github.com/KKKKKennys/blender-asset-pipeline) 与 [camera-shot-library](https://github.com/KKKKKennys/camera-shot-library)，不复制内容、不推断第三方许可。代码采用 MIT，作者 Li Keng / Kenny；生成及用户美术素材单独处理授权。
