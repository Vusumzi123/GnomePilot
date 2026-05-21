import sys
from pathlib import Path

from loguru import logger
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

logger.remove(0)


def configure(verbose: bool = False, log_dir: str = "logs",
              retention_days: int = 7, rotation: str = "10 MB") -> None:
    """Bootstrap Loguru with two sinks: stderr (live) + file (persistent).

    Called once from main.py.  Safe to call multiple times — subsequent calls
    are no-ops because we only add a handler when the list is empty.
    """
    try:
        logger.remove(0)
    except ValueError:
        pass

    fmt = "<level>{level:7}</level> | <cyan>{name}</cyan> | <level>{message}</level>"
    logger.add(sys.stderr, format=fmt, level="DEBUG" if verbose else "INFO",
               colorize=True)

    log_path = Path(log_dir) / "opencode_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_path),
        level="DEBUG",
        rotation=rotation,
        retention=f"{retention_days} days",
        compression="gz",
        enqueue=True,
        diagnose=True,
    )


class DebugCallbackHandler(BaseCallbackHandler):
    """LangChain callback that logs LLM prompts and tool calls via Loguru."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def on_chat_model_start(self, serialized, messages, **kwargs):
        msgs = messages[0]
        total_chars = sum(len(str(m.content)) for m in msgs)
        model = serialized.get("kwargs", {}).get("model", "?")
        if self.verbose:
            for m in msgs:
                role = (
                    "system" if isinstance(m, SystemMessage)
                    else "human" if isinstance(m, HumanMessage)
                    else "ai"
                )
                logger.debug("=== {} ({} chars) ===", role, len(str(m.content)))
                for line in str(m.content).split("\n"):
                    logger.debug("  {}", line)
        else:
            logger.info("[LLM → {}] {} messages (~{} chars)", model, len(msgs), total_chars)

    def on_chat_model_end(self, response, **kwargs):
        content = response.generations[0][0].text.strip()
        logger.info("[LLM ←] {}…", content[:200].replace("\n", " "))

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = serialized.get("name", "?")
        logger.info("[TOOL →] {}({})", name, str(input_str)[:200])

    def on_tool_end(self, output, **kwargs):
        logger.info("[TOOL ←] {}", str(output)[:200].replace("\n", " "))
