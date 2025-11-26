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
from typing import Dict, Any, Optional, Tuple
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


class DifyAgentTester:
    """Dify Agent 测试器"""
    MULTILINE_CMD = ":paste"
    MULTILINE_END = ":end"
    MULTILINE_CANCEL = ":cancel"
    MODE_TOGGLE_CMD = ":chmod"
    
    def __init__(self, config_path: str = "config.json"):
        """
        初始化测试器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.conversation_id: Optional[str] = None
        self.timeout = 60  # 60秒超时
        self.multiline_mode = True
        self._multiline_hint_shown = False
        self._prompt_session = self._create_prompt_session()

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
        
    def load_config(self) -> None:
        """加载配置文件"""
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            print(f"错误: 配置文件不存在: {self.config_path}")
            print(f"请创建配置文件或使用 --config 参数指定配置文件路径")
            sys.exit(1)
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except json.JSONDecodeError as e:
            print(f"错误: 配置文件格式错误: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"错误: 读取配置文件失败: {e}")
            sys.exit(1)
        
        # 验证必需字段
        required_fields = ['api_key', 'dify_base_url', 'timezone', 'user']
        missing_fields = [field for field in required_fields if field not in self.config]
        
        if missing_fields:
            print(f"错误: 配置文件缺少必需字段: {', '.join(missing_fields)}")
            sys.exit(1)
        
        # 设置默认值
        self.config.setdefault('current_state', {})
        self.config.setdefault('user_memory', {})
        self.config.setdefault('behavioral_patterns', {})
        self.config.setdefault('insight', {})
        self.config.setdefault('candidate_items', [])
        
        print("✓ 配置文件加载成功")
    
    def display_config_info(self) -> None:
        """显示配置信息（隐藏敏感信息）"""
        print("\n" + "=" * 60)
        print("配置信息:")
        print("-" * 60)
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
        
        print(f"\n正在调用 Dify API...")
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
        raw_line = await self._prompt_line("请输入 user_input (或输入命令): ")
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
            self._multiline_hint_shown = True

        lines = []
        if initial_content:
            lines.append(initial_content)

        first_prompt = not lines

        while True:
            prompt_text = "请输入 user_input (多行模式): " if first_prompt else "... "
            line = await self._prompt_line(prompt_text)
            stripped = line.strip()
            normalized = stripped.lower()

            if not lines and normalized in {'exit', 'quit', 'reset', 'config', self.MODE_TOGGLE_CMD}:
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
                if user_input.lower() in ['exit', 'quit']:
                    print("\n再见！")
                    break
                
                if user_input.lower() == 'reset':
                    self.conversation_id = None
                    print("✓ 对话已重置\n")
                    continue
                
                if user_input.lower() == 'config':
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
        default='config.json',
        help='配置文件路径（默认: config.json）'
    )
    
    args = parser.parse_args()
    
    # 创建测试器并运行
    tester = DifyAgentTester(config_path=args.config)
    tester.load_config()
    tester.display_config_info()
    
    await tester.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
