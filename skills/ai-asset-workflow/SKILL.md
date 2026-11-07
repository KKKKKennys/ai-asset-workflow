---
name: ai-asset-workflow
description: 编排用户授权的 Claude Code 控制器、Codex CLI 原生图像生成与 Blender MCP 资产任务；用于需要候选图审阅、逐图审批、阶段回执和交付验收的 ai-asset-workflow 仓库工作流。
---

# AI Asset Workflow

在本仓库中完成“brief → 概念图 → 用户审批 → Blender 制作 → 检查与验收”的可追溯流程。技能只提供编排指引，不附带执行权限、工具后端或用户批准。

先读 [README](../../README.md) 的当前状态；需要命令时读[控制器指南](../../docs/controller-guide.md)，需要判断状态与证据时读[架构说明](../../docs/architecture.md)。相对路径依赖完整仓库，不能只复制本文件就假定 CLI 和文档仍可用。

## 支持范围与当前证据

本版本使用 Codex CLI 原生图像工具和已配置的 Blender MCP，不包含 ComfyUI 或独立图像 API 适配器。每次执行先读取项目状态并检查工具连接；不要将历史连接状态当作当前状态。实际验证范围见 [验证记录](../../docs/validation.md)。执行代理模型与图像模型分别记录，未暴露的图像模型 ID 保持 null。

## 执行原则

1. 从仓库根目录调用 `python -m workflow`，用 `init` 建立本次项目、用 `status` 读取事实；不手工修改项目状态绕过检查。确认授权范围、新输出目录、Codex 路径和既有 MCP 可用性。
2. 用 `generate-concepts` 调度原生图像工具，默认仅处理 `needs_concept`，显式 `--asset ID` 请求单资产变体；也可用 `ingest-concepts` 导入已有 worker 回执，或用 `register` 登记单图。回执图片路径相对回执目录，`approved: false`；图像模型未暴露时保留 `null`。用 `review` 展示具体图片及哈希。
3. 只在用户明确批准已展示图片时调用 `approve`，绑定资产 ID、完整候选哈希与用户逐字原文。主题选择、继续生成、默认同意和代理判断都不能代替批准。更换图片须重新审批。
4. `model`、`deliver` 两阶段都要求选中参考哈希获批。`run-codex` 自行创建任务包、执行并登记结果；外部授权会话则用 `packet` 创建任务、执行后用 `record-result` 登记真实回执。不混用任务身份或重复登记。
5. 同一 Blender 工程串行执行，只操作本任务明确的新输出。MCP 不可用就失败并报告，不能静默启动后台 Blender 再称为 MCP 成功，不修改用户实时工程或全局工具配置。
6. `model_review` 时检查可编辑工程、尺度、结构与实际画面，再推进交付；`delivery_review` 时核对文件和哈希并查看交付预览。stdout 或报告中的“完成”不构成验证。
7. 只有检查后用户明确接受交付，才调用 `accept-delivery` 记录真实验收文字并报告 `completed`。`retry` 仅针对 `failed`；原因未解决或原任务仍在运行时，不继续重试。

## 依赖与发布

按任务需要引用公共 Skill：[blender-asset-pipeline](https://github.com/KKKKKennys/blender-asset-pipeline)、[camera-shot-library](https://github.com/KKKKKennys/camera-shot-library)。仅链接，不复制；不代其声明许可证。相机库只在任务涉及镜头与展示时加载。

图片审批前仅准备可移植 brief、文档、脚本和代码绘制的文档封面。`runs/`、日志、原始审批文本、本地路径、凭据与产物保持私有。代码 MIT，作者 Li Keng / Kenny；美术素材授权单独处理。制作审批不包含公开发布授权。本技能不授权新建远端仓库、推送、全局安装或 Claude 留言板同步。
