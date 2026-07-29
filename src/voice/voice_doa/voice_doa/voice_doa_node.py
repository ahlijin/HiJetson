#!/usr/bin/env python3
"""
voice_doa_node.py

Reads Direction-of-Arrival (DOA) angle from the ReSpeaker Mic Array v2.0 (XVF3000)
via USB vendor control registers or HID fallback. Also handles:

  - Hardware VAD  — reads VOICEACTIVITY register on each poll tick
  - LED ring      — ReSpeaker's 12-LED ring shows DOA direction (trace mode)
  - Param tuning  — service to read/write any XVF3000 register (HPF, AGC, AEC…)

Three backends tried in order: pyusb → hidapi → hidraw.

Topics published:
  /voice/doa_angle      (Float32)   DOA angle  0-360°
  /voice/doa_direction  (String)    direction label
  /voice/vad_hw         (Bool)      hardware VAD status

Subscribed:
  /status_led           (std_msgs/ColorRGBA)  LED colour override

Services:
  /voice/respeaker_get_param   — read  any XVF3000 register
  /voice/respeaker_set_param   — write any XVF3000 register

Parameters (~voice_doa):
  poll_rate      (int)   Hz (10)
  doa_vid, doa_pid        USB VID:PID (0x2886:0x0018)
  angle_offset   (float) mounting offset ° (0.0)
  backend        (str)   auto / pyusb / hidapi / hidraw
  led_enable     (bool)  LED ring on/off  (true)
  led_brightness (int)   LED brightness 0-255 (20)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, String, Bool, ColorRGBA
from voice_msgs.srv import Param  # for set_param, get_param

import struct
import time
import os

# ── Direction labels (12 × 30° sectors, 0 = front) ────────────────
_SECTOR_LABELS = [
    "front", "front_right", "right_front", "right",
    "right_back", "back_right", "back", "back_left",
    "left_back", "left", "left_front", "front_left",
]
_NO_DIRECTION = "none"

def _sector_to_center(sector: int) -> float:
    return (sector * 30 + 15) % 360

def _angle_to_label(angle: float) -> str:
    if angle < 0:
        return _NO_DIRECTION
    idx = int(((angle + 15) % 360) // 30)
    return _SECTOR_LABELS[idx]


# ── XVF3000 register map ──────────────────────────────────────────
# name: (id, offset, type, max, min, rw, info…)
_PARAMS = {
    'DOAANGLE':         (21, 0,  'int',   359, 0,   'ro', 'DOA angle'),
    'VOICEACTIVITY':    (19, 32, 'int',   1,   0,   'ro', 'VAD status'),
    'HPFONOFF':         (18, 27, 'int',   3,   0,   'rw', 'HPF: 0=off  1=70Hz  2=125Hz  3=180Hz'),
    'AGCONOFF':         (19, 0,  'int',   1,   0,   'rw', 'AGC on/off'),
    'AGCMAXGAIN':       (19, 1,  'float', 1000, 1,   'rw', 'Max AGC gain factor'),
    'AGCDESIREDLEVEL':  (19, 2,  'float', 0.99, 1e-8,'rw', 'Target output power level'),
    'AGCGAIN':          (19, 3,  'float', 1000, 1,   'rw', 'Current AGC gain'),
    'AGCTIME':          (19, 4,  'float', 1,    0.1, 'rw', 'AGC time constant'),
    'STATNOISEONOFF':   (19, 8,  'int',   1,   0,   'rw', 'Stationary noise suppression'),
    'NONSTATNOISEONOFF':(19, 11, 'int',   1,   0,   'rw', 'Non-stationary noise suppression'),
    'ECHOONOFF':        (19, 14, 'int',   1,   0,   'rw', 'Echo suppression'),
    'FREEZEONOFF':      (19, 6,  'int',   1,   0,   'rw', 'Freeze beamformer adaptation'),
    'GAMMAVAD_SR':      (19, 39, 'float', 1000, 0,   'rw', 'VAD threshold dB'),
    'AECFREEZEONOFF':   (18, 7,  'int',   1,   0,   'rw', 'AEC freeze'),
}
# Type for "int" uses payload flag 1; "float" uses flag 0
_PARAM_TYPE_FLAG = {'int': 1, 'float': 0}


# ── Low-level XVF3000 interface ────────────────────────────────────

class XVF3000HID:
    """Low-level access to XVF3000 via pyusb (vendor ctrl) or HID fallback."""

    _HID_REPORT_LEN = 2
    _USB_TIMEOUT = 100000

    def __init__(self, vid: int, pid: int, backend: str = "auto", logger=None):
        self._vid = vid
        self._pid = pid
        self._backend_force = backend
        self._log = logger or print
        self._fd: int | None = None
        self._hid_dev = None
        self._usb_dev = None
        self._backend: str | None = None
        self._hidraw_path: str | None = None
        self._pixel_ring = None

    # ── Open / Close ──────────────────────────────────────────────

    def open(self) -> bool:
        order = ["pyusb", "hidapi", "hidraw"]
        if self._backend_force != "auto":
            order = [self._backend_force]
        for name in order:
            fn = getattr(self, f"_try_{name}", None)
            if fn and fn():
                self._backend = name
                self._log(f"XVF3000: opened via {name}")
                return True
        self._log(f"XVF3000: no backend (VID=0x{self._vid:04x} PID=0x{self._pid:04x})")
        return False

    def close(self):
        self._close_pixel_ring()
        if self._usb_dev:
            try:
                import usb.util
                usb.util.dispose_resources(self._usb_dev)
            except Exception:
                pass
        if self._hid_dev:
            self._hid_dev.close()
        if self._fd is not None:
            os.close(self._fd)

    @property
    def is_pyusb(self) -> bool:
        return self._backend == "pyusb" and self._usb_dev is not None

    # ── DOA ───────────────────────────────────────────────────────

    def read_doa(self) -> int | None:
        if self._backend == "pyusb":
            return self._read_pyusb_doa()
        if self._backend == "hidapi":
            return self._read_hidapi_doa()
        if self._backend == "hidraw":
            return self._read_hidraw_doa()
        return None

    # ── VAD ───────────────────────────────────────────────────────

    def read_vad(self) -> bool | None:
        if not self.is_pyusb:
            return None
        try:
            import usb.util
            v = self._read_reg(19, 32, 'int')
            return bool(v) if v is not None else None
        except Exception:
            return None

    # ── Register read / write (pyusb only) ────────────────────────

    def read_register(self, name: str) -> int | float | None:
        """Read any XVF3000 register by name. Returns None on error."""
        info = _PARAMS.get(name)
        if not info or not self.is_pyusb:
            return None
        try:
            return self._read_reg(info[0], info[1], info[2])
        except Exception:
            return None

    def write_register(self, name: str, value: int | float) -> bool:
        """Write any RW register by name. Returns True on success."""
        info = _PARAMS.get(name)
        if not info or not self.is_pyusb or info[5] == 'ro':
            return False
        try:
            import usb.util
            flag = _PARAM_TYPE_FLAG.get(info[2], 1)
            if info[2] == 'int':
                payload = struct.pack(b'iii', info[1], int(value), flag)
            else:
                payload = struct.pack(b'ifi', info[1], float(value), flag)
            self._usb_dev.ctrl_transfer(
                usb.util.CTRL_OUT | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
                0, 0, info[0], payload, self._USB_TIMEOUT)
            return True
        except Exception:
            return False

    # ── LED pixel ring ────────────────────────────────────────────

    def init_pixel_ring(self) -> bool:
        if not self.is_pyusb:
            return False
        try:
            from pixel_ring import usb_pixel_ring_v2
            self._pixel_ring = usb_pixel_ring_v2.PixelRing(self._usb_dev)
            return True
        except ImportError:
            self._log("pixel_ring not installed — LED disabled")
            return False
        except Exception as e:
            self._log(f"pixel_ring init failed: {e}")
            return False

    def led_think(self):
        if self._pixel_ring:
            self._pixel_ring.set_brightness(10)
            self._pixel_ring.think()

    def led_trace(self, brightness: int = 20):
        if self._pixel_ring:
            self._pixel_ring.set_brightness(brightness)
            self._pixel_ring.trace()

    def led_color(self, r: float, g: float, b: float, a: float = 1.0):
        if self._pixel_ring:
            self._pixel_ring.set_brightness(int(20 * a))
            self._pixel_ring.set_color(r=int(r*255), g=int(g*255), b=int(b*255))

    def _close_pixel_ring(self):
        self._pixel_ring = None

    # ── Internal helpers ──────────────────────────────────────────

    def _read_reg(self, reg_id: int, offset: int, ty: str) -> int | float | None:
        import usb.util
        cmd = 0x80 | offset | (0x40 if ty == 'int' else 0)
        response = self._usb_dev.ctrl_transfer(
            usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE,
            0, cmd, reg_id, 8, self._USB_TIMEOUT)
        result = struct.unpack(b'ii', bytes(response))
        if ty == 'int':
            return result[0]
        return result[0] * (2. ** result[1])

    # ── pyusb backend ─────────────────────────────────────────────

    def _try_pyusb(self) -> bool:
        try:
            import usb.core, usb.util
        except ImportError:
            return False
        try:
            dev = usb.core.find(idVendor=self._vid, idProduct=self._pid)
            if dev is None:
                return False
            # 不 detach 任何内核驱动！ALSA 音频接口必须保留
            # 靠 udev MODE=0666 权限直接做 vendor control transfer
            try:
                dev.set_configuration()
            except usb.core.USBError:
                pass
            self._usb_dev = dev
            return True
        except Exception:
            return False

    def _read_pyusb_doa(self) -> int | None:
        try:
            return self._read_reg(21, 0, 'int')
        except Exception:
            return None

    # ── hidapi backend ────────────────────────────────────────────

    def _try_hidapi(self) -> bool:
        try:
            import hid
        except ImportError:
            return False
        try:
            dev = hid.device()
            dev.open(self._vid, self._pid)
            dev.set_nonblocking(True)
            self._hid_dev = dev
            return True
        except Exception:
            return False

    def _read_hidapi_doa(self) -> int | None:
        try:
            raw = self._hid_dev.read(self._HID_REPORT_LEN)
            return raw[1] if raw and len(raw) >= 2 else None
        except Exception:
            return None

    # ── hidraw backend ────────────────────────────────────────────

    def _find_hidraw(self) -> str | None:
        for entry in os.listdir('/dev/'):
            if not entry.startswith('hidraw'):
                continue
            hidraw_path = f'/dev/{entry}'
            sysfs = f'/sys/class/hidraw/{entry}/device/uevent'
            if not os.path.isfile(sysfs):
                continue
            try:
                with open(sysfs) as fh:
                    ue = fh.read()
                for prefix in ('0000', '0001', '0003'):
                    if f'HID_ID={prefix}:{self._vid:04X}:{self._pid:04X}' in ue:
                        return hidraw_path
            except OSError:
                continue
        return None

    def _try_hidraw(self) -> bool:
        path = self._find_hidraw()
        if not path:
            return False
        try:
            self._fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            self._hidraw_path = path
            return True
        except OSError:
            return False

    def _read_hidraw_doa(self) -> int | None:
        try:
            raw = os.read(self._fd, self._HID_REPORT_LEN)
            return raw[1] if raw and len(raw) >= 2 else None
        except Exception:
            return None


# ── ROS2 Node ──────────────────────────────────────────────────────

class VoiceDOANode(Node):
    def __init__(self):
        super().__init__('voice_doa')

        self.poll_rate = self.declare_parameter('poll_rate', 10).value
        self.doa_vid = self.declare_parameter('doa_vid', 0x2886).value
        self.doa_pid = self.declare_parameter('doa_pid', 0x0018).value
        self.angle_offset = self.declare_parameter('angle_offset', 0.0).value
        self.no_doa_value = self.declare_parameter('no_doa_value', 12).value
        self.backend = self.declare_parameter('backend', 'auto').value
        self._led_enable = self.declare_parameter('led_enable', True).value
        self._led_brightness = self.declare_parameter('led_brightness', 20).value

        # ── Publishers ──
        self._angle_pub = self.create_publisher(Float32, '/voice/doa_angle', 10)
        self._dir_pub = self.create_publisher(String, '/voice/doa_direction', 10)
        self._vad_pub = self.create_publisher(Bool, '/voice/vad_hw', 10)

        # ── Hardware interface ──
        self._hid = XVF3000HID(self.doa_vid, self.doa_pid, self.backend, self.get_logger().info)
        if not self._hid.open():
            self.get_logger().error(
                "Cannot open XVF3000. Install:\n"
                "  pip3 install pyusb hidapi pixel-ring\n"
                "  sudo apt install libhidapi-libusb0\n"
                "  sudo cp scripts/99-respeaker.rules /etc/udev/rules.d/\n"
                "  lsusb | grep -i xvf"
            )

        # ── LED ring ──
        if self._hid.is_pyusb and self._led_enable:
            if self._hid.init_pixel_ring():
                self._hid.led_think()
                time.sleep(0.5)
                self._hid.led_trace(self._led_brightness)
                self.get_logger().info("LED ring initialized")
        else:
            self.get_logger().info("LED ring disabled (needs pyusb backend)")

        # ── LED colour override (external control via topic) ──
        self._led_timer = None
        self._led_sub = self.create_subscription(
            ColorRGBA, '/voice/status_led', self._led_callback, 10
        )

        # ── Parameter tuning services ──
        self._srv_set = self.create_service(
            Param, '/voice/respeaker_set_param', self._set_param_cb
        )
        self._srv_get = self.create_service(
            Param, '/voice/respeaker_get_param', self._get_param_cb
        )

        # ── Timer ──
        self._timer = self.create_timer(1.0 / self.poll_rate, self._poll_doa)
        self._last_valid_doa: float | None = None
        self._last_valid_time = 0.0

        self.get_logger().info(
            f"DOA node started: poll={self.poll_rate}Hz "
            f"VID=0x{self.doa_vid:04x}:{self.doa_pid:04x} "
            f"backend={self.backend} led={self._led_enable}"
        )

    # ── LED colour callback ───────────────────────────────────────

    def _led_callback(self, msg: ColorRGBA):
        if not self._hid.is_pyusb:
            return
        self._hid.led_color(r=msg.r, g=msg.g, b=msg.b, a=msg.a)
        self._hid.led_trace(self._led_brightness)
        # Reset to trace mode after 3 s
        if self._led_timer:
            self._led_timer.cancel()
        self._led_timer = self.create_timer(3.0, self._led_trace_reset)

    def _led_trace_reset(self):
        self._hid.led_trace(self._led_brightness)
        self._led_timer.cancel()

    # ── Parameter service callbacks ────────────────────────────────

    def _set_param_cb(self, req, resp):
        """Usage: request.data = 'HPFONOFF=2'  or  'GAMMAVAD_SR=3.5'"""
        try:
            if '=' not in req.data:
                resp.message = "format: PARAM=VALUE"
                return resp
            name, val_str = req.data.split('=', 1)
            name = name.strip().upper()
            info = _PARAMS.get(name)
            if not info:
                resp.message = f"unknown param: {name}"
                return resp
            val = float(val_str) if info[2] == 'float' else int(float(val_str))
            ok = self._hid.write_register(name, val)
            resp.message = "ok" if ok else f"failed (read-only or pyusb not available)"
        except Exception as e:
            resp.message = f"error: {e}"
        return resp

    def _get_param_cb(self, req, resp):
        """Usage: request.data = 'HPFONOFF'  reads register, returns value."""
        name = req.data.strip().upper()
        val = self._hid.read_register(name)
        if val is None:
            resp.message = f"failed (unknown param or pyusb not available)"
        else:
            resp.message = str(val)
        return resp

    # ── Poll loop ─────────────────────────────────────────────────

    def _poll_doa(self):
        raw = self._hid.read_doa()
        if raw is None:
            return

        # VAD
        vad = self._hid.read_vad()
        if vad is not None:
            msg = Bool()
            msg.data = vad
            self._vad_pub.publish(msg)

        now = self.get_clock().now().nanoseconds / 1e9

        if self._hid._backend == "pyusb":
            if raw < 0 or raw > 359:
                if self._last_valid_doa is not None and (now - self._last_valid_time) > 1.0:
                    self._publish_none()
                return
            angle = (raw + self.angle_offset) % 360
        else:
            if raw >= self.no_doa_value or raw > 11:
                if self._last_valid_doa is not None and (now - self._last_valid_time) > 1.0:
                    self._publish_none()
                return
            angle = (_sector_to_center(raw) + self.angle_offset) % 360

        self._last_valid_doa = angle
        self._last_valid_time = now

        # Publish topics
        msg_a = Float32(); msg_a.data = float(angle)
        self._angle_pub.publish(msg_a)
        msg_d = String(); msg_d.data = _angle_to_label(angle)
        self._dir_pub.publish(msg_d)

        # LED — trace mode auto-follows DOA on pixel-ring firmware
        self.get_logger().info(
            f"DOA: angle={angle:.0f}° dir={msg_d.data} vad={vad}",
            throttle_duration_sec=2.0,
        )

    def _publish_none(self):
        self._angle_pub.publish(Float32(data=-1.0))
        self._dir_pub.publish(String(data=_NO_DIRECTION))

    def destroy_node(self):
        self._hid.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VoiceDOANode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
