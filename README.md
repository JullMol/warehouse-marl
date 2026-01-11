# 🏭 Warehouse MARL - AI Fleet Control

An advanced Multi-Agent Reinforcement Learning (MARL) simulation interface for warehouse robot fleet management. Built with **Golang (Wails)** and **Svelte**, featuring a modern Cyberpunk/Industrial aesthetic.

## ✨ Features

- **Interactive Grid Editor**: Design warehouse layouts with racks, robots, and tasks.
- **Real-time Simulation**: Visualize robot movements, task completion, and fleet coordination.
- **AI Bridge**: Connects to Python-based Reinforcement Learning models via HTTP/Websockets.
- **Cyberpunk UI**: Premium dark-mode interface with glassmorphism and neon accents.
- **Fleet Statistics**: Monitor utility, task completion rates, and active agents.

## 🚀 Getting Started

### Prerequisites

- **Go** 1.21+
- **Node.js** 18+
- **Wails** (`go install github.com/wailsapp/wails/v2/cmd/wails@latest`)

### Running Locally

```bash
# Clone the repository
git clone https://github.com/your-username/warehouse-marl.git

# Enter the UI directory
cd warehouse_ui

# Run in Development Mode
wails dev
```

### Building for Production

```bash
wails build -platform windows/amd64
```
The executable will be in `build/bin/warehouse_ui.exe`.

## 🧠 AI Integration

To run the AI brain backend:
1. Navigate to `ai_server/`.
2. Install requirements using Python.
3. Run `python app.py` (or your entry point).
4. Connect via the "Connect" button in the UI.

## 🛠️ Tech Stack

- **Backend**: Go (Wails Framework)
- **Frontend**: Svelte, CSS3 (Variables + Flex/Grid)
- **Design**: "Cyberpunk Industrial" Theme

