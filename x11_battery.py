"""
ATTACK SHARK X11 - заряд акумулятора і DPI у віджетах біля системного трея Windows.
Чистий ctypes (без pip-залежностей). Читає input-звіти донгла VID 1D57 / PID FA60,
інтерфейс з usage page 0x0A (MI_02 COL03): 03 55 40 <стан> <заряд %>.
"""
import ctypes, json, os, re, struct, sys, threading, time
from ctypes import wintypes as wt
import winreg

VID, PID = 0x1D57, 0xFA60
APP = "X11Battery"
VERSION = "0.8.1"
STALE_SEC = 15  # скільки секунд без звітів вважати "немає даних"

# Значення DPI для ступенів беруться з файлу dpi.txt поруч з програмою (.exe або .py).
def app_dir():
    base = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    return os.path.dirname(base)

CONFIG_PATH = os.path.join(app_dir(), "dpi.txt")
_cfg = {"mtime": None, "data": {}}

def ensure_config():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(config_template())
        except OSError:
            pass

def load_dpi_stages():
    try:
        mt = os.path.getmtime(CONFIG_PATH)
    except OSError:
        return {}
    if mt != _cfg["mtime"]:
        data = {}
        try:
            with open(CONFIG_PATH, encoding="utf-8-sig", errors="ignore") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()
                    if "=" not in line:
                        continue
                    k, v = (x.strip() for x in line.split("=", 1))
                    if k.isdigit() and v.isdigit():
                        data[int(k)] = int(v)
        except OSError:
            pass
        _cfg["mtime"], _cfg["data"] = mt, data
    return _cfg["data"]

P = ctypes.c_void_p
LRESULT = ctypes.c_ssize_t

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
uxtheme = ctypes.WinDLL("uxtheme", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)


# ---------------- структури ----------------
class GUID(ctypes.Structure):
    _fields_ = [("D1", wt.DWORD), ("D2", wt.WORD), ("D3", wt.WORD), ("D4", ctypes.c_ubyte * 8)]

class SP_DID(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("Guid", GUID), ("Flags", wt.DWORD), ("Reserved", ctypes.c_void_p)]

class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wt.USHORT), ("UsagePage", wt.USHORT),
                ("InLen", wt.USHORT), ("OutLen", wt.USHORT), ("FeatLen", wt.USHORT),
                ("Reserved", wt.USHORT * 17), ("NumLinkNodes", wt.USHORT),
                ("NumInBtn", wt.USHORT), ("NumInVal", wt.USHORT), ("NumInIdx", wt.USHORT),
                ("NumOutBtn", wt.USHORT), ("NumOutVal", wt.USHORT), ("NumOutIdx", wt.USHORT),
                ("NumFeatBtn", wt.USHORT), ("NumFeatVal", wt.USHORT), ("NumFeatIdx", wt.USHORT)]

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", P), ("hIcon", P), ("hCursor", P),
                ("hbrBackground", P), ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", P), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", P), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", P)]

class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                ("hbmMask", P), ("hbmColor", P)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

class TOOLINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("uFlags", wt.UINT), ("hwnd", P), ("uId", ctypes.c_size_t),
                ("rect", wt.RECT), ("hinst", P), ("lpszText", P), ("lParam", wt.LPARAM), ("lpReserved", P)]

class MENUITEMINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("fMask", wt.UINT), ("fType", wt.UINT), ("fState", wt.UINT),
                ("wID", wt.UINT), ("hSubMenu", P), ("hbmpChecked", P), ("hbmpUnchecked", P),
                ("dwItemData", ctypes.c_size_t), ("dwTypeData", wt.LPWSTR), ("cch", wt.UINT),
                ("hbmpItem", P)]

class TEXTMETRICW(ctypes.Structure):
    _fields_ = [("tmHeight", wt.LONG), ("tmAscent", wt.LONG), ("tmDescent", wt.LONG),
                ("tmInternalLeading", wt.LONG), ("tmExternalLeading", wt.LONG),
                ("tmAveCharWidth", wt.LONG), ("tmMaxCharWidth", wt.LONG), ("tmWeight", wt.LONG),
                ("tmOverhang", wt.LONG), ("tmDigitizedAspectX", wt.LONG), ("tmDigitizedAspectY", wt.LONG),
                ("tmFirstChar", wt.WCHAR), ("tmLastChar", wt.WCHAR), ("tmDefaultChar", wt.WCHAR),
                ("tmBreakChar", wt.WCHAR), ("tmItalic", wt.BYTE), ("tmUnderlined", wt.BYTE),
                ("tmStruckOut", wt.BYTE), ("tmPitchAndFamily", wt.BYTE), ("tmCharSet", wt.BYTE)]

class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD), ("hwndTrack", P), ("dwHoverTime", wt.DWORD)]

class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT),
                ("dwFlags", wt.DWORD), ("szDevice", wt.WCHAR * 32)]

MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, P, P, P, wt.LPARAM)

class INITCOMMONCONTROLSEX(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("dwICC", wt.DWORD)]

# ---------------- прототипи ----------------
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
k32.CreateFileW.restype = P
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, P, wt.DWORD, wt.DWORD, P]
k32.ReadFile.argtypes = [P, P, wt.DWORD, P, P]
k32.CloseHandle.argtypes = [P]
k32.GetModuleHandleW.restype = P
k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
k32.CreateMutexW.restype = P
k32.CreateMutexW.argtypes = [P, wt.BOOL, wt.LPCWSTR]
k32.GetUserPreferredUILanguages.argtypes = [wt.DWORD, ctypes.POINTER(wt.ULONG), P, ctypes.POINTER(wt.ULONG)]
k32.GetUserDefaultLocaleName.argtypes = [wt.LPWSTR, ctypes.c_int]
INVALID = P(-1).value

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.restype = P
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, P, P, P, P]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), P, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.PostMessageW.argtypes = [P, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
user32.SetTimer.argtypes = [P, ctypes.c_size_t, wt.UINT, P]
user32.CreatePopupMenu.restype = P
user32.AppendMenuW.argtypes = [P, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [P, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, P, P]
user32.DestroyMenu.argtypes = [P]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetForegroundWindow.argtypes = [P]
user32.DestroyIcon.argtypes = [P]
user32.DestroyWindow.argtypes = [P]
user32.GetDC.restype = P
user32.GetDC.argtypes = [P]
user32.ReleaseDC.argtypes = [P, P]
user32.FillRect.argtypes = [P, ctypes.POINTER(wt.RECT), P]
user32.DrawTextW.argtypes = [P, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT]
user32.CreateIconIndirect.restype = P
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.LoadCursorW.restype = P
user32.LoadCursorW.argtypes = [P, P]
gdi32.CreateCompatibleDC.restype = P
gdi32.CreateCompatibleDC.argtypes = [P]
gdi32.CreateCompatibleBitmap.restype = P
gdi32.CreateCompatibleBitmap.argtypes = [P, ctypes.c_int, ctypes.c_int]
gdi32.CreateBitmap.restype = P
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wt.UINT, wt.UINT, P]
gdi32.SelectObject.restype = P
gdi32.SelectObject.argtypes = [P, P]
gdi32.CreateSolidBrush.restype = P
gdi32.CreateSolidBrush.argtypes = [wt.DWORD]
gdi32.DeleteObject.argtypes = [P]
gdi32.DeleteDC.argtypes = [P]
gdi32.SetTextColor.argtypes = [P, wt.DWORD]
gdi32.SetBkMode.argtypes = [P, ctypes.c_int]
gdi32.CreateFontW.restype = P
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
user32.FindWindowW.restype = P
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowExW.restype = P
user32.FindWindowExW.argtypes = [P, P, wt.LPCWSTR, wt.LPCWSTR]
user32.GetWindowRect.argtypes = [P, ctypes.POINTER(wt.RECT)]
user32.SetWindowPos.argtypes = [P, P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.ShowWindow.argtypes = [P, ctypes.c_int]
user32.IsWindow.argtypes = [P]
user32.SetCapture.argtypes = [P]
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [P, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.UpdateLayeredWindow.argtypes = [P, P, P, P, P, P, wt.DWORD, P, wt.DWORD]
gdi32.CreateDIBSection.restype = P
gdi32.CreateDIBSection.argtypes = [P, P, wt.UINT, P, P, wt.DWORD]
gdi32.GdiFlush.argtypes = []
gdi32.CreatePen.restype = P
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetStockObject.restype = P
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.MoveToEx.argtypes = [P, ctypes.c_int, ctypes.c_int, P]
gdi32.LineTo.argtypes = [P, ctypes.c_int, ctypes.c_int]
gdi32.RoundRect.argtypes = [P] + [ctypes.c_int] * 6
gdi32.Polygon.argtypes = [P, P, ctypes.c_int]
gdi32.GetTextExtentPoint32W.argtypes = [P, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE)]
gdi32.TextOutW.argtypes = [P, ctypes.c_int, ctypes.c_int, wt.LPCWSTR, ctypes.c_int]
gdi32.GetTextFaceW.argtypes = [P, ctypes.c_int, wt.LPWSTR]
gdi32.GetTextMetricsW.argtypes = [P, ctypes.POINTER(TEXTMETRICW)]
user32.GetWindowTextW.argtypes = [P, wt.LPWSTR, ctypes.c_int]
user32.SetWindowTextW.argtypes = [P, wt.LPCWSTR]
user32.MessageBoxW.argtypes = [P, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
user32.AdjustWindowRectEx.argtypes = [ctypes.POINTER(wt.RECT), wt.DWORD, wt.BOOL, wt.DWORD]
user32.IsDialogMessageW.argtypes = [P, ctypes.POINTER(wt.MSG)]
user32.SetFocus.argtypes = [P]
user32.GetClientRect.argtypes = [P, ctypes.POINTER(wt.RECT)]
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
user32.IsWindowVisible.argtypes = [P]
gdi32.SetBkColor.argtypes = [P, wt.DWORD]
uxtheme.SetWindowTheme.argtypes = [P, wt.LPCWSTR, wt.LPCWSTR]
dwmapi.DwmSetWindowAttribute.argtypes = [P, wt.DWORD, P, wt.DWORD]
user32.InsertMenuItemW.argtypes = [P, wt.UINT, wt.BOOL, ctypes.POINTER(MENUITEMINFOW)]
user32.LoadImageW.restype = P
user32.LoadImageW.argtypes = [P, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.GetMenuItemCount.restype = ctypes.c_int
user32.GetMenuItemCount.argtypes = [P]
comctl32.InitCommonControlsEx.argtypes = [P]
user32.EnumDisplayMonitors.argtypes = [P, P, MONITORENUMPROC, wt.LPARAM]
user32.GetMonitorInfoW.argtypes = [P, P]
user32.MonitorFromWindow.restype = P
user32.MonitorFromWindow.argtypes = [P, wt.DWORD]
shell32.ShellExecuteW.restype = P
shell32.ShellExecuteW.argtypes = [P, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_int]
try:
    user32.GetDpiForWindow.restype = wt.UINT
    user32.GetDpiForWindow.argtypes = [P]
except AttributeError:
    pass

# ---------------- мови інтерфейсу (автовизначення мови Windows) ----------------
LANG_DIR = os.path.join(app_dir(), "lang")  # додаткові мови: lang/xx.json
RTL_LANGS = {"ar", "he", "fa", "ur"}
TR = {
    "en": {
        "waiting": "waiting for data...",
        "stale": "no data (last: {pct}%)",
        "charging": "(charging)",
        "dpi_press": "press the DPI button",
        "dpi_unknown": "unknown (set the values in dpi.txt)",
        "m_autostart": "Start with Windows",
        "m_dpi_widget": "Show DPI near the tray",
        "m_lock": "Lock position",
        "m_reset": "Reset position",
        "m_monitor": "Monitor for the widgets",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(primary)",
        "m_no_taskbar": "(no taskbar)",
        "m_dpi_setup": "Set DPI values...",
        "m_version": "Version {v}",
        "m_exit": "Exit",
        "m_language": "Language",
        "m_lang_auto": "Auto (Windows language)",
        "d_title": "DPI values",
        "d_hint": "Enter the DPI for each of the 6 stages of the mouse DPI button.",
        "d_stage": "Stage {n}",
        "d_save": "Save",
        "d_cancel": "Cancel",
        "d_err_range": "Stage {n}: the value must be from 1 to 100000.",
        "d_err_write": "Could not write dpi.txt (is the folder write-protected?).",
        "cfg_comment": "DPI values for the DPI button stages.\nEdit them via the app menu: \"{menu}\".\nFormat: stage_number = DPI",
    },
    "uk": {
        "waiting": "очікування даних...",
        "stale": "немає даних (останнє {pct}%)",
        "charging": "(заряджається)",
        "dpi_press": "натисни кнопку DPI",
        "dpi_unknown": "невідомо (вкажи значення в dpi.txt)",
        "m_autostart": "Запускати разом з Windows",
        "m_dpi_widget": "Показувати DPI біля трея",
        "m_lock": "Закріпити положення",
        "m_reset": "Скинути положення",
        "m_monitor": "Монітор для віджетів",
        "m_monitor_n": "Монітор {n}",
        "m_primary": "(основний)",
        "m_no_taskbar": "(немає панелі завдань)",
        "m_dpi_setup": "Налаштувати значення DPI...",
        "m_version": "Версія {v}",
        "m_exit": "Вихід",
        "m_language": "Мова",
        "m_lang_auto": "Авто (мова Windows)",
        "d_title": "Значення DPI",
        "d_hint": "Впиши DPI для кожного ступеня кнопки DPI на мишці (їх 6).",
        "d_stage": "Ступінь {n}",
        "d_save": "Зберегти",
        "d_cancel": "Скасувати",
        "d_err_range": "Ступінь {n}: значення має бути від 1 до 100000.",
        "d_err_write": "Не вдалося записати dpi.txt (папка захищена від запису?).",
        "cfg_comment": "Значення DPI для ступенів кнопки DPI.\nЗмінюється через меню програми: \"{menu}\".\nФормат: номер_ступеня = DPI",
    },
    "ru": {
        "waiting": "ожидание данных...",
        "stale": "нет данных (последнее: {pct}%)",
        "charging": "(заряжается)",
        "dpi_press": "нажмите кнопку DPI",
        "dpi_unknown": "неизвестно (укажите значения в dpi.txt)",
        "m_autostart": "Запускать вместе с Windows",
        "m_dpi_widget": "Показывать DPI возле трея",
        "m_lock": "Закрепить положение",
        "m_reset": "Сбросить положение",
        "m_monitor": "Монитор для виджетов",
        "m_monitor_n": "Монитор {n}",
        "m_primary": "(основной)",
        "m_no_taskbar": "(нет панели задач)",
        "m_dpi_setup": "Настроить значения DPI...",
        "m_version": "Версия {v}",
        "m_exit": "Выход",
        "m_language": "Язык",
        "m_lang_auto": "Авто (язык Windows)",
        "d_title": "Значения DPI",
        "d_hint": "Укажите DPI для каждой из 6 ступеней кнопки DPI на мыши.",
        "d_stage": "Ступень {n}",
        "d_save": "Сохранить",
        "d_cancel": "Отмена",
        "d_err_range": "Ступень {n}: значение должно быть от 1 до 100000.",
        "d_err_write": "Не удалось записать dpi.txt (папка защищена от записи?).",
        "cfg_comment": "Значения DPI для ступеней кнопки DPI.\nИзменяются через меню программы: \"{menu}\".\nФормат: номер_ступени = DPI",
    },
    "pl": {
        "waiting": "oczekiwanie na dane...",
        "stale": "brak danych (ostatnio: {pct}%)",
        "charging": "(ładowanie)",
        "dpi_press": "naciśnij przycisk DPI",
        "dpi_unknown": "nieznane (podaj wartości w dpi.txt)",
        "m_autostart": "Uruchamiaj z systemem Windows",
        "m_dpi_widget": "Pokaż DPI obok zasobnika",
        "m_lock": "Zablokuj położenie",
        "m_reset": "Resetuj położenie",
        "m_monitor": "Monitor dla widżetów",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(główny)",
        "m_no_taskbar": "(brak paska zadań)",
        "m_dpi_setup": "Ustaw wartości DPI...",
        "m_version": "Wersja {v}",
        "m_exit": "Zakończ",
        "m_language": "Język",
        "m_lang_auto": "Automatycznie (język Windows)",
        "d_title": "Wartości DPI",
        "d_hint": "Wpisz DPI dla każdego z 6 poziomów przycisku DPI myszy.",
        "d_stage": "Poziom {n}",
        "d_save": "Zapisz",
        "d_cancel": "Anuluj",
        "d_err_range": "Poziom {n}: wartość musi mieścić się w zakresie od 1 do 100000.",
        "d_err_write": "Nie można zapisać dpi.txt (folder chroniony przed zapisem?).",
        "cfg_comment": "Wartości DPI dla poziomów przycisku DPI.\nZmieniaj je w menu programu: \"{menu}\".\nFormat: numer_poziomu = DPI",
    },
    "de": {
        "waiting": "Warte auf Daten...",
        "stale": "keine Daten (zuletzt: {pct}%)",
        "charging": "(wird geladen)",
        "dpi_press": "DPI-Taste drücken",
        "dpi_unknown": "unbekannt (Werte in dpi.txt eintragen)",
        "m_autostart": "Mit Windows starten",
        "m_dpi_widget": "DPI neben dem Infobereich anzeigen",
        "m_lock": "Position sperren",
        "m_reset": "Position zurücksetzen",
        "m_monitor": "Monitor für die Widgets",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(primär)",
        "m_no_taskbar": "(keine Taskleiste)",
        "m_dpi_setup": "DPI-Werte festlegen...",
        "m_version": "Version {v}",
        "m_exit": "Beenden",
        "m_language": "Sprache",
        "m_lang_auto": "Automatisch (Windows-Sprache)",
        "d_title": "DPI-Werte",
        "d_hint": "Gib die DPI für jede der 6 Stufen der DPI-Taste deiner Maus ein.",
        "d_stage": "Stufe {n}",
        "d_save": "Speichern",
        "d_cancel": "Abbrechen",
        "d_err_range": "Stufe {n}: Der Wert muss zwischen 1 und 100000 liegen.",
        "d_err_write": "dpi.txt konnte nicht geschrieben werden (Ordner schreibgeschützt?).",
        "cfg_comment": "DPI-Werte für die Stufen der DPI-Taste.\nÄnderung über das Programmmenü: \"{menu}\".\nFormat: Stufennummer = DPI",
    },
    "fr": {
        "waiting": "en attente de données...",
        "stale": "aucune donnée (dernier : {pct}%)",
        "charging": "(en charge)",
        "dpi_press": "appuyez sur le bouton DPI",
        "dpi_unknown": "inconnu (renseignez les valeurs dans dpi.txt)",
        "m_autostart": "Lancer avec Windows",
        "m_dpi_widget": "Afficher le DPI près de la zone de notification",
        "m_lock": "Verrouiller la position",
        "m_reset": "Réinitialiser la position",
        "m_monitor": "Écran des widgets",
        "m_monitor_n": "Écran {n}",
        "m_primary": "(principal)",
        "m_no_taskbar": "(pas de barre des tâches)",
        "m_dpi_setup": "Définir les valeurs DPI...",
        "m_version": "Version {v}",
        "m_exit": "Quitter",
        "m_language": "Langue",
        "m_lang_auto": "Auto (langue de Windows)",
        "d_title": "Valeurs DPI",
        "d_hint": "Saisissez le DPI de chacun des 6 niveaux du bouton DPI de la souris.",
        "d_stage": "Niveau {n}",
        "d_save": "Enregistrer",
        "d_cancel": "Annuler",
        "d_err_range": "Niveau {n} : la valeur doit être comprise entre 1 et 100000.",
        "d_err_write": "Impossible d'écrire dpi.txt (dossier protégé en écriture ?).",
        "cfg_comment": "Valeurs DPI des niveaux du bouton DPI.\nÀ modifier via le menu du programme : « {menu} ».\nFormat : numéro_du_niveau = DPI",
    },
    "es": {
        "waiting": "esperando datos...",
        "stale": "sin datos (último: {pct}%)",
        "charging": "(cargando)",
        "dpi_press": "pulsa el botón DPI",
        "dpi_unknown": "desconocido (indica los valores en dpi.txt)",
        "m_autostart": "Iniciar con Windows",
        "m_dpi_widget": "Mostrar DPI junto a la bandeja",
        "m_lock": "Bloquear posición",
        "m_reset": "Restablecer posición",
        "m_monitor": "Monitor de los widgets",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(principal)",
        "m_no_taskbar": "(sin barra de tareas)",
        "m_dpi_setup": "Configurar valores DPI...",
        "m_version": "Versión {v}",
        "m_exit": "Salir",
        "m_language": "Idioma",
        "m_lang_auto": "Automático (idioma de Windows)",
        "d_title": "Valores DPI",
        "d_hint": "Introduce el DPI de cada uno de los 6 niveles del botón DPI del ratón.",
        "d_stage": "Nivel {n}",
        "d_save": "Guardar",
        "d_cancel": "Cancelar",
        "d_err_range": "Nivel {n}: el valor debe estar entre 1 y 100000.",
        "d_err_write": "No se pudo escribir dpi.txt (¿carpeta protegida contra escritura?).",
        "cfg_comment": "Valores DPI de los niveles del botón DPI.\nSe cambian desde el menú del programa: \"{menu}\".\nFormato: número_de_nivel = DPI",
    },
    "pt": {
        "waiting": "aguardando dados...",
        "stale": "sem dados (último: {pct}%)",
        "charging": "(carregando)",
        "dpi_press": "pressione o botão DPI",
        "dpi_unknown": "desconhecido (informe os valores em dpi.txt)",
        "m_autostart": "Iniciar com o Windows",
        "m_dpi_widget": "Mostrar DPI perto da bandeja",
        "m_lock": "Fixar posição",
        "m_reset": "Redefinir posição",
        "m_monitor": "Monitor dos widgets",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(principal)",
        "m_no_taskbar": "(sem barra de tarefas)",
        "m_dpi_setup": "Definir valores de DPI...",
        "m_version": "Versão {v}",
        "m_exit": "Sair",
        "m_language": "Idioma",
        "m_lang_auto": "Automático (idioma do Windows)",
        "d_title": "Valores de DPI",
        "d_hint": "Informe o DPI de cada um dos 6 níveis do botão DPI do mouse.",
        "d_stage": "Nível {n}",
        "d_save": "Salvar",
        "d_cancel": "Cancelar",
        "d_err_range": "Nível {n}: o valor deve estar entre 1 e 100000.",
        "d_err_write": "Não foi possível gravar dpi.txt (pasta protegida contra gravação?).",
        "cfg_comment": "Valores de DPI dos níveis do botão DPI.\nAltere pelo menu do programa: \"{menu}\".\nFormato: número_do_nível = DPI",
    },
    "it": {
        "waiting": "in attesa di dati...",
        "stale": "nessun dato (ultimo: {pct}%)",
        "charging": "(in carica)",
        "dpi_press": "premi il pulsante DPI",
        "dpi_unknown": "sconosciuto (imposta i valori in dpi.txt)",
        "m_autostart": "Avvia con Windows",
        "m_dpi_widget": "Mostra DPI vicino all'area di notifica",
        "m_lock": "Blocca posizione",
        "m_reset": "Reimposta posizione",
        "m_monitor": "Monitor per i widget",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(principale)",
        "m_no_taskbar": "(nessuna barra delle applicazioni)",
        "m_dpi_setup": "Imposta valori DPI...",
        "m_version": "Versione {v}",
        "m_exit": "Esci",
        "m_language": "Lingua",
        "m_lang_auto": "Automatica (lingua di Windows)",
        "d_title": "Valori DPI",
        "d_hint": "Inserisci i DPI per ciascuno dei 6 livelli del pulsante DPI del mouse.",
        "d_stage": "Livello {n}",
        "d_save": "Salva",
        "d_cancel": "Annulla",
        "d_err_range": "Livello {n}: il valore deve essere compreso tra 1 e 100000.",
        "d_err_write": "Impossibile scrivere dpi.txt (cartella protetta da scrittura?).",
        "cfg_comment": "Valori DPI per i livelli del pulsante DPI.\nModificali dal menu del programma: \"{menu}\".\nFormato: numero_livello = DPI",
    },
    "nl": {
        "waiting": "wachten op gegevens...",
        "stale": "geen gegevens (laatst: {pct}%)",
        "charging": "(wordt opgeladen)",
        "dpi_press": "druk op de DPI-knop",
        "dpi_unknown": "onbekend (stel de waarden in dpi.txt in)",
        "m_autostart": "Starten met Windows",
        "m_dpi_widget": "DPI naast het systeemvak tonen",
        "m_lock": "Positie vergrendelen",
        "m_reset": "Positie herstellen",
        "m_monitor": "Monitor voor de widgets",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(primair)",
        "m_no_taskbar": "(geen taakbalk)",
        "m_dpi_setup": "DPI-waarden instellen...",
        "m_version": "Versie {v}",
        "m_exit": "Afsluiten",
        "m_language": "Taal",
        "m_lang_auto": "Automatisch (Windows-taal)",
        "d_title": "DPI-waarden",
        "d_hint": "Voer de DPI in voor elk van de 6 standen van de DPI-knop van de muis.",
        "d_stage": "Stand {n}",
        "d_save": "Opslaan",
        "d_cancel": "Annuleren",
        "d_err_range": "Stand {n}: de waarde moet tussen 1 en 100000 liggen.",
        "d_err_write": "Kan dpi.txt niet schrijven (map beveiligd tegen schrijven?).",
        "cfg_comment": "DPI-waarden voor de standen van de DPI-knop.\nWijzigen via het programmamenu: \"{menu}\".\nIndeling: standnummer = DPI",
    },
    "tr": {
        "waiting": "veri bekleniyor...",
        "stale": "veri yok (son: {pct}%)",
        "charging": "(şarj oluyor)",
        "dpi_press": "DPI düğmesine basın",
        "dpi_unknown": "bilinmiyor (değerleri dpi.txt içinde belirtin)",
        "m_autostart": "Windows ile başlat",
        "m_dpi_widget": "DPI'yi bildirim alanının yanında göster",
        "m_lock": "Konumu kilitle",
        "m_reset": "Konumu sıfırla",
        "m_monitor": "Pencere öğeleri için monitör",
        "m_monitor_n": "Monitör {n}",
        "m_primary": "(birincil)",
        "m_no_taskbar": "(görev çubuğu yok)",
        "m_dpi_setup": "DPI değerlerini ayarla...",
        "m_version": "Sürüm {v}",
        "m_exit": "Çıkış",
        "m_language": "Dil",
        "m_lang_auto": "Otomatik (Windows dili)",
        "d_title": "DPI değerleri",
        "d_hint": "Farenin DPI düğmesinin 6 kademesinin her biri için DPI değerini girin.",
        "d_stage": "Kademe {n}",
        "d_save": "Kaydet",
        "d_cancel": "İptal",
        "d_err_range": "Kademe {n}: değer 1 ile 100000 arasında olmalıdır.",
        "d_err_write": "dpi.txt yazılamadı (klasör yazmaya karşı korumalı mı?).",
        "cfg_comment": "DPI düğmesi kademeleri için DPI değerleri.\nProgram menüsünden değiştirin: \"{menu}\".\nBiçim: kademe_numarası = DPI",
    },
    "cs": {
        "waiting": "čekání na data...",
        "stale": "žádná data (naposledy: {pct}%)",
        "charging": "(nabíjí se)",
        "dpi_press": "stiskněte tlačítko DPI",
        "dpi_unknown": "neznámé (zadejte hodnoty v dpi.txt)",
        "m_autostart": "Spouštět s Windows",
        "m_dpi_widget": "Zobrazit DPI vedle oznamovací oblasti",
        "m_lock": "Zamknout pozici",
        "m_reset": "Obnovit pozici",
        "m_monitor": "Monitor pro widgety",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(hlavní)",
        "m_no_taskbar": "(žádný hlavní panel)",
        "m_dpi_setup": "Nastavit hodnoty DPI...",
        "m_version": "Verze {v}",
        "m_exit": "Konec",
        "m_language": "Jazyk",
        "m_lang_auto": "Automaticky (jazyk Windows)",
        "d_title": "Hodnoty DPI",
        "d_hint": "Zadejte DPI pro každý ze 6 stupňů tlačítka DPI na myši.",
        "d_stage": "Stupeň {n}",
        "d_save": "Uložit",
        "d_cancel": "Zrušit",
        "d_err_range": "Stupeň {n}: hodnota musí být od 1 do 100000.",
        "d_err_write": "Soubor dpi.txt se nepodařilo zapsat (složka je chráněna proti zápisu?).",
        "cfg_comment": "Hodnoty DPI pro stupně tlačítka DPI.\nMění se v nabídce programu: \"{menu}\".\nFormát: číslo_stupně = DPI",
    },
    "ro": {
        "waiting": "se așteaptă date...",
        "stale": "fără date (ultima: {pct}%)",
        "charging": "(se încarcă)",
        "dpi_press": "apasă butonul DPI",
        "dpi_unknown": "necunoscut (setează valorile în dpi.txt)",
        "m_autostart": "Pornește cu Windows",
        "m_dpi_widget": "Afișează DPI lângă zona de notificare",
        "m_lock": "Blochează poziția",
        "m_reset": "Resetează poziția",
        "m_monitor": "Monitor pentru widgeturi",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(principal)",
        "m_no_taskbar": "(fără bară de activități)",
        "m_dpi_setup": "Setează valorile DPI...",
        "m_version": "Versiunea {v}",
        "m_exit": "Ieșire",
        "m_language": "Limbă",
        "m_lang_auto": "Automat (limba Windows)",
        "d_title": "Valori DPI",
        "d_hint": "Introdu DPI pentru fiecare dintre cele 6 trepte ale butonului DPI al mouse-ului.",
        "d_stage": "Treapta {n}",
        "d_save": "Salvează",
        "d_cancel": "Anulează",
        "d_err_range": "Treapta {n}: valoarea trebuie să fie între 1 și 100000.",
        "d_err_write": "Nu s-a putut scrie dpi.txt (folderul este protejat la scriere?).",
        "cfg_comment": "Valori DPI pentru treptele butonului DPI.\nSe modifică din meniul programului: \"{menu}\".\nFormat: număr_treaptă = DPI",
    },
    "ar": {
        "waiting": "في انتظار البيانات...",
        "stale": "لا توجد بيانات (آخر قيمة: {pct}%)",
        "charging": "(قيد الشحن)",
        "dpi_press": "اضغط على زر DPI",
        "dpi_unknown": "غير معروف (أدخل القيم في dpi.txt)",
        "m_autostart": "التشغيل مع Windows",
        "m_dpi_widget": "إظهار DPI بجوار منطقة الإعلام",
        "m_lock": "تثبيت الموضع",
        "m_reset": "إعادة تعيين الموضع",
        "m_monitor": "الشاشة المخصصة للأدوات",
        "m_monitor_n": "الشاشة {n}",
        "m_primary": "(الرئيسية)",
        "m_no_taskbar": "(لا يوجد شريط مهام)",
        "m_dpi_setup": "ضبط قيم DPI...",
        "m_version": "الإصدار {v}",
        "m_exit": "خروج",
        "m_language": "اللغة",
        "m_lang_auto": "تلقائي (لغة Windows)",
        "d_title": "قيم DPI",
        "d_hint": "أدخل قيمة DPI لكل مستوى من المستويات الستة لزر DPI في الماوس.",
        "d_stage": "المستوى {n}",
        "d_save": "حفظ",
        "d_cancel": "إلغاء",
        "d_err_range": "المستوى {n}: يجب أن تكون القيمة بين 1 و100000.",
        "d_err_write": "تعذرت كتابة dpi.txt (هل المجلد محمي ضد الكتابة؟).",
        "cfg_comment": "قيم DPI لمستويات زر DPI.\nتُعدَّل من قائمة البرنامج: \"{menu}\".\nالصيغة: رقم_المستوى = DPI",
    },
    "he": {
        "waiting": "ממתין לנתונים...",
        "stale": "אין נתונים (אחרון: {pct}%)",
        "charging": "(בטעינה)",
        "dpi_press": "לחץ על כפתור ה-DPI",
        "dpi_unknown": "לא ידוע (הגדר את הערכים ב-dpi.txt)",
        "m_autostart": "הפעל עם Windows",
        "m_dpi_widget": "הצג DPI ליד אזור ההתראות",
        "m_lock": "נעל מיקום",
        "m_reset": "אפס מיקום",
        "m_monitor": "מסך עבור הווידג'טים",
        "m_monitor_n": "מסך {n}",
        "m_primary": "(ראשי)",
        "m_no_taskbar": "(אין שורת משימות)",
        "m_dpi_setup": "הגדר ערכי DPI...",
        "m_version": "גרסה {v}",
        "m_exit": "יציאה",
        "m_language": "שפה",
        "m_lang_auto": "אוטומטי (שפת Windows)",
        "d_title": "ערכי DPI",
        "d_hint": "הזן DPI עבור כל אחת מ-6 הרמות של כפתור ה-DPI בעכבר.",
        "d_stage": "רמה {n}",
        "d_save": "שמור",
        "d_cancel": "ביטול",
        "d_err_range": "רמה {n}: הערך חייב להיות בין 1 ל-100000.",
        "d_err_write": "לא ניתן לכתוב את dpi.txt (התיקייה מוגנת מפני כתיבה?).",
        "cfg_comment": "ערכי DPI עבור רמות כפתור ה-DPI.\nמשנים דרך תפריט התוכנה: \"{menu}\".\nפורמט: מספר_רמה = DPI",
    },
    "hi": {
        "waiting": "डेटा की प्रतीक्षा है...",
        "stale": "कोई डेटा नहीं (आखिरी: {pct}%)",
        "charging": "(चार्ज हो रहा है)",
        "dpi_press": "DPI बटन दबाएँ",
        "dpi_unknown": "अज्ञात (मान dpi.txt में दर्ज करें)",
        "m_autostart": "Windows के साथ शुरू करें",
        "m_dpi_widget": "ट्रे के पास DPI दिखाएँ",
        "m_lock": "स्थिति लॉक करें",
        "m_reset": "स्थिति रीसेट करें",
        "m_monitor": "विजेट के लिए मॉनिटर",
        "m_monitor_n": "मॉनिटर {n}",
        "m_primary": "(मुख्य)",
        "m_no_taskbar": "(कोई टास्कबार नहीं)",
        "m_dpi_setup": "DPI मान सेट करें...",
        "m_version": "संस्करण {v}",
        "m_exit": "बाहर निकलें",
        "m_language": "भाषा",
        "m_lang_auto": "स्वचालित (Windows की भाषा)",
        "d_title": "DPI मान",
        "d_hint": "माउस के DPI बटन के 6 स्तरों में से प्रत्येक के लिए DPI दर्ज करें।",
        "d_stage": "स्तर {n}",
        "d_save": "सहेजें",
        "d_cancel": "रद्द करें",
        "d_err_range": "स्तर {n}: मान 1 से 100000 के बीच होना चाहिए।",
        "d_err_write": "dpi.txt नहीं लिखा जा सका (क्या फ़ोल्डर लिखने से सुरक्षित है?)।",
        "cfg_comment": "DPI बटन के स्तरों के लिए DPI मान।\nप्रोग्राम मेनू से बदलें: \"{menu}\".\nप्रारूप: स्तर_संख्या = DPI",
    },
    "th": {
        "waiting": "กำลังรอข้อมูล...",
        "stale": "ไม่มีข้อมูล (ล่าสุด: {pct}%)",
        "charging": "(กำลังชาร์จ)",
        "dpi_press": "กดปุ่ม DPI",
        "dpi_unknown": "ไม่ทราบ (ตั้งค่าใน dpi.txt)",
        "m_autostart": "เริ่มพร้อม Windows",
        "m_dpi_widget": "แสดง DPI ข้างถาดระบบ",
        "m_lock": "ล็อกตำแหน่ง",
        "m_reset": "รีเซ็ตตำแหน่ง",
        "m_monitor": "จอภาพสำหรับวิดเจ็ต",
        "m_monitor_n": "จอภาพ {n}",
        "m_primary": "(หลัก)",
        "m_no_taskbar": "(ไม่มีแถบงาน)",
        "m_dpi_setup": "ตั้งค่า DPI...",
        "m_version": "เวอร์ชัน {v}",
        "m_exit": "ออก",
        "m_language": "ภาษา",
        "m_lang_auto": "อัตโนมัติ (ภาษาของ Windows)",
        "d_title": "ค่า DPI",
        "d_hint": "ป้อนค่า DPI สำหรับแต่ละระดับจาก 6 ระดับของปุ่ม DPI บนเมาส์",
        "d_stage": "ระดับ {n}",
        "d_save": "บันทึก",
        "d_cancel": "ยกเลิก",
        "d_err_range": "ระดับ {n}: ค่าต้องอยู่ระหว่าง 1 ถึง 100000",
        "d_err_write": "ไม่สามารถเขียน dpi.txt ได้ (โฟลเดอร์ถูกป้องกันการเขียนหรือไม่)",
        "cfg_comment": "ค่า DPI สำหรับแต่ละระดับของปุ่ม DPI\nแก้ไขผ่านเมนูของโปรแกรม: \"{menu}\"\nรูปแบบ: หมายเลขระดับ = DPI",
    },
    "vi": {
        "waiting": "đang chờ dữ liệu...",
        "stale": "không có dữ liệu (gần nhất: {pct}%)",
        "charging": "(đang sạc)",
        "dpi_press": "nhấn nút DPI",
        "dpi_unknown": "chưa rõ (hãy đặt giá trị trong dpi.txt)",
        "m_autostart": "Khởi động cùng Windows",
        "m_dpi_widget": "Hiển thị DPI cạnh khay hệ thống",
        "m_lock": "Khóa vị trí",
        "m_reset": "Đặt lại vị trí",
        "m_monitor": "Màn hình cho các widget",
        "m_monitor_n": "Màn hình {n}",
        "m_primary": "(chính)",
        "m_no_taskbar": "(không có thanh tác vụ)",
        "m_dpi_setup": "Đặt giá trị DPI...",
        "m_version": "Phiên bản {v}",
        "m_exit": "Thoát",
        "m_language": "Ngôn ngữ",
        "m_lang_auto": "Tự động (ngôn ngữ Windows)",
        "d_title": "Giá trị DPI",
        "d_hint": "Nhập DPI cho từng mức trong 6 mức của nút DPI trên chuột.",
        "d_stage": "Mức {n}",
        "d_save": "Lưu",
        "d_cancel": "Hủy",
        "d_err_range": "Mức {n}: giá trị phải từ 1 đến 100000.",
        "d_err_write": "Không thể ghi dpi.txt (thư mục có bị bảo vệ ghi không?).",
        "cfg_comment": "Giá trị DPI cho các mức của nút DPI.\nThay đổi qua menu chương trình: \"{menu}\".\nĐịnh dạng: số_mức = DPI",
    },
    "id": {
        "waiting": "menunggu data...",
        "stale": "tidak ada data (terakhir: {pct}%)",
        "charging": "(mengisi daya)",
        "dpi_press": "tekan tombol DPI",
        "dpi_unknown": "tidak diketahui (atur nilai di dpi.txt)",
        "m_autostart": "Jalankan bersama Windows",
        "m_dpi_widget": "Tampilkan DPI di dekat baki sistem",
        "m_lock": "Kunci posisi",
        "m_reset": "Setel ulang posisi",
        "m_monitor": "Monitor untuk widget",
        "m_monitor_n": "Monitor {n}",
        "m_primary": "(utama)",
        "m_no_taskbar": "(tidak ada bilah tugas)",
        "m_dpi_setup": "Atur nilai DPI...",
        "m_version": "Versi {v}",
        "m_exit": "Keluar",
        "m_language": "Bahasa",
        "m_lang_auto": "Otomatis (bahasa Windows)",
        "d_title": "Nilai DPI",
        "d_hint": "Masukkan DPI untuk setiap dari 6 tingkat tombol DPI pada mouse.",
        "d_stage": "Tingkat {n}",
        "d_save": "Simpan",
        "d_cancel": "Batal",
        "d_err_range": "Tingkat {n}: nilai harus antara 1 dan 100000.",
        "d_err_write": "Tidak dapat menulis dpi.txt (folder dilindungi dari penulisan?).",
        "cfg_comment": "Nilai DPI untuk tingkat tombol DPI.\nUbah melalui menu program: \"{menu}\".\nFormat: nomor_tingkat = DPI",
    },
    "ja": {
        "waiting": "データを待っています...",
        "stale": "データなし (最後: {pct}%)",
        "charging": "(充電中)",
        "dpi_press": "DPI ボタンを押してください",
        "dpi_unknown": "不明 (dpi.txt に値を設定してください)",
        "m_autostart": "Windows と同時に起動",
        "m_dpi_widget": "トレイの横に DPI を表示",
        "m_lock": "位置を固定",
        "m_reset": "位置をリセット",
        "m_monitor": "ウィジェットを表示するモニター",
        "m_monitor_n": "モニター {n}",
        "m_primary": "(メイン)",
        "m_no_taskbar": "(タスクバーなし)",
        "m_dpi_setup": "DPI 値を設定...",
        "m_version": "バージョン {v}",
        "m_exit": "終了",
        "m_language": "言語",
        "m_lang_auto": "自動 (Windows の言語)",
        "d_title": "DPI 値",
        "d_hint": "マウスの DPI ボタンの 6 段階それぞれの DPI を入力してください。",
        "d_stage": "段階 {n}",
        "d_save": "保存",
        "d_cancel": "キャンセル",
        "d_err_range": "段階 {n}: 値は 1 から 100000 の範囲で指定してください。",
        "d_err_write": "dpi.txt を書き込めませんでした (フォルダーが書き込み禁止ではありませんか?)。",
        "cfg_comment": "DPI ボタンの各段階の DPI 値。\nプログラムのメニュー「{menu}」から変更します。\n形式: 段階番号 = DPI",
    },
    "ko": {
        "waiting": "데이터를 기다리는 중...",
        "stale": "데이터 없음 (마지막: {pct}%)",
        "charging": "(충전 중)",
        "dpi_press": "DPI 버튼을 누르세요",
        "dpi_unknown": "알 수 없음 (dpi.txt에 값을 설정하세요)",
        "m_autostart": "Windows와 함께 시작",
        "m_dpi_widget": "트레이 옆에 DPI 표시",
        "m_lock": "위치 고정",
        "m_reset": "위치 초기화",
        "m_monitor": "위젯을 표시할 모니터",
        "m_monitor_n": "모니터 {n}",
        "m_primary": "(주)",
        "m_no_taskbar": "(작업 표시줄 없음)",
        "m_dpi_setup": "DPI 값 설정...",
        "m_version": "버전 {v}",
        "m_exit": "끝내기",
        "m_language": "언어",
        "m_lang_auto": "자동 (Windows 언어)",
        "d_title": "DPI 값",
        "d_hint": "마우스 DPI 버튼의 6단계 각각에 대한 DPI를 입력하세요.",
        "d_stage": "{n}단계",
        "d_save": "저장",
        "d_cancel": "취소",
        "d_err_range": "{n}단계: 값은 1에서 100000 사이여야 합니다.",
        "d_err_write": "dpi.txt를 쓸 수 없습니다 (폴더가 쓰기 금지 상태인가요?).",
        "cfg_comment": "DPI 버튼 단계별 DPI 값.\n프로그램 메뉴 \"{menu}\"에서 변경하세요.\n형식: 단계_번호 = DPI",
    },
    "zh-Hans": {
        "waiting": "正在等待数据...",
        "stale": "无数据(最后一次:{pct}%)",
        "charging": "(正在充电)",
        "dpi_press": "请按 DPI 按钮",
        "dpi_unknown": "未知(请在 dpi.txt 中设置数值)",
        "m_autostart": "随 Windows 启动",
        "m_dpi_widget": "在托盘旁显示 DPI",
        "m_lock": "锁定位置",
        "m_reset": "重置位置",
        "m_monitor": "显示小组件的显示器",
        "m_monitor_n": "显示器 {n}",
        "m_primary": "(主)",
        "m_no_taskbar": "(无任务栏)",
        "m_dpi_setup": "设置 DPI 数值...",
        "m_version": "版本 {v}",
        "m_exit": "退出",
        "m_language": "语言",
        "m_lang_auto": "自动(Windows 语言)",
        "d_title": "DPI 数值",
        "d_hint": "请为鼠标 DPI 按钮的 6 个档位分别输入 DPI。",
        "d_stage": "档位 {n}",
        "d_save": "保存",
        "d_cancel": "取消",
        "d_err_range": "档位 {n}:数值必须在 1 到 100000 之间。",
        "d_err_write": "无法写入 dpi.txt(文件夹是否被写保护?)。",
        "cfg_comment": "DPI 按钮各档位的 DPI 数值。\n请通过程序菜单“{menu}”修改。\n格式:档位编号 = DPI",
    },
    "zh-Hant": {
        "waiting": "正在等待資料...",
        "stale": "沒有資料(最後一次:{pct}%)",
        "charging": "(充電中)",
        "dpi_press": "請按 DPI 按鈕",
        "dpi_unknown": "未知(請在 dpi.txt 中設定數值)",
        "m_autostart": "隨 Windows 啟動",
        "m_dpi_widget": "在系統匣旁顯示 DPI",
        "m_lock": "鎖定位置",
        "m_reset": "重設位置",
        "m_monitor": "顯示小工具的螢幕",
        "m_monitor_n": "螢幕 {n}",
        "m_primary": "(主要)",
        "m_no_taskbar": "(無工作列)",
        "m_dpi_setup": "設定 DPI 數值...",
        "m_version": "版本 {v}",
        "m_exit": "結束",
        "m_language": "語言",
        "m_lang_auto": "自動(Windows 語言)",
        "d_title": "DPI 數值",
        "d_hint": "請為滑鼠 DPI 按鈕的 6 個檔位分別輸入 DPI。",
        "d_stage": "檔位 {n}",
        "d_save": "儲存",
        "d_cancel": "取消",
        "d_err_range": "檔位 {n}:數值必須介於 1 到 100000 之間。",
        "d_err_write": "無法寫入 dpi.txt(資料夾是否受到寫入保護?)。",
        "cfg_comment": "DPI 按鈕各檔位的 DPI 數值。\n請透過程式功能表「{menu}」修改。\n格式:檔位編號 = DPI",
    },
}
LANG_NAMES = {
    "en": "English",
    "uk": "Українська",
    "ru": "Русский",
    "pl": "Polski",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pt": "Português",
    "it": "Italiano",
    "nl": "Nederlands",
    "tr": "Türkçe",
    "cs": "Čeština",
    "ro": "Română",
    "ar": "العربية",
    "he": "עברית",
    "hi": "हिन्दी",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
    "ja": "日本語",
    "ko": "한국어",
    "zh-Hans": "简体中文",
    "zh-Hant": "繁體中文",
}
ext_langs = {}       # мови з файлів lang/*.json
lang_override = ""   # "" = автоматично (мова Windows)
lang_code = "en"

def load_external_langs():
    """lang/xx.json поруч з програмою: додає нові мови або перекриває окремі рядки вбудованих."""
    try:
        for fn in sorted(os.listdir(LANG_DIR)):
            if not fn.lower().endswith(".json") or fn.startswith("_"):
                continue
            try:
                with open(os.path.join(LANG_DIR, fn), encoding="utf-8-sig") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    ext_langs[fn[:-5]] = {k: v for k, v in d.items() if isinstance(v, str)}
            except (OSError, ValueError):
                pass
    except OSError:
        pass

def lang_codes():
    codes = list(TR)
    codes += [c for c in ext_langs if c not in codes]
    return codes

def lang_name(code):
    return ext_langs.get(code, {}).get("_name") or LANG_NAMES.get(code, code)

def ui_languages():
    """Мови інтерфейсу Windows за пріоритетом (напр. ['uk-UA', 'en-US'])."""
    out = []
    try:
        n, size = wt.ULONG(0), wt.ULONG(0)
        k32.GetUserPreferredUILanguages(8, ctypes.byref(n), None, ctypes.byref(size))  # MUI_LANGUAGE_NAME
        if size.value:
            buf = ctypes.create_unicode_buffer(size.value)
            if k32.GetUserPreferredUILanguages(8, ctypes.byref(n), buf, ctypes.byref(size)):
                out = [x for x in buf[:size.value].split("\0") if x]
    except Exception:
        pass
    if not out:
        try:
            b = ctypes.create_unicode_buffer(85)
            if k32.GetUserDefaultLocaleName(b, 85):
                out = [b.value]
        except Exception:
            pass
    return out

def map_lang_tag(tag, codes):
    """'ja-JP' -> 'ja', 'zh-TW' -> 'zh-Hant', 'pt-BR' -> 'pt' (якщо така мова є серед codes)."""
    tl = tag.lower()
    head = tl.split("-")[0]
    if head == "zh":
        cand = ["zh-Hant" if any(x in tl for x in ("tw", "hk", "mo", "hant")) else "zh-Hans"]
    elif head in ("nb", "nn", "no"):
        cand = ["nb", "no"]
    else:
        cand = [tag, head]
    for c in cand:
        for a in codes:
            if a.lower() == c.lower():
                return a
    return None

def detect_lang(codes):
    for tag in ui_languages():
        c = map_lang_tag(tag, codes)
        if c:
            return c
    return "en"

def set_language(override=None):
    global lang_code, lang_override
    if override is not None:
        lang_override = override
    codes = lang_codes()
    lang_code = lang_override if lang_override in codes else detect_lang(codes)

def is_rtl():
    return lang_code.split("-")[0] in RTL_LANGS

def t(key, **kw):
    """Переклад рядка: lang/xx.json > вбудований переклад > англійська > сам ключ."""
    s = None
    for table in (ext_langs.get(lang_code), TR.get(lang_code), TR["en"], ext_langs.get("en")):
        if table and key in table:
            s = table[key]
            break
    if s is None:
        s = key
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError, ValueError):
        return s

def config_comment_lines():
    return ["# " + ln for ln in t("cfg_comment", menu=t("m_dpi_setup")).split("\n")]

def config_template():
    return "\n".join(config_comment_lines() + ["# 1 = 800", "# 2 = 1600", "# 3 = 3200", ""])

# ---------------- HID ----------------
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

def get_caps(h):
    pp = P()
    if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
        return None
    caps = HIDP_CAPS()
    hid.HidP_GetCaps(pp, ctypes.byref(caps))
    hid.HidD_FreePreparsedData(pp)
    return caps

def open_target():
    """Знаходить інтерфейс usage page 0x0A (там приходять звіти зі зарядом)."""
    for p in find_paths():
        h = k32.CreateFileW(p, 0xC0000000, 3, None, 3, 0, None)
        if not h or h == INVALID:
            continue
        caps = get_caps(h)
        if caps and caps.UsagePage == 0x000A and caps.InLen >= 5:
            return h, caps.InLen
        k32.CloseHandle(h)
    return None, 0

# ---------------- стан ----------------
lock = threading.Lock()
state = {"pct": None, "charging": False, "raw": "", "ts": 0.0, "dpi": None, "dpi_raw": ""}
WM_APP_UPDATE = 0x8001
WM_TRAY = 0x8002
hwnd_main = None

# --- збереження останнього ступеня DPI між запусками (%APPDATA%\\X11Battery\\state.json) ---
STATE_DIR = os.path.join(os.environ.get("APPDATA") or app_dir(), "X11Battery")
STATE_PATH = os.path.join(STATE_DIR, "state.json")

def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        v = d.get("dpi")
        if isinstance(v, int) and 0 < v < 100:
            with lock:
                state["dpi"] = v
    except (OSError, ValueError):
        pass

def save_state():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"dpi": state["dpi"]}, f)
    except OSError:
        pass

# --- налаштування в реєстрі (HKCU\\Software\\X11Battery) ---
SETTINGS_KEY = r"Software\X11Battery"

def reg_get(name, default):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as k:
            return int(winreg.QueryValueEx(k, name)[0])
    except (OSError, ValueError):
        return default

def reg_set(name, value):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))
    except OSError:
        pass

def reg_get_str(name, default=""):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as k:
            return str(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return default

def reg_set_str(name, value):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SETTINGS_KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
    except OSError:
        pass

def log_exc():
    """Пише помилки в x11_battery.log поруч з програмою (для діагностики)."""
    try:
        import traceback
        path = os.path.join(app_dir(), "x11_battery.log")
        if os.path.exists(path) and os.path.getsize(path) > 200000:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except OSError:
        pass

def on_report(d):
    # 03 55 40 <стан> <заряд>
    if len(d) >= 5 and d[0] == 0x03 and d[1] == 0x55 and d[2] == 0x40 and d[4] <= 100:
        with lock:
            state["pct"] = d[4]
            state["charging"] = bool(d[3] & 0x02)
            state["raw"] = " ".join(f"{x:02x}" for x in d[:5])
            state["ts"] = time.time()
        if hwnd_main:
            user32.PostMessageW(hwnd_main, WM_APP_UPDATE, 0, 0)
    # 03 55 10 <ступінь DPI> 00  (приходить при натисканні кнопки DPI)
    elif len(d) >= 4 and d[0] == 0x03 and d[1] == 0x55 and d[2] == 0x10:
        with lock:
            changed = state["dpi"] != d[3]
            state["dpi"] = d[3]
            state["dpi_raw"] = " ".join(f"{x:02x}" for x in d[:5])
        if changed:
            save_state()
        if hwnd_main:
            user32.PostMessageW(hwnd_main, WM_APP_UPDATE, 0, 0)

def reader():
    while True:
        h, n = open_target()
        if not h:
            time.sleep(3)
            continue
        buf = (ctypes.c_ubyte * n)()
        got = wt.DWORD(0)
        while k32.ReadFile(h, buf, n, ctypes.byref(got), None):
            on_report(bytes(buf[:got.value]))
        k32.CloseHandle(h)
        time.sleep(2)

# ---------------- автозапуск ----------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def launch_cmd():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}"'

def autostart_on():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
        return True
    except OSError:
        return False

def set_autostart(on):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, launch_cmd())
            else:
                winreg.DeleteValue(k, APP)
    except OSError:
        pass

def first_run_autostart():
    """При першому запуску вмикає автозапуск (далі керується з меню)."""
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\X11Battery").Close()
    except OSError:
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\X11Battery").Close()
        set_autostart(True)

# ---------------- іконка ----------------
def rgb(r, g, b):
    return r | (g << 8) | (b << 16)

# ---------------- трей ----------------
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
cur_icon = None
taskbar_created = 0

def snapshot():
    with lock:
        return dict(state)

def dpi_text(st):
    s = st["dpi"]
    if s is None:
        return "DPI: " + t("dpi_press")
    v = load_dpi_stages().get(s)
    return f"DPI: {v}" if v else "DPI: " + t("dpi_unknown")

def build_view():
    text, bg, tip = _battery_view()
    return text, bg, tip + "\n" + dpi_text(snapshot())

def _battery_view():
    st = snapshot()
    pct = st["pct"]
    if pct is None:
        return "?", rgb(190, 190, 190), f"ATTACK SHARK X11: {t('waiting')}"
    stale = (time.time() - st["ts"]) > STALE_SEC
    if stale:
        return str(pct), rgb(190, 190, 190), f"ATTACK SHARK X11: {t('stale', pct=pct)}"
    if st["charging"]:
        bg = rgb(90, 170, 255)
    elif pct <= 15:
        bg = rgb(255, 90, 80)
    elif pct <= 40:
        bg = rgb(255, 200, 40)
    else:
        bg = rgb(90, 210, 110)
    tip = f"ATTACK SHARK X11: {pct}%" + (" " + t("charging") if st["charging"] else "")
    return str(pct), bg, tip

def refresh(hwnd=None, add=False):
    widgets_update()

# ---------------- меню у стилі Windows 11 (тема Windows + іконки Segoe Fluent) ----------------
ICON_FACES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")
MENU_ICONS = {"autostart": 0xE768, "dpi": 0xE7B3, "lock": 0xE72E, "reset": 0xE777,
              "monitor": 0xE7F4, "settings": 0xE713, "exit": 0xE7E8, "language": 0xE774}

def apply_menu_theme():
    """Змушує popup-меню слідувати темі Windows (темна/світла). Недокументовані
    функції uxtheme: SetPreferredAppMode (ординал 135) і FlushMenuThemes (136)."""
    try:
        set_mode = uxtheme[135]
        set_mode.restype = ctypes.c_int
        set_mode.argtypes = [ctypes.c_int]
        flush = uxtheme[136]
        flush.restype = None
        flush.argtypes = []
        set_mode(3 if light_theme() else 2)  # 3 = ForceLight, 2 = ForceDark
        flush()
    except Exception:
        pass

def make_menu_icon(codepoint):
    """Іконка-гліф Segoe Fluent Icons -> 32-бітний ARGB bitmap кольору тексту теми (для hbmpItem)."""
    sc = get_scale()
    px = max(16, int(round(16 * sc)))
    S = 4
    W = px * S
    hdc0 = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc0)
    font, oldf = pick_font(mdc, W, ICON_FACES)
    ch = chr(codepoint)
    sz = wt.SIZE()
    gdi32.GetTextExtentPoint32W(mdc, ch, 1, ctypes.byref(sz))
    bmi = BITMAPINFOHEADER(40, W, -W, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    oldb = gdi32.SelectObject(mdc, dib)
    gdi32.SetBkMode(mdc, 1)
    gdi32.SetTextColor(mdc, 0xFFFFFF)
    gdi32.TextOutW(mdc, (W - sz.cx) // 2, (W - sz.cy) // 2, ch, 1)
    gdi32.GdiFlush()
    arr = (ctypes.c_uint32 * (W * W)).from_address(bits.value)
    r, g, b = theme_color()
    n = S * S
    out = [0] * (px * px)
    for y in range(px):
        acc = [0] * px
        for dy in range(S):
            base = (y * S + dy) * W
            row = arr[base:base + W]
            for dx in range(S):
                acc = [a + (v & 0xFF) for a, v in zip(acc, row[dx::S])]
        for x in range(px):
            cov = acc[x] // n
            if cov:
                out[y * px + x] = (cov << 24) | ((r * cov // 255) << 16) | ((g * cov // 255) << 8) | (b * cov // 255)
    gdi32.SelectObject(mdc, oldb)
    gdi32.DeleteObject(dib)
    gdi32.SelectObject(mdc, oldf)
    gdi32.DeleteObject(font)
    gdi32.DeleteDC(mdc)
    # фінальний bitmap потрібного розміру
    fbmi = BITMAPINFOHEADER(40, px, -px, 1, 32, 0, 0, 0, 0, 0, 0)
    fbits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(hdc0, ctypes.byref(fbmi), 0, ctypes.byref(fbits), None, 0)
    farr = (ctypes.c_uint32 * (px * px)).from_address(fbits.value)
    farr[:] = out
    user32.ReleaseDC(None, hdc0)
    return hbm

def menu_add(menu, text="", cid=0, checked=False, grayed=False, hbm=None, sub=None, sep=False):
    mii = MENUITEMINFOW()
    mii.cbSize = ctypes.sizeof(MENUITEMINFOW)
    if sep:
        mii.fMask = 0x100   # MIIM_FTYPE
        mii.fType = 0x800   # MFT_SEPARATOR
    else:
        mii.fMask = 0x1 | 0x40 | (0x2 if cid else 0) | (0x80 if hbm else 0) | (0x4 if sub else 0)
        mii.fState = (0x3 if grayed else 0) | (0x8 if checked else 0)
        mii.wID = cid
        mii.dwTypeData = text
        mii.hbmpItem = hbm
        mii.hSubMenu = sub
    user32.InsertMenuItemW(menu, user32.GetMenuItemCount(menu), True, ctypes.byref(mii))

def tick(active):
    """Галочка в кінці рядка: текст після табуляції меню вирівнює праворуч."""
    return "\t\u2713" if active else ""

def show_menu(hwnd):
    global menu_monitors
    st = snapshot()
    _, _, tip = _battery_view()
    apply_menu_theme()
    icons = []
    def ic(name):
        try:
            h = make_menu_icon(MENU_ICONS[name])
            icons.append(h)
            return h
        except Exception:
            log_exc()
            return None
    menu = user32.CreatePopupMenu()
    menu_add(menu, tip, grayed=True)
    menu_add(menu, dpi_text(st), grayed=True)
    menu_add(menu, sep=True)
    menu_add(menu, t("m_autostart") + tick(autostart_on()), 1, hbm=ic("autostart"))
    menu_add(menu, t("m_dpi_widget") + tick(dpi_widget_enabled), 4, hbm=ic("dpi"))
    menu_add(menu, t("m_lock") + tick(locked), 5, hbm=ic("lock"))
    menu_add(menu, t("m_reset"), 7, hbm=ic("reset"))
    menu_monitors = monitor_list()
    if len(menu_monitors) > 1:
        sub = user32.CreatePopupMenu()
        for i, (hmon, dev, prim) in enumerate(menu_monitors):
            has_tb = bool(find_taskbar_for(hmon))
            label = monitor_label(dev, prim) + ("" if has_tb else " " + t("m_no_taskbar"))
            menu_add(sub, label + tick(dev == active_dev), 100 + i, grayed=not has_tb)
        menu_add(menu, t("m_monitor"), sub=sub, hbm=ic("monitor"))
    menu_add(menu, sep=True)
    menu_add(menu, t("m_dpi_setup"), 6, hbm=ic("settings"))
    menu_langs[:] = lang_codes()
    sub2 = user32.CreatePopupMenu()
    menu_add(sub2, t("m_lang_auto") + tick(not lang_override), 200)
    for i, code in enumerate(menu_langs):
        menu_add(sub2, lang_name(code) + tick(lang_override == code), 201 + i)
    menu_add(menu, t("m_language") + ("" if lang_code == "en" else " / Language"), sub=sub2, hbm=ic("language"))
    menu_add(menu, t("m_version", v=VERSION), grayed=True)
    menu_add(menu, sep=True)
    menu_add(menu, t("m_exit"), 2, hbm=ic("exit"))
    pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    user32.TrackPopupMenu(menu, 0x20 | 0x2 | (0x8000 if is_rtl() else 0), pt.x, pt.y, 0, hwnd, None)  # TPM_LAYOUTRTL для ar/he
    user32.PostMessageW(hwnd, 0, 0, 0)
    user32.DestroyMenu(menu)
    for h in icons:
        gdi32.DeleteObject(h)

# ---------------- віджети біля трея: [DPI 1600] [мишка 93%] ----------------
SS = 3  # супервибірка для згладжування
HINST = None
dpi_widget_enabled = True
offset_dp = 8  # відступ від трея вліво (при 100% масштабі), можна перетягнути мишею
GAP_DP = 4     # проміжок між віджетами
monitor_dev = ""    # обраний монітор (ім'я пристрою, напр. DISPLAY2); "" = основний
active_dev = ""     # монітор, на якому віджети зараз реально показані
locked = False      # True - положення закріплено, перетягування заборонене
menu_monitors = []  # список моніторів, показаний у меню
menu_langs = []     # список мов, показаний у меню
_scale = {"v": None}
drag = {"active": False, "x0": 0, "off0": 0, "moved": False}
widgets = {}   # hwnd -> Widget
TIP_DARK_BG = (43, 43, 43)
TIP_DARK_FG = (255, 255, 255)
TIP_LIGHT_BG = (249, 249, 249)
TIP_LIGHT_FG = (26, 26, 26)
TIP_LIGHT_BORDER = (205, 205, 205)  # тонка рамка лише у світлій темі
FONT_FACES = ("Segoe UI Variable Text", "Segoe UI")  # шрифт Windows 11 (як у меню Пуск)

def get_scale():
    if _scale["v"]:
        return _scale["v"]
    try:
        return max(1.0, user32.GetDpiForSystem() / 96.0)
    except (AttributeError, OSError):
        return 1.0

def dpi_scale_of(hwnd):
    try:
        d = user32.GetDpiForWindow(hwnd)
        if d:
            return max(1.0, d / 96.0)
    except (AttributeError, OSError):
        pass
    return None

def light_theme():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False

def theme_color():
    return (20, 20, 20) if light_theme() else (240, 240, 240)

def monitor_list():
    """[(hmonitor, ім'я_пристрою, основний?)], основний - першим."""
    mons = []
    def cb(hmon, hdc, lprc, lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            mons.append((hmon, mi.szDevice, bool(mi.dwFlags & 1)))
        return True
    proc = MONITORENUMPROC(cb)
    user32.EnumDisplayMonitors(None, None, proc, 0)
    mons.sort(key=lambda m: (not m[2], m[1]))
    return mons

def monitor_label(dev, primary):
    m = re.search(r"(\d+)$", dev or "")
    name = t("m_monitor_n", n=m.group(1) if m else "?")
    return name + (" " + t("m_primary") if primary else "")

def offset_key(dev):
    return "offset_" + re.sub(r"[^0-9A-Za-z]", "", dev or "")

def find_taskbar_for(hmon):
    """Панель завдань, що стоїть на заданому моніторі (основна або додаткова)."""
    cands = []
    tb = user32.FindWindowW("Shell_TrayWnd", None)
    if tb:
        cands.append(tb)
    prev = None
    while True:
        h = user32.FindWindowExW(None, prev, "Shell_SecondaryTrayWnd", None)
        if not h:
            break
        cands.append(h)
        prev = h
    for h in cands:
        if user32.MonitorFromWindow(h, 2) == hmon:  # MONITOR_DEFAULTTONEAREST
            return h
    return None

def taskbar_info():
    """(вікно панелі, її прямокутник, прямокутник трея) для обраного монітора."""
    global active_dev, offset_dp
    mons = monitor_list()
    if not mons:
        return None
    m = None
    if monitor_dev:
        for c in mons:
            if c[1] == monitor_dev and find_taskbar_for(c[0]):
                m = c
                break
    if m is None:  # обраного монітора немає або на ньому немає панелі - основний
        m = next((c for c in mons if c[2]), mons[0])
    tb = find_taskbar_for(m[0])
    if not tb:
        return None
    if m[1] != active_dev:  # перемкнули монітор - підхоплюємо його збережений відступ
        active_dev = m[1]
        offset_dp = reg_get(offset_key(active_dev), reg_get("offset", 8))
    _scale["v"] = dpi_scale_of(tb)
    rtb = wt.RECT()
    if not user32.GetWindowRect(tb, ctypes.byref(rtb)):
        return None
    if (rtb.bottom - rtb.top) > (rtb.right - rtb.left):  # вертикальна панель - не підтримується
        return None
    rtray = wt.RECT()
    tray = user32.FindWindowExW(tb, None, "TrayNotifyWnd", None)
    if not (tray and user32.GetWindowRect(tray, ctypes.byref(rtray))):
        # на додатковій панелі трея немає - лише годинник: відступаємо від правого краю
        rtray.left = rtb.right - int((120 if m[2] is False else 260) * get_scale())
    return tb, rtb, rtray

def battery_view():
    st = snapshot()
    pct = st["pct"]
    light = light_theme()
    gray = (110, 110, 110) if light else (150, 150, 150)
    if pct is None:
        return "--%", gray, False
    if (time.time() - st["ts"]) > STALE_SEC:
        return f"{pct}%", gray, False
    if st["charging"]:
        return f"{pct}%", ((30, 150, 60) if light else (110, 220, 120)), True
    if pct <= 15:
        return f"{pct}%", ((200, 40, 30) if light else (255, 100, 90)), False
    return f"{pct}%", theme_color(), False

def dpi_widget_text():
    s = snapshot()["dpi"]
    if s is None:
        return "DPI: --"
    v = load_dpi_stages().get(s)
    return f"DPI: {v}" if v else "DPI: --"  # значення береться з dpi.txt

def pick_font(mdc, px, faces=FONT_FACES):
    """Шрифт Windows 11 (Segoe UI Variable Text); якщо його немає - Segoe UI."""
    face_buf = ctypes.create_unicode_buffer(64)
    font = None
    for face in faces:
        f = gdi32.CreateFontW(-px, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 4, 0, face)
        old = gdi32.SelectObject(mdc, f)
        gdi32.GetTextFaceW(mdc, 64, face_buf)
        if face_buf.value.lower() == face.lower() or face == faces[-1]:
            return f, old
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(f)
    return font, None

def draw_widget_bitmap(text, color, charging, h, icon):
    """Малює (іконку мишки +) текст у білому на чорному в SS-кратному розмірі, потім зменшує:
    отримуємо згладжену маску -> піксельна прозорість (без фону)."""
    sc = get_scale()
    S = SS
    hdc0 = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc0)
    fh = max(8, int(round(15 * sc))) * S
    font, oldf = pick_font(mdc, fh)
    sz = wt.SIZE()
    gdi32.GetTextExtentPoint32W(mdc, text, len(text), ctypes.byref(sz))
    tw, th = sz.cx, sz.cy
    pad = int(4 * sc * S)
    gap = int(6 * sc * S) if icon else 0
    iw = int(12 * sc * S) if icon else 0
    ih = int(17 * sc * S)
    bw = int(6 * sc * S) if charging else 0
    bh = int(12 * sc * S)
    bgap = int(3 * sc * S) if charging else 0
    W = pad + iw + gap + bw + bgap + tw + pad
    w = (W + S - 1) // S
    W, H = w * S, h * S
    tm = TEXTMETRICW()
    gdi32.GetTextMetricsW(mdc, ctypes.byref(tm))
    cap = 0.70 * (tm.tmHeight - tm.tmInternalLeading)  # висота цифр / великих літер
    ty = int(H / 2 + cap / 2 - tm.tmAscent)            # їхній центр = центр панелі

    bmi = BITMAPINFOHEADER(40, W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    oldb = gdi32.SelectObject(mdc, dib)
    white = 0xFFFFFF

    if icon:  # мишка
        pw = max(S, int(1.6 * sc * S))
        pen = gdi32.CreatePen(0, pw, white)
        oldp = gdi32.SelectObject(mdc, pen)
        oldbr = gdi32.SelectObject(mdc, gdi32.GetStockObject(5))  # NULL_BRUSH
        x0, y0 = pad, (H - ih) // 2
        gdi32.RoundRect(mdc, x0 + pw // 2, y0 + pw // 2, x0 + iw - pw // 2, y0 + ih - pw // 2,
                        int(iw * 0.9), int(iw * 0.9))
        cx = x0 + iw // 2
        gdi32.MoveToEx(mdc, cx, y0 + int(ih * 0.20), None)
        gdi32.LineTo(mdc, cx, y0 + int(ih * 0.40))
        gdi32.SelectObject(mdc, oldbr)
        gdi32.SelectObject(mdc, oldp)
        gdi32.DeleteObject(pen)

    if charging:  # блискавка
        br = gdi32.CreateSolidBrush(white)
        oldbr = gdi32.SelectObject(mdc, br)
        oldp = gdi32.SelectObject(mdc, gdi32.GetStockObject(8))  # NULL_PEN
        bx, by = pad + iw + gap, (H - bh) // 2
        rel = [(0.65, 0.0), (0.05, 0.58), (0.45, 0.58), (0.32, 1.0), (0.95, 0.38), (0.55, 0.38)]
        pts = (wt.POINT * len(rel))(*[wt.POINT(int(bx + a * bw), int(by + b * bh)) for a, b in rel])
        gdi32.Polygon(mdc, pts, len(rel))
        gdi32.SelectObject(mdc, oldp)
        gdi32.SelectObject(mdc, oldbr)
        gdi32.DeleteObject(br)

    gdi32.SetBkMode(mdc, 1)
    gdi32.SetTextColor(mdc, white)
    tx = pad + iw + gap + bw + bgap
    gdi32.TextOutW(mdc, tx, ty, text, len(text))
    gdi32.GdiFlush()

    # зменшення в S разів -> покриття 0..255 -> попередньо помножений ARGB
    arr = (ctypes.c_uint32 * (W * H)).from_address(bits.value)
    r, g, b = color
    n = S * S
    out = [0] * (w * h)
    for y in range(h):
        acc = [0] * w
        for dy in range(S):
            base = (y * S + dy) * W
            row = arr[base:base + W]
            for dx in range(S):
                acc = [a + (v & 0xFF) for a, v in zip(acc, row[dx::S])]
        o = y * w
        for x in range(w):
            cov = acc[x] // n
            if cov == 0:
                out[o + x] = 0x01000000  # майже невидимий, але ловить клік/наведення
            else:
                out[o + x] = (cov << 24) | ((r * cov // 255) << 16) | ((g * cov // 255) << 8) | (b * cov // 255)

    gdi32.SelectObject(mdc, oldb)
    gdi32.DeleteObject(dib)
    gdi32.SelectObject(mdc, oldf)
    gdi32.DeleteObject(font)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(None, hdc0)
    return w, out

def apply_bitmap(hwnd, w, h, out):
    hdc0 = user32.GetDC(None)
    bmi = BITMAPINFOHEADER(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    dib = gdi32.CreateDIBSection(hdc0, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    fdc = gdi32.CreateCompatibleDC(hdc0)
    old = gdi32.SelectObject(fdc, dib)
    arr = (ctypes.c_uint32 * (w * h)).from_address(bits.value)
    arr[:] = out
    size = wt.SIZE(w, h)
    src = wt.POINT(0, 0)
    bf = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, AC_SRC_ALPHA
    user32.UpdateLayeredWindow(hwnd, hdc0, None, ctypes.byref(size), fdc,
                               ctypes.byref(src), 0, ctypes.byref(bf), 2)
    gdi32.SelectObject(fdc, old)
    gdi32.DeleteObject(dib)
    gdi32.DeleteDC(fdc)
    user32.ReleaseDC(None, hdc0)

class Widget:
    """Одне прозоре дочірнє вікно панелі завдань: kind = 'bat' (мишка + %) або 'dpi' (текст DPI)."""
    def __init__(self, kind):
        self.kind = kind
        self.hwnd = None
        self.parent = None
        self.key = None
        self.pending = None
        self.size = [1, 1]
        self.tip_text = ""

    def alive(self):
        return bool(self.hwnd) and bool(user32.IsWindow(self.hwnd))

    def create(self, tb):
        # WS_EX_LAYERED | WS_EX_NOACTIVATE ; WS_CHILD | WS_VISIBLE
        hw = user32.CreateWindowExW(0x80000 | 0x08000000, "X11BatteryWidget", "", 0x40000000 | 0x10000000,
                                    0, 0, 10, 10, tb, None, HINST, None)
        if not hw:
            return False
        self.hwnd, self.parent, self.key, self.pending = hw, tb, None, None
        widgets[hw] = self
        return True

    def destroy(self):
        hide_tip(self)
        if self.hwnd:
            widgets.pop(self.hwnd, None)
            if user32.IsWindow(self.hwnd):
                user32.DestroyWindow(self.hwnd)
        self.hwnd, self.key, self.pending = None, None, None

    def view(self):
        if self.kind == "bat":
            text, color, charging = battery_view()
            return text, color, charging, True
        return dpi_widget_text(), theme_color(), False, False

    def render(self, h):
        text, color, charging, icon = self.view()
        key = (text, color, charging, icon, h, get_scale())
        if key != self.key:
            w, out = draw_widget_bitmap(text, color, charging, h, icon)
            self.size = [w, h]
            self.pending = out
            self.key = key

    def set_tip(self, text):
        self.tip_text = text
        if tip_state["owner"] is self and tip_state["text"] != text:  # текст змінився, поки підказка видима
            show_tip(self)

# ---------------- власна підказка (без системної рамки), підлаштовується під тему ----------------
tip_state = {"hwnd": None, "owner": None, "text": None}

def _ss_cov(arr, W, S, w, h):
    """Зменшує маску в S разів -> покриття 0..255 для кожного пікселя (список w*h)."""
    n = S * S
    out = [0] * (w * h)
    for y in range(h):
        acc = [0] * w
        for dy in range(S):
            base = (y * S + dy) * W
            row = arr[base:base + W]
            for dx in range(S):
                acc = [a + (v & 0xFF) for a, v in zip(acc, row[dx::S])]
        o = y * w
        for x in range(w):
            out[o + x] = acc[x] // n
    return out

def draw_tip_bitmap(text):
    """Заокруглений прямокутник + текст (шрифт Windows 11), піксельна прозорість. Темна тема - без рамки."""
    sc = get_scale()
    S = 3
    dark = not light_theme()
    bg, fg = (TIP_DARK_BG, TIP_DARK_FG) if dark else (TIP_LIGHT_BG, TIP_LIGHT_FG)
    lines = text.split("\n")
    hdc0 = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc0)
    font, oldf = pick_font(mdc, max(9, int(round(12 * sc))) * S)
    tm = TEXTMETRICW()
    gdi32.GetTextMetricsW(mdc, ctypes.byref(tm))
    line_h = tm.tmHeight + int(3 * sc * S)
    widths = []
    for ln in lines:
        sz = wt.SIZE()
        gdi32.GetTextExtentPoint32W(mdc, ln, len(ln), ctypes.byref(sz))
        widths.append(sz.cx)
    padx, pady = int(10 * sc * S), int(7 * sc * S)
    w = (max(widths) + 2 * padx + S - 1) // S
    h = (len(lines) * line_h + 2 * pady + S - 1) // S
    W, H = w * S, h * S
    white = 0xFFFFFF

    def mask(draw):
        bmi = BITMAPINFOHEADER(40, W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(mdc, dib)
        draw()
        gdi32.GdiFlush()
        cov = _ss_cov((ctypes.c_uint32 * (W * H)).from_address(bits.value), W, S, w, h)
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(dib)
        return cov

    def rounded(inset):
        def draw():
            br = gdi32.CreateSolidBrush(white)
            ob = gdi32.SelectObject(mdc, br)
            op = gdi32.SelectObject(mdc, gdi32.GetStockObject(6))  # WHITE_PEN
            r = max(2, int(6 * sc * S) - inset)
            gdi32.RoundRect(mdc, inset, inset, W - inset, H - inset, 2 * r, 2 * r)
            gdi32.SelectObject(mdc, op)
            gdi32.SelectObject(mdc, ob)
            gdi32.DeleteObject(br)
        return draw

    def draw_text():
        gdi32.SetBkMode(mdc, 1)
        gdi32.SetTextColor(mdc, white)
        for i, ln in enumerate(lines):
            gdi32.TextOutW(mdc, padx, pady + i * line_h, ln, len(ln))

    shape = mask(rounded(0))
    inner = shape if dark else mask(rounded(S))  # внутрішня частина: решта - тонка рамка (лише світла тема)
    txt = mask(draw_text)
    gdi32.SelectObject(mdc, oldf)
    gdi32.DeleteObject(font)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(None, hdc0)

    out = [0] * (w * h)
    for i in range(w * h):
        a = shape[i]
        if not a:
            continue
        ic = 255 if dark else min(255, inner[i] * 255 // a)  # частка "всередині" для цього пікселя
        tc = txt[i]
        px = 0
        for ch in range(3):
            base = (bg[ch] * ic + TIP_LIGHT_BORDER[ch] * (255 - ic)) // 255 if not dark else bg[ch]
            c = (base * (255 - tc) + fg[ch] * tc) // 255
            px = (px << 8) | (c * a // 255)
        out[i] = (a << 24) | px
    return w, h, out

def show_tip(widget):
    try:
        text = widget.tip_text
        if not text or not widget.hwnd:
            return
        th = tip_state["hwnd"]
        if th and tip_state["owner"] is widget and tip_state["text"] == text and user32.IsWindowVisible(th):
            return
        if not th or not user32.IsWindow(th):
            # LAYERED | TOOLWINDOW | TOPMOST | NOACTIVATE | TRANSPARENT (миша проходить крізь підказку); WS_POPUP
            th = user32.CreateWindowExW(0x80000 | 0x80 | 0x8 | 0x08000000 | 0x20, "X11BatteryTip", "",
                                        0x80000000, 0, 0, 10, 10, None, None, HINST, None)
            if not th:
                return
            tip_state["hwnd"] = th
        tw, tht, out = draw_tip_bitmap(text)
        rc = wt.RECT()
        user32.GetWindowRect(widget.hwnd, ctypes.byref(rc))
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(user32.MonitorFromWindow(widget.hwnd, 2), ctypes.byref(mi))
        gap = int(8 * get_scale())
        x = (rc.left + rc.right) // 2 - tw // 2
        x = max(mi.rcMonitor.left + 4, min(x, mi.rcMonitor.right - tw - 4))
        y = rc.top - tht - gap                      # над віджетом
        if y < mi.rcMonitor.top:                    # панель угорі - під віджетом
            y = rc.bottom + gap
        user32.SetWindowPos(th, ctypes.c_void_p(-1), x, y, tw, tht, 0x10)  # HWND_TOPMOST, NOACTIVATE
        apply_bitmap(th, tw, tht, out)
        user32.ShowWindow(th, 4)  # SW_SHOWNOACTIVATE
        tip_state["owner"], tip_state["text"] = widget, text
    except Exception:
        log_exc()

def hide_tip(widget=None):
    if widget is not None and tip_state["owner"] is not widget:
        return
    th = tip_state["hwnd"]
    if th and user32.IsWindow(th):
        user32.ShowWindow(th, 0)
    tip_state["owner"] = tip_state["text"] = None

def tip_proc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

_tip_proc_ref = WNDPROC(tip_proc)

bat_w = Widget("bat")
dpi_w = Widget("dpi")

def place(w, x, h):
    user32.SetWindowPos(w.hwnd, None, x, 0, w.size[0], h, 0x10 | 0x40)  # NOACTIVATE | SHOWWINDOW

def clamp_offset(info):
    """Не даємо віджетам заїхати за край панелі (ліворуч) або за трей (праворуч)."""
    global offset_dp
    tb, rtb, rtray = info
    sc = get_scale()
    total = bat_w.size[0]
    if dpi_w.hwnd and dpi_widget_enabled:
        total += int(GAP_DP * sc) + dpi_w.size[0]
    max_px = max(0, (rtray.left - rtb.left) - total)
    off_px = min(max(0, int(offset_dp * sc)), max_px)
    offset_dp = int(off_px / sc)

def layout(info=None):
    """Праворуч - віджет заряду (біля трея), лівіше від нього - віджет DPI."""
    info = info or taskbar_info()
    if not info:
        return
    tb, rtb, rtray = info
    sc = get_scale()
    h = rtb.bottom - rtb.top
    clamp_offset(info)
    x = rtray.left - rtb.left - bat_w.size[0] - int(offset_dp * sc)
    if bat_w.hwnd:
        place(bat_w, x, h)
    if dpi_w.hwnd and dpi_widget_enabled:
        place(dpi_w, x - int(GAP_DP * sc) - dpi_w.size[0], h)

def widgets_update(force=False):
    try:
        info = taskbar_info()
        if not info:
            return
        tb, rtb, rtray = info
        h = rtb.bottom - rtb.top
        if not dpi_widget_enabled and dpi_w.hwnd:
            dpi_w.destroy()
        active = [bat_w] + ([dpi_w] if dpi_widget_enabled else [])
        for w in active:
            if not w.alive() or w.parent != tb:
                w.destroy()
                if not w.create(tb):
                    continue
            if force:
                w.key = None
            w.render(h)
        layout(info)
        for w in active:
            if w.hwnd and w.pending is not None:
                apply_bitmap(w.hwnd, w.size[0], w.size[1], w.pending)
                w.pending = None
        if bat_w.hwnd:
            bat_w.set_tip(build_view()[2])
        if dpi_w.hwnd:
            dpi_w.set_tip(dpi_text(snapshot()))
    except Exception:
        log_exc()

def recreate_widgets():
    bat_w.destroy()
    dpi_w.destroy()
    widgets_update(force=True)

def toggle_lock():
    global locked
    locked = not locked
    reg_set("locked", int(locked))

def reset_position():
    global offset_dp
    offset_dp = 8
    reg_set(offset_key(active_dev), offset_dp)
    layout()

def select_language(i):
    """i = 0 - автоматично (мова Windows), далі - мови зі списку меню."""
    if i == 0:
        set_language("")
    elif 1 <= i <= len(menu_langs):
        set_language(menu_langs[i - 1])
    else:
        return
    reg_set_str("language", lang_override)
    widgets_update(force=True)

def select_monitor(i):
    global monitor_dev
    if 0 <= i < len(menu_monitors):
        monitor_dev = menu_monitors[i][1]
        reg_set_str("monitor", monitor_dev)
        recreate_widgets()

# ---------------- іконка програми ----------------
dlg_icons = []

def icon_path():
    """X11Battery.ico: усередині exe (PyInstaller) або поруч зі скриптом."""
    for base in (getattr(sys, "_MEIPASS", None), app_dir()):
        if base:
            p = os.path.join(base, "X11Battery.ico")
            if os.path.exists(p):
                return p
    return None

def load_icon(size):
    p = icon_path()
    if not p:
        return None
    try:
        return user32.LoadImageW(None, p, 1, size, size, 0x10) or None  # IMAGE_ICON, LR_LOADFROMFILE
    except Exception:
        log_exc()
        return None

# ---------------- вікно налаштування значень DPI (6 ступенів) ----------------
DPI_ROWS = 6
dlg_hwnd = None
dlg_edits = []
dlg_font = None
dlg_busy = False
dlg_dark = False   # темна тема вікна (за темою Windows)
dlg_brushes = []   # [фон вікна, фон полів введення] - лише в темній темі
DLG_FG = (240, 240, 240)
DLG_BG = (32, 32, 32)
DLG_EDIT_BG = (45, 45, 45)

def _free_dlg_theme():
    global dlg_dark
    for b in dlg_brushes:
        gdi32.DeleteObject(b)
    dlg_brushes.clear()
    dlg_dark = False

def read_edit(h):
    buf = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(h, buf, 64)
    return buf.value

def save_dpi_stages(vals):
    """Записує dpi.txt: ступені 1..6 з вікна (+ збережені раніше ступені понад 6)."""
    merged = {k: v for k, v in load_dpi_stages().items() if k > DPI_ROWS}
    merged.update(vals)
    lines = config_comment_lines() + [""]
    lines += [f"{k} = {merged[k]}" for k in sorted(merged)]
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    _cfg["mtime"] = None

def dlg_paste(i):
    """Якщо в поле вставили кілька чисел (400 800 1600 ...) - розкладаємо їх по полях від поточного."""
    global dlg_busy
    if i >= len(dlg_edits):
        return
    text = read_edit(dlg_edits[i])
    nums = re.findall(r"\d+", text)
    if not nums:
        if text:
            dlg_busy = True
            try:
                user32.SetWindowTextW(dlg_edits[i], "")
            finally:
                dlg_busy = False
        return
    if len(nums) == 1 and nums[0] == text:
        return
    dlg_busy = True
    try:
        for k, n in enumerate(nums):
            if i + k >= len(dlg_edits):
                break
            user32.SetWindowTextW(dlg_edits[i + k], n)
    finally:
        dlg_busy = False

def dlg_save():
    vals = {}
    for i, h in enumerate(dlg_edits):
        m = re.search(r"\d+", read_edit(h))
        if m:
            v = int(m.group())
            if not (0 < v <= 100000):
                user32.MessageBoxW(dlg_hwnd, t("d_err_range", n=i + 1),
                                   "X11 Battery", 0x30)
                return
            vals[i + 1] = v
    try:
        save_dpi_stages(vals)
    except OSError:
        user32.MessageBoxW(dlg_hwnd, t("d_err_write"),
                           "X11 Battery", 0x10)
        return
    user32.DestroyWindow(dlg_hwnd)
    widgets_update(force=True)

def dlg_proc(hwnd, msg, wparam, lparam):
    global dlg_hwnd, dlg_font
    if dlg_dark and dlg_brushes:
        if msg == 0x14:  # WM_ERASEBKGND - темний фон вікна
            rc = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rc))
            user32.FillRect(wparam, ctypes.byref(rc), dlg_brushes[0])
            return 1
        if msg == 0x138:  # WM_CTLCOLORSTATIC - підписи
            gdi32.SetTextColor(wparam, rgb(*DLG_FG))
            gdi32.SetBkColor(wparam, rgb(*DLG_BG))
            return dlg_brushes[0]
        if msg == 0x133:  # WM_CTLCOLOREDIT - поля введення
            gdi32.SetTextColor(wparam, rgb(*DLG_FG))
            gdi32.SetBkColor(wparam, rgb(*DLG_EDIT_BG))
            return dlg_brushes[1]
    if msg == 0x111:  # WM_COMMAND
        cid, code = wparam & 0xFFFF, (wparam >> 16) & 0xFFFF
        if cid == 1 and code == 0:
            dlg_save()
        elif cid == 2 and code == 0:
            user32.DestroyWindow(hwnd)
        elif 101 <= cid < 101 + DPI_ROWS and code == 0x300 and not dlg_busy:  # EN_CHANGE
            dlg_paste(cid - 101)
        return 0
    if msg == 0x400:  # DM_GETDEFID - кнопка за замовчуванням (Enter)
        return (0x534B << 16) | 1
    if msg == 0x10:  # WM_CLOSE
        user32.DestroyWindow(hwnd)
        return 0
    if msg == 0x2:  # WM_DESTROY
        if dlg_font:
            gdi32.DeleteObject(dlg_font)
        dlg_font = None
        dlg_hwnd = None
        dlg_edits.clear()
        _free_dlg_theme()
        for ih in dlg_icons:
            user32.DestroyIcon(ih)
        dlg_icons.clear()
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

_dlg_proc_ref = WNDPROC(dlg_proc)

def open_dpi_dialog():
    global dlg_hwnd, dlg_font, dlg_busy
    if dlg_hwnd and user32.IsWindow(dlg_hwnd):
        user32.ShowWindow(dlg_hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(dlg_hwnd)
        return
    sc = get_scale()
    S = lambda v: int(round(v * sc))
    cw = S(360)
    dlg_font = gdi32.CreateFontW(-S(13), 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 4, 0, "Segoe UI")
    hint = t("d_hint")
    # висоту підказки вимірюємо за справжнім шрифтом і шириною - рядків може бути 2, 3 чи 4
    hdc0 = user32.GetDC(None)
    oldf = gdi32.SelectObject(hdc0, dlg_font)
    trc = wt.RECT(0, 0, cw - S(32), 0)
    user32.DrawTextW(hdc0, hint, -1, ctypes.byref(trc), 0x10 | 0x400)  # DT_WORDBREAK | DT_CALCRECT
    gdi32.SelectObject(hdc0, oldf)
    user32.ReleaseDC(None, hdc0)
    head_h = trc.bottom + S(6)
    y0 = S(12) + head_h + S(10)
    ch = y0 + DPI_ROWS * S(34) + S(8) + S(32) + S(16)
    style = 0x00C00000 | 0x00080000  # WS_CAPTION | WS_SYSMENU
    rc = wt.RECT(0, 0, cw, ch)
    user32.AdjustWindowRectEx(ctypes.byref(rc), style, False, 0x8)
    w, h = rc.right - rc.left, rc.bottom - rc.top
    sx, sy = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    global dlg_dark
    dark = not light_theme()
    apply_menu_theme()  # режим застосунку (темний/світлий) для стилів DarkMode_*
    if dark:
        dlg_brushes[:] = [gdi32.CreateSolidBrush(rgb(*DLG_BG)), gdi32.CreateSolidBrush(rgb(*DLG_EDIT_BG))]
        dlg_dark = True
    dlg_busy = True
    hw = user32.CreateWindowExW(0x8 | (0x400000 if is_rtl() else 0),  # WS_EX_LAYOUTRTL для ar/he
                                "X11BatteryDpiDlg", t("d_title"), style,
                                (sx - w) // 2, (sy - h) // 2, w, h, None, None, HINST, None)
    if not hw:
        dlg_busy = False
        gdi32.DeleteObject(dlg_font)
        dlg_font = None
        _free_dlg_theme()
        return
    dlg_hwnd = hw
    if dark:  # темний заголовок вікна (DWMWA_USE_IMMERSIVE_DARK_MODE: 20, на старих Win10 - 19)
        try:
            val = ctypes.c_int(1)
            if dwmapi.DwmSetWindowAttribute(hw, 20, ctypes.byref(val), 4) != 0:
                dwmapi.DwmSetWindowAttribute(hw, 19, ctypes.byref(val), 4)
        except Exception:
            pass
    for kind, metric in ((1, 11), (0, 49)):  # ICON_BIG / ICON_SMALL за системними розмірами
        ih = load_icon(user32.GetSystemMetrics(metric))
        if ih:
            dlg_icons.append(ih)
            user32.SendMessageW(hw, 0x80, kind, ih)  # WM_SETICON
    kids = []
    def mk(cls, text, st, ex, x, y, ww, hh, cid=0):
        c = user32.CreateWindowExW(ex, cls, text, 0x40000000 | 0x10000000 | st,
                                   x, y, ww, hh, hw, cid, HINST, None)
        kids.append(c)
        return c
    mk("STATIC", hint, 0, 0, S(16), S(12), cw - S(32), head_h)
    stages = load_dpi_stages()
    dlg_edits.clear()
    for i in range(DPI_ROWS):
        y = y0 + i * S(34)
        mk("STATIC", t("d_stage", n=i + 1), 0x200, 0, S(16), y, S(90), S(26))  # SS_CENTERIMAGE
        v = stages.get(i + 1)
        dlg_edits.append(mk("EDIT", str(v) if v else "", 0x10000 | 0x80, 0x200,  # TABSTOP | AUTOHSCROLL | CLIENTEDGE
                            S(110), y, S(170), S(26), 101 + i))
    by = y0 + DPI_ROWS * S(34) + S(8)
    cx = cw - S(16) - S(100)
    mk("BUTTON", t("d_save"), 0x10000 | 0x1, 0, cx - S(8) - S(100), by, S(100), S(32), 1)  # DEFPUSHBUTTON
    mk("BUTTON", t("d_cancel"), 0x10000, 0, cx, by, S(100), S(32), 2)
    for c in kids:
        user32.SendMessageW(c, 0x30, dlg_font, 1)  # WM_SETFONT
    if dark:  # темні стилі елементів: поля введення і кнопки
        try:
            for c in dlg_edits:
                uxtheme.SetWindowTheme(c, "DarkMode_CFD", None)
            for c in kids[-2:]:
                uxtheme.SetWindowTheme(c, "DarkMode_Explorer", None)
        except Exception:
            pass
    dlg_busy = False
    user32.ShowWindow(hw, 5)
    user32.SetForegroundWindow(hw)
    if dlg_edits:
        user32.SetFocus(dlg_edits[0])
        user32.SendMessageW(dlg_edits[0], 0xB1, 0, -1)  # EM_SETSEL: виділити все

def toggle_dpi_widget():
    global dpi_widget_enabled
    dpi_widget_enabled = not dpi_widget_enabled
    reg_set("dpi_widget", int(dpi_widget_enabled))
    widgets_update(force=True)

def widget_proc(hwnd, msg, wparam, lparam):
    global offset_dp
    if msg == 0x201:  # WM_LBUTTONDOWN - початок перетягування
        hide_tip()
        pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
        drag.update(active=True, x0=pt.x, off0=offset_dp, moved=False)
        user32.SetCapture(hwnd)
        return 0
    if msg == 0x200 and drag["active"]:  # WM_MOUSEMOVE
        pt = wt.POINT(); user32.GetCursorPos(ctypes.byref(pt))
        dx = drag["x0"] - pt.x
        if abs(dx) > 3 and not locked:
            drag["moved"] = True
        if drag["moved"]:
            offset_dp = max(0, int(drag["off0"] + dx / get_scale()))
            layout()
        return 0
    if msg == 0x200:  # WM_MOUSEMOVE без перетягування - чекаємо наведення (400 мс) для підказки
        tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), 0x1 | 0x2, hwnd, 400)  # TME_HOVER | TME_LEAVE
        user32.TrackMouseEvent(ctypes.byref(tme))
        return 0
    if msg == 0x2A1:  # WM_MOUSEHOVER
        w = widgets.get(hwnd)
        if w and not drag["active"]:
            show_tip(w)
        return 0
    if msg == 0x2A3:  # WM_MOUSELEAVE
        hide_tip(widgets.get(hwnd))
        return 0
    if msg == 0x202:  # WM_LBUTTONUP
        if drag["active"]:
            drag["active"] = False
            user32.ReleaseCapture()
            if drag["moved"]:
                reg_set(offset_key(active_dev), offset_dp)
            # звичайний лівий клік нічого не робить - меню відкривається лише правою кнопкою
        return 0
    if msg == 0x205:  # WM_RBUTTONUP
        hide_tip()
        if hwnd_main:
            show_menu(hwnd_main)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

_widget_proc_ref = WNDPROC(widget_proc)

def wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_APP_UPDATE or msg == 0x113:  # WM_TIMER
        refresh(hwnd)
        return 0
    if msg == WM_TRAY:
        if (lparam & 0xFFFF) in (0x205, 0x202):  # правий / лівий клік
            show_menu(hwnd)
        return 0
    if msg == 0x111:  # WM_COMMAND
        cid = wparam & 0xFFFF
        if cid == 1:
            set_autostart(not autostart_on())
        elif cid == 4:
            toggle_dpi_widget()
        elif cid == 5:
            toggle_lock()
        elif cid == 6:
            open_dpi_dialog()
        elif cid == 7:
            reset_position()
        elif 100 <= cid < 200:
            select_monitor(cid - 100)
        elif 200 <= cid < 400:
            select_language(cid - 200)
        elif cid == 2:
            os._exit(0)
        return 0
    if taskbar_created and msg == taskbar_created:  # explorer перезапущено
        recreate_widgets()
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

_wndproc_ref = WNDPROC(wndproc)

def main():
    global hwnd_main, taskbar_created, HINST, dpi_widget_enabled, monitor_dev, locked
    try:  # чіткий віджет на екранах з масштабуванням
        user32.SetProcessDpiAwarenessContext.argtypes = [P]
        user32.SetProcessDpiAwarenessContext(P(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        pass
    k32.CreateMutexW(None, False, "Local\\X11BatteryTrayMutex")
    if ctypes.get_last_error() == 183:  # вже запущено
        return
    first_run_autostart()
    load_external_langs()
    set_language(reg_get_str("language", ""))  # мова: збережений вибір або мова Windows
    ensure_config()
    load_state()  # останній відомий ступінь DPI
    dpi_widget_enabled = bool(reg_get("dpi_widget", 1))
    monitor_dev = reg_get_str("monitor", "")
    locked = bool(reg_get("locked", 0))
    taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
    HINST = k32.GetModuleHandleW(None)

    wc = WNDCLASSW()
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = HINST
    wc.lpszClassName = "X11BatteryTrayWnd"
    user32.RegisterClassW(ctypes.byref(wc))

    wc2 = WNDCLASSW()
    wc2.lpfnWndProc = _widget_proc_ref
    wc2.hInstance = HINST
    wc2.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
    wc2.lpszClassName = "X11BatteryWidget"
    user32.RegisterClassW(ctypes.byref(wc2))

    wc3 = WNDCLASSW()
    wc3.lpfnWndProc = _dlg_proc_ref
    wc3.hInstance = HINST
    wc3.hCursor = user32.LoadCursorW(None, 32512)
    wc3.hbrBackground = 16  # COLOR_BTNFACE + 1
    wc3.lpszClassName = "X11BatteryDpiDlg"
    user32.RegisterClassW(ctypes.byref(wc3))

    wc4 = WNDCLASSW()
    wc4.lpfnWndProc = _tip_proc_ref
    wc4.hInstance = HINST
    wc4.lpszClassName = "X11BatteryTip"
    user32.RegisterClassW(ctypes.byref(wc4))

    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, APP, 0, 0, 0, 0, 0, None, None, HINST, None)
    hwnd_main = hwnd
    refresh(hwnd)
    user32.SetTimer(hwnd, 1, 5000, None)
    threading.Thread(target=reader, daemon=True).start()
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        if dlg_hwnd and user32.IsDialogMessageW(dlg_hwnd, ctypes.byref(msg)):
            continue
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

if __name__ == "__main__":
    main()
