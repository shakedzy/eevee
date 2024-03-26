import gradio as gr
from typing import List, Tuple, Generator, Set
from .chatbot import Chatbot
from .settings import Settings
from .package_types import Framework


class UI:
    def __init__(self, chatbot: Chatbot, available_frameworks: Set[Framework]) -> None:
        self.ui: gr.Blocks | None = None
        self.chatbot = chatbot
        self.available_frameworks = available_frameworks

    def __enter__(self) -> gr.Blocks:
        self.ui = self._build_ui()
        self.ui.launch(favicon_path=None, inbrowser=True, show_error=True)
        return self.ui

    def __exit__(self, *args) -> None:
        if self.ui:
            self.ui.close()

    def _get_list_of_models(self) -> List[str]:
        available_models: List[str] = list()
        for framework in self.available_frameworks:
            models: List[str] = Settings().models[framework]
            available_models += models
        return available_models

    def _add_user_message_to_chat(self, prompt: str, history: List[List[str | None]]) -> Tuple[str, List[List[str | None]]]:
        return '', history + [[prompt, None]]

    def _add_bot_message_to_chat(self, history: List[List[str | None]], model: str, temperature: float, as_json: bool, system_prompt: str) -> Generator:
        if as_json:
            generator = self.chatbot.get_json_response(history[-1][0] or '', system_prompt=system_prompt, model=model, temperature=temperature)
        else:
            generator = self.chatbot.get_stream_response(history[-1][0] or '', system_prompt=system_prompt, model=model, temperature=temperature)
        
        for token in generator:
            if token.startswith(self.chatbot.TOOL_TOKEN):
                gr.Info(f"Running tool: {token.strip(self.chatbot.TOOL_TOKEN)}")
            else:
                if history[-1][1] is None:
                    history[-1][1] = ''
                history[-1][1] += token
                yield history 

    def _build_ui(self) -> gr.Blocks:
        available_models = self._get_list_of_models()
        preferred_model = Settings().defaults.model
        if preferred_model not in available_models:
            preferred_model = available_models[0]
        preferred_temperature = min(1., max(0., Settings().defaults.temperature))

        with gr.Blocks(title="Eevee") as ui:
            with gr.Row():
                with gr.Column(scale=10):
                    gr.Markdown("# Eevee")
                with gr.Column(scale=1):
                    new_chat = gr.Button("New Chat")
            
            with gr.Row():
                with gr.Column(scale=1, variant='panel'):
                    with gr.Group():
                        model = gr.Dropdown(label="Model", interactive=True, choices=available_models, value=preferred_model)  # type: ignore
                        with gr.Accordion(label="System Prompt", open=False):
                            system_prompt = gr.TextArea(value="You are a helpful AI assistance named Bruno, and your task is to assist the user with all its requests in the best way possible", container=False, interactive=True, lines=10)
                        temperature = gr.Slider(label="Temperature", minimum=0., maximum=1., step=.01, value=preferred_temperature)
                        force_json = gr.Checkbox(label="Force JSON", value=False, interactive=True)
                    gr.Markdown("------")
                    load_chat = gr.UploadButton("Load Chat")

                with gr.Column(scale=10):
                    chat = gr.Chatbot(show_label=False, show_copy_button=True, height='80vh')
                    with gr.Row():
                        undo_last = gr.Button("Undo Last", variant='stop')
                        msg = gr.Textbox(label="Prompt (Press Enter to Send)", show_label=False, scale=9, container=False)
                        submit = gr.Button("Submit", variant='primary', scale=1)
                        stop = gr.Button("🟥 Stop", variant='stop', scale=1, visible=False)

            submit.click(
                self._add_user_message_to_chat, [msg, chat], [msg, chat]
            ).then(
                self._add_bot_message_to_chat, [chat, model, temperature, force_json, system_prompt], chat
            )
            msg.submit(
                self._add_user_message_to_chat, [msg, chat], [msg, chat]
            ).then(
                self._add_bot_message_to_chat, [chat, model, temperature, force_json, system_prompt], chat
            )

        return ui
    