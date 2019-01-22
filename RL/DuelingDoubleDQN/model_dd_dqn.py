import numpy as np
import torch
import torch.nn as nn
import math
EPS_START = 0.9
EPS_END = 0.05
EPS_DECAY = 200


def epsilon_greedy_policy(network, eps_end, eps_start, eps_decay, actions, device):
    """
    Create a epsilon greedy policy function based on the given network Q-function
    :param network: network used to approximate the Q-function
    :return: action
    """
    def policy_fn(observation, steps_done):
        sample = np.random.random()
        eps_threshold = eps_end + (eps_start - eps_end) * math.exp(-1. * steps_done * eps_decay)
        with torch.no_grad():
            if sample > eps_threshold:
                input = observation.unsqueeze(0).to(device)
                q_values = network.forward(input)[0]
                best_action = torch.max(q_values, dim=0)[1]
                return best_action.cpu().item(), eps_threshold
            else:
                return np.random.randint(low=0, high=len(actions)), eps_threshold
    return policy_fn


# def epsilon_greedy_policy(network):
#     """
#     Create a epsilon greedy policy function based on the given network Q-function
#     :param network: network used to approximate the Q-function
#     :return: action
#     """
#     def policy_fn(observation, epsilon):
#         A = TENSOR_TYPE["f_tensor"](np.ones(network.action_space)) * epsilon / network.action_space
#         q_values = network.forward(Variable(observation.cuda(), volatile=True))[0]
#         best_action = torch.max(q_values, dim=0)[1]
#         A[best_action] += (1.0 - epsilon)
#         action = torch.multinomial(A, num_samples=1, replacement=True)
#         return action.cpu()
#     return policy_fn

class DDDQN_Network(nn.Module):
    def __init__(self, batch_size, action_space, n_frames_input, kernels_size, out_channels, strides, fc_size):
        """
        DQN netowrk
        """
        super(DDDQN_Network, self).__init__()

        self.batch_size = batch_size
        self.action_space = action_space
        self.n_frame_input = n_frames_input

        assert len(out_channels) == 3
        self.out_channels = out_channels
        assert len(kernels_size) == 3
        self.kernels_size = kernels_size
        assert len(strides) == 3
        self.strides = strides

        assert len(fc_size) == 2
        self.fc_size = fc_size


        self.conv1 = nn.Sequential(nn.Conv2d(in_channels=self.n_frame_input,
                                             out_channels=self.out_channels[0],
                                             kernel_size=(kernels_size[0], kernels_size[0]),
                                             stride=self.strides[0]),
                                   nn.ELU())

        self.conv2 = nn.Sequential(nn.Conv2d(in_channels=self.out_channels[0],
                                             out_channels=self.out_channels[1],
                                             kernel_size=(kernels_size[1], kernels_size[1]),
                                             stride=self.strides[1]),
                                   nn.ELU())

        self.conv3 = nn.Sequential(nn.Conv2d(in_channels=self.out_channels[1],
                                             out_channels=self.out_channels[2],
                                             kernel_size=(kernels_size[2], kernels_size[2]),
                                             stride=self.strides[2]),
                                   nn.ELU())

        self.value_fc = nn.Sequential(nn.Linear(in_features=self.fc_size[0],
                                           out_features=self.fc_size[1]),
                                      nn.ELU())

        self.value = nn.Sequential(nn.Linear(in_features=self.fc_size[1],
                                             out_features=1))   # value function for given state s_t

        self.advantage_fc = nn.Sequential(
            nn.Linear(in_features=self.fc_size[0],
                      out_features=self.fc_size[1]),
            nn.ELU()
        )
        self.advantage = nn.Sequential(
            nn.Linear(in_features=self.fc_size[1],
                      out_features=self.action_space))          # advantage of each action at state s_t

        self._loss = nn.MSELoss(reduction='none')

    def reset_parameters(self):
        for p in self.parameters():
            if len(p.data.shape) > 1:
                nn.init.xavier_uniform_(p)


    def forward(self, X):
        """
        Estimate the value function (expected future reward for the given input and every action)
        :param X: input state
        :return:
        """
        # Our input are 4 RGB frames of shape 160, 160 each
        X_conv1 = self.conv1(X)
        X_conv2 = self.conv2(X_conv1)
        X_conv3 = self.conv3(X_conv2)

        X_flatten = X_conv3.view(X_conv3.size(0), -1)
        X_value = self.value_fc(X_flatten)
        value = self.value(X_value)

        X_advantage = self.advantage_fc(X_flatten)
        advantage = self.advantage(X_advantage)

        q_values = value + (advantage - torch.mean(advantage, dim=1, keepdim=True))

        return q_values

    def compute_q_value(self, state, actions):
        """
        Return the q_value for the given state and action
        :param state: state s_t obtained from the env
        :param actions: an array of action
        :return: 
        """
        q_values = self.forward(state)
        q_value = torch.sum(torch.mul(q_values, actions), dim=1)
        return q_value

    def compute_loss(self, q_values, q_target, weights):
        """
        compute the loss between the q-values taken w.r.t the optimal ones
        :param q_values: current estimation of the state-action values obtained following an e-greedy policy
        :param q_target: q_values obtained following an optimal policy on a previous network parametrization
        :param IS_weights: weight used to remove the bias of the priority sampling
        :return: 
        """

        absolute_error = torch.abs(q_target - q_values)
        self.loss =  torch.mean(weights * self._loss(q_target, q_values))
        return self.loss, absolute_error
