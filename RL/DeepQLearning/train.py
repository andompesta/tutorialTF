import itertools
import sys
from os.path import join as path_join
import numpy as np
import torch
from torch.autograd import Variable
from RL.DeepQLearning.model_dqn import epsilon_greedy_policy
from gym.wrappers import Monitor
import RL.DeepQLearning.helper as helper

if "../" not in sys.path:
  sys.path.append("../")

from collections import namedtuple
GLOBAL_STEP = 0


def work(env, q_network, t_network, args, vis, exp_name, optimizer):
    """
    Train the model
    :param env: OpenAI environment
    :param q_network: q-valueRL. network 
    :param t_network: target network
    :param args: args to be used
    :param vis: Visdom server
    :param exp_name: experiment name
    :param optimizer: optimizer used 
    :return: 
    """
    global GLOBAL_STEP
    torch.manual_seed(args.seed)
    Transition = namedtuple("Transition", ["state", "action", "reward", "next_state", "done"])


    # local variable for plotting
    update_performance = None
    update_reward = None
    update_loss = None

    # path variable
    video_path = path_join(args.monitor_path, exp_name)
    summary_path = path_join(args.model_path, exp_name)
    helper.ensure_dir(summary_path)
    helper.ensure_dir(video_path)


    if optimizer is None:
        optimizer = torch.optim.Adam(q_network.parameters(), lr=args.learning_rate)

    # Keeps track of useful statistics
    stats = helper.EpisodeStats(episode_lengths=0, episode_rewards=0)
    replay_memory = helper.ExperienceBuffer(buffer_size=args.replay_memory_size)

    # The epsilon decay schedule
    epsilons = np.linspace(args.epsilon_start, args.epsilon_end, args.epsilon_decay_steps)

    # The policy we're following
    policy = epsilon_greedy_policy(q_network)

    # Populate the replay memory with initial experience
    print("Populating replay memory...")
    state = env.reset()
    state = helper.state_processor(state)
    state = torch.stack([state] * 4, dim=1)
    for i in range(args.replay_memory_init_size):
        action, epsilon = policy(state, GLOBAL_STEP)
        next_state, reward, done, _ = env.step(action[0])
        next_state = helper.state_processor(next_state)
        next_state = torch.cat((state[:, 1:, :, :], next_state.unsqueeze(dim=0)), dim=1)

        # Add epsilon to Visdom
        vis.line(Y=np.array([epsilon]),
                 X=np.array([GLOBAL_STEP]),
                 opts=dict(legend=["epsilon"],
                           title="epsilon",
                           showlegend=True),
                 win="plane_perfromance_{}".format(exp_name),
                 update=update_performance)
        update_performance = "append"

        # action_probs = policy(state, epsilons[min(GLOBAL_STEP, args.epsilon_decay_steps - 1)])
        # action = torch.multinomial(action_probs, num_samples=1, replacement=True)
        # action = np.random.choice(np.arange(len(action_probs)), p=action_probs)     # initially take random action
        # next_state, reward, done, _ = env.step(action[0])
        # next_state = helper.state_processor(next_state)
        # next_state = np.append(state[1:, :, :], np.expand_dims(next_state, 0), axis=0)

        replay_memory.add(Transition(state, action, reward, next_state, float(done)))
        if done:
            state = env.reset()
            state = helper.state_processor(state)
            state = torch.stack([state] * 4, dim=1)
        else:
            state = next_state
        GLOBAL_STEP += 1
    # Record videos
    env = Monitor(env, directory=video_path, video_callable=lambda count: count % args.record_video_every == 0,
                  resume=True)
    # for i_episode in range(args.num_episodes):
    i_episode = 0
    while True:
        # Save the current checkpoint
        torch.save(q_network.state_dict(), helper.ensure_dir(
            path_join(summary_path, 'q_net-{}.cptk'.format(i_episode))))
        torch.save(t_network.state_dict(), helper.ensure_dir(
            path_join(summary_path, 't_net-{}.cptk'.format(i_episode))))

        # Reset the environment
        state = env.reset()
        state = helper.state_processor(state)
        state = torch.stack([state] * 4, dim=1)

        # Update statistics
        stats.episode_rewards = 0
        stats.episode_lengths = 0

        # One step in the environment
        for t in itertools.count():
            action, epsilon = policy(state, GLOBAL_STEP)
            next_state, reward, done, _ = env.step(action[0])
            next_state = helper.state_processor(next_state)
            next_state = torch.cat((state[:, 1:, :, :], next_state.unsqueeze(dim=0)), dim=1)

            # # Epsilon for this time step
            # epsilon = epsilons[min(GLOBAL_STEP, args.epsilon_decay_steps - 1)]

            # Add epsilon to Visdom
            vis.line(Y=np.array([epsilon]),
                     X=np.array([GLOBAL_STEP]),
                     opts=dict(legend=["epsilon"],
                               title="epsilon",
                               showlegend=True),
                     win="plane_perfromance_{}".format(exp_name),
                     update=update_performance)
            update_performance = "append"



            if GLOBAL_STEP % args.update_target_estimator_every == 0:
                t_network.load_state_dict(q_network.state_dict())
                print("\nCopied model parameters to target network.")

            # Take a step in the environment
            # action_probs = policy(state, epsilons[min(GLOBAL_STEP, args.epsilon_decay_steps - 1)])
            # # action = np.random.choice(np.arange(len(action_probs)), p=action_probs)  # initially take random action
            # # next_state, reward, done, _ = env.step(args.actions[action])
            # action = torch.multinomial(action_probs, num_samples=1, replacement=True)
            # next_state, reward, done, _ = env.step(action[0])
            #
            # next_state = helper.state_processor(next_state)
            # next_state = np.append(state[1:, :, :], np.expand_dims(next_state, 0), axis=0)

            # Save transition to replay memory
            replay_memory.add(Transition(state, action, reward, next_state, float(done)))

            # Update statistics
            stats.episode_rewards += reward
            stats.episode_lengths = t


            # Sample a minibatch from the replay memory
            state_batch, action_batch, reward_batch, next_state_batch, done_batch = replay_memory.sample(args.batch_size)

            # Calculate q values and targets
            q_value = q_network.compute_q_value(Variable(state_batch), Variable(action_batch))

            q_value_next_max = t_network.forward(Variable(next_state_batch)).detach().max(dim=1)[0]
            t_values = Variable(reward_batch) + args.discount_factor * (Variable(1 - done_batch) * q_value_next_max) # remove reward of final state


            # Perform gradient descent update
            optimizer.zero_grad()
            loss = q_network.compute_loss(q_value, t_values)
            loss.backward()
            torch.nn.utils.clip_grad_norm(q_network.parameters(), args.max_grad_norm)
            optimizer.step()
            vis.line(Y=np.array([[loss.data[0], q_value.max().data[0]]]),
                     X=np.array([[GLOBAL_STEP, GLOBAL_STEP]]),
                     opts=dict(legend=["loss", "max_q_value"],
                               title="{}_network".format(q_network.type._name_),
                               showlegend=True),
                     win="plane_{}_network_{}".format(q_network.type._name_, exp_name),
                     update=update_loss)
            update_loss = "append"

            # Print out which step we're on, useful for debugging.
            print("\rStep {} ({}) @ Episode {}".format(t, GLOBAL_STEP, i_episode + 1, loss.data[0]), end="")
            sys.stdout.flush()
            if done:
                # game ended
                break
            state = next_state
            GLOBAL_STEP += 1

        vis.line(Y=np.array([[stats.episode_rewards, stats.episode_lengths]]),
                 X=np.array([[i_episode, i_episode]]),
                 opts=dict(legend=["episode_reward", "episode_length"],
                           title="rewards",
                           showlegend=True),
                 win="plane_reward_{}".format(exp_name),
                 update=update_reward)
        update_reward = "append"
        vis.save(["main"])
        i_episode += 1

        yield GLOBAL_STEP, stats

    env.monitor.close()
    return stats