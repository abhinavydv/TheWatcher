from typing import Type

def bytes_enum(cls: Type) -> Type:
    """
        Convert all constant `int` values from `cls` to `bytes`
        and return a new class having these `bytes` values.
        All constants in `cls` should be of type `int` and from 0 to 255
    """
    for i in filter(lambda x: x.isupper(), dir(cls)):
        num: int = getattr(cls, i)
        if not isinstance(num, int):
            raise Exception(f"Expected constant to be 'int' "
                f"found '{num.__class__}'")
        if num < 0 or num > 255:
            raise Exception(f"expected constant to be from "
                f"0 to 255, found '{num}'")
        delattr(cls, i)
        setattr(cls, i, num.to_bytes(1, "big"))
    return cls


@bytes_enum
class Reasons:
    ALREADY_CONNECTED = 0x0


@bytes_enum
class Status:
    TARGET_WAITING = 0x0
    TARGET_RUNNING = 0x1


@bytes_enum
class Actions:
    DISCONNECT = 0x0
    SEND_TARGET_LIST = 0x1
    STOP_WATCHING = 0x2
    RESTART_TARGET = 0x3


@bytes_enum
class ClientTypes:
    TARGET = 0x00
    TARGET_SCREEN_READER = 0x01
    TARGET_CONTROLLER = 0x02

    WATCHER = 0x10
    WATCHER_SCREEN_READER = 0x11
    WATCHER_CONTROLLER = 0x12


@bytes_enum
class ControlDevice:
    CONTROL_MOUSE = 0x0
    CONTROL_KEYBOARD = 0x1


@bytes_enum
class ImageSendModes:
    DIRECT_JPG = 0x0  # send the whole new image
    DIFF = 0x1        # subtract one image from another and send diff
    CHANGES = 0x2     # send the changed areas of image


# not making this as bytes_enum as that would make transmitted message longer
class ControlEvents:
    MOUSE_UP = 0x0
    MOUSE_DOWN = 0x1
    MOUSE_MOVE = 0x2
