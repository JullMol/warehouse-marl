import torch
import torch.nn as nn

class ActorCritic(nn.Module):
    def __init__(self, state_dim=27, action_dim=5, hidden_sizes=[128, 64]):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(state_dim, hidden_sizes[0]),
            nn.ReLU(),
            nn.Linear(hidden_sizes[0], hidden_sizes[1]),
            nn.ReLU()
        )
        self.actor = nn.Linear(hidden_sizes[1], action_dim)
        self.critic = nn.Linear(hidden_sizes[1], 1)
    
    def forward(self, x):
        shared = self.shared(x)
        action_probs = torch.softmax(self.actor(shared), dim=-1)
        return action_probs, self.critic(shared)
    
    def get_action(self, state):
        with torch.no_grad():
            probs, _ = self.forward(state)
            return probs.argmax(dim=-1).item()