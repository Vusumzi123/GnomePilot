"""Tests for skill unavailable handlers — unit tests, no Ollama needed."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.vision import handler as vision_handler
from src.tools.application import handler as application_handler
from src.tools.package_manager import handler as package_manager_handler
from src.tools.web_search import handler as web_search_handler
from src.tools.window_manager import handler as window_manager_handler


async def test_all_handlers_return_message():
    handlers = {
        "vision": vision_handler,
        "application": application_handler,
        "package_manager": package_manager_handler,
        "web_search": web_search_handler,
        "window_manager": window_manager_handler,
    }
    for name, fn in handlers.items():
        result = await fn({}, None)
        msgs = result.get("messages", [])
        assert len(msgs) == 1, f"{name}: expected 1 message, got {len(msgs)}"
        text = msgs[0].content
        assert len(text) > 20, f"{name}: message too short ({len(text)} chars)"
        assert "cannot" in text.lower() or "not enabled" in text.lower(), \
            f"{name}: message doesn't mention unavailability: {text!r}"
        print(f"  {name}: {text[:60]}...")


async def test_handlers_read_manifest_messages():
    """Handlers load their unavailable_message from manifest.toml."""
    import tomllib

    for handler_fn, skill_name, expected_phrase in [
        (vision_handler, "vision", "vision/screenshot"),
        (application_handler, "application", "application tools"),
        (package_manager_handler, "package_manager", "package management"),
        (web_search_handler, "web_search", "web search"),
        (window_manager_handler, "window_manager", "window management"),
    ]:
        result = await handler_fn({}, None)
        text = result["messages"][0].content
        # Verify the manifest.toml message is being used (not the hardcoded fallback)
        assert expected_phrase in text.lower(), \
            f"{skill_name}: expected phrase '{expected_phrase}' in message: {text!r}"
    print("  handlers read manifest messages: OK")


async def test_handler_is_not_re_entrant():
    """Each handler call returns fresh AIMessage — no shared state."""
    r1 = await vision_handler({}, None)
    r2 = await vision_handler({}, None)
    assert r1["messages"][0].content == r2["messages"][0].content
    assert r1["messages"][0] is not r2["messages"][0]  # different objects
    print("  handler returns fresh messages: OK")


async def main():
    await test_all_handlers_return_message()
    await test_handlers_read_manifest_messages()
    await test_handler_is_not_re_entrant()
    print()
    print("=" * 50)
    print("All handler tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
