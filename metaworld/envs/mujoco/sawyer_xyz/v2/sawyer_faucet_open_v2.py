import numpy as np
from gym.spaces import Box

from metaworld.envs.asset_path_utils import full_v2_path_for
from metaworld.envs.mujoco.sawyer_xyz.sawyer_xyz_env import SawyerXYZEnv, _assert_task_is_set


class SawyerFaucetOpenEnvV2(SawyerXYZEnv):
    def __init__(self):

        hand_low = (-0.5, 0.40, -0.15)
        hand_high = (0.5, 1, 0.5)
        obj_low = (-0.05, 0.8, 0.0)
        obj_high = (0.05, 0.85, 0.0)

        super().__init__(
            self.model_name,
            hand_low=hand_low,
            hand_high=hand_high,
        )

        self.init_config = {
            'obj_init_pos': np.array([0, 0.8, 0.0]),
            'hand_init_pos': np.array([0., .4, .2]),
        }
        self.obj_init_pos = self.init_config['obj_init_pos']
        self.hand_init_pos = self.init_config['hand_init_pos']

        goal_low = self.hand_low
        goal_high = self.hand_high

        self.max_path_length = 150

        self._random_reset_space = Box(
            np.array(obj_low),
            np.array(obj_high),
        )
        self.goal_space = Box(np.array(goal_low), np.array(goal_high))

        self.handle_length = 0.175

    @property
    def model_name(self):
        return full_v2_path_for('sawyer_xyz/sawyer_faucet.xml')

    @_assert_task_is_set
    def step(self, action):
        ob = super().step(action)
        reward, reachDist, pullDist = self.compute_reward(action, ob)
        self.curr_path_length += 1
        info = {
            'reachDist': reachDist,
            'goalDist': pullDist,
            'epRew': reward,
            'pickRew': None,
            'success': float(pullDist <= 0.05),
        }

        return ob, reward, False, info

    @property
    def _target_site_config(self):
        return [
            ('goal_open', self._target_pos),
            ('goal_close', np.array([10., 10., 10.]))
        ]

    def _get_pos_objects(self):
        knob_center = self.get_body_com('faucetBase') + np.array([.0, .0, .125])
        knob_angle_rad = self.data.get_joint_qpos('knob_Joint_1')

        offset = np.array([
            np.sin(knob_angle_rad),
            -np.cos(knob_angle_rad),
            0
        ])
        offset *= self.handle_length

        return knob_center + offset

    def reset_model(self):
        self._reset_hand()

        # Compute faucet position
        self.obj_init_pos = self._get_state_rand_vec() if self.random_init \
            else self.init_config['obj_init_pos']
        # Set mujoco body to computed position
        self.sim.model.body_pos[self.model.body_name2id(
            'faucetBase'
        )] = self.obj_init_pos

        self._target_pos = self.obj_init_pos + np.array(
            [+self.handle_length, .0, .125]
        )

        self.maxPullDist = np.linalg.norm(self._target_pos - self.obj_init_pos)

        return self._get_obs()

    def _reset_hand(self):
        super()._reset_hand()
        self.reachCompleted = False

    def compute_reward(self, actions, obs):
        del actions

        objPos = obs[3:6]

        rightFinger, leftFinger = self._get_site_pos('rightEndEffector'), self._get_site_pos('leftEndEffector')
        fingerCOM  =  (rightFinger + leftFinger)/2

        pullGoal = self._target_pos

        pullDist = np.linalg.norm(objPos - pullGoal)
        reachDist = np.linalg.norm(objPos - fingerCOM)
        reachRew = -reachDist

        self.reachCompleted = reachDist < 0.05

        def pullReward():
            c1 = 1000
            c2 = 0.01
            c3 = 0.001

            if self.reachCompleted:
                pullRew = 1000*(self.maxPullDist - pullDist) + c1*(np.exp(-(pullDist**2)/c2) + np.exp(-(pullDist**2)/c3))
                pullRew = max(pullRew,0)
                return pullRew
            else:
                return 0

        pullRew = pullReward()
        reward = reachRew + pullRew

        return [reward, reachDist, pullDist]

    def tmp_relabeling_fn(
            self,
            states: dict,
            actions,
            next_states: dict,
            contexts: dict,
    ):
        del actions
        del states

        obs = next_states['state_observation']

        objPos = obs[..., 3:6]
        fingerCOM = obs[..., 0:3]
        pullGoal = contexts['state_desired_goal'][..., 3:6]
        pullDist = np.linalg.norm(objPos - pullGoal, axis=-1)
        reachDist = np.linalg.norm(objPos - fingerCOM, axis=-1)

        reachCompleted = reachDist < 0.05

        c1 = 1000
        c2 = 0.01
        c3 = 0.001
        reachRew = -reachDist
        maxPullDist = np.linalg.norm([0.175, 0.125])

        pullRew = reachCompleted * (
          1000*(maxPullDist - pullDist) + c1*(np.exp(-(pullDist**2)/c2) + np.exp(-(pullDist**2)/c3))
        )
        pullRew = np.maximum(pullRew, 0)
        reward = reachRew + pullRew

        return reward
