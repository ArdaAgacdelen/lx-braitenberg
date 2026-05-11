from typing import Tuple

import numpy as np


def get_motor_left_matrix(shape: Tuple[int, int]) -> np.ndarray:
    res = np.zeros(shape=shape, dtype="float32")
    # TODO define left matrix
    W = shape[1]
    res[:, 0: W//2] = 1
    res[:, W//2:W] = -1
    return res


def get_motor_right_matrix(shape: Tuple[int, int]) -> np.ndarray:
    res = np.zeros(shape=shape, dtype="float32")
    # TODO define right matrix
    W = shape[1]
    res[:, 0: W//2] = -1
    res[:, W//2:W] = 1
    return res
