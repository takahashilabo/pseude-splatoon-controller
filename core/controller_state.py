"""
Nintendo Switch Controller State
"""

from enum import IntFlag, IntEnum


class SwitchButton(IntFlag):
    NONE    = 0x0000
    Y       = 0x0001
    B       = 0x0002
    A       = 0x0004
    X       = 0x0008
    L       = 0x0010
    R       = 0x0020
    ZL      = 0x0040
    ZR      = 0x0080
    MINUS   = 0x0100
    PLUS    = 0x0200
    LCLICK  = 0x0400  # Lスティック押し込み
    RCLICK  = 0x0800  # Rスティック押し込み
    HOME    = 0x1000
    CAPTURE = 0x2000


class SwitchHat(IntEnum):
    TOP          = 0x00
    TOP_RIGHT    = 0x01
    RIGHT        = 0x02
    BOTTOM_RIGHT = 0x03
    BOTTOM       = 0x04
    BOTTOM_LEFT  = 0x05
    LEFT         = 0x06
    TOP_LEFT     = 0x07
    CENTER       = 0x08  # ニュートラル (非入力)


class ControllerState:
    def __init__(self):
        self.buttons: SwitchButton = SwitchButton.NONE
        self.hat: SwitchHat = SwitchHat.CENTER
        # スティック: -100.0 〜 +100.0 (0.0が中心)
        self.lx: float = 0.0
        self.ly: float = 0.0
        self.rx: float = 0.0
        self.ry: float = 0.0

    def reset(self):
        """全入力をニュートラル状態に戻す"""
        self.buttons = SwitchButton.NONE
        self.hat = SwitchHat.CENTER
        self.lx = 0.0
        self.ly = 0.0
        self.rx = 0.0
        self.ry = 0.0

    def set_button(self, button: SwitchButton, pressed: bool):
        if pressed:
            self.buttons |= button
        else:
            self.buttons &= ~button

