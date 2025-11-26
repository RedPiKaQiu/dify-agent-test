#!/usr/bin/env python3
"""
Dify Agent 测试脚本
独立于后端应用，用于测试 Dify agent 的意图识别功能
支持命令行交互和多轮对话
"""

import json
import asyncio
import argparse
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import aiohttp

# prompt_toolkit 提供对 CJK 字符友好的输入体验
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
except ImportError:  # pragma: no cover - 可选依赖
    PromptSession = None
    InMemoryHistory = None

from dify_helper import (
    get_context_info,
    format_response
)


def discover_default_config_files() -> List[str]:
    """
    自动发现当前目录下的配置文件

    Returns:
        List[str]: 存在的配置文件路径列表
    """
    base_dir = Path.cwd()
    discovered: List[str] = []

    main_config = base_dir / "config.json"
    if main_config.exists():
        discovered.append(str(main_config))

    for cfg in sorted(base_dir.glob("config_*.json")):
        # 避免重复添加 config.json
        if cfg.name == "config.json":
            continue
        discovered.append(str(cfg))

    return discovered


def resolve_config_paths(primary: Optional[str], secondary: Optional[str]) -> Dict[str, str]:
    """
    根据用户输入或自动发现结果构建配置文件映射

    Args:
        primary: --config 参数
        secondary: --config2 参数

    Returns:
        Dict[str, str]: agent名称到配置路径的映射
    """
    manual_paths = [path for path in [primary, secondary] if path]

    if manual_paths:
        return {
            f"agent{i + 1}": manual_paths[i]
            for i in range(len(manual_paths))
        }

    discovered = discover_default_config_files()
    if not discovered:
        print("错误: 当前目录未找到 config.json 或 config_*.json 配置文件")
        print("请至少提供一个配置文件，或使用 --config 参数指定路径")
        sys.exit(1)

    return {
        f"agent{i + 1}": path
        for i, path in enumerate(discovered)
    }


class DifyAgentTester:
    """Dify Agent 测试器"""
    MULTILINE_CMD = ":paste"
    MULTILINE_END = ":end"
    MULTILINE_CANCEL = ":cancel"
    MODE_TOGGLE_CMD = ":chmod"
    
    def __init__(self, config_paths: Dict[str, str]):
        """
        初始化测试器
        
        Args:
            config_paths: agent名称到配置文件路径的映射
        """
        if not config_paths:
            raise ValueError("至少需要提供一个配置文件")

        self.config_paths = config_paths
        self.active_agent = next(iter(config_paths))
        self.config: Dict[str, Any] = {}
        self.agent_configs: Dict[str, Dict[str, Any]] = {}
        self.conversation_ids: Dict[str, Optional[str]] = {}
        self.conversation_id: Optional[str] = None
        self.timeout = 60  # 60秒超时
        self.multiline_mode = True
        self._multiline_hint_shown = False
        self._prompt_session = self._create_prompt_session()
        self.agent_switch_commands = {
            f":{agent_name.lower()}": agent_name
            for agent_name in self.config_paths
        }

    def _create_prompt_session(self):
        """初始化 prompt_toolkit session（可选）"""
        if PromptSession is None:
            return None
        history = InMemoryHistory() if InMemoryHistory else None
        try:
            return PromptSession(history=history)
        except Exception:
            # prompt_toolkit 初始化失败时回退到内置 input
            return None

    def _toggle_input_mode(self) -> None:
        """切换输入模式"""
        self.multiline_mode = not self.multiline_mode
        if self.multiline_mode:
            self._multiline_hint_shown = False
        mode_name = "多行模式" if self.multiline_mode else "单行模式"
        print(f"已切换为{mode_name}。\n")

    def _prompt_with_agent(self, text: str) -> str:
        """构建带 agent 标签的提示语"""
        return f"[{self.active_agent}] {text}"
    
    def _normalize_agent_alias(self, alias: str) -> str:
        """将 agent 命令名标准化"""
        normalized = str(alias).strip()
        if not normalized:
            return ""
        return normalized.replace(" ", "_")

    def _resolve_agent_alias(self, fallback_name: str, config: Dict[str, Any],
                             existing: Dict[str, str]) -> str:
        """确定最终用于命令的 agent 名称"""
        custom_name = config.get("agent_name")
        candidate = self._normalize_agent_alias(custom_name) if custom_name else ""

        if custom_name and candidate != custom_name:
            print(f"⚠️ agent_name '{custom_name}' 已转换为 '{candidate}' 以用于命令。")

        if not candidate:
            candidate = self._normalize_agent_alias(fallback_name) or fallback_name

        unique_name = candidate
        suffix = 2
        while unique_name in existing:
            unique_name = f"{candidate}_{suffix}"
            suffix += 1
        return unique_name

    def _refresh_agent_switch_commands(self) -> None:
        """根据当前 agent 列表更新切换命令映射"""
        self.agent_switch_commands = {
            f":{agent_name.lower()}": agent_name
            for agent_name in self.agent_configs
        }

    def _format_agent_switch_hint(self) -> str:
        """生成 agent 切换命令提示"""
        commands = [f":{name}" for name in self.agent_configs]
        return "/".join(commands)
        
    def load_config(self) -> None:
        """加载配置文件（支持多个 agent）"""
        resolved_paths: Dict[str, str] = {}
        resolved_configs: Dict[str, Dict[str, Any]] = {}
        resolved_conversation_ids: Dict[str, Optional[str]] = {}

        for fallback_name, path in list(self.config_paths.items()):
            config = self._load_single_config(fallback_name, path)
            alias = self._resolve_agent_alias(fallback_name, config, resolved_paths)

            resolved_paths[alias] = path
            resolved_configs[alias] = config
            resolved_conversation_ids[alias] = self.conversation_ids.get(alias)

        self.config_paths = resolved_paths
        self.agent_configs = resolved_configs
        self.conversation_ids = resolved_conversation_ids
        self._refresh_agent_switch_commands()

        if self.active_agent not in self.agent_configs:
            self.active_agent = next(iter(self.agent_configs))

        self.switch_agent(self.active_agent, silent=True)

        loaded_count = len(self.agent_configs)
        if loaded_count > 1:
            agents = ", ".join(self.agent_configs.keys())
            print(f"✓ 已加载 {loaded_count} 个 agent 配置: {agents}")
        else:
            print("✓ 配置文件加载成功")

    def _load_single_config(self, agent_name: str, path: str) -> Dict[str, Any]:
        """读取并验证单个 agent 的配置"""
        config_file = Path(path)

        if not config_file.exists():
            print(f"错误: {agent_name} 配置文件不存在: {path}")
            print("请检查文件路径或使用 --config/--config2 参数指定正确的配置文件")
            sys.exit(1)

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"错误: {agent_name} 配置文件格式错误: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"错误: 读取 {agent_name} 配置文件失败: {e}")
            sys.exit(1)

        required_fields = ['api_key', 'dify_base_url', 'timezone', 'user']
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            print(f"错误: {agent_name} 配置缺少必需字段: {', '.join(missing_fields)}")
            sys.exit(1)

        config.setdefault('current_state', {})
        config.setdefault('user_memory', {})
        config.setdefault('behavioral_patterns', {})
        config.setdefault('insight', {})
        config.setdefault('candidate_items', [])
        return config
    
    def display_config_info(self) -> None:
        """显示配置信息（隐藏敏感信息）"""
        print("\n" + "=" * 60)
        print("配置信息:")
        print("-" * 60)
        print(f"当前 Agent: {self.active_agent} ({self.config_paths.get(self.active_agent)})")
        if len(self.agent_configs) > 1:
            print("可用 Agent 配置:")
            for agent_name, path in self.config_paths.items():
                marker = "*" if agent_name == self.active_agent else " "
                agent_info = self.agent_configs.get(agent_name, {})
                raw_name = agent_info.get('agent_name', '未设置')
                print(f"  {marker} {agent_name}: {path} (agent_name: {raw_name})")
        print(f"API Key: {self.config['api_key'][:10]}..." if len(self.config['api_key']) > 10 else f"API Key: {self.config['api_key']}")
        print(f"Dify Base URL: {self.config['dify_base_url']}")
        print(f"时区: {self.config['timezone']}")
        print(f"用户标识: {self.config['user']}")
        print(f"当前状态: {json.dumps(self.config['current_state'], ensure_ascii=False)}")
        print(f"用户记忆: {json.dumps(self.config['user_memory'], ensure_ascii=False)}")
        print(f"行为模式: {json.dumps(self.config['behavioral_patterns'], ensure_ascii=False)}")
        print(f"洞察数据: {json.dumps(self.config['insight'], ensure_ascii=False)}")
        print(f"候选事项数量: {len(self.config.get('candidate_items', []))}")
        print("=" * 60 + "\n")
    
    def build_payload(self, user_input: str) -> Dict[str, Any]:
        """
        构建发送给 Dify API 的 payload
        
        Args:
            user_input: 用户输入
            
        Returns:
            Dict: 完整的请求 payload
        """
        # 构建上下文信息（配置优先，缺失字段自动补全）
        context_overrides = self.config.get('context_info')
        context_info = get_context_info(self.config.get('timezone'), context_overrides)
        
        # 构建 query 数据
        query_data = {
            "user_input": user_input,
            "current_state": self.config['current_state'],
            "insight": self.config['insight'],
            "candidate_items": self.config.get('candidate_items', []),
            "context_info": context_info
        }
        
        # 构建 payload
        payload = {
            "inputs": {},
            "query": query_data,
            "response_mode": "blocking",
            "user": self.config['user']
        }
        
        # 如果有 conversation_id，添加到 payload 中（用于多轮对话）
        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id
        
        return payload

    def switch_agent(self, agent_name: str, silent: bool = False) -> bool:
        """切换当前使用的 agent 配置"""
        if agent_name not in self.agent_configs:
            print(f"⚠️ 未找到 {agent_name} 的配置，无法切换。")
            return False

        self.active_agent = agent_name
        self.config = self.agent_configs[agent_name]
        self.conversation_id = self.conversation_ids.get(agent_name)

        if not silent:
            print(f"✓ 已切换到 {agent_name} (配置: {self.config_paths.get(agent_name)})\n")
        return True
    
    async def call_dify_api(self, user_input: str) -> Tuple[Dict[str, Any], float]:
        """
        调用 Dify API
        
        Args:
            user_input: 用户输入
            
        Returns:
            Tuple[Dict, float]: (API 响应数据, 响应时间秒数)
        """
        api_key = self.config['api_key']
        base_url = self.config['dify_base_url']
        url = f"{base_url}/chat-messages"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = self.build_payload(user_input)
        
        print(f"\n正在调用 Dify API... (Agent: {self.active_agent})")
        print(f"用户输入: {user_input[:50]}{'...' if len(user_input) > 50 else ''}")
        if self.conversation_id:
            print(f"对话ID: {self.conversation_id}")
        
        start_time = datetime.now()
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        end_time = datetime.now()
                        response_time = (end_time - start_time).total_seconds()
                        print("✓ API 调用成功")
                        return result, response_time
                    else:
                        error_text = await response.text()
                        raise Exception(f"Dify API调用失败: HTTP {response.status}, {error_text}")
        
        except asyncio.TimeoutError:
            raise Exception("API调用超时（60秒）")
        except aiohttp.ClientError as e:
            raise Exception(f"网络错误: {str(e)}")
        except Exception as e:
            raise Exception(f"调用失败: {str(e)}")
    
    def process_response(self, response: Dict[str, Any], response_time: float) -> None:
        """
        处理 API 响应
        
        Args:
            response: API 响应数据
            response_time: API 响应时间（秒）
        """
        # 提取 answer 和 conversation_id
        answer = response.get("answer", "")
        conversation_id = response.get("conversation_id")
        metadata = response.get("metadata", {})
        
        # 更新 conversation_id（用于多轮对话）
        if conversation_id:
            self.conversation_id = conversation_id
            self.conversation_ids[self.active_agent] = conversation_id
        
        # 格式化并显示响应
        formatted_response = format_response(answer, conversation_id, metadata, response_time)
        print("\n" + formatted_response + "\n")
    
    async def _prompt_line(self, prompt_text: str = "") -> str:
        """统一处理输入，支持 prompt_toolkit 回退到内置 input"""
        if self._prompt_session:
            try:
                return await self._prompt_session.prompt_async(prompt_text)
            except (KeyboardInterrupt, EOFError):
                raise
            except Exception:
                # prompt_toolkit 读取失败时自动回退
                pass

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: input(prompt_text))

    async def _read_user_input(self) -> Optional[str]:
        """根据当前模式读取用户输入"""
        if self.multiline_mode:
            return await self._read_multiline_input()
        return await self._read_single_line_input()

    async def _read_single_line_input(self) -> Optional[str]:
        """读取单行输入，保留旧的 :paste 行为"""
        raw_line = await self._prompt_line(self._prompt_with_agent("请输入 user_input (或输入命令): "))
        stripped_line = raw_line.strip()

        if not stripped_line:
            return None

        left_trimmed = raw_line.lstrip()
        normalized = left_trimmed.lower()

        if stripped_line.lower() == self.MODE_TOGGLE_CMD:
            return self.MODE_TOGGLE_CMD

        if not normalized.startswith(self.MULTILINE_CMD):
            return stripped_line

        # 处理 :paste 后立即粘贴内容的情况
        initial_content = left_trimmed[len(self.MULTILINE_CMD):]
        if initial_content.startswith(" "):
            initial_content = initial_content[1:]

        return await self._read_multiline_input(initial_content=initial_content.rstrip("\n"), force_notice=True)

    async def _read_multiline_input(
        self,
        initial_content: Optional[str] = None,
        force_notice: bool = False
    ) -> Optional[str]:
        """读取多行输入"""
        if force_notice or not self._multiline_hint_shown:
            print(
                "多行模式开启，输入 "
                f"'{self.MULTILINE_END}' 完成，输入 "
                f"'{self.MULTILINE_CANCEL}' 取消当前输入，输入 "
                f"'{self.MODE_TOGGLE_CMD}' 可切换为单行模式。"
            )
            if len(self.agent_configs) > 1:
                print(f"可随时输入 {self._format_agent_switch_hint()} 切换不同 agent。")
            self._multiline_hint_shown = True

        lines = []
        if initial_content:
            lines.append(initial_content)

        first_prompt = not lines

        while True:
            prompt_text = (
                self._prompt_with_agent("请输入 user_input (多行模式): ")
                if first_prompt else "... "
            )
            line = await self._prompt_line(prompt_text)
            stripped = line.strip()
            normalized = stripped.lower()

            if not lines and (
                normalized in {'exit', 'quit', 'reset', 'config', self.MODE_TOGGLE_CMD}
                or normalized in self.agent_switch_commands
            ):
                return stripped

            if normalized == self.MULTILINE_CANCEL:
                print("⚠️ 当前多行输入已取消，您可以重新输入。")
                return None

            if normalized == self.MULTILINE_END:
                break
            lines.append(line)
            first_prompt = False

        combined = "\n".join(lines).strip()
        if not combined:
            print("⚠️ 未输入任何内容，多行模式已退出。\n")
            return None

        return combined

    async def run_interactive(self) -> None:
        """运行交互式命令行界面"""
        print("\n" + "=" * 60)
        print("Dify Agent 测试工具")
        print("=" * 60)
        print("输入 'exit' 或 'quit' 退出")
        print("输入 'reset' 重置对话（清空 conversation_id）")
        print("输入 'config' 显示当前配置")
        print(f"默认处于多行模式（输入 '{self.MULTILINE_END}' 完成输入，输入 '{self.MULTILINE_CANCEL}' 取消当前输入）")
        print(f"输入 '{self.MODE_TOGGLE_CMD}' 切换单行/多行模式")
        print(f"在单行模式下可输入 '{self.MULTILINE_CMD}' 临时进入多行模式")
        if len(self.agent_configs) > 1:
            print(f"输入 {self._format_agent_switch_hint()} 在不同 agent 配置间切换")
        print(f"当前 Agent: {self.active_agent}")
        print("=" * 60 + "\n")
        
        while True:
            try:
                user_input = await self._read_user_input()

                if not user_input:
                    continue
                
                if user_input.lower() == self.MODE_TOGGLE_CMD:
                    self._toggle_input_mode()
                    continue
                
                # 处理命令
                normalized_input = user_input.lower()

                if normalized_input in self.agent_switch_commands:
                    target_agent = self.agent_switch_commands[normalized_input]
                    if target_agent == self.active_agent:
                        print(f"⚠️ 已经在 {target_agent}，无需切换。\n")
                    else:
                        self.switch_agent(target_agent)
                    continue

                if normalized_input in ['exit', 'quit']:
                    print("\n再见！")
                    break
                
                if normalized_input == 'reset':
                    self.conversation_id = None
                    self.conversation_ids[self.active_agent] = None
                    print("✓ 对话已重置\n")
                    continue
                
                if normalized_input == 'config':
                    self.display_config_info()
                    continue
                
                # 调用 API
                try:
                    response, response_time = await self.call_dify_api(user_input)
                    self.process_response(response, response_time)
                except Exception as e:
                    print(f"\n❌ 错误: {str(e)}\n")
            
            except KeyboardInterrupt:
                print("\n\n程序被用户中断")
                break
            except EOFError:
                print("\n\n再见！")
                break
            except Exception as e:
                print(f"\n❌ 未预期的错误: {str(e)}\n")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Dify Agent 测试工具 - 用于测试 Dify agent 的意图识别功能"
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径（默认: 自动搜索当前目录）'
    )
    parser.add_argument(
        '--config2',
        type=str,
        default=None,
        help='第二个 agent 的配置文件路径（可选）'
    )
    
    args = parser.parse_args()
    
    # 创建测试器并运行
    config_paths = resolve_config_paths(args.config, args.config2)
    tester = DifyAgentTester(config_paths=config_paths)
    tester.load_config()
    tester.display_config_info()
    
    await tester.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
