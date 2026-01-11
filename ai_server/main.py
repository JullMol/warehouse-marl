from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
import numpy as np
from task_manager import TaskManager
from models import ActorCritic
import json
import heapq
from collections import deque

app = FastAPI()
model = None
task_manager = None
layout = None

position_history = {}

def astar_next_action(pos, target, grid):
    if pos[0] == target[0] and pos[1] == target[1]: return 0
    rows, cols = len(grid), len(grid[0])
    start, goal = tuple(pos), tuple(target)
    def heuristic(a, b): return abs(a[0] - b[0]) + abs(a[1] - b[1])
    open_set = [(heuristic(start, goal), 0, start)]
    came_from = {}
    g_score = {start: 0}
    closed = set()
    
    while open_set:
        _, _, current = heapq.heappop(open_set)
        if current in closed: continue
        closed.add(current)
        
        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.reverse()
            if path:
                next_pos = path[0]
                dy, dx = next_pos[0] - pos[0], next_pos[1] - pos[1]
                if dy == -1: return 1
                if dy == 1: return 2
                if dx == -1: return 3
                if dx == 1: return 4
            return 0
        
        for dy, dx in [(-1,0), (1,0), (0,-1), (0,1)]:
            ny, nx = current[0] + dy, current[1] + dx
            neighbor = (ny, nx)
            if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] == 0 and neighbor not in closed:
                tentative_g = g_score[current] + 1
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f, tentative_g, neighbor))
    return 0

def is_stuck(robot_id, current_pos):
    if robot_id not in position_history:
        position_history[robot_id] = deque(maxlen=6)
    
    hist = position_history[robot_id]
    hist.append(tuple(current_pos))
    
    if len(hist) >= 4:
        unique_pos = set(hist)
        if len(unique_pos) <= 2: 
            return True
    return False

def validate_action(action, pos, grid):
    ny, nx = pos[0], pos[1]
    if action == 1: ny -= 1
    elif action == 2: ny += 1
    elif action == 3: nx -= 1
    elif action == 4: nx += 1
    
    if 0 <= ny < len(grid) and 0 <= nx < len(grid[0]):
        return grid[ny][nx] == 0
    return False

@app.get("/")
def root():
    return {"status": "running", "model": "Smart Hybrid RL"}

class LayoutRequest(BaseModel):
    json_path: str

@app.on_event("startup")
def startup():
    global model
    try:
        model = ActorCritic(state_dim=27, action_dim=5, hidden_sizes=[128, 64])
        model.load_state_dict(torch.load('models/rl_astar_model.pth', weights_only=True))
        model.eval()
        print("SMART HYBRID RL Engine Ready")
    except Exception as e:
        print(f"Failed to load RL model: {e}")
        model = None

@app.post("/init_env")
async def init_env(req: LayoutRequest):
    global task_manager, layout, position_history
    try:
        with open(req.json_path, 'r') as f:
            layout = json.load(f)
        num_robots = len(layout['robots'])
        task_manager = TaskManager(num_robots)
        task_manager.distribute_tasks(layout['task_pool'])
        position_history = {} 
        print(f"Env Init: {num_robots} robots")
        return {"status": "success", "robots": num_robots}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/get_action")
async def get_action(data: dict):
    robot_id = data['robot_id']
    pos = data['current_pos']
    grid = data['grid']
    
    if task_manager is None:
        return {"action": 0, "completed": True, "message": "Task Manager Not Ready"}

    target = task_manager.get_next_task(robot_id)
    if target is None:
        return {"action": 0, "completed": True, "message": "All tasks done"}
    
    if pos[0] == target[0] and pos[1] == target[1]:
        task_manager.complete_task(robot_id)
        if robot_id in position_history: position_history[robot_id].clear()
        
        new_target = task_manager.get_next_task(robot_id)
        if new_target is None:
            return {"action": 0, "completed": True, "message": f"Robot {robot_id} done"}
        target = new_target
    
    action = 0
    
    if not hasattr(get_action, "unstuck_cooldown"):
        get_action.unstuck_cooldown = {} 

    current_cooldown = get_action.unstuck_cooldown.get(robot_id, 0)

    if current_cooldown > 0:
        action = astar_next_action(pos, target, grid)
        get_action.unstuck_cooldown[robot_id] -= 1
    
    elif is_stuck(robot_id, pos):
        action = astar_next_action(pos, target, grid)
        get_action.unstuck_cooldown[robot_id] = 5 
        if robot_id in position_history: position_history[robot_id].clear()
    
    elif model is not None:
        padded = np.pad(np.array(grid), 2, mode='constant', constant_values=1)
        local_view = padded[pos[0]:pos[0]+5, pos[1]:pos[1]+5].flatten()
        vec_to_target = np.array(target) - np.array(pos)
        state = np.concatenate([local_view, vec_to_target]).astype(np.float32)
        state_tensor = torch.FloatTensor(state).unsqueeze(0)
        
        rl_action = model.get_action(state_tensor)
        
        if rl_action != 0 and validate_action(rl_action, pos, grid):
            action = rl_action
        else:
            action = astar_next_action(pos, target, grid)
            
    else:
        action = astar_next_action(pos, target, grid)
    
    target_list = list(target) if not isinstance(target, list) else target
    remaining = len(task_manager.queues[robot_id]) if task_manager and robot_id in task_manager.queues else 0
    return {
        "action": int(action),
        "target": target_list,
        "remaining_tasks": remaining,
        "completed": False
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)