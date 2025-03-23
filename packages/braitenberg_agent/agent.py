#!/usr/bin/env python3

import math
from asyncio import AbstractEventLoop

import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from dtps import context, ContextConfig, DTPSContext
from dtps_http import RawData
from duckietown_messages.sensors.compressed_image import CompressedImage
from duckietown_messages.actuators.differential_pwm import DifferentialPWM
from duckietown_messages.utils.exceptions import DataDecodingError
from dt_robot_utils import get_robot_name


from solution.connections import get_motor_left_matrix, get_motor_right_matrix
from solution.preprocessing import preprocess


def rescale(a: float, L: float, U: float):
    if np.allclose(L, U):
        return 0.0
    return (a - L) / (U - L)


@dataclass
class BraitenbergAgentConfig:
    gain: float = 0.5
    const: float = 0.1


class BraitenbergAgent:
    config = BraitenbergAgentConfig()

    left: Optional[np.ndarray]
    right: Optional[np.ndarray]
    rgb: Optional[np.ndarray]
    l_max: float
    r_max: float
    l_min: float
    r_min: float

    def __init__(self):
        self.rgb = None
        self.l_max = -500000.0
        self.r_max = -500000.0
        self.l_min = math.inf
        self.r_min = math.inf
        self.left = None
        self.right = None

        self.is_shutdown = False

        self._camera_name = "front_center"
        self._wheels_name = "base"

        self._robot_name = get_robot_name()

        self._pwm: Optional[DTPSContext] = None
        self._loop: Optional[AbstractEventLoop] = None




    def compute_commands(self) -> Tuple[float, float]:
        """Returns the commands (pwm_left, pwm_right)"""
        # If we have not received any image, we don't move
        if self.rgb is None:
            return 0.0, 0.0

        if self.left is None:
            # if it is the first time, we initialize the structures
            shape = self.rgb.shape[0], self.rgb.shape[1]
            self.left = get_motor_left_matrix(shape)
            self.right = get_motor_right_matrix(shape)

        from matplotlib import pyplot as plt
        plt.imshow(self.rgb, interpolation='nearest')
        plt.show()
        # let's take only the intensity of RGB
        P = preprocess(self.rgb)
        # now we just compute the activation of our sensors
        l = float(np.sum(P * self.left))
        r = float(np.sum(P * self.right))
        print(f"l = {l}")
        print(f"r = {r}")
        # These are big numbers -- we want to normalize them.
        # We normalize them using the history

        # first, we remember the high/low of these raw signals
        self.l_max = max(l, self.l_max)
        self.r_max = max(r, self.r_max)
        self.l_min = min(l, self.l_min)
        self.r_min = min(r, self.r_min)

        print(f"l_max = {self.l_max}")
        print(f"r_max = {self.r_max}")
        print(f"l_min = {self.l_min}")
        print(f"r_min = {self.r_min}")

        # now rescale from 0 to 1
        ls = rescale(l, self.l_min, self.l_max)
        print(f"ls = {ls}")
        rs = rescale(r, self.r_min, self.r_max)
        print(f"rs = {rs}")
        gain = self.config.gain
        const = self.config.const
        pwm_left = const + ls * gain
        pwm_right = const + rs * gain

        return pwm_left, pwm_right



    async def on_received_image(self, data: RawData):
        try:
            jpeg: CompressedImage = CompressedImage.from_rawdata(data)
        except DataDecodingError as e:
            self.logerr(f"Failed to decode an incoming message: {e.message}")
            return

        if self.rgb is None:
            print("received first observations")

        self.rgb = jpeg.to_rgb()
        pwm_left, pwm_right = self.compute_commands()
        data = DifferentialPWM(left=pwm_left, right=pwm_right)
        try:
            await self._pwm.publish(data.to_rawdata())
        except Exception as e:
            print(f"Failed to publish last command. {e}")

    async def worker(self):
        # create switchboard context
        switchboard = (await context("switchboard")).navigate(self._robot_name)
        # wait for camera to be ready
        jpeg = await (switchboard / "sensor" / "camera" / self._camera_name / "jpeg").until_ready()
        self._pwm = await (switchboard / "actuator" / "wheels" / self._wheels_name / "pwm").until_ready()
        # Enable dynamic reconnection to the topic
        jpeg = jpeg.configure(ContextConfig(patient=True))

        # subscribe
        await jpeg.subscribe(self.on_received_image)
        # ---
        await self.join()

    async def join(self):
        while not self.is_shutdown:
            await asyncio.sleep(1)

    def spin(self):
        try:
            asyncio.run(self.worker())
        except RuntimeError:
            if not self.is_shutdown:
                self.logerr("An error occurred while running the event loop")
                raise

    def on_shutdown(self):
        if self._loop is not None:
            self.loginfo("Shutting down the event loop")
            self._loop.stop()
        self.is_shutdown = True


if __name__ == "__main__":
    # initialize the node
    agent_node = BraitenbergAgent()
    # keep the node alive
    agent_node.spin()


