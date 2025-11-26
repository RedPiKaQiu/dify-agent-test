# Dify Agent 测试工具

这是一个独立的测试脚本，用于测试 Dify agent 的意图识别功能。脚本完全独立于后端应用，所有依赖都在 `agentTest/` 目录内。

## 功能特性

- ✅ 命令行交互界面
- ✅ 支持多轮对话（通过 conversation_id）
- ✅ 用户信息从配置文件读取
- ✅ API_KEY 可配置
- ✅ 独立于后端应用，无需数据库
- ✅ 清晰的错误提示和日志输出

## 文件结构

```
agentTest/
├── test_dify_agent.py    # 主测试脚本
├── dify_helper.py        # 工具模块
├── config.json           # 配置文件示例
└── README.md            # 使用说明
```

## 依赖要求

- Python 3.9+
- aiohttp
- prompt_toolkit（提供对中文/全角字符友好的输入体验，解决退格显示错位问题）

安装依赖：

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 配置准备

编辑 `config.json` 文件，设置以下必需字段：

- `api_key`: Dify API 密钥
- `dify_base_url`: Dify API 基础URL（默认: https://api.dify.ai/v1）
- `timezone`: 时区（默认: Asia/Shanghai）
- `user`: 用户标识符

可选字段：

- `agent_name`: agent 的命令名称（如设置为 `"nameA"`，即可通过 `:nameA` 在 CLI 中切换）
- `current_state`: 当前状态对象
- `user_memory`: 用户记忆对象
- `behavioral_patterns`: 行为模式对象
- `insight`: 洞察数据对象
- `candidate_items`: 候选事项列表
- `context_info`: 上下文信息（如果为 null，会自动生成）

### 2. 运行脚本

脚本默认会在当前目录中自动扫描 `config.json` 及 `config_*.json` 文件，自动加载所有存在的配置；
也可以通过命令行参数显式指定需要的配置文件。

```bash
# 进入 agentTest 目录
cd agentTest

# 使用默认配置文件（自动识别 config.json、config_*.json）
python test_dify_agent.py

# 指定自定义配置文件
python test_dify_agent.py --config custom_config.json

# 同时加载两个 agent 配置（若提供 agent_name，可通过 :自定义名称 切换）
python test_dify_agent.py --config agent1_config.json --config2 agent2_config.json
```

### 3. 交互命令

- 直接输入 `user_input` 内容进行测试
- 输入 `exit` 或 `quit` 退出程序
- 输入 `reset` 重置对话（清空 conversation_id）
- 输入 `config` 显示当前配置信息
- 默认处于多行模式（输入 `:end` 完成输入，输入 `:cancel` 放弃当前多行输入）
- 输入 `:chmod` 在单行/多行模式之间切换；单行模式下也可用 `:paste` 临时进入多行模式
- CLI 默认使用 `prompt_toolkit`，确保中文和其他宽字符在退格时光标位置正确；如未安装该依赖则自动回退到标准输入（体验略逊）
- 同时加载多个配置时，可输入 `:agentName`（来源于配置中的 `agent_name` 字段，默认 `:agent1/:agent2/...`）切换调用的 agent

## 配置示例

```json
{
  "api_key": "app-xxx",
  "dify_base_url": "https://api.dify.ai/v1",
  "timezone": "Asia/Shanghai",
  "user": "test_user_001",
  "agent_name": "dailyAgent",
  "current_state": {
    "physical_energy": "medium",
    "stress_level": "low",
    "sleep_quality": "good",
    "activity_readiness": "ready",
    "cycle_phase": "unknown"
  },
  "user_memory": {
    "recent_state": [],
    "short_term_focus": [],
    "long_term_interests": [],
    "values_and_priorities": [],
    "interests_and_intentions": [],
    "pending_life_items": []
  },
  "behavioral_patterns": {
    "energy_rhythms": [],
    "success_factors": [],
    "procrastination_triggers": [],
    "energy_management": [],
    "decision_making": [],
    "mood_triggers": [],
    "attention_patterns": [],
    "physical_influences": [],
    "risk_factors": []
  },
  "insight": {
    "recent_you": [],
    "you_focus_on": [],
    "you_tend_to": []
  },
  "candidate_items": [],
  "context_info": null
}
```

## 使用示例

```bash
$ cd agentTest
$ python test_dify_agent.py

============================================================
Dify Agent 测试工具
============================================================
输入 'exit' 或 'quit' 退出
输入 'reset' 重置对话（清空 conversation_id）
输入 'config' 显示当前配置
============================================================

✓ 配置文件加载成功

============================================================
配置信息:
------------------------------------------------------------
API Key: app-xxx...
Dify Base URL: https://api.dify.ai/v1
时区: Asia/Shanghai
用户标识: test_user_001
...
============================================================

请输入 user_input (或输入命令): 我想创建一个任务

正在调用 Dify API...
用户输入: 我想创建一个任务
✓ API 调用成功

============================================================
AI 响应:
------------------------------------------------------------
[AI 返回的答案内容]
------------------------------------------------------------
对话ID: abc123...
Token 使用量: 1234
模型: gpt-4
============================================================

请输入 user_input (或输入命令): 这个任务需要30分钟

正在调用 Dify API...
用户输入: 这个任务需要30分钟
对话ID: abc123...
✓ API 调用成功

...
```

## 多轮对话

脚本会自动管理 `conversation_id`，实现多轮对话：

1. 首次调用：不传递 `conversation_id`
2. 后续调用：使用 API 返回的 `conversation_id`
3. 重置对话：输入 `reset` 命令清空 `conversation_id`

## 注意事项

1. **API 密钥安全**: 请妥善保管 `config.json` 中的 API 密钥，不要提交到版本控制系统
2. **超时设置**: 默认超时时间为 60 秒，可在代码中修改 `timeout` 变量
3. **独立运行**: 脚本完全独立，不依赖后端数据库或其他模块
4. **配置文件格式**: 必须使用有效的 JSON 格式
5. **中文输入体验**: 已内置 `prompt_toolkit`，可保障退格键在中文、Emoji 等宽字符场景下显示正常；如禁用该依赖，请注意回退到标准输入时光标可能存在偏差

## 故障排查

### 配置文件不存在
```
错误: 配置文件不存在: config.json
```
**解决方案**: 确保 `config.json` 文件存在于 `agentTest/` 目录下，或使用 `--config` 参数指定配置文件路径

### API 调用失败
```
❌ 错误: Dify API调用失败: HTTP 401, ...
```
**解决方案**: 检查 `api_key` 是否正确，以及 API 密钥是否有权限访问对应的 Dify agent

### 网络超时
```
❌ 错误: API调用超时（60秒）
```
**解决方案**: 检查网络连接，或增加超时时间（修改代码中的 `timeout` 变量）

## 技术实现

脚本参考了 `app/services/input_analysis_service.py` 的实现方式：

- 使用 `aiohttp` 发送异步 HTTP 请求
- 构建符合 Dify API 规范的 payload
- 处理 `inputs`（category, repetition, nowtime）和 `query`（完整输入数据）
- 支持 `conversation_id` 实现多轮对话

工具模块 `dify_helper.py` 提供了独立实现的工具函数：

- `build_category_string()`: 构建任务分类字符串
- `build_repetition_string()`: 构建重复频率字符串
- `build_nowtime()`: 生成 ISO 格式时间字符串
- `get_context_info()`: 获取环境上下文信息
- `format_response()`: 格式化响应输出

## 许可证

本工具为内部测试工具，仅供开发和测试使用。
