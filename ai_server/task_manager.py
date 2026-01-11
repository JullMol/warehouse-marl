import numpy as np

class TaskManager:
    def __init__(self, num_robots):
        self.num_robots = num_robots
        self.queues = {i: [] for i in range(num_robots)}
        self.current_targets = {i: None for i in range(num_robots)}

    def distribute_tasks(self, task_pool):
        self.queues = {i: [] for i in range(self.num_robots)}
        self.current_targets = {i: None for i in range(self.num_robots)}
        for i, task in enumerate(task_pool):
            robot_id = i % self.num_robots
            self.queues[robot_id].append(task['pos'])
        for i in range(self.num_robots):
            if self.queues[i]:
                self.current_targets[i] = self.queues[i][0]
        return self.queues

    def get_next_task(self, robot_id):
        if robot_id not in self.current_targets:
            return None
        return self.current_targets.get(robot_id)

    def complete_task(self, robot_id):
        if robot_id in self.queues and self.queues[robot_id]:
            self.queues[robot_id].pop(0)
            if self.queues[robot_id]:
                self.current_targets[robot_id] = self.queues[robot_id][0]
            else:
                self.current_targets[robot_id] = None
            return True
        return False
