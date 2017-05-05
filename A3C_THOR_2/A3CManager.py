import sys
sys.path.append('../')
sys.path.append('../THOR')
import random
import tensorflow as tf
import numpy as np

from THOR import THORConfig
import TFUtil
import THORNet
from THOR.THOREnv import THOREnvironment
from THOR import THOROfflineEnv

import A3CUtil
import A3CConfig
import ImgUtil
import threading

from collections import deque
from A3CAgent import A3CAgent

class A3CManager:
    def __init__(self, num_agents, model_save_interval, model_save_path, offline_mode = False, feature_mode = False):
        # model related setting
        self._model_save_interval = model_save_interval
        self._model_save_path = model_save_path

        # environment related objects
        self._num_agents = num_agents
        self._supported_scens = THORConfig.supported_envs
        self._num_scenes = len(self._supported_scens)
        self._feature_mode = feature_mode
        self._offline_mode = offline_mode

        # preload the databse
        #THOREnvironment.pre_load(feat_mode = feature_mode)     
       
        self._global_agent = None  
        self._local_agents = [] 


    def learn(self, check_point, use_gpu, gpu_id=None):
        device_str = TFUtil.get_device_str(use_gpu=use_gpu, gpu_id=gpu_id)
        with tf.Graph().as_default():
            with tf.device(device_str):
                # initialize a global agent
                self._global_agent = A3CAgent(scope = "global", feature_mode = self._feature_mode)
                self._global_agent._init_network(check_point = check_point) 
                            
                # start training
                # create learner threads
                learner_threads = []
                for i in xrange(self._num_agents):
                    local_scope = "agent_{0:03d}".format(i)
                    local_agent = A3CAgent(scope = local_scope, feature_mode = self._feature_mode)
                    local_agent._init_network()
                    learner_threads.append(
                        threading.Thread(
                            target=local_agent.learn,
                            args=(use_gpu, gpu_id)))
                
                self._global_agent.create_summary_ops
                #with tf.Session() as sess:
                #    init = tf.global_variables_initializer()
                #    sess.run(init)
        for t in learner_threads:
            t.start()
        for t in learner_threads:
            t.join()

        print('Training started, please open Tensorboard to monitor the training process.')
        # Show the agents training and write summary statistics
        
        last_save_frame = 0
        cur_frame = 0
        while cur_frame <= A3CConfig.max_iterations:
            cur_frame = A3CAgent.num_frames
            if cur_frame - last_save_frame > self._model_save_interval or cur_frame >= A3CConfig.max_iterations:
                print("Model saved after {} frames".format(cur_frame))
                self._global_agent.save(self._model_save_path, global_step = cur_frame)


    def test(self, check_point, use_gpu, gpu_id=None):
        assert(len(self._envs) == 1)
        env = self._envs[0]
        history_buffer = A3CUtil.HistoryBuffer()

        # build network
        device_str = TFUtil.get_device_str(use_gpu=use_gpu, gpu_id=gpu_id)
        with tf.device(device_str):
            #self._init_network()
            # initialize all variables from the model
            self.load(self._model_save_path, check_point)

        # start new episode
        episode_idx = 0
        total_rewards = 0
        state, target = self._request_new_episode(env)

        # perform testing
        while episode_idx <= A3CConfig.max_iterations:
            # sample and perform action, store history
            action = self._select_action(env, state, target, episode_idx, test_mode = True)
            next_state, reward, done = self._perform_action(env, state, target, action, history_buffer)
            total_rewards += reward
            state = next_state

            if done:
                episode_idx += 1
                print('total_reward received: {0}'.format(total_rewards))
                history_buffer.clean_up()
                state = self._request_new_episode(env)
                total_rewards = 0
