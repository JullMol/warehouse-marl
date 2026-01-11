<script>
  import { onMount } from 'svelte';
  import { CheckAIConnection, GetDefaultLayout, InitAIEnv, GetRobotAction, SaveLayout } from '../wailsjs/go/main/App';

  let layout = null;
  let aiConnected = false;
  let simRunning = false;
  let robotPositions = [];
  let targets = [];
  let step = 0;
  let editMode = 'rack';
  let statusMessage = 'Initializing...';
  let intervalId = null;
  let gridSize = 20;
  let totalWorkload = 0;

  const CELL_SIZE = 32;
  const COLORS = {
    floor: '#1e293b',
    rack: '#f59e0b',
    robot: ['#06b6d4', '#8b5cf6', '#ec4899', '#22c55e'],
    target: '#22c55e',
  };

  const EDIT_MODES = [
    { id: 'rack', icon: '📦', label: 'Rak' },
    { id: 'robot', icon: '🤖', label: 'Robot' },
    { id: 'task', icon: '🎯', label: 'Task' },
    { id: 'erase', icon: '🧹', label: 'Hapus' },
  ];

  onMount(async () => {
    try {
      console.log('Loading default layout...');
      layout = await GetDefaultLayout();
      console.log('Layout loaded:', layout);
      syncPositions();
      checkConnection();
    } catch (e) {
      console.error('Error loading layout:', e);
      statusMessage = '❌ Error loading layout';
    }
  });

  function syncPositions() {
    if (!layout) return;
    robotPositions = (layout.robots || []).map(r => [...r.spawn_pos]);
    targets = (layout.task_pool || []).map(t => t.pos);
    console.log('Synced positions:', { robotPositions, targets });
  }

  async function checkConnection() {
    try {
      const result = await CheckAIConnection();
      aiConnected = result.connected;
      statusMessage = aiConnected ? '🟢 AI Brain Connected' : '🔴 AI Offline';
    } catch {
      aiConnected = false;
      statusMessage = '🔴 AI Offline - Run bridge.py';
    }
  }

  function handleCellClick(row, col) {
    if (simRunning) return;
    if (row === 0 || row === gridSize-1 || col === 0 || col === gridSize-1) return;
    if (editMode === 'rack') {
      if (hasRobotAt(row, col) < 0 && !hasTaskAt(row, col)) {
        layout.map_data[row][col] = layout.map_data[row][col] === 0 ? 1 : 0;
        layout = layout;
      }
    } else if (editMode === 'robot') {
      if (layout.map_data[row][col] === 0 && hasRobotAt(row, col) < 0) {
        const newId = layout.robots.length;
        layout.robots = [...layout.robots, { id: newId, spawn_pos: [row, col] }];
        robotPositions = [...robotPositions, [row, col]];
        statusMessage = `🤖 Robot ${newId} ditempatkan`;
      }
    } else if (editMode === 'task') {
      if (layout.map_data[row][col] === 0 && hasRobotAt(row, col) < 0 && !hasTaskAt(row, col)) {
        const newTask = { item_id: `ITEM_${layout.task_pool.length}`, pos: [row, col] };
        layout.task_pool = [...layout.task_pool, newTask];
        targets = [...targets, [row, col]];
        statusMessage = `🎯 Task ditambahkan`;
      }
    } else if (editMode === 'erase') {
      console.log(`Erase at [${row},${col}]`);
      const robotIdx = robotPositions.findIndex(p => p[0] === row && p[1] === col);
      console.log(`Robot index: ${robotIdx}`);
      if (robotIdx >= 0) {
        const newRobots = layout.robots.filter((_, i) => i !== robotIdx);
        const newPositions = robotPositions.filter((_, i) => i !== robotIdx);
        layout.robots = newRobots.map((r, i) => ({ ...r, id: i }));
        robotPositions = [...newPositions];
        layout = {...layout};
        console.log('After delete - robotPositions:', robotPositions);
        statusMessage = `🧹 Robot dihapus`;
        return;
      }
      const taskIdx = targets.findIndex(t => t[0] === row && t[1] === col);
      console.log(`Task index: ${taskIdx}`);
      if (taskIdx >= 0) {
        const newTasks = layout.task_pool.filter((_, i) => i !== taskIdx);
        const newTargets = targets.filter((_, i) => i !== taskIdx);
        layout.task_pool = newTasks;
        targets = [...newTargets];
        layout = {...layout};
        console.log('After delete - targets:', targets);
        statusMessage = `🧹 Task dihapus`;
        return;
      }
      if (layout.map_data[row][col] === 1) {
        layout.map_data[row][col] = 0;
        layout = {...layout};
        statusMessage = `🧹 Rak dihapus`;
      }
    }
  }

  async function startSimulation() {
    if (!aiConnected) {
      statusMessage = '⚠️ Connect AI first!';
      return;
    }
    if (layout.robots.length === 0) {
      statusMessage = '⚠️ Tambahkan robot dulu!';
      return;
    }
    if (layout.task_pool.length === 0) {
      statusMessage = '⚠️ Tambahkan task dulu!';
      return;
    }
    await SaveLayout(layout, 'simulation.json');
    await InitAIEnv('../data/layouts/simulation.json');
    robotPositions = layout.robots.map(r => [...r.spawn_pos]);
    step = 0;
    simRunning = true;
    statusMessage = '▶️ Simulation Running...';
    runSimLoop();
  }

  async function runSimLoop() {
    let completedCount = 0;
    intervalId = setInterval(async () => {
      if (!simRunning) {
        clearInterval(intervalId);
        return;
      }
      completedCount = 0;
      totalWorkload = 0;
      for (let i = 0; i < robotPositions.length; i++) {
        try {
          const result = await GetRobotAction(i, robotPositions[i], layout.map_data);
          if (result.completed) {
            completedCount++;
            if (result.message) console.log(result.message);
            continue;
          }
          const action = result.action;
          if (result.target) targets[i] = result.target;
          let [y, x] = robotPositions[i];
          if (action === 1) y--;
          else if (action === 2) y++;
          else if (action === 3) x--;
          else if (action === 4) x++;
          if (y >= 0 && y < gridSize && x >= 0 && x < gridSize && layout.map_data[y][x] === 0) {
            robotPositions[i] = [y, x];
          }
          if (result.remaining_tasks !== undefined) {
             totalWorkload += result.remaining_tasks;
          }
        } catch (e) {
          console.error('GetRobotAction error:', e);
        }
      }
      robotPositions = [...robotPositions];
      targets = [...targets];
      step++;
      if (completedCount >= robotPositions.length) {
        stopSimulation();
        statusMessage = '✅ All tasks completed!';
      }
    }, 150);
  }

  function stopSimulation() {
    simRunning = false;
    if (intervalId) clearInterval(intervalId);
    statusMessage = '⏹️ Simulation Stopped';
  }

  function resetSimulation() {
    stopSimulation();
    robotPositions = layout.robots.map(r => [...r.spawn_pos]);
    targets = layout.task_pool.map(t => t.pos);
    step = 0;
    statusMessage = '🔄 Reset Complete';
  }

  function clearAll() {
    if (simRunning) return;
    for (let i = 1; i < gridSize-1; i++) {
      for (let j = 1; j < gridSize-1; j++) {
        layout.map_data[i][j] = 0;
      }
    }
    layout.robots = [];
    layout.task_pool = [];
    robotPositions = [];
    targets = [];
    layout = layout;
    statusMessage = '🧹 Semua dihapus';
  }

  function hasRobotAt(row, col) {
    return robotPositions.findIndex(p => p[0] === row && p[1] === col);
  }

  function hasTaskAt(row, col) {
    return targets.some(t => t[0] === row && t[1] === col);
  }

  function getTasksPerRobot() {
    if (!layout || !layout.robots || layout.robots.length === 0) return 0;
    return Math.ceil(layout.task_pool.length / layout.robots.length);
  }

  $: loading = layout === null;
</script>

<main>
  {#if loading}
  <div class="loading-screen">
    <div class="loader"></div>
    <p>Loading Warehouse...</p>
  </div>
  {:else}
  <aside class="sidebar glass">
    <div class="logo">
      <span class="icon">🏭</span>
      <h1>Warehouse MARL</h1>
      <p>Simulation Engine</p>
    </div>
    <div class="status-card glass glow">
      <div class="status-indicator" class:connected={aiConnected}></div>
      <span>{statusMessage}</span>
    </div>
    <div class="section">
      <h3>Edit Mode</h3>
      <div class="edit-modes">
        {#each EDIT_MODES as mode}
          <button
            class="mode-btn"
            class:active={editMode === mode.id}
            on:click={() => editMode = mode.id}
            disabled={simRunning}
          >
            <span class="mode-icon">{mode.icon}</span>
            <span>{mode.label}</span>
          </button>
        {/each}
      </div>
    </div>
    <div class="controls">
      <button class="btn primary" on:click={startSimulation} disabled={simRunning}>
        ▶️ Start Simulation
      </button>
      <button class="btn warning" on:click={stopSimulation} disabled={!simRunning}>
        ⏹️ Stop
      </button>
      <div class="btn-row">
        <button class="btn secondary" on:click={resetSimulation}>🔄 Reset</button>
        <button class="btn danger" on:click={clearAll} disabled={simRunning}>🗑️ Clear</button>
      </div>
      <button class="btn secondary" on:click={checkConnection}>🔌 Reconnect</button>
    </div>
    <div class="stats glass">
      <div class="stat">
        <span class="label">Step</span>
        <span class="value">{step}</span>
      </div>
      <div class="stat">
        <span class="label">Robots</span>
        <span class="value">{layout?.robots?.length || 0}</span>
      </div>
      <div class="stat">
        <span class="label">Tasks</span>
        <span class="value">{layout?.task_pool?.length || 0}</span>
      </div>
    </div>
    <div class="workload">
    <h4>Workload per Robot</h4>
    <div class="workload-val">{totalWorkload} tasks</div>
  </div>
    <div class="legend">
      <h3>Legend</h3>
      <div class="legend-item"><span class="box" style="background:{COLORS.floor}"></span>Floor</div>
      <div class="legend-item"><span class="box" style="background:{COLORS.rack}"></span>Rack</div>
      <div class="legend-item"><span class="box" style="background:{COLORS.robot[0]}"></span>Robot</div>
      <div class="legend-item"><span class="box" style="background:{COLORS.target}"></span>Target</div>
    </div>
  </aside>
  <section class="canvas-area">
    <div class="canvas-header">
      <h2>Warehouse Grid Editor</h2>
      <p>Mode: <strong>{EDIT_MODES.find(m => m.id === editMode)?.label}</strong> | Klik untuk edit</p>
    </div>
    {#if layout}
    {#key step + robotPositions.length + targets.length + JSON.stringify(layout.map_data)}
    <div class="grid-container glass glow">
      <div class="grid" style="--cols:{gridSize}; --cell:{CELL_SIZE}px">
        {#each layout.map_data as row, y}
          {#each row as cell, x}
            <div
              class="cell"
              class:rack={cell === 1}
              class:wall={y === 0 || y === gridSize-1 || x === 0 || x === gridSize-1}
              class:target={hasTaskAt(y, x)}
              on:click={() => handleCellClick(y, x)}
            >
              {#if hasRobotAt(y, x) >= 0}
                {@const idx = hasRobotAt(y, x)}
                <div class="robot" style="background: linear-gradient(135deg, {COLORS.robot[idx % 4]}, {COLORS.robot[(idx+1) % 4]}); box-shadow: 0 0 12px {COLORS.robot[idx % 4]}80;">
                  R{idx}
                </div>
              {/if}
              {#if hasTaskAt(y, x) && hasRobotAt(y, x) < 0}
                <div class="target-marker">T</div>
              {/if}
            </div>
          {/each}
        {/each}
      </div>
    </div>
    {/key}
    {/if}
  </section>
  {/if}
</main>

<style>
  main {
    display: flex;
    height: 100vh;
    gap: 20px;
    padding: 20px;
  }
  .sidebar {
    width: 300px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow-y: auto;
  }
  .logo {
    text-align: center;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .logo .icon { font-size: 40px; display: block; margin-bottom: 6px; }
  .logo h1 {
    font-size: 1.3rem;
    background: linear-gradient(135deg, var(--accent), #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .logo p { color: var(--text-secondary); font-size: 0.8rem; }
  .status-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    font-size: 0.8rem;
  }
  .status-indicator {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--danger);
    box-shadow: 0 0 8px var(--danger);
  }
  .status-indicator.connected {
    background: var(--success);
    box-shadow: 0 0 8px var(--success);
  }
  .section h3 { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 10px; }
  .edit-modes {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .mode-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: 10px 8px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text-secondary);
    font-size: 0.75rem;
  }
  .mode-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .mode-btn.active {
    background: linear-gradient(135deg, var(--accent), #0ea5e9);
    color: white;
    border-color: var(--accent);
  }
  .mode-icon { font-size: 1.2rem; }
  .controls { display: flex; flex-direction: column; gap: 8px; }
  .btn {
    padding: 10px 14px;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    font-size: 0.8rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .btn.primary { background: linear-gradient(135deg, var(--accent), #0ea5e9); color: white; }
  .btn.warning { background: linear-gradient(135deg, var(--warning), #ea580c); color: white; }
  .btn.secondary { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border); }
  .btn.danger { background: linear-gradient(135deg, var(--danger), #dc2626); color: white; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
  .btn-row { display: flex; gap: 8px; }
  .btn-row .btn { flex: 1; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; padding: 12px; }
  .stat { text-align: center; }
  .stat .label { display: block; font-size: 0.7rem; color: var(--text-secondary); margin-bottom: 2px; }
  .stat .value { font-size: 1.3rem; font-weight: 700; color: var(--accent); }
  .workload { padding: 12px; text-align: center; }
  .workload h4 { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 6px; }
  .workload-val { font-size: 1.5rem; font-weight: 700; color: var(--success); }
  .legend { margin-top: auto; }
  .legend h3 { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 10px; }
  .legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; margin-bottom: 6px; }
  .legend-item .box { width: 16px; height: 16px; border-radius: 4px; }
  .canvas-area { flex: 1; display: flex; flex-direction: column; gap: 12px; }
  .canvas-header h2 { font-size: 1.1rem; }
  .canvas-header p { color: var(--text-secondary); font-size: 0.8rem; }
  .canvas-header strong { color: var(--accent); }
  .grid-container { flex: 1; display: flex; align-items: center; justify-content: center; padding: 20px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(var(--cols), var(--cell));
    gap: 1px;
    background: var(--border);
  }
  .cell {
    width: var(--cell); height: var(--cell);
    background: #1e293b;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.1s ease;
    position: relative;
  }
  .cell:hover { filter: brightness(1.3); }
  .cell.rack { background: #f59e0b; }
  .cell.wall { background: #475569; cursor: not-allowed; }
  .cell.target { background: rgba(34, 197, 94, 0.25); }
  .robot {
    width: 24px; height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.6rem;
    font-weight: 700;
    color: white;
    z-index: 10;
    animation: pulse 1.5s ease-in-out infinite;
  }
  .target-marker {
    width: 18px; height: 18px;
    border-radius: 4px;
    background: var(--success);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.6rem;
    font-weight: 700;
    color: white;
  }
  @keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
  }
  .loading-screen {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    gap: 20px;
  }
  .loading-screen p {
    color: var(--text-secondary);
    font-size: 1rem;
  }
  .loader {
    width: 50px;
    height: 50px;
    border: 4px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
