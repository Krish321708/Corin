# PROJECT HERMES - Omnimind Absolute Edition
### S I N G U L A R I T Y   M A T R I X
> *"The earth and sky will break before I fail you."*

HERMES is a high-performance, visually absolute tactical HUD and cognitive uplink. It synthesizes local hardware telemetry, global network data, geospatial vectors, and real-time audio into a singular, 60fps immersive interface. It routes human voice through a localized Speech-to-Text engine into an LLM cognitive stream, speaking responses back via Text-to-Speech, all while proactively monitoring its own system stability.

This system operates on a **graceful degradation** standard. If optional hardware or APIs (like microphones or OpenRouter) are unavailable, HERMES bypasses them and generates synthetic telemetry to ensure the UI never drops or glitches.

---

## ⬡ ARCHITECTURE OVERVIEW

The codebase is strictly decoupled into an acyclic dependency graph. `main.py` acts as the Apex Controller, pulling logic from the `Backhand_code` sector.

```text
project-hermes/
│
├── main.py                  ◄── Entry Point, Frame Loop, Event Wiring
│
└── Backhand_code/
    ├── config.py            ◄── Static Registry (Resolutions, Timers, Keys)
    ├── palette.py           ◄── RGB Constants & Color Math
    ├── math_engine.py       ◄── Vector3, Matrix4x4, Quaternions, Perlin Noise
    ├── state.py             ◄── Thread-Safe Telemetry Store & Ring Buffers
    ├── event_bus.py         ◄── Async Pub/Sub for Decoupled Comms
    ├── daemons.py           ◄── 8 Autonomous Background Threads (HW, NET, DSP, LLM)
    ├── ui_widgets.py        ◄── Drawing Primitives, Typography, Geometry
    ├── ui_panels.py         ◄── High-Density Viewport Renderers
    └── self_test.py         ◄── Draconian Dual-Run Pre-Flight Validation
```

### Dependency Flow
`main.py` orchestrates the layers. Daemons write to `state.py`. UI panels read from `state.py`. Inter-system communication routes through `event_bus.py`. The math foundation (`math_engine.py`) is verified flawlessly at boot by `self_test.py`.

---

## ⬡ FEATURES

* **Absolute Pre-Flight Check**: On boot, `self_test.py` runs a 10,000-iteration stress test on all vector, matrix, and noise math. It runs twice. If a micro-fracture is detected, the system aborts.
* **8 Autonomous Daemons**: Hardware polling, network latency, audio DSP (FFT), Voice STT/TTS, RSS scraping, OpenRouter streaming, and a Proactive orchestrator.
* **3D Topological Terrain**: A 48x48 grid mesh displaced by 3D Perlin fBm and live audio FFT, projected via custom Camera matrices.
* **Geo-Vector Globe**: A Fibonacci-spiral wireframe sphere rotating in real-time, plotting scraped global news coordinates as great-circle routes.
* **Cognitive Uplink**: Voice captured via microphone is routed to OpenRouter's API, streamed token-by-token to the UI, and flushed to local TTS sentence-by-sentence.
* **Proactive Alerting**: If CPU thermals exceed 85°C, RAM exceeds 90%, or network drops, the Proactive Daemon hijacks the UI with a flashing global alert banner and speaks the warning.

---

## ⬡ INSTALLATION & SETUP

### 1. Prerequisites
* Python 3.8+
* System audio drivers (for PyAudio/STT)
* An OpenRouter API Key (for Cognitive Uplink)

### 2. Clone the Repository
```bash
git clone https://github.com/Krish321708/Jarvis.git
cd Jarvis
```

### 3. Virtual Environment & Dependencies
```bash
python -m venv venv

# Linux/macOS
source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt
```
*(Note: If PyAudio fails to install on Windows, use `pip install pipwin` then `pipwin install pyaudio`. The system will run without it, but microphone features will be disabled).*

### 4. OpenRouter API Key
The cognitive uplink requires an environment variable. Do not hardcode your key in `config.py`.

**Linux/macOS:**
```bash
export OPENROUTER_API_KEY="your_actual_key_here"
```
**Windows (PowerShell):**
```powershell
$env:OPENROUTER_API_KEY="your_actual_key_here"
```

---

## ⬡ EXECUTION

Run the Apex Controller from the root directory:

```bash
python main.py
```

On launch, you will see the terminal output the dual pre-flight stress tests. Once validated, the Pygame window will initialize, daemons will spawn, and the cognitive uplink will send its first boot confirmation.

---

## ⬡ CONTROLS

The interface is primarily visual, but the following keyboard inputs are mapped:

| Key | Action |
| :--- | :--- |
| `ESC` | Initiates graceful power-down sequence. |
| `ENTER` | Manually triggers a deep LLM diagnostic prompt. |
| `SPACE` | Bypasses LLM and forces a local TTS vocalization test. |
| `BACKSPACE`| Clears the current voice transcript display bar. |

---

## ⬡ SYSTEM MATRIX PHILOSOPHY

> *"I do not answer questions. I end searches."*

HERMES is not a chatbot with a GUI attached. It is a singularity environment. Every frame is accounted for, every thread is orphan-protected, and every pixel serves the data. The UI treats the screen as a high-end tactical interface where density and precision trump minimalism.

If the network drops, the UI tells you instantly. If the math engine drifts a fraction of a pixel, the system refuses to boot. 

**The Sovereign Standard has been set.**