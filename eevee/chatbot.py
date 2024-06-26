import os
import traceback
from datetime import datetime
from typing import Set, Dict, List, Generator, Any, Tuple
from .messages import Messages, Message, ChatMessagePiece
from .tools import tools_params_definitions, tool_display_message
from .color_logger import get_logger
from .framework_models import get_model_framework
from .saved_chat import SavedChat
from .chat_connectors.connector_interface import Connector
from .chat_connectors.openai_connector import OpenAIConnector
from .chat_connectors.anthropic_connector import AnthropicConnector
from .chat_connectors.mistral_connector import MistralConnector
from .chat_connectors.deepseek_connector import DeepSeekConnector
from .chat_connectors.google_connector import GoogleConnector
from ._types import Framework
from . import ROOT_DIR


class Chatbot:
    def __init__(self, available_frameworks: Set[Framework]) -> None:
        if not available_frameworks:
            raise RuntimeError('No available frameworks found! Make sure you supplied API keys')

        self.clients: Dict[Framework, Connector] = dict()
        self.callables = {f.__name__: f for f in tools_params_definitions.keys()}
        self.tools = self._build_tools()
        self.messages = Messages()
        self.logger = get_logger()
        self.start_time = datetime.now()

        for framework in available_frameworks:
            match framework:
                case 'openai':
                    client = OpenAIConnector()
                case 'mistral':
                    client = MistralConnector()
                case 'anthropic':
                    client = AnthropicConnector()
                case 'deepseek':
                    client = DeepSeekConnector()
                case 'google':
                    client = GoogleConnector()
                case _:
                    raise ValueError(f'No connector defined for framework {framework}!')
            self.clients[framework] = client

    def _build_tools(self) -> List[Dict[str, Any]]:
        tools = list()
        for func, v in tools_params_definitions.items():
            params = {}
            required = []
            for p in v:
                params[p[0]] = p[1]
                if p[2]: 
                    required.append(p[0])

            tools.append({
                "type": "function",
                "function": {
                    "name": func.__name__,
                    "description": func.__doc__,
                    "parameters": {
                        "type": "object",
                        "properties": params
                    },
                    "required": required
                }
            })
        return tools 
    
    @property
    def saved_chats_dir(self) -> str:
        SAVED_CHATS_DIR = "saved_chats"
        directory = os.path.join(ROOT_DIR, SAVED_CHATS_DIR)
        if not os.path.exists(directory):
            os.makedirs(directory)
        return directory
    
    def reset_chat(self) -> None:
        self.messages = Messages()
        self.start_time = datetime.now()

    def delete_last_interaction(self) -> None:
        if self.messages.empty: return None
        self.messages.pop()
        last_message = self.messages[-1]
        while not last_message.displayed:
            if last_message.role == 'system' or self.messages.empty:
                break
            self.messages.pop()
            last_message = self.messages[-1]

    def _prepare_for_response(self, prompt: str, system_prompt: str) -> None:
        if self.messages.empty:
            self.messages.append("system", system_prompt)
        else:
            self.messages.edit(0, content=system_prompt)
        self.messages.append('user', prompt)      

    def get_stream_response(self, prompt: str, *, system_prompt: str, model: str, temperature: float) -> Generator[ChatMessagePiece, None, None]:        
        framework = get_model_framework(model)
        self._prepare_for_response(prompt=prompt, system_prompt=system_prompt)

        try:
            final_message = False
            while not final_message:
                final_message = True
                generator = self.clients[framework].get_streaming_response(model=model, temperature=temperature, messages=self.messages, tools=self.tools)
                for chat_piece in generator:
                    if chat_piece.tool_calls:
                        final_message = False
                        if self.messages[self.messages.last_message_index].role == 'assistant':
                            self.messages.update(self.messages.last_message_index, tool_calls=chat_piece.tool_calls)
                        else:
                            self.messages.append('assistant', content=None, tool_calls=chat_piece.tool_calls, model=model)
                        for tool_call in chat_piece.tool_calls:
                            yield ChatMessagePiece(info_message=tool_display_message(tool_call.function, **tool_call.arguments))
                            self.logger.info(f"Running tool {tool_call.function}: {str(tool_call.arguments)}", color='yellow')
                            tool_output = self.callables[tool_call.function](**tool_call.arguments)
                            self.logger.debug("Tool output:\n" + tool_output)
                            self.messages.append(role='tool', content=tool_output, tool_calls=[tool_call])
                    else:
                        if self.messages[self.messages.last_message_index].role == 'assistant':
                            self.messages.update(self.messages.last_message_index, content=chat_piece.content)
                        else:
                            self.messages.append('assistant', content=chat_piece.content, model=model)
                        chat_piece.model = model
                        yield chat_piece
        
        except Exception as e:
            self.logger.error(traceback.format_exc())
            yield ChatMessagePiece(content=f'❌ _**{e.__class__.__name__}:** {e}_')

    def get_json_response(self, prompt: str, *, system_prompt: str, model: str, temperature: float) -> Generator[ChatMessagePiece, None, None]:
        framework = get_model_framework(model)
        self._prepare_for_response(prompt=prompt, system_prompt=system_prompt)

        final_message = False
        while not final_message:
            final_message = True
            response = self.clients[framework].get_json_response(model=model, temperature=temperature, messages=self.messages, tools=self.tools)
            for chat_piece in response:
                if chat_piece.tool_calls:
                    final_message = False
                    self.messages.append(role='assistant', content=None, tool_calls=chat_piece.tool_calls, model=model)
                    for tool_call in chat_piece.tool_calls:
                        yield ChatMessagePiece(info_message=tool_display_message(tool_call.function, **tool_call.arguments))
                        self.logger.info(f"Running tool {tool_call.function}: {str(tool_call.arguments)}", color='yellow')
                        tool_output = self.callables[tool_call.function](**tool_call.arguments)
                        self.logger.debug("Tool output:\n" + tool_output)
                        self.messages.append(role='tool', content=tool_output, tool_calls=[tool_call])
                else:
                    self.messages.append(role='assistant', content=chat_piece.content, model=model)
                    chat_piece.model = model
                    yield chat_piece

    def export_chat(self) -> None:
        SavedChat(messages=self.messages, start_time=self.start_time, directory=self.saved_chats_dir).save_to_file()

    def load_chat(self, title: str, start_time: datetime) -> None:
        self.reset_chat()
        saved_chat = SavedChat.from_chat_title_and_time(title, start_time, directory=self.saved_chats_dir)
        self.messages = saved_chat.messages

    def get_displayed_messages(self) -> List[Message]:
        return [message for message in self.messages if message.displayed]
    
    def list_saved_chats(self) -> List[Tuple[str, datetime]]:
        chat_filenames = [f for f in os.listdir(self.saved_chats_dir) if os.path.isfile(os.path.join(self.saved_chats_dir, f)) and f.startswith(SavedChat.FILE_PREFIX) and f.endswith(SavedChat.FILE_SUFFIX)]
        saved_list = [SavedChat.filename_to_title_and_time(filename) for filename in chat_filenames]
        return sorted(saved_list, key=lambda t: t[1], reverse=True)
