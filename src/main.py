import asyncio
import sys

from .pipeline import Pipeline
from .agents import Agents
from .router import Router
from .executor import Executor
from .history import History
from .formatter import Formatter
from .extractor import Extractor
from .voice import listen, speak
from .config import (debug_enabled, debug_verbose, debug_log_dir,
                     debug_retention_days, debug_rotation,
                     chat_history_size, history_max_tokens,
                     formatter_enabled, bootstrap_config_if_missing)


async def main_async() -> None:
    """Initialize the pipeline and run the interactive CLI/TTS loop.

    Accepts voice (stub) or text input, routes through the pipeline, prints and
    speaks the response. Handles Ctrl+C and normal exit gracefully.
    """
    # Auto-create config.json if missing (first run after fresh clone)
    bootstrap_config_if_missing()

    print("=" * 50)
    print("  CachyOS GNOME Local AI Assistant")
    print("  Models: config.json  |  TTS: Piper")
    print("  Subagents: general + vision  |  MCP tools")
    print("  Architecture: Pipeline (Enrich→Route→Build→Execute→Format→Store)")
    print("  Type 'exit' or 'quit' to stop.")
    print("=" * 50)

    if debug_enabled():
        from .debug import configure
        configure(
            verbose=debug_verbose(),
            log_dir=debug_log_dir(),
            retention_days=debug_retention_days(),
            rotation=debug_rotation(),
        )
        print("  Debug: ON    (stderr + {}/opencode_*.log)".format(debug_log_dir()))

    print()

    agents = Agents()
    await agents.start()

    pipeline = Pipeline(
        router=Router(llm=agents.general_llm, prompt=agents.router_prompt),
        executor=Executor(agents=agents),
        history=History(max_turns=chat_history_size(),
                        max_tokens=history_max_tokens()),
        formatter=Formatter(enabled=formatter_enabled()),
        extractor=Extractor(),
    )

    print("Initializing MCP tools... done.\n")

    try:
        while True:
            try:
                text = None

                stt_input = listen()
                if stt_input is not None:
                    text = stt_input
                    print(f"\n[Voice input]: {text}")
                else:
                    text = input("\nYou: ").strip()

                if not text:
                    continue

                if text.lower() in ("exit", "quit"):
                    speak("Goodbye!")
                    print("Goodbye!")
                    break

                print("Assistant: ", end="", flush=True)
                response = await pipeline.process(text)
                print(response)
                speak(response)

            except KeyboardInterrupt:
                print()
                break
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)

    finally:
        print("\nShutting down...")
        try:
            await asyncio.shield(agents.shutdown())
        except Exception:
            pass
        print("Done.")


def main() -> None:
    """Entry point: run the async CLI loop, suppressing double KeyboardInterrupt."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
