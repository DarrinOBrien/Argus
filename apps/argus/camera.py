"""Standard-library V4L2 camera for Argus (no OpenCV/numpy/PIL on the board).

Captures YUYV 1280x720 from a UVC camera and derives, at C speed with slicing only:
  - a 640x360 grayscale BMP preview for the web UI
  - 512x512 PPM crops per zone for the vision model (the ZETIC SDK needs exactly 512x512 RGB)

Colour is dropped (luma only): pure-Python YUV->RGB is too slow, and item counting works on shape.
"""
import fcntl
import mmap
import os
import select
import struct
import threading
import time

W, H = 1280, 720
# Zone = left x offset in the 1024x512 squeezed frame. Left half = tray, right half = patient area.
ZONES = {"tray": 0, "patient": 512}
CROP = 512


def _ioc(d, nr, size):
    return (d << 30) | (size << 16) | (ord("V") << 8) | nr


_S_FMT, _REQBUFS, _QUERYBUF = _ioc(3, 5, 208), _ioc(3, 8, 20), _ioc(3, 9, 88)
_QBUF, _DQBUF, _STREAMON, _STREAMOFF = _ioc(3, 15, 88), _ioc(3, 17, 88), _ioc(1, 18, 4), _ioc(1, 19, 4)
_YUYV = struct.unpack("<I", b"YUYV")[0]


def _bmp_gray(pixels, w, h):
    """8-bit top-down grayscale BMP (rows are already 4-byte aligned for w=640)."""
    palette = b"".join(bytes((i, i, i, 0)) for i in range(256))
    off = 14 + 40 + len(palette)
    header = b"BM" + struct.pack("<IHHI", off + len(pixels), 0, 0, off)
    info = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 8, 0, len(pixels), 2835, 2835, 256, 0)
    return header + info + palette + pixels


def find_camera():
    """First USB (uvcvideo) capture node; device numbers change across reboots."""
    base = "/sys/class/video4linux"
    try:
        nodes = sorted(os.listdir(base), key=lambda n: int(n[5:]))
    except (OSError, ValueError):
        return "/dev/video0"
    for node in nodes:
        try:
            driver = os.path.basename(os.readlink(f"{base}/{node}/device/driver"))
            index = open(f"{base}/{node}/index").read().strip()
        except OSError:
            continue
        if driver == "uvcvideo" and index == "0":
            return "/dev/" + node
    return "/dev/video0"


class Camera:
    """Background capture thread holding the latest luma plane."""

    def __init__(self, device="/dev/video0", mock=False):
        self.auto, self.mock = device == "auto", mock
        self.device = find_camera() if self.auto else device
        self.error = None
        self._luma = None
        self._stamp = 0.0
        self._lock = threading.Lock()
        self._stop = False
        if mock:
            row = bytes((x * 255 // W) for x in range(W))
            self._luma, self._stamp = row * H, time.time()
        else:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop:
            try:
                if self.auto:
                    self.device = find_camera()  # picks the camera up again after a re-plug
                self._capture()
            except OSError as exc:  # camera unplugged or busy: report as data and retry
                self.error = f"camera: {exc}"
                time.sleep(2)

    def _capture(self):
        fd = os.open(self.device, os.O_RDWR)
        try:
            fmt = bytearray(208)
            struct.pack_into("<I", fmt, 0, 1)
            struct.pack_into("<IIII", fmt, 8, W, H, _YUYV, 1)
            fcntl.ioctl(fd, _S_FMT, fmt)
            got = struct.unpack_from("<III", fmt, 8)
            if got != (W, H, _YUYV):
                raise OSError(f"camera did not accept YUYV {W}x{H}, got {got}")
            req = bytearray(struct.pack("<III", 4, 1, 1) + bytes(8))
            fcntl.ioctl(fd, _REQBUFS, req)
            maps = []
            for k in range(struct.unpack_from("<I", req, 0)[0]):
                qb = bytearray(88)
                struct.pack_into("<II", qb, 0, k, 1)
                struct.pack_into("<I", qb, 60, 1)
                fcntl.ioctl(fd, _QUERYBUF, qb)
                off, ln = struct.unpack_from("<I", qb, 64)[0], struct.unpack_from("<I", qb, 72)[0]
                maps.append(mmap.mmap(fd, ln, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=off))
                fcntl.ioctl(fd, _QBUF, qb)
            fcntl.ioctl(fd, _STREAMON, struct.pack("<I", 1))
            seen = 0
            try:
                while not self._stop:
                    if not select.select([fd], [], [], 5)[0]:
                        raise OSError("timeout waiting for a frame")
                    qb = bytearray(88)
                    struct.pack_into("<II", qb, 0, 0, 1)
                    struct.pack_into("<I", qb, 60, 1)
                    fcntl.ioctl(fd, _DQBUF, qb)
                    k, used = struct.unpack_from("<I", qb, 0)[0], struct.unpack_from("<I", qb, 8)[0]
                    seen += 1
                    if used >= W * H * 2 and seen > 10:  # the first frames after stream start are black
                        luma = maps[k][0:W * H * 2:2]  # Y of YUYV
                        with self._lock:
                            self._luma, self._stamp, self.error = luma, time.time(), None
                    fcntl.ioctl(fd, _QBUF, qb)
            finally:
                fcntl.ioctl(fd, _STREAMOFF, struct.pack("<I", 1))
                for m in maps:
                    m.close()
        finally:
            os.close(fd)

    def luma(self, max_age=3.0):
        with self._lock:
            luma, stamp = self._luma, self._stamp
        if luma is None or (not self.mock and time.time() - stamp > max_age):
            raise OSError(self.error or "no recent camera frame")
        return luma

    def preview_bmp(self, step=2):
        """Grayscale preview, downsampled by `step` (2 -> 640x360; 8 -> 160x90 for the serial bridge)."""
        luma = self.luma()
        rows = [luma[r * W:(r + 1) * W:step] for r in range(0, H, step)]
        return _bmp_gray(b"".join(rows), W // step, H // step)

    def zone_ppm(self, zone, path):
        """Write the zone's 512x512 view as a binary PPM; return the path.

        The frame minus 40 rows top and bottom (1280x640) is squeezed 5:4 to 1024x512 by dropping every
        fifth column and row. Left half = tray, right half = patient area, so the zones tile the full width.
        """
        luma = self.luma()
        sw = W * 4 // 5
        squeezed = bytearray(sw * H)
        for k in range(4):
            squeezed[k::4] = luma[k::5]
        x0 = ZONES[zone]
        rows = [r for r in range(40, H - 40) if (r - 40) % 5 != 4]
        gray = b"".join(squeezed[r * sw + x0:r * sw + x0 + CROP] for r in rows)
        rgb = bytearray(CROP * CROP * 3)
        rgb[0::3] = gray
        rgb[1::3] = gray
        rgb[2::3] = gray
        with open(path, "wb") as f:
            f.write(b"P6\n%d %d\n255\n" % (CROP, CROP) + rgb)
        return path

    def close(self):
        self._stop = True
