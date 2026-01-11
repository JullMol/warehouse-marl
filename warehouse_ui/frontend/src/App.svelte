<script>
  import { onMount } from 'svelte';
  import { CheckAIConnection, GetDefaultLayout, InitAIEnv, GetRobotAction, SaveLayout } from '../wailsjs/go/main/App';

  // State
  let layout = null;
  let aiConnected = false;
  let simRunning = false;
  let robotPositions = [];
  let targets = []; // Array of [row, col]
  let step = 0;
  let editMode = 'rack'; // rack, robot, task, erase
  let statusMessage = 'SYSTEM INITIALIZING...';
  let intervalId = null;
  let gridSize = 20;
  let totalWorkload = 0;

  // Constants & Config
  const CELL_SIZE = 34; // Increased slightly
  
  // Theme Colors (mapped from style.css for JS logic)
  const COLORS = {
    rack: '#ffbf00',    // Amber
    robot: ['#00f0ff', '#7000ff', '#ff0055', '#00ff9d'], // Cyan, Purple, Red, Green
    target: '#00ff9d',  // Green
  };

  const EDIT_MODES = [
    { id: 'rack', label: 'RACK', icon: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z' }, // Box/Square
    { id: 'robot', label: 'BOT', icon: 'M12 2a2 2 0 0 1 2 2c0 .74-.4 1.38-1 1.72V7h-2v-.28c-.6-.34-1-.98-1-1.72a2 2 0 0 1 2-2zm-2 6h4v3h2v-1h2v6h-2v-2h-6v2H8V9h2V8zm4 7h-4v7h4v-7z' }, // Robot (simplified)
    { id: 'task', label: 'TASK', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z' }, // Check circle
    { id: 'erase', label: 'DEL', icon: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z' }, // Trash
  ];

  onMount(async () => {
    try {
      layout = await GetDefaultLayout();
      syncPositions();
      checkConnection();
    } catch (e) {
      console.error('Error loading layout:', e);
      statusMessage = '❌ LAYOUT LOAD ERROR';
    }
  });

  function syncPositions() {
    if (!layout) return;
    robotPositions = (layout.robots || []).map(r => [...r.spawn_pos]);
    targets = (layout.task_pool || []).map(t => t.pos);
  }

  async function checkConnection() {
    try {
      const result = await CheckAIConnection();
      aiConnected = result.connected;
      statusMessage = aiConnected ? '🟢 AI ONLINE' : '🔴 AI OFFLINE';
    } catch {
      aiConnected = false;
      statusMessage = '🔴 DISCONNECTED';
    }
  }

  function handleCellClick(row, col) {
    if (simRunning) return;
    if (row === 0 || row === gridSize-1 || col === 0 || col === gridSize-1) return; // Walls

    if (editMode === 'rack') {
      if (hasRobotAt(row, col) < 0 && !hasTaskAt(row, col)) {
        layout.map_data[row][col] = layout.map_data[row][col] === 0 ? 1 : 0;
        layout = layout; // Trigger reactivity
      }
    } else if (editMode === 'robot') {
      if (layout.map_data[row][col] === 0 && hasRobotAt(row, col) < 0) {
        const newId = layout.robots.length;
        layout.robots = [...layout.robots, { id: newId, spawn_pos: [row, col] }];
        robotPositions = [...robotPositions, [row, col]];
        statusMessage = `ROBOT ${newId} DEPLOYED`;
      }
    } else if (editMode === 'task') {
      if (layout.map_data[row][col] === 0 && hasRobotAt(row, col) < 0 && !hasTaskAt(row, col)) {
        const newTask = { item_id: `ITEM_${layout.task_pool.length}`, pos: [row, col] };
        layout.task_pool = [...layout.task_pool, newTask];
        targets = [...targets, [row, col]];
        statusMessage = `TASK ADDED: [${row},${col}]`;
      }
    } else if (editMode === 'erase') {
        const robotIdx = robotPositions.findIndex(p => p[0] === row && p[1] === col);
        if (robotIdx >= 0) {
            const newRobots = layout.robots.filter((_, i) => i !== robotIdx);
            const newPositions = robotPositions.filter((_, i) => i !== robotIdx);
            // Re-index robots
            layout.robots = newRobots.map((r, i) => ({ ...r, id: i }));
            robotPositions = [...newPositions];
            layout = {...layout};
            statusMessage = `ROBOT REMOVED`;
            return;
        }

        const taskIdx = targets.findIndex(t => t[0] === row && t[1] === col);
        if (taskIdx >= 0) {
            const newTasks = layout.task_pool.filter((_, i) => i !== taskIdx);
            const newTargets = targets.filter((_, i) => i !== taskIdx);
            layout.task_pool = newTasks;
            targets = [...newTargets];
            layout = {...layout};
            statusMessage = `TASK REMOVED`;
            return;
        }

        if (layout.map_data[row][col] === 1) {
            layout.map_data[row][col] = 0;
            layout = {...layout};
            statusMessage = `RACK REMOVED`;
        }
    }
  }

  async function startSimulation() {
    if (!aiConnected) { statusMessage = '⚠️ AI DISCONNECTED'; return; }
    if (layout.robots.length === 0) { statusMessage = '⚠️ NO ROBOTS'; return; }
    if (layout.task_pool.length === 0) { statusMessage = '⚠️ NO TASKS'; return; }
    
    await SaveLayout(layout, 'simulation.json');
    await InitAIEnv('../data/layouts/simulation.json');
    
    // Reset positions to spawn
    robotPositions = layout.robots.map(r => [...r.spawn_pos]);
    step = 0;
    simRunning = true;
    statusMessage = '▶️ SIMULATION ACTIVE';
    runSimLoop();
  }

  async function runSimLoop() {
    let completedCount = 0;
    intervalId = setInterval(async () => {
      if (!simRunning) { clearInterval(intervalId); return; }
      
      completedCount = 0;
      totalWorkload = 0;

      for (let i = 0; i < robotPositions.length; i++) {
        try {
          const result = await GetRobotAction(i, robotPositions[i], layout.map_data);
          
          if (result.completed) {
            completedCount++;
            continue;
          }

          const action = result.action;
          if (result.target) targets[i] = result.target;
          
          let [y, x] = robotPositions[i];
          if (action === 1) y--;
          else if (action === 2) y++;
          else if (action === 3) x--;
          else if (action === 4) x++;

          // Collision check (basic)
          if (y >= 0 && y < gridSize && x >= 0 && x < gridSize && layout.map_data[y][x] !== 1) {
             robotPositions[i] = [y, x];
          }

          if (result.remaining_tasks !== undefined) totalWorkload += result.remaining_tasks;

        } catch (e) {
          console.error('Sim error:', e);
        }
      }
      
      robotPositions = [...robotPositions];
      targets = [...targets];
      step++;

      if (completedCount >= robotPositions.length) {
        stopSimulation();
        statusMessage = '✅ MISSION COMPLETE';
      }
    }, 150);
  }

  function stopSimulation() {
    simRunning = false;
    if (intervalId) clearInterval(intervalId);
    statusMessage = '⏹️ SIMULATION PAUSED';
  }

  function resetSimulation() {
    stopSimulation();
    robotPositions = layout.robots.map(r => [...r.spawn_pos]);
    targets = layout.task_pool.map(t => t.pos);
    step = 0;
    statusMessage = '🔄 SYSTEM RESET';
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
    statusMessage = '⚠️ GRID CLEARED';
  }

  // Helpers
  function hasRobotAt(row, col) {
    return robotPositions.findIndex(p => p[0] === row && p[1] === col);
  }
  function hasTaskAt(row, col) {
    return targets.some(t => t[0] === row && t[1] === col);
  }
</script>

<main>
  {#if !layout}
    <div class="loader-container">
      <div class="spinner"></div>
      <p class="mono" style="color: var(--accent-primary)">INITIALIZING SYSTEM...</p>
    </div>
  {:else}
    <!-- Top Bar -->
    <header class="glass">
      <div class="brand">
        <div class="logo-icon">💠</div>
        <div>
          <h1>WAREHOUSE<span style="color:var(--accent-primary)">MARL</span></h1>
          <span class="subtitle">FLEET CONTROL SYSTEM</span>
        </div>
      </div>
      
      <div class="status-bar mono glow-panel">
        <span class="status-dot" class:online={aiConnected}></span>
        {statusMessage}
      </div>

      <div class="actions">
        <button class="btn btn-secondary" on:click={checkConnection}>RECONNECT</button>
      </div>
    </header>

    <div class="content-wrapper">
      <!-- Sidebar Tools -->
      <aside class="sidebar glass">
        <section>
          <h3 class="mono">EDIT MODE</h3>
          <div class="tool-grid">
            {#each EDIT_MODES as mode}
              <button 
                class="tool-btn" 
                class:active={editMode === mode.id}
                on:click={() => editMode = mode.id}
                disabled={simRunning}
              >
                <svg class="icon" viewBox="0 0 24 24"><path d={mode.icon} fill="currentColor"/></svg>
                <span class="mono">{mode.label}</span>
              </button>
            {/each}
          </div>
        </section>

        <section class="controls-section">
          <h3 class="mono">SIMULATION</h3>
          <div class="control-group">
            <button class="btn btn-primary" on:click={startSimulation} disabled={simRunning}>
              <span>▶ START</span>
            </button>
            <button class="btn btn-warning" on:click={stopSimulation} disabled={!simRunning}>
              <span>⏹ STOP</span>
            </button>
            <button class="btn btn-secondary" on:click={resetSimulation}>
              <span>🔄 RESET</span>
            </button>
          </div>
          <button class="btn btn-danger" style="width:100%; margin-top:10px" on:click={clearAll} disabled={simRunning}>
            CLEAR GRID
          </button>
        </section>

        <section class="stats-panel glass glow-panel">
          <div class="stat-row">
            <span class="label mono">STEP</span>
            <span class="value mono">{step}</span>
          </div>
           <div class="stat-row">
            <span class="label mono">TASKS</span>
            <span class="value mono">{layout?.task_pool?.length || 0}</span>
          </div>
           <div class="stat-row">
            <span class="label mono">ROBOTS</span>
            <span class="value mono">{layout?.robots?.length || 0}</span>
          </div>
           <div class="stat-row highlight">
            <span class="label mono">PENDING</span>
            <span class="value mono" style="color: var(--accent-warning)">{totalWorkload}</span>
          </div>
        </section>
      </aside>

      <!-- Main Canvas -->
      <section class="canvas-container">
        <div class="grid-wrapper glow-panel glass">
          {#key step + robotPositions.length + targets.length + JSON.stringify(layout.map_data)}
            <div class="grid" style="--cols:{gridSize}; --cell:{CELL_SIZE}px">
              {#each layout.map_data as row, y}
                {#each row as cell, x}
                  <!-- svelte-ignore a11y-click-events-have-key-events -->
                  <div
                    class="cell"
                    class:rack={cell === 1}
                    class:wall={y === 0 || y === gridSize-1 || x === 0 || x === gridSize-1}
                    class:target={hasTaskAt(y, x)}
                    on:click={() => handleCellClick(y, x)}
                  >
                    {#if hasRobotAt(y, x) >= 0}
                      {@const idx = hasRobotAt(y, x)}
                      <div 
                        class="robot" 
                        style="
                          background: {COLORS.robot[idx % COLORS.robot.length]};
                          box-shadow: 0 0 10px {COLORS.robot[idx % COLORS.robot.length]};
                        "
                      >
                        {idx}
                      </div>
                    {/if}
                    
                    {#if hasTaskAt(y, x) && hasRobotAt(y, x) < 0}
                      <div class="task-dot"></div>
                    {/if}
                  </div>
                {/each}
              {/each}
            </div>
          {/key}
        </div>
      </section>
    </div>
  {/if}
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    padding: 1rem;
    gap: 1rem;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.5rem;
    height: 80px;
    flex-shrink: 0;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .logo-icon {
    font-size: 2rem;
    animation: float 3s ease-in-out infinite;
  }

  h1 {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    line-height: 1;
  }
  .subtitle {
    font-size: 0.7rem;
    color: var(--text-muted);
    letter-spacing: 0.2em;
  }

  .status-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 1.25rem;
    background: var(--bg-secondary);
    border-radius: 20px;
    font-size: 0.8rem;
    letter-spacing: 0.1em;
    min-width: 200px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-danger);
    box-shadow: 0 0 8px var(--accent-danger);
  }
  .status-dot.online {
    background: var(--accent-success);
    box-shadow: 0 0 8px var(--accent-success);
  }

  .content-wrapper {
    display: flex;
    flex: 1;
    gap: 1rem;
    overflow: hidden;
  }

  /* Sidebar */
  .sidebar {
    width: 280px;
    padding: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 2rem;
    overflow-y: auto;
  }

  h3 {
    font-size: 0.75rem;
    color: var(--text-secondary);
    letter-spacing: 0.15em;
    margin-bottom: 1rem;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 0.5rem;
  }

  .tool-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }

  .tool-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem;
    background: var(--bg-secondary);
    border: 1px solid transparent;
    border-radius: 8px;
    color: var(--text-secondary);
    transition: all 0.2s;
  }

  .tool-btn:hover:not(:disabled) {
    background: var(--bg-elevated);
    color: var(--text-primary);
  }

  .tool-btn.active {
    background: rgba(0, 240, 255, 0.1);
    border-color: var(--accent-primary);
    color: var(--accent-primary);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.1);
  }
  
  .tool-btn .icon {
    width: 24px;
    height: 24px;
  }

  .control-group {
    display: grid;
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }

  .stats-panel {
    padding: 1rem;
    margin-top: auto;
    background: var(--bg-secondary);
  }

  .stat-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-size: 0.85rem;
  }
  .stat-row:last-child { margin-bottom: 0; }
  .stat-row .label { color: var(--text-muted); }
  .stat-row .value { color: var(--text-primary); font-weight: 700; }
  
  /* Canvas */
  .canvas-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    padding: 2rem;
  }

  .grid-wrapper {
    padding: 1rem;
    background: var(--bg-secondary);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(var(--cols), var(--cell));
    gap: 1px;
    background: rgba(255,255,255,0.05);
  }

  .cell {
    width: var(--cell);
    height: var(--cell);
    background: var(--bg-primary);
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: crosshair;
    transition: background 0.1s;
  }

  .cell:hover {
    background: rgba(255,255,255,0.05);
  }

  .cell.wall {
    background: #334155;
    cursor: default;
  }

  .cell.rack {
    background: var(--accent-warning);
    box-shadow: inset 0 0 5px rgba(0,0,0,0.5);
  }

  .cell.target {
    background: rgba(0, 255, 157, 0.1);
  }

  .robot {
    width: 80%;
    height: 80%;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    font-weight: 900;
    color: #000;
    z-index: 10;
    transition: all 0.15s ease-out;
  }

  .task-dot {
    width: 30%;
    height: 30%;
    border-radius: 50%;
    background: var(--accent-success);
    box-shadow: 0 0 5px var(--accent-success);
    animation: pulse 2s infinite;
  }

  @keyframes float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-5px); }
  }

  @keyframes pulse {
    0% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.2); opacity: 0.7; }
    100% { transform: scale(1); opacity: 1; }
  }
</style>

