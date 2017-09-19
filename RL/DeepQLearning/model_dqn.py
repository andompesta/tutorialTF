import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
from RL.DeepQLearning.helper import NetworkType
from RL.DeepQLearning.helper import TENSOR_TYPE



def epsilon_greedy_policy(network):
    """
    Create a epsilon greedy policy function based on the given network Q-function
    :param network: network used to approximate the Q-function
    :return: action
    """
    def policy_fn(observation, epsilon):
        A = TENSOR_TYPE["f_tensor"](np.ones(network.action_space)) * epsilon / network.action_space
        q_values = network.forward(Variable(observation.unsqueeze(dim=0), volatile=True))[0]
        best_action = torch.max(q_values, dim=0)[1]
        A[best_action] += (1.0 - epsilon)
        return A
    return policy_fn

class DQN_Network(nn.Module):
    def __init__(self, batch_size, action_space, n_frames_input, kernels_size, out_channels, strides, fc_size, type_):
        """
        DQN netowrk
        """
        super(DQN_Network, self).__init__()

        self.batch_size = batch_size
        self.action_space = action_space
        self.n_frame_input = n_frames_input
        self.type = NetworkType(type_)
        if self.type._value_ == 1:
            self.step = 0

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
                                   nn.ReLU())

        self.conv2 = nn.Sequential(nn.Conv2d(in_channels=self.out_channels[0],
                                             out_channels=self.out_channels[1],
                                             kernel_size=(kernels_size[1], kernels_size[1]),
                                             stride=self.strides[1]),
                                   nn.ReLU())

        self.conv3 = nn.Sequential(nn.Conv2d(in_channels=self.out_channels[1],
                                             out_channels=self.out_channels[2],
                                             kernel_size=(kernels_size[2], kernels_size[2]),
                                             stride=self.strides[2]),
                                   nn.ReLU())

        self.fc1 = nn.Sequential(nn.Linear(in_features=self.fc_size[0],
                                           out_features=self.fc_size[1]),
                                 nn.ReLU())
        self.fc2 = nn.Sequential(nn.Linear(in_features=self.fc_size[1],
                                           out_features=self.action_space),
                                 nn.ReLU())

        self._loss = nn.SmoothL1Loss()

    def forward(self, X):
        # Our input are 4 RGB frames of shape 160, 160 each
        self.X_pl = X  # [batch_size, 80, 80, n_frames_input]

        X_conv1 = self.conv1(self.X_pl)
        X_conv2 = self.conv2(X_conv1)
        X_conv3 = self.conv3(X_conv2)

        X_flatten = X_conv3.view(self.X_pl.size(0), -1)
        X_fc1 = self.fc1(X_flatten)
        self.prediction = self.fc2(X_fc1)
        return self.prediction.data

    def compute_action_pred(self, actions):
        """
        Return the q_value for the given actions
        :param actions: a numpy array of action
        :return: 
        """
        # Integer id of which action was selected
        self.actions_pl = i_type(actions.tolist())  # [batch_size, 1]

        mask_index = i_type(range(self.batch_size)) * self.action_space + self.actions_pl
        self.action_predictions = self.prediction.view(-1)[mask_index]
        return self.action_predictions

    def compute_loss(self, target):
        """
        compute the loss between the q-values taken w.r.t the optimal ones
        :param target: target values obtained following an optimal policy
        :return: 
        """
        # The TD target value
        self.y_pl = Variable(f_type(target))  # [batch_size, 1]
        self.loss = self._loss(self.action_predictions, self.y_pl)
        return self.loss
