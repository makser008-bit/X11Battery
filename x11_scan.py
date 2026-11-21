"""
Сканер HID-інтерфейсів донгла ATTACK SHARK X11 (VID 1D57, PID FA60). Чистий ctypes, без залежностей.

  python x11_scan.py              - список інтерфейсів (usage page, довжини звітів)
  python x11_scan.py listen 40    - слухати input-звіти 40 с (рухай мишу, тисни DPI, підключи зарядку)
  python x11_scan.py feature      - прочитати feature-звіти (id 0-255) з усіх інтерфейсів

Результат вставляй у чат. Все також пишеться у x11_scan_log.txt поруч зі скриптом.
"""
import ctypes, os, struct, sys, threading, time
from ctypes import wintypes as wt

VID, PID = 0x1D57, 0xFA60

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

class GUID(ctypes.Structure):
    _fields_ = [("D1", wt.DWORD), ("D2", wt.WORD), ("D3", wt.WORD), ("D4", ctypes.c_ubyte * 8)]

class SP_DID(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("Guid", GUID), ("Flags", wt.DWORD), ("Reserved", ctypes.c_void_p)]

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT),
                ("InLen", wt.USHORT), ("OutLen", wt.USHORT), ("FeatLen", wt.USHORT),
                ("Reserved", wt.USHORT * 17),
                ("NumLinkNodes", wt.USHORT),
                ("NumInBtn", wt.USHORT), ("NumInVal", wt.USHORT), ("NumInIdx", wt.USHORT),
                ("NumOutBtn", wt.USHORT), ("NumOutVal", wt.USHORT), ("NumOutIdx", wt.USHORT),
                ("NumFeatBtn", wt.USHORT), ("NumFeatVal", wt.USHORT), ("NumFeatIdx", wt.USHORT)]

P = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.restype = P
setupapi.SetupDiGetClassDevsW.argtypes = [P, wt.LPCWSTR, P, wt.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [P, P, P, wt.DWORD, P]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [P, P, P, wt.DWORD, P, P]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [P]
hid.HidD_GetHidGuid.argtypes = [P]
hid.HidD_GetPreparsedData.argtypes = [P, P]
hid.HidD_FreePreparsedData.argtypes = [P]
hid.HidP_GetCaps.argtypes = [P, P]
hid.HidP_GetCaps.restype = ctypes.c_long
hid.HidD_GetFeature.argtypes = [P, P, wt.ULONG]
k32.CreateFileW.restype = P
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, P, wt.DWORD, wt.DWORD, P]
k32.ReadFile.argtypes = [P, P, wt.DWORD, P, P]
k32.CloseHandle.argtypes = [P]
INVALID = P(-1).value

LOG = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x11_scan_log.txt"), "a", encoding="utf-8")
def out(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n"); LOG.flush()

def hexs(b):
    return " ".join(f"{x:02x}" for x in b)

def find_paths():
    g = GUID(); hid.HidD_GetHidGuid(ctypes.byref(g))
    hdev = setupapi.SetupDiGetClassDevsW(ctypes.byref(g), None, None, 0x2 | 0x10)
    paths, i = [], 0
    while True:
        d = SP_DID(); d.cbSize = ctypes.sizeof(SP_DID)
        if not setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(g), i, ctypes.byref(d)):
            break
        i += 1
        req = wt.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(d), None, 0, ctypes.byref(req), None)
        buf = ctypes.create_string_buffer(req.value)
        struct.pack_into("I", buf, 0, 8 if ctypes.sizeof(P) == 8 else 6)
        if setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(d), buf, req.value, None, None):
            p = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            if f"vid_{VID:04x}" in p.lower() and f"pid_{PID:04x}" in p.lower():
                paths.append(p)
    setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return paths

def open_dev(path):
    """повертає (handle, can_rw)"""
    h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
    if h and h != INVALID:
        return h, True
    h = k32.CreateFileW(path, 0, 3, None, 3, 0, None)
    if h and h != INVALID:
        return h, False
    return None, False

def get_caps(h):
    pp = P()
    if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
        return None
    caps = HIDP_CAPS()
    hid.HidP_GetCaps(pp, ctypes.byref(caps))
    hid.HidD_FreePreparsedData(pp)
    return caps

def short(path):
    p = path.lower()
    mi = p.split("mi_")[1][:2] if "mi_" in p else "--"
    col = p.split("&col")[1][:2] if "&col" in p else "--"
    return f"MI_{mi} COL{col}"

def devices():
    res = []
    for p in find_paths():
        h, rw = open_dev(p)
        caps = get_caps(h) if h else None
        res.append((p, h, rw, caps))
    return res

def cmd_list():
    out(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} scan {VID:04x}:{PID:04x} ===")
    for p, h, rw, c in devices():
        if c is None:
            out(f"{short(p)}  не вдалось відкрити  {p}")
            continue
        vend = "  <-- VENDOR" if c.UsagePage >= 0xFF00 else ""
        out(f"{short(p)}  usage_page=0x{c.UsagePage:04x} usage=0x{c.Usage:04x}  "
            f"in={c.InLen} out={c.OutLen} feat={c.FeatLen}  rw={rw}{vend}")
        out(f"    {p}")

def cmd_listen(sec):
    out(f"=== listen {sec}s === (рухай мишу, крутни колесо, тисни DPI, встав/вийми зарядку)")
    t0 = time.time()
    def worker(name, h, n):
        buf = (ctypes.c_ubyte * n)()
        got = wt.DWORD(0)
        while True:
            if not k32.ReadFile(h, buf, n, ctypes.byref(got), None):
                out(f"[{name}] ReadFile помилка {ctypes.get_last_error()}"); return
            out(f"{time.time()-t0:7.2f}s [{name}] {hexs(bytes(buf[:got.value]))}")
    for p, h, rw, c in devices():
        if c is None or not rw or c.InLen == 0:
            out(f"{short(p)}: пропущено (rw={rw}, in={c.InLen if c else '-'})")
            continue
        threading.Thread(target=worker, args=(short(p), h, c.InLen), daemon=True).start()
    time.sleep(sec)
    out("=== кінець ===")
    os._exit(0)

def cmd_feature():
    out("=== feature reports ===")
    for p, h, rw, c in devices():
        if c is None or c.FeatLen == 0:
            continue
        out(f"{short(p)} feat_len={c.FeatLen}")
        for rid in range(256):
            buf = (ctypes.c_ubyte * c.FeatLen)(); buf[0] = rid
            if hid.HidD_GetFeature(h, buf, c.FeatLen):
                out(f"    id=0x{rid:02x}: {hexs(bytes(buf))}")

if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "list"
    if m == "listen":
        cmd_listen(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif m == "feature":
        cmd_feature()
    else:
        cmd_list()
