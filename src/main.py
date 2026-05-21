import asyncio
import sys

from .orchestrator import Orchestrator
from .voice import listen, speak
from .config import debug_enabled, debug_verbose, debug_log_dir, debug_retention_days, debug_rotation


async def main_async() -> None:
    """Initialize the orchestrator and run the interactive CLI/TTS loop.
    
    Accepts voice (stub) or text input, routes to the orchestrator, prints and
    speaks the response. Handles Ctrl+C and normal exit gracefully.
    """
    print("=" * 50)
    print("  CachyOS GNOME Local AI Assistant")
    print("  Models: config.json  |  TTS: Piper")
    print("  Subagents: general + vision  |  MCP tools")
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

    orchestrator = Orchestrator()

    print("Initializing MCP tools...", end=" ", flush=True)
    await orchestrator.initialize()
    print("done.\n")

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
                response = await orchestrator.ainvoke(text)
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
            await asyncio.shield(orchestrator.close())
        except Exception:
            pass
        print("Done.")


def main() -> None:
    """Entry point: run the async CLI loop, suppressing double KeyboardInterrupt."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass  # Ctrl+C handled cleanly — already printed "Goodbye!"


if __name__ == "__main__":
    main()
