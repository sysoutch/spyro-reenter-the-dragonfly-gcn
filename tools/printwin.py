"""PrintWindow capture of one window (works when it is covered): printwin.py HWND OUT.png"""
import ctypes, sys
from ctypes import wintypes
from PIL import Image

u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
u32.SetProcessDPIAware()
hwnd = wintypes.HWND(int(sys.argv[1]))
r = wintypes.RECT()
u32.GetWindowRect(hwnd, ctypes.byref(r))
w, h = r.right - r.left, r.bottom - r.top
wdc = u32.GetWindowDC(hwnd)
mdc = g32.CreateCompatibleDC(wdc)
bmp = g32.CreateCompatibleBitmap(wdc, w, h)
g32.SelectObject(mdc, bmp)
ok = u32.PrintWindow(hwnd, mdc, 2)

class BIH(ctypes.Structure):
    _fields_ = [('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32), ('biHeight', ctypes.c_int32),
                ('biPlanes', ctypes.c_uint16), ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
                ('biSizeImage', ctypes.c_uint32), ('a', ctypes.c_int32), ('b', ctypes.c_int32),
                ('c', ctypes.c_uint32), ('d', ctypes.c_uint32)]

bi = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
buf = ctypes.create_string_buffer(w * h * 4)
g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB').save(sys.argv[2])
g32.DeleteObject(bmp); g32.DeleteDC(mdc); u32.ReleaseDC(hwnd, wdc)
print('printwindow', ok, w, h)
