# 控制器指南

本指南面向用户授权的 Claude Code 控制器，也可手动执行。v0.1.0-dev 核心 CLI 已实现，Claude Code 主导的完整串联尚未验证。用户可让自己的 Claude Code 读取本指南，在具备对应工具权限的环境中操作。

展示中的目标分工是：Codex CLI **编辑 ComfyUI 批量生图工作流，或调用 GPT Image**；ComfyUI / GPT Image **按设定批量生成候选图片**。当前版本仅接入 Codex 原生图像工具，尚无 ComfyUI 或独立图像 API 适配器。下列命令说明现有实现。

## 先确认本次任务边界

读取 brief，确定资产 ID、输出目录和允许操作的全新 Blender 工程。只使用本任务明确指定的新输出，不修改用户正在使用的工程。确认 Codex 可执行文件的真实路径、既有工具权限与 Blender MCP 可用性；不全局安装依赖、不改全局 MCP 配置、不读取或同步 Claude 留言板。

原生 Codex 图像工具使用已有登录与工具权限，无需为本流程另填 API key。此前已确认 `codex exec` 可见 `image_gen`，但工具未暴露实际图像模型标识。记录来源为 `codex-imagegen`；不能根据执行代理 `gpt-6-astra` 推断图像模型，也不能标成 GPT-Image2.6。

`equipment-case`、`inspection-lamp`、`control-console` 的真实概念图均已生成并查看，原生 Codex CLI worker 经任务提示词实测退出码为 0，实际图像模型标识记录为 `null`。三图仍未获用户批准，也不公开。`generate-concepts` 封装的合成协议测试已有记录，尚未再次发起真实生图。Blender 制作未验证；执行前需检查实际 MCP 连接。以上为既有记录，本次未重新实测。

## 命令约定

以下命令均从仓库根目录执行。`PROJECT`、`ID`、`PATH`、`HASH` 和文本是参数说明，执行时替换为实际值；`[...]` 表示可选参数，不要原样输入。

```text
python -m workflow init --brief examples/sci-lab.json --project runs/sci-lab/project.json
python -m workflow status --project PROJECT
python -m workflow generate-concepts --project PROJECT --codex ABS_EXE [--model gpt-6-astra --timeout 1200 --asset ID]
python -m workflow ingest-concepts --project PROJECT --receipt PRIVATE_JSON
python -m workflow register --project PROJECT --asset ID --image PATH --source codex-imagegen [--prompt-file PATH]
python -m workflow review --project PROJECT
python -m workflow approve --project PROJECT --asset ID --candidate HASH --decision-note EXACT_HUMAN_TEXT
python -m workflow packet --project PROJECT --asset ID --stage model|deliver
python -m workflow run-codex --project PROJECT --asset ID --stage model|deliver --codex PATH [--model gpt-6-astra --timeout 1200]
python -m workflow record-result --project PROJECT --asset ID --stage model|deliver --receipt PATH
python -m workflow retry --project PROJECT --asset ID
python -m workflow accept-delivery --project PROJECT --asset ID --decision-note TEXT
```

`model|deliver` 表示二选一；`ABS_EXE` 是 Codex 可执行文件绝对路径，`PRIVATE_JSON` 是项目私有目录内的图像回执。当前实现中 `--model` 默认为 `gpt-6-astra`，`--timeout` 默认为 1200 秒；上文显式写出便于复现。字段与回执格式以同版本 CLI 帮助、生成的任务包和实现为准；遇到不一致先报告，不手工篡改项目状态绕过命令。

## 从候选图到制作授权

1. `init` 从可移植 brief 创建本地项目，随后用 `status` 查看实际状态。运行目录保留在 `runs/`，不要提交到公开仓库。
2. `generate-concepts` 默认只处理 `needs_concept` 资产，并导入 worker 回执；显式 `--asset ID` 可为该资产请求新变体，不能绕过运行中或失败状态。也可用 `ingest-concepts` 导入已有原生 worker 回执，或用 `register` 登记已有单图；后两者不生成图片。保留实际提示词与来源，不能用示意图代替生成成果。
3. `review` 写出 `review/index.html`。按返回路径打开页面，展示具体图片、资产 ID 与候选哈希；控制器自己也应查看图像是否可读、有无明显结构问题。
4. 等待用户对已经展示的具体图片作出明确批准，再用 `approve` 写入完整候选哈希和用户逐字原文。不能由代理编造、润色或补全批准语句，也不能复制本文占位符。

“做科幻主题”“先试设备箱”“继续生成”不构成图片批准。模糊的“可以”只有在上下文唯一指向已展示图片时才可使用；否则先确认指向。用户同时明确批准多张图时，分别绑定对应候选哈希，保留同一条真实批准原文与其上下文。

未收到图片批准就停在待审阅状态。新增或修改图片是新候选；原批准不自动转移。审批材料与运行记录中的用户原话保持本地私有。

### 图像 worker 回执

以 [workflow/concepts.py](../workflow/concepts.py) 为字段依据。下面只示意格式，不是生成证据；回执位于项目私有目录内，`image_path` 相对回执所在目录解析，且不能逃逸该目录。填写实际提示词与工具名；若提供 `sha256`，必须是实际文件哈希。

```json
{
  "schema_version": 1,
  "approved": false,
  "generation_tool": "<实际工具名>",
  "assets": [
    {
      "asset_id": "equipment-case",
      "image_path": "outputs/equipment-case.png",
      "status": "generated",
      "approved": false,
      "prompt": "<实际完整提示词>",
      "generation_tool": "<实际工具名>",
      "image_model": null
    }
  ]
}
```

每个资产只放一个本批次条目；导入要求真实 PNG、JPEG 或 WebP。`generate-concepts` 要求回执恰好覆盖请求的资产集合；`ingest-concepts` 可导入已有批次。工具未暴露图像模型时保留 `null`。worker 无权审批：顶层和条目均保持 `approved: false`，用户决定另经 `approve` 写入。

## 建模、检查与交付

`packet` 创建可供外部授权会话执行的独立任务包；`run-codex` 会自行创建新的任务包、执行并登记回执，不消费上一次 `packet` 的任务。两条路径择一使用，不能混用其回执。`model` 与 `deliver` 都核对获批参考图哈希；参考文件字节变更时先登记新候选并重新审批。

同一个 Blender 工程只允许一个写入任务。控制器应等当前阶段结束、确认回执与实际文件状态后，再推进下一个资产或阶段；不要假定 CLI 已实现跨进程锁。既有 MCP 连接不可用时，本次执行应失败并报告，不能启动独立后台 Blender 冒充 MCP 执行。

### 执行模型阶段

```powershell
python -m workflow run-codex --project runs/sci-lab/project.json --asset equipment-case --stage model --codex "<codex可执行文件绝对路径>" --model gpt-6-astra --timeout 1200
python -m workflow status --project runs/sci-lab/project.json
```

当前 MCP 未恢复前，不执行 `run-codex` 的 Blender 阶段。可读取任务包核对范围，但不能把任务包的存在称为建模成功。

如果由另一个经授权的执行会话完成阶段，先用 `packet` 创建任务，按其中的输出目录执行，再登记该任务的真实回执：

```powershell
python -m workflow packet --project runs/sci-lab/project.json --asset equipment-case --stage model
# 外部授权会话按返回任务包完成后：
python -m workflow record-result --project runs/sci-lab/project.json --asset equipment-case --stage model --receipt "<该任务的实际模型回执路径>"
```

回执应遵循同版本任务包要求，不手工伪造成功数据。先查 `status`：若运行入口已登记该回执，不重复登记。模型结果进入 `model_review` 后，检查实际 `.blend` 是否存在且可打开、参考哈希是否对应、对象是否可编辑、尺度与结构是否可信；查看全貌和关键连接处。结构或画面存在问题时先修复并复核，不仅凭退出码推进交付。

### 执行交付阶段

模型检查通过后，使用同一已审批参考及本次任务工程继续：

```powershell
python -m workflow run-codex --project runs/sci-lab/project.json --asset equipment-case --stage deliver --codex "<codex可执行文件绝对路径>" --model gpt-6-astra --timeout 1200
python -m workflow status --project runs/sci-lab/project.json
```

外部授权会话则先生成交付任务包，执行完成后登记其回执：

```powershell
python -m workflow packet --project runs/sci-lab/project.json --asset equipment-case --stage deliver
# 外部授权会话按返回任务包完成后：
python -m workflow record-result --project runs/sci-lab/project.json --asset equipment-case --stage deliver --receipt "<该任务的实际交付回执路径>"
```

`delivery_review` 表示待检查。核对任务约定的可编辑工程、预览与导出文件及哈希；实际打开工程、查看预览构图与细节。文件完整性和视觉质量分别给结论；没有看过的画面不能报告为视觉通过。向用户展示交付物、路径、已检查项目与剩余限制。

当前阶段回执使用 `schema_version: 1`，包含 `job_id`、`asset_id`、`stage`、`reference_sha256`、`status`、`artifacts`、`checks` 和 `limitations`；`status` 为 `produced` 或 `failed`，失败需写原因。产物路径相对该任务目录且必须位于 `outputs/` 内：模型阶段要求未压缩 `.blend` 与预览，交付阶段要求 GLB 与预览。文件头和哈希检查不能代替打开工程、重导入 GLB 或视觉检查。

用户检查并明确接受交付后，保留其真实验收文字：

```powershell
python -m workflow accept-delivery --project runs/sci-lab/project.json --asset equipment-case --decision-note "<用户检查后明确接受交付的原文>"
```

只有这一验收完成后，才可以把资产报告为 `completed`。概念图审批不能替代交付验收。

## 失败与恢复

`failed` 才能使用 `retry`。先用 `status` 确认失败阶段，查看本地日志与回执，解决真实原因，再为该资产重试：

```powershell
python -m workflow retry --project runs/sci-lab/project.json --asset equipment-case
python -m workflow status --project runs/sci-lab/project.json
```

重试不是成功，也不补足审批。重新启动前检查原执行是否仍占用 Blender；超时不证明其子任务已经退出。失败原因未改变时停止重复运行，报告阻塞条件。工具缺失、MCP 断开、哈希不符或产物缺失都不能靠修改 JSON 状态“修好”。

## 私有记录与公开材料

项目 JSON、候选图片、审阅页、原始提示词、审批原文、回执、日志和绝对路径留在私有运行目录。公开前检查暂存文件内容；`.gitignore` 无法清除已跟踪文件，也无法发现文档中意外写入的本地路径或秘密。

图片获批前，只准备可移植 brief、文档、脚本与代码绘制的文档封面。图片获准用于建模，不代表获准公开或重新许可。代码作者为 Li Keng / Kenny，代码用 MIT；生成及用户美术素材单独处理授权。外部 Skill 仅链接原仓库，遵循其实际许可证，不复制其内容或替其声明许可。
