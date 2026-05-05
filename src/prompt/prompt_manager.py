from collections.abc import Callable, Coroutine
from pathlib import Path
from string import Formatter
from typing import Any, Optional

import inspect

from src.common.logger import get_logger
from src.common.prompt_i18n import list_prompt_templates, load_prompt


logger = get_logger("Prompt")

_LEFT_BRACE = chr(0xFDE9)
_RIGHT_BRACE = chr(0xFDEA)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = PROJECT_ROOT / "prompts"
DATA_DIR = PROJECT_ROOT / "data"
CUSTOM_PROMPTS_DIR = DATA_DIR / "custom_prompts"
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
CUSTOM_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
SUFFIX_PROMPT = ".prompt"


class Prompt:
    def __init__(self, prompt_name: str, template: str) -> None:
        self.prompt_name = prompt_name
        self.template = template
        self.prompt_render_context: dict[str, Callable[[str], str | Coroutine[Any, Any, str]]] = {}
        self._is_cloned = False
        self.__post_init__()

    def add_context(self, name: str, func_or_str: Callable[[str], str | Coroutine[Any, Any, str]] | str) -> None:
        if name in self.prompt_render_context:
            raise KeyError(f"Context function name '{name}' 已存在于 Prompt '{self.prompt_name}' 中")
        if isinstance(func_or_str, str):

            def tmp_func(_: str) -> str:
                return func_or_str

            render_function = tmp_func
        else:
            render_function = func_or_str
        self.prompt_render_context[name] = render_function

    def clone(self) -> "Prompt":
        return Prompt(self.prompt_name, self.template)

    @property
    def is_cloned(self) -> bool:
        return self._is_cloned

    def mark_as_cloned(self) -> None:
        self._is_cloned = True

    def __post_init__(self) -> None:
        if not self.prompt_name:
            raise ValueError("prompt_name 不能为空")
        if not self.template:
            raise ValueError("template 不能为空")
        tmp = self.template.replace("{{", _LEFT_BRACE).replace("}}", _RIGHT_BRACE)
        if "{}" in tmp:
            raise ValueError(r"模板中不允许使用未命名的占位符 '{}'")


class PromptManager:
    def __init__(self) -> None:
        self.prompts: dict[str, Prompt] = {}
        """存储 Prompt 实例，禁止直接从外部访问，否则将引起不可知后果"""
        self._context_construct_functions: dict[str, tuple[Callable[[str], str | Coroutine[Any, Any, str]], str]] = {}
        """存储上下文构造函数及其所属模块"""
        self._formatter = Formatter()  # 仅用来解析模板
        """模板解析器"""
        self._prompt_to_save: set[str] = set()
        """需要保存的 Prompt 名称集合"""

    def add_prompt(self, prompt: Prompt, need_save: bool = False) -> None:
        """
        添加一个新的 Prompt 实例

        Args:
            prompt (Prompt): 要添加的 Prompt 实例
            need_save (bool): 是否需要保存该 Prompt，默认为 False
        Raises:
            KeyError: 如果 Prompt 名称已存在则引发该异常
        """
        if prompt.prompt_name in self.prompts or prompt.prompt_name in self._context_construct_functions:
            # 确保名称无冲突
            raise KeyError(f"Prompt name '{prompt.prompt_name}' 已存在")
        self.prompts[prompt.prompt_name] = prompt
        if need_save:
            self._prompt_to_save.add(prompt.prompt_name)

    def remove_prompt(self, prompt_name: str) -> None:
        """
        移除一个已存在的 Prompt 实例
        Args:
            prompt_name (str): 要移除的 Prompt 名称
        Raises:
            KeyError: 如果 Prompt 名称不存在则引发该异常
        """
        if prompt_name not in self.prompts:
            raise KeyError(f"Prompt name '{prompt_name}' 不存在")
        del self.prompts[prompt_name]
        if prompt_name in self._prompt_to_save:
            self._prompt_to_save.remove(prompt_name)

    def replace_prompt(self, prompt: Prompt, need_save: bool = False) -> None:
        """
        替换一个已存在的 Prompt 实例
        Args:
            prompt (Prompt): 要替换的 Prompt 实例
            need_save (bool): 是否需要保存该 Prompt，默认为 False
        Raises:
            KeyError: 如果 Prompt 名称不存在则引发该异常
        """
        if prompt.prompt_name not in self.prompts:
            raise KeyError(f"Prompt name '{prompt.prompt_name}' 不存在，无法替换")
        self.prompts[prompt.prompt_name] = prompt
        if need_save:
            self._prompt_to_save.add(prompt.prompt_name)
        elif prompt.prompt_name in self._prompt_to_save:
            self._prompt_to_save.remove(prompt.prompt_name)

    def add_context_construct_function(self, name: str, func: Callable[[str], str | Coroutine[Any, Any, str]]) -> None:
        """
        添加一个上下文构造函数

        Args:
            name (str): 上下文名称
            func (Callable[[str], str | Coroutine[Any, Any, str]]): 构造函数，接受 Prompt 名称作为参数，返回字符串或返回字符串的协程
        Raises:
            KeyError: 如果上下文名称已存在则引发该异常
        """
        if name in self._context_construct_functions or name in self.prompts:
            raise KeyError(f"Construct function name '{name}' 已存在")
        # 获取调用栈
        frame = inspect.currentframe()
        if not frame:
            # 不应该出现的情况
            raise RuntimeError("无法获取调用栈")
        caller_frame = frame.f_back
        if not caller_frame:
            # 不应该出现的情况
            raise RuntimeError("无法获取调用栈的上一级")
        caller_module = caller_frame.f_globals.get("__name__", "unknown")
        if caller_module == "unknown":
            logger.warning("无法获取调用函数的模块名，使用 'unknown' 作为默认值")

        self._context_construct_functions[name] = func, caller_module

    def get_prompt(self, prompt_name: str) -> Prompt:
        """
        获取指定名称的 Prompt 实例的克隆

        Args:
            prompt_name (str): 要获取的 Prompt 名称
        Returns:
            return (Prompt): 指定名称的 Prompt 实例的克隆
        Raises:
            KeyError: 如果 Prompt 名称不存在则引发该异常
        """
        if prompt_name not in self.prompts:
            raise KeyError(f"Prompt name '{prompt_name}' 不存在")
        prompt = self.prompts[prompt_name].clone()
        prompt.mark_as_cloned()
        return prompt

    async def render_prompt(self, prompt: Prompt) -> str:
        """
        渲染一个 Prompt 实例

        Args:
            prompt (Prompt): 要渲染的 Prompt 实例
        Returns:
            return (str): 渲染后的字符串
        Raises:
            ValueError: 如果传入的 Prompt 实例不是通过 get_prompt 方法获取的克隆实例则引发该异常
        """
        if not prompt.is_cloned:
            raise ValueError(
                "只能渲染通过 PromptManager.get_prompt 方法获取的 Prompt 实例，你可能对原始实例进行了修改和渲染操作"
            )
        return await self._render(prompt)

    async def _render(
        self,
        prompt: Prompt,
        recursive_level: int = 0,
        additional_construction_function_dict: dict[str, Callable[[str], str | Coroutine[Any, Any, str]]] | None = None,
    ) -> str:
        if additional_construction_function_dict is None:
            additional_construction_function_dict = {}
        prompt.template = prompt.template.replace("{{", _LEFT_BRACE).replace("}}", _RIGHT_BRACE)
        if recursive_level > 10:
            raise RecursionError("递归层级过深，可能存在循环引用")
        field_block = {field_name for _, field_name, _, _ in self._formatter.parse(prompt.template) if field_name}
        rendered_fields: dict[str, str] = {}
        for field_name in field_block:
            if field_name in self.prompts:
                nested_prompt = self.get_prompt(field_name)
                merged_context = additional_construction_function_dict | prompt.prompt_render_context
                rendered_fields[field_name] = await self._render(
                    nested_prompt,
                    recursive_level + 1,
                    merged_context,
                )
            elif field_name in prompt.prompt_render_context:
                # 优先使用内部构造函数
                func = prompt.prompt_render_context[field_name]
                rendered_fields[field_name] = await self._get_function_result(
                    func,
                    prompt.prompt_name,
                    field_name,
                    is_prompt_context=True,
                )
            elif field_name in self._context_construct_functions:
                # 随后查找全局构造函数
                func, module = self._context_construct_functions[field_name]
                rendered_fields[field_name] = await self._get_function_result(
                    func,
                    prompt.prompt_name,
                    field_name,
                    is_prompt_context=False,
                    module=module,
                )
            elif field_name in additional_construction_function_dict:
                # 最后查找额外传入的构造函数
                func = additional_construction_function_dict[field_name]
                rendered_fields[field_name] = await self._get_function_result(
                    func,
                    prompt.prompt_name,
                    field_name,
                    is_prompt_context=True,
                )
            else:
                raise KeyError(f"Prompt '{prompt.prompt_name}' 中缺少必要的内容块或构建函数: '{field_name}'")
        rendered_template = prompt.template.format(**rendered_fields)
        return rendered_template.replace(_LEFT_BRACE, "{").replace(_RIGHT_BRACE, "}")

    def save_prompts(self) -> None:
        """
        保存需要保存的 Prompt 实例到自定义目录，将清空未注册的自定义 Prompt 文件
        Raises:
            Exception: 如果在保存过程中出现任何文件操作错误则引发该异常
        """
        # 先清空自定义目录下的所有 Prompt 文件
        for prompt_file in CUSTOM_PROMPTS_DIR.glob(f"*{SUFFIX_PROMPT}"):
            try:
                prompt_file.unlink()
            except Exception as exc:
                logger.error(f"删除自定义 Prompt 文件 '{prompt_file}' 时出错，错误信息: {exc}")
                raise
        for prompt_name in self._prompt_to_save:
            prompt = self.prompts[prompt_name]
            file_path = CUSTOM_PROMPTS_DIR / f"{prompt_name}{SUFFIX_PROMPT}"
            try:
                file_path.write_text(prompt.template, encoding="utf-8")
            except Exception as exc:
                logger.error(f"保存 Prompt '{prompt_name}' 时出错，文件路径: '{file_path}'，错误信息: {exc}")
                raise

    def _load_prompt_template(self, prompt_name: str) -> tuple[str, bool]:
        custom_prompt_path = CUSTOM_PROMPTS_DIR / f"{prompt_name}{SUFFIX_PROMPT}"
        if custom_prompt_path.exists():
            return custom_prompt_path.read_text(encoding="utf-8"), True
        return load_prompt(prompt_name, prompts_root=PROMPTS_DIR), False

    def load_prompts(self) -> None:
        """
        加载全部 Prompt 实例，优先加载自定义目录下的文件，支持覆盖加载
        Raises:
            Exception: 如果在加载过程中出现任何文件操作错误则引发该异常
        """
        prompt_templates = list_prompt_templates(prompts_root=PROMPTS_DIR)
        for prompt_name, prompt_template in prompt_templates.items():
            try:
                template, need_save = self._load_prompt_template(prompt_name)
                self.add_prompt(Prompt(prompt_name=prompt_name, template=template), need_save=need_save)
            except Exception as exc:
                logger.error(f"加载 Prompt 文件 '{prompt_template.path}' 时出错，错误信息: {exc}")
                raise
        for prompt_file in CUSTOM_PROMPTS_DIR.glob(f"*{SUFFIX_PROMPT}"):
            if prompt_file.stem in prompt_templates:
                continue  # 已经加载过了，跳过
            try:
                template = prompt_file.read_text(encoding="utf-8")
                self.add_prompt(Prompt(prompt_name=prompt_file.stem, template=template), need_save=True)
            except Exception as exc:
                logger.error(f"加载自定义 Prompt 文件 '{prompt_file}' 时出错，错误信息: {exc}")
                raise

    async def _get_function_result(
        self,
        func: Callable[[str], str | Coroutine[Any, Any, str]],
        prompt_name: str,
        field_name: str,
        is_prompt_context: bool,
        module: Optional[str] = None,
    ) -> str:
        try:
            res = func(prompt_name)
            if isinstance(res, Coroutine):
                res = await res
            return res
        except Exception as exc:
            if is_prompt_context:
                logger.error(f"调用 Prompt '{prompt_name}' 内部上下文构造函数 '{field_name}' 时出错，错误信息: {exc}")
            else:
                logger.error(f"调用上下文构造函数 '{field_name}' 时出错，所属模块: '{module}'，错误信息: {exc}")
            raise


prompt_manager = PromptManager()
