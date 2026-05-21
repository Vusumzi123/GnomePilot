# OpenCode Prompt: CachyOS GNOME Local AI Assistant

**System Context for the Coding Agent:**
You are an expert systems programmer and AI engineer tasked with building a fully local, voice-responsive OS assistant for an Arch-based Linux distribution (CachyOS) running the GNOME desktop environment on Wayland. The system must use an Orchestrator-Worker sub-agent architecture leveraging the Model Context Protocol (MCP) for tool execution. 

All machine learning models must be capable of running locally via Ollama and fit comfortably within a 12GB VRAM GPU environment.

The user will review and approve the codebase after each defined phase. Do not proceed to the next phase until the user explicitly approves the current phase's tests.

---

## Architecture Requirements

* **Language:** Python 3.11+
* **Orchestrator:** LangChain or AutoGen (Python) to route intents via function calling.
* **Audio/Voice:** OpenWakeWord for wake word detection, Whisper (small/base) for STT, Piper TTS for fast local speech generation.
* **Vision:** `grim` (Wayland screenshot tool) + `llava:7b` via Ollama.
* **LLM:** `llama3:8b-instruct` (or similar 8B model via Ollama) for the core orchestrator.
* **Tooling Standard:** Model Context Protocol (MCP) for system execution.
* **Window Management:** GNOME Wayland requires a custom DBus/GNOME Extension bridge, as standard X11 tools (`wmctrl`) will not work.

---

## Phase 1: Core Orchestrator and Voice Foundation

**Task 1.1: Environment & Orchestrator Setup**
* Initialize a Python project with `poetry` or `venv`.
* Set up the main Orchestrator loop using LangChain/AutoGen that connects to a local Ollama instance (running `llama3:8b`).
* Implement a simple command-line interface to pass text to the Orchestrator and receive text back.

**Task 1.2: Voice Integration (TTS & STT)**
* Integrate `piper-tts` for text-to-speech output. Write a function that takes the Orchestrator's text response and plays it via standard Linux audio (ALSA/PulseAudio/PipeWire).
* *(Optional for Phase 1, but prepare architecture):* Stub out the Speech-to-Text (STT) input function.

**Phase 1 Review Gate:**
* Test 1: Run the script, input "Hello system", and verify the LLM responds appropriately in text.
* Test 2: Verify the response is spoken audibly using Piper TTS.
* *Pause and wait for user approval.*

---

## Phase 2: System Management Sub-Agents (MCP Integration)

**Task 2.1: Implement the MCP Client**
* Integrate an MCP client into the Orchestrator to allow secure, standardized tool execution.

**Task 2.2: Application Agent (Open/Close)**
* Implement an MCP tool/skill to find and launch applications by parsing `/usr/share/applications` `.desktop` files (using `gtk-launch` or `gio open`).
* Implement an MCP tool to close applications gracefully, falling back to `killall` or `pkill` if necessary.

**Task 2.3: Package Manager Agent**
* Implement an MCP tool that interacts with `pacman` and `yay`/`paru`. 
* It should support searching for a package and installing it. (Assume `sudoers` is configured to allow pacman without a password for this script, or use `pkexec`).

**Phase 2 Review Gate:**
* Test 1: Prompt: "Open Firefox." Verify the Orchestrator calls the App Agent and Firefox launches.
* Test 2: Prompt: "Close Firefox." Verify the browser is terminated.
* Test 3: Prompt: "Install htop." Verify the Package Agent executes the Arch package manager successfully.
* *Pause and wait for user approval.*

---

## Phase 3: Spatial Awareness & Vision (Wayland/GNOME specific)

**Task 3.1: The Vision Agent**
* Implement a Python skill that uses the `grim` command-line tool to capture a screenshot to a temporary `.png` file.
* Pass this image path to Ollama running a local Vision Language Model (`llava:7b` or `minicpm-v`).
* Return the VLM's text analysis to the Orchestrator.

**Task 3.2: The GNOME Window Agent (DBus Bridge)**
* *Critical Wayland Constraint:* Since `wmctrl` fails on GNOME Wayland, write a minimalist GNOME Shell Extension (JavaScript) that exposes a DBus interface (e.g., `org.gnome.Shell.Extensions.Assistant`).
* The extension must include a method `MoveWindowToWorkspace(appName, workspaceIndex)`.
* Write the Python MCP tool to send DBus messages to this extension using `pydbus` or `dbus-python`.

**Phase 3 Review Gate:**
* Test 1: Prompt: "What is on my screen?" Verify `grim` fires, LLaVA processes the image, and the Orchestrator speaks the summary.
* Test 2: Prompt: "Move the terminal to workspace 2." Verify the DBus message fires and GNOME Mutter shifts the window.
* *Pause and wait for user approval.*

---

## Phase 4: Integration, Autonomy, and Refinement

**Task 4.1: Chaining & Sub-agent Routing**
* Refine the Orchestrator's system prompt so it correctly chains multiple tools. 
* Implement logic for the Orchestrator to decide *which* sub-agent to invoke without hardcoded if/else statements (rely on LLM function-calling capabilities).

**Task 4.2: Continuous Listening (Optional but recommended)**
* Implement the continuous listening loop using OpenWakeWord (e.g., "Hey Computer") and Whisper to stream voice directly into the Orchestrator's prompt queue.

**Phase 4 Review Gate:**
* Final Integration Test: Speak/Type: "Take a look at my screen, tell me what app is open, and then move it to workspace 3." 
* Verify the Orchestrator coordinates the Vision Agent and Window Agent sequentially and outputs a final voice confirmation.
