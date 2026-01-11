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
  let statusMessage = 'INITIALIZING SYSTEMS...';
  let intervalId = null;
  let gridSize = 20;
  let totalWorkload = 0;
  let currentTime = '';

  const CELL_SIZE = 32;
  
  const COLORS = {
    rack: '#f59e0b',
    robot: ['#00f0ff', '#a855f7', '#ec4899', '#10b981'],
    target: '#10b981',
  };

  const EDIT_MODES = [
    { id: 'rack', label: 'RACK', icon: 'M4 4h16v16H4z', color: 'var(--accent-amber)' },
    { id: 'robot', label: 'ROBOT', icon: 'M12 2a2 2 0 012 2c0 .74-.4 1.38-1 1.72V7h-2v-1.28c-.6-.34-1-.98-1-1.72a2 2 0 012-2zm-4 8h8v10H8V10zm2 2v2h4v-2h-4z', color: 'var(--accent-cyan)' },
    { id: 'task', label: 'TASK', icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z', color: 'var(--accent-green)' },
    { id: 'erase', label: 'ERASE', icon: 'M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z', color: 'var(--accent-red)' },
  ];

  onMount(async () => {
    try {
      layout = await GetDefaultLayout();
      syncPositions();
      checkConnection();
      updateTime();
      setInterval(updateTime, 1000);
    } catch (e) {
      console.error('Error loading layout:', e);
      statusMessage = 'LAYOUT LOAD ERROR';
    }
  });

  function updateTime() {
    const now = new Date();
    currentTime = now.toLocaleTimeString('en-US', { hour12: false });
  }

  function syncPositions() {
    if (!layout) return;
    robotPositions = (layout.robots || []).map(r => [...r.spawn_pos]);
    targets = (layout.task_pool || []).map(t => t.pos);
  }

  async function checkConnection() {
    try {
      const result = await CheckAIConnection();
      aiConnected = result.connected;
      statusMessage = aiConnected ? 'AI CORE ONLINE' : 'AI CORE OFFLINE';
    } catch {
      aiConnected = false;
      statusMessage = 'CONNECTION FAILED';
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
        statusMessage = `ROBOT ${newId} DEPLOYED`;
      }
    } else if (editMode === 'task') {
      if (layout.map_data[row][col] === 0 && hasRobotAt(row, col) < 0 && !hasTaskAt(row, col)) {
        const newTask = { item_id: `ITEM_${layout.task_pool.length}`, pos: [row, col] };
        layout.task_pool = [...layout.task_pool, newTask];
        targets = [...targets, [row, col]];
        statusMessage = `TASK ASSIGNED [${row},${col}]`;
      }
    } else if (editMode === 'erase') {
        const robotIdx = robotPositions.findIndex(p => p[0] === row && p[1] === col);
        if (robotIdx >= 0) {
            const newRobots = layout.robots.filter((_, i) => i !== robotIdx);
            const newPositions = robotPositions.filter((_, i) => i !== robotIdx);
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
    if (!aiConnected) { statusMessage = 'AI DISCONNECTED'; return; }
    if (layout.robots.length === 0) { statusMessage = 'NO ROBOTS DEPLOYED'; return; }
    if (layout.task_pool.length === 0) { statusMessage = 'NO TASKS ASSIGNED'; return; }
    
    await SaveLayout(layout, 'simulation.json');
    await InitAIEnv('../data/layouts/simulation.json');
    
    robotPositions = layout.robots.map(r => [...r.spawn_pos]);
    step = 0;
    simRunning = true;
    statusMessage = 'SIMULATION ACTIVE';
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
        statusMessage = 'MISSION COMPLETE';
      }
    }, 150);
  }

  function stopSimulation() {
    simRunning = false;
    if (intervalId) clearInterval(intervalId);
    statusMessage = 'SIMULATION PAUSED';
  }

  function resetSimulation() {
    stopSimulation();
    robotPositions = layout.robots.map(r => [...r.spawn_pos]);
    targets = layout.task_pool.map(t => t.pos);
    step = 0;
    statusMessage = 'SYSTEM RESET';
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
    statusMessage = 'GRID CLEARED';
  }

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
      <p class="mono" style="color: var(--accent-cyan); font-size: 1rem; letter-spacing: 0.2em;">INITIALIZING SYSTEMS...</p>
    </div>
  {:else}
    <div class="hud-corner top-left"></div>
    <div class="hud-corner top-right"></div>
    <div class="hud-corner bottom-left"></div>
    <div class="hud-corner bottom-right"></div>

    <header class="glass-accent">
      <div class="brand">
        <div class="logo-container">
          <div class="logo-ring"></div>
          <div class="logo-icon">W</div>
        </div>
        <div class="brand-text">
          <h1 class="heading">WAREHOUSE<span class="text-gradient">MARL</span></h1>
          <span class="subtitle mono">FLEET CONTROL SYSTEM v2.0</span>
        </div>
      </div>
      
      <div class="status-display">
        <div class="status-item">
          <span class="status-label mono">TIME</span>
          <span class="status-value mono">{currentTime}</span>
        </div>
        <div class="status-item">
          <span class="status-label mono">STEP</span>
          <span class="status-value mono">{step.toString().padStart(4, '0')}</span>
        </div>
        <div class="status-bar glass" class:online={aiConnected}>
          <div class="status-indicator">
            <span class="status-dot"></span>
            <span class="status-ring"></span>
          </div>
          <span class="mono">{statusMessage}</span>
        </div>
      </div>

      <div class="header-actions">
        <button class="btn btn-secondary" on:click={checkConnection}>
          <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
          RECONNECT
        </button>
      </div>
    </header>

    <div class="content-wrapper">
      <aside class="sidebar glass-accent">
        <section class="tool-section">
          <div class="section-header">
            <div class="section-line"></div>
            <h3 class="mono">EDIT MODE</h3>
            <div class="section-line"></div>
          </div>
          <div class="tool-grid">
            {#each EDIT_MODES as mode}
              <button 
                class="tool-btn" 
                class:active={editMode === mode.id}
                style="--tool-color: {mode.color}"
                on:click={() => editMode = mode.id}
                disabled={simRunning}
              >
                <div class="tool-icon">
                  <svg viewBox="0 0 24 24"><path d={mode.icon} fill="currentColor"/></svg>
                </div>
                <span class="mono">{mode.label}</span>
              </button>
            {/each}
          </div>
        </section>

        <section class="controls-section">
          <div class="section-header">
            <div class="section-line"></div>
            <h3 class="mono">SIMULATION</h3>
            <div class="section-line"></div>
          </div>
          <div class="control-group">
            <button class="btn btn-primary control-btn" on:click={startSimulation} disabled={simRunning}>
              <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>
              START
            </button>
            <button class="btn btn-warning control-btn" on:click={stopSimulation} disabled={!simRunning}>
              <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M6 6h12v12H6z"/></svg>
              STOP
            </button>
            <button class="btn btn-secondary control-btn" on:click={resetSimulation}>
              <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
              RESET
            </button>
          </div>
          <button class="btn btn-danger" style="width:100%; margin-top:12px" on:click={clearAll} disabled={simRunning}>
            CLEAR GRID
          </button>
        </section>

        <section class="stats-panel glass">
          <div class="stats-header mono">TELEMETRY</div>
          <div class="stat-row">
            <span class="stat-icon">📊</span>
            <span class="stat-label mono">TASKS</span>
            <span class="stat-value mono">{layout?.task_pool?.length || 0}</span>
          </div>
          <div class="stat-row">
            <span class="stat-icon">🤖</span>
            <span class="stat-label mono">ROBOTS</span>
            <span class="stat-value mono">{layout?.robots?.length || 0}</span>
          </div>
          <div class="stat-row highlight">
            <span class="stat-icon">⏳</span>
            <span class="stat-label mono">PENDING</span>
            <span class="stat-value mono warning">{totalWorkload}</span>
          </div>
        </section>

        <div class="sidebar-footer mono">
          <span>MARL ENGINE</span>
          <span class="version">v2.0.0</span>
        </div>
      </aside>

      <section class="canvas-container">
        <div class="grid-wrapper glass-accent glow-panel">
          <div class="grid-header">
            <span class="mono">WAREHOUSE GRID</span>
            <span class="mono grid-size">{gridSize}x{gridSize}</span>
          </div>
          {#key step + robotPositions.length + targets.length + JSON.stringify(layout.map_data)}
            <div class="grid" style="--cols:{gridSize}; --cell:{CELL_SIZE}px">
              {#each layout.map_data as row, y}
                {#each row as cell, x}
                  <div
                    class="cell"
                    class:rack={cell === 1}
                    class:wall={y === 0 || y === gridSize-1 || x === 0 || x === gridSize-1}
                    class:target={hasTaskAt(y, x)}
                    on:click={() => handleCellClick(y, x)}
                    on:keydown={(e) => e.key === 'Enter' && handleCellClick(y, x)}
                    role="button"
                    tabindex="0"
                  >
                    {#if hasRobotAt(y, x) >= 0}
                      {@const idx = hasRobotAt(y, x)}
                      <div 
                        class="robot" 
                        style="
                          --robot-color: {COLORS.robot[idx % COLORS.robot.length]};
                          background: radial-gradient(circle at 30% 30%, {COLORS.robot[idx % COLORS.robot.length]}, {COLORS.robot[idx % COLORS.robot.length]}88);
                        "
                      >
                        <span class="robot-id">{idx}</span>
                        <div class="robot-ring"></div>
                      </div>
                    {/if}
                    
                    {#if hasTaskAt(y, x) && hasRobotAt(y, x) < 0}
                      <div class="task-marker">
                        <div class="task-dot"></div>
                        <div class="task-pulse"></div>
                      </div>
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
    position: relative;
  }

  .hud-corner {
    position: fixed;
    width: 60px;
    height: 60px;
    pointer-events: none;
    z-index: 100;
  }

  .hud-corner::before,
  .hud-corner::after {
    content: '';
    position: absolute;
    background: var(--accent-cyan);
    opacity: 0.4;
  }

  .top-left { top: 0; left: 0; }
  .top-left::before { width: 40px; height: 2px; top: 10px; left: 10px; }
  .top-left::after { width: 2px; height: 40px; top: 10px; left: 10px; }

  .top-right { top: 0; right: 0; }
  .top-right::before { width: 40px; height: 2px; top: 10px; right: 10px; }
  .top-right::after { width: 2px; height: 40px; top: 10px; right: 10px; }

  .bottom-left { bottom: 0; left: 0; }
  .bottom-left::before { width: 40px; height: 2px; bottom: 10px; left: 10px; }
  .bottom-left::after { width: 2px; height: 40px; bottom: 10px; left: 10px; }

  .bottom-right { bottom: 0; right: 0; }
  .bottom-right::before { width: 40px; height: 2px; bottom: 10px; right: 10px; }
  .bottom-right::after { width: 2px; height: 40px; bottom: 10px; right: 10px; }

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

  .logo-container {
    position: relative;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .logo-ring {
    position: absolute;
    width: 100%;
    height: 100%;
    border: 2px solid var(--accent-cyan);
    border-radius: 50%;
    animation: spin 10s linear infinite;
    opacity: 0.5;
  }

  .logo-ring::before {
    content: '';
    position: absolute;
    top: -4px;
    left: 50%;
    width: 8px;
    height: 8px;
    background: var(--accent-cyan);
    border-radius: 50%;
    transform: translateX(-50%);
    box-shadow: 0 0 10px var(--accent-cyan);
  }

  .logo-icon {
    font-family: 'Orbitron', sans-serif;
    font-size: 1.5rem;
    font-weight: 900;
    color: var(--accent-cyan);
    text-shadow: 0 0 20px var(--accent-cyan);
  }

  .brand-text h1 {
    font-size: 1.3rem;
    letter-spacing: 0.15em;
    line-height: 1.2;
  }

  .subtitle {
    font-size: 0.65rem;
    color: var(--text-muted);
    letter-spacing: 0.25em;
  }

  .status-display {
    display: flex;
    align-items: center;
    gap: 1.5rem;
  }

  .status-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .status-label {
    font-size: 0.6rem;
    color: var(--text-muted);
    letter-spacing: 0.1em;
  }

  .status-value {
    font-size: 0.9rem;
    color: var(--accent-cyan);
    text-shadow: 0 0 10px var(--accent-cyan);
  }

  .status-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 1.25rem;
    border-radius: 25px;
    font-size: 0.75rem;
    letter-spacing: 0.12em;
    min-width: 200px;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }

  .status-bar.online {
    border-color: rgba(16, 185, 129, 0.3);
  }

  .status-indicator {
    position: relative;
    width: 12px;
    height: 12px;
  }

  .status-dot {
    position: absolute;
    width: 8px;
    height: 8px;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    background: var(--accent-red);
    box-shadow: 0 0 10px var(--accent-red);
  }

  .status-bar.online .status-dot {
    background: var(--accent-green);
    box-shadow: 0 0 10px var(--accent-green);
  }

  .status-ring {
    position: absolute;
    width: 100%;
    height: 100%;
    border: 1px solid var(--accent-red);
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
  }

  .status-bar.online .status-ring {
    border-color: var(--accent-green);
  }

  .content-wrapper {
    display: flex;
    flex: 1;
    gap: 1rem;
    overflow: hidden;
  }

  .sidebar {
    width: 260px;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    overflow-y: auto;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .section-line {
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
    opacity: 0.3;
  }

  .section-header h3 {
    font-size: 0.7rem;
    color: var(--text-secondary);
    letter-spacing: 0.2em;
    white-space: nowrap;
  }

  .tool-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .tool-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.4rem;
    padding: 0.75rem;
    background: var(--bg-secondary);
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    transition: all 0.25s;
    cursor: pointer;
  }

  .tool-btn:hover:not(:disabled) {
    background: var(--bg-elevated);
    color: var(--text-primary);
    transform: translateY(-2px);
  }

  .tool-btn.active {
    background: rgba(0, 240, 255, 0.08);
    border-color: var(--tool-color);
    color: var(--tool-color);
    box-shadow: 0 0 15px color-mix(in srgb, var(--tool-color) 20%, transparent);
  }

  .tool-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .tool-icon {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .tool-icon svg {
    width: 20px;
    height: 20px;
  }

  .tool-btn span {
    font-size: 0.65rem;
    letter-spacing: 0.1em;
  }

  .control-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .control-btn {
    justify-content: flex-start;
    padding-left: 1rem;
  }

  .stats-panel {
    padding: 1rem;
    margin-top: auto;
    background: var(--bg-secondary);
  }

  .stats-header {
    font-size: 0.65rem;
    color: var(--text-muted);
    letter-spacing: 0.15em;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }

  .stat-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0;
    font-size: 0.8rem;
  }

  .stat-icon {
    font-size: 0.9rem;
    width: 20px;
    text-align: center;
  }

  .stat-label {
    color: var(--text-muted);
    flex: 1;
    font-size: 0.7rem;
    letter-spacing: 0.1em;
  }

  .stat-value {
    color: var(--text-primary);
    font-weight: 600;
    font-size: 0.9rem;
  }

  .stat-value.warning {
    color: var(--accent-amber);
    text-shadow: 0 0 8px var(--accent-amber);
  }

  .stat-row.highlight {
    background: rgba(245, 158, 11, 0.05);
    margin: 0 -0.5rem;
    padding: 0.5rem;
    border-radius: var(--radius-sm);
  }

  .sidebar-footer {
    display: flex;
    justify-content: space-between;
    font-size: 0.6rem;
    color: var(--text-muted);
    padding-top: 0.75rem;
    border-top: 1px solid rgba(255,255,255,0.05);
  }

  .version {
    color: var(--accent-cyan);
  }

  .canvas-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .grid-wrapper {
    padding: 1rem;
    background: var(--bg-secondary);
  }

  .grid-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(0, 240, 255, 0.1);
    font-size: 0.7rem;
    color: var(--text-muted);
    letter-spacing: 0.15em;
  }

  .grid-size {
    color: var(--accent-cyan);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(var(--cols), var(--cell));
    gap: 1px;
    background: rgba(0, 240, 255, 0.03);
    border: 1px solid rgba(0, 240, 255, 0.1);
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
    transition: all 0.15s;
  }

  .cell:hover {
    background: rgba(0, 240, 255, 0.05);
    box-shadow: inset 0 0 10px rgba(0, 240, 255, 0.1);
  }

  .cell.wall {
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    cursor: default;
  }

  .cell.rack {
    background: linear-gradient(135deg, var(--accent-amber) 0%, #b45309 100%);
    box-shadow: inset 0 0 8px rgba(0,0,0,0.4), 0 0 5px rgba(245, 158, 11, 0.3);
  }

  .cell.target {
    background: rgba(16, 185, 129, 0.1);
  }

  .robot {
    width: 80%;
    height: 80%;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    transition: all 0.15s ease-out;
    position: relative;
    box-shadow: 0 0 15px var(--robot-color), 0 2px 8px rgba(0,0,0,0.5);
  }

  .robot-id {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.65rem;
    font-weight: 700;
    color: #000;
    z-index: 2;
  }

  .robot-ring {
    position: absolute;
    width: 120%;
    height: 120%;
    border: 1px solid var(--robot-color);
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
    opacity: 0.5;
  }

  .task-marker {
    position: relative;
    width: 50%;
    height: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .task-dot {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, var(--accent-green-bright), var(--accent-green));
    box-shadow: 0 0 10px var(--accent-green);
  }

  .task-pulse {
    position: absolute;
    width: 150%;
    height: 150%;
    border: 2px solid var(--accent-green);
    border-radius: 50%;
    animation: pulse 1.5s ease-out infinite;
    opacity: 0.6;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @keyframes pulse {
    0% { transform: scale(1); opacity: 0.6; }
    50% { transform: scale(1.3); opacity: 0; }
    100% { transform: scale(1); opacity: 0; }
  }
</style>
