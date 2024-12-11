from abc import abstractmethod
import numpy as np
from numpy import ndarray
import torch
from torch import Tensor
from typing import TypeVar

ActionType = TypeVar("ActionType")
AgentID = TypeVar("AgentID")
ObsType = TypeVar("ObsType")

class RolloutBuffer4IPPO:
    """Rollout buffer for IPPO class.
    
    Rollout buffer is usually used to store experiences while training on-policy RL algorithm.
    Since RolloutBufferForMAPPO is for independent PPO algorithm, the buffer store experiences of all agents.

    An experience consists of (obs, action, reward, next_obs, done, log_prob).
    """
    def __init__(
        self,
        buffer_size: int,
        agent_num: int,
        obs_shape: tuple[int],
        action_shape: tuple[int],
        device: torch.device
    ) -> None:
        """Initialize RolloutBufferForMAPPO.

        Args:
            buffer_size (int): Buffer size.
            obs_shape (tuple[int]): Observation shape.
            action_shape (tuple[int]): Action shape.
            agent_num (int): Number of agents.
            device (torch.device): Device.
        """
        self.buffer_size: int = int(buffer_size)
        self.agent_num: int = int(agent_num)
        self.obs_shape: tuple[int] = obs_shape
        self.action_shape: tuple[int] = action_shape
        self.device: torch.device = device
        self._initialize_buffer()

    def _initialize_buffer(self) -> None:
        """Initialize buffer.
        
        RolloutBuffer4IPPO stores rollout experiences of all agents.
        """
        self.is_storing_dic: dict[int, bool] = {
            agent_idx: True for agent_idx in range(self.agent_num)
        }
        self.next_idx_dic: dict[int, int] = {
            agent_idx: 0 for agent_idx in range(self.agent_num)
        }
        self.obses: Tensor = torch.empty(
            (self.buffer_size, self.agent_num, *self.obs_shape),
            dtype=torch.float, device=self.device
        )
        self.actions: Tensor = torch.empty(
            (self.buffer_size, self.agent_num, *self.action_shape),
            dtype=torch.float, device=self.device
        )
        self.rewards: Tensor = torch.empty(
            (self.buffer_size, self.agent_num),
            dtype=torch.float, device=self.device
        )
        self.rewards: Tensor = torch.empty(
            (self.buffer_size, self.agent_num),
            dtype=torch.float, device=self.device
        )
        self.dones: Tensor = torch.empty(
            (self.buffer_size, self.agent_num),
            dtype=torch.float, device=self.device
        )
        self.log_probs: Tensor = torch.empty(
            (self.buffer_size, self.agent_num),
            dtype=torch.float, device=self.device
        )
        self.next_obses: Tensor = torch.empty(
            (self.buffer_size, self.agent_num, *self.obs_shape),
            dtype=torch.float, device=self.device
        )

    def append(
        self,
        agent_idx: int,
        obs_tensor: Tensor,
        action_tensor: Tensor,
        reward: float,
        done: bool,
        log_prob: float
    ) -> None:
        """add one experience to buffer.
        
        RolloutBuffer4IPPO synchronously stores experiences of all agents. In other words,
        .append() method will not append filled agents' experiences to the buffer until all buffer will be filled.
        
        """
        next_idx: int = self.next_idx_dic[agent_idx]
        is_storing: bool = self.is_storing_dic[agent_idx]
        if not is_storing:
            if next_idx == 0:
                self.obses[-1, agent_idx].copy_(
                    obs_tensor.view(self.obs_shape)
                )
            self.next_idx_dic[agent_idx] = 1
            return
        else:
            self.next_obses[next_idx-1, agent_idx].copy_(
                obs_tensor.view(self.obs_shape)
            )
        self.obses[next_idx, agent_idx].copy_(obs_tensor.view(self.obs_shape))
        self.actions[next_idx, agent_idx].copy_(action_tensor.view(self.action_shape))
        self.rewards[next_idx, agent_idx] = float(reward)
        self.dones[next_idx, agent_idx] = float(done)
        self.log_probs[next_idx, agent_idx] = float(log_prob)
        self.next_idx_dic[agent_idx] = (next_idx + 1) % self.buffer_size
        if next_idx + 1 == self.buffer_size:
            self.is_storing_dic[agent_idx] = False

    def is_filled(self) -> bool:
        """Check if the buffer is filled.
        
        Returns:
            bool: If the buffer is filled.
        """
        return not any(self.is_storing_dic.values())

    def get(self) -> tuple[Tensor]:
        """Get all experiences.
        
        Returns:
            experiences (tuple[Tensor]): All experiences.
        """
        experiences: tuple[Tensor] = (
            self.obses, self.actions, self.rewards, self.dones, self.log_probs, self.next_obses
        )
        self._initialize_buffer()
        return experiences
