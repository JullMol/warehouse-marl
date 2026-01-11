import torch
import torch.optim as optim
import numpy as np
import heapq
import os
from torch.distributions import Categorical
from models import ActorCritic

def astar_path_length(start, goal, grid):
    if start[0] == goal[0] and start[1] == goal[1]: return 0
    rows, cols = len(grid), len(grid[0])
    open_set = [(0, tuple(start))]
    g_score = {tuple(start): 0}
    while open_set:
        _, current = heapq.heappop(open_set)
        if current == tuple(goal): return g_score[current]
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny, nx = current[0]+dy, current[1]+dx
            if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] == 0:
                neighbor = (ny, nx)
                tentative_g = g_score[current] + 1
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    h = abs(ny - goal[0]) + abs(nx - goal[1])
                    heapq.heappush(open_set, (tentative_g + h, neighbor))
    return 999

def get_state(pos, target, grid):
    padded = np.pad(grid, 2, mode='constant', constant_values=1)
    local_view = padded[pos[0]:pos[0]+5, pos[1]:pos[1]+5].flatten()
    vec_to_target = np.array(target) - np.array(pos)
    return np.concatenate([local_view, vec_to_target]).astype(np.float32)

def compute_reward(pos_before, pos_after, target, grid, reached):
    if reached:
        return 50.0
    dist_before = astar_path_length(pos_before, target, grid)
    dist_after = astar_path_length(pos_after, target, grid)
    if dist_after < dist_before:
        return 2.0
    elif dist_after > dist_before:
        return -1.0
    else:
        return -0.2

def train():
    print("RL Training with A* Reward Shaping")
    print("="*50)
    model = ActorCritic(state_dim=27, action_dim=5, hidden_sizes=[128, 64])
    optimizer = optim.Adam(model.parameters(), lr=0.0003)
    num_episodes = 500
    grid_size = 20
    gamma = 0.99
    best_reward = -float('inf')
    for ep in range(num_episodes):
        grid = np.zeros((grid_size, grid_size), dtype=int)
        grid[0, :] = grid[-1, :] = grid[:, 0] = grid[:, -1] = 1
        for _ in range(np.random.randint(3, 8)):
            oy, ox = np.random.randint(2, grid_size-2), np.random.randint(2, grid_size-2)
            grid[oy, ox] = 1
        while True:
            pos = [np.random.randint(1, grid_size-1), np.random.randint(1, grid_size-1)]
            if grid[pos[0], pos[1]] == 0: break
        while True:
            target = [np.random.randint(1, grid_size-1), np.random.randint(1, grid_size-1)]
            if grid[target[0], target[1]] == 0 and target != pos: break
        log_probs, values, rewards = [], [], []
        ep_reward = 0
        for step in range(100):
            state = torch.FloatTensor(get_state(pos, target, grid)).unsqueeze(0)
            action, log_prob, value = model.act(state)
            log_probs.append(log_prob)
            values.append(value)
            pos_before = pos.copy()
            ny, nx = pos[0], pos[1]
            if action == 1 and pos[0] > 1 and grid[pos[0]-1][pos[1]] == 0: ny = pos[0] - 1
            elif action == 2 and pos[0] < grid_size-2 and grid[pos[0]+1][pos[1]] == 0: ny = pos[0] + 1
            elif action == 3 and pos[1] > 1 and grid[pos[0]][pos[1]-1] == 0: nx = pos[1] - 1
            elif action == 4 and pos[1] < grid_size-2 and grid[pos[0]][pos[1]+1] == 0: nx = pos[1] + 1
            pos = [ny, nx]
            reached = (pos[0] == target[0] and pos[1] == target[1])
            reward = compute_reward(pos_before, pos, target, grid, reached)
            rewards.append(reward)
            ep_reward += reward
            if reached: break
        if len(rewards) < 2: continue
        returns, R = [], 0
        for r in reversed(rewards):
            R = r + gamma * R
            returns.insert(0, R)
        returns = torch.FloatTensor(returns)
        mean, std = returns.mean(), returns.std()
        if std > 0:
            returns = (returns - mean) / (std + 1e-8)
        policy_loss, value_loss = 0, 0
        for log_prob, value, R in zip(log_probs, values, returns):
            advantage = R - value.detach()
            policy_loss += -log_prob * advantage
            value_loss += (value - R) ** 2
        optimizer.zero_grad()
        loss = policy_loss + 0.5 * value_loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5)
        optimizer.step()
        if ep_reward > best_reward:
            best_reward = ep_reward
        if (ep + 1) % 50 == 0:
            print(f"Episode {ep+1:4d} | Reward: {ep_reward:7.1f} | Best: {best_reward:.1f}")
    
    os.makedirs('models', exist_ok=True)
    torch.save(model.state_dict(), 'models/rl_astar_model.pth')
    print(f"\nModel saved: models/rl_astar_model.pth")
    print(f"Best reward: {best_reward:.1f}")

if __name__ == "__main__":
    train()
