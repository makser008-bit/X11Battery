X11 Battery Tray - version 0.8.1
=================================
Українська версія: README.txt


ABOUT
-----
X11 Battery Tray is a small Windows program that shows the battery level and the current DPI of an
ATTACK SHARK X11 gaming mouse right on the taskbar, next to the system tray:

    [DPI: 800] [mouse 93%] ^

It reads the data directly from the mouse's 2.4 GHz dongle and does not need the vendor software:
start it once and the numbers are always in front of you. It runs in the background, starts with
Windows, follows the Windows theme (dark/light), the system language and the display scale, and is
designed for minimal load. The interface is styled like Windows 11.

Features:
  * battery level in percent (with charging and low-battery indication);
  * current DPI (the actual number, not the stage number) in a separate widget that can be hidden;
  * remembers the last DPI stage even after the PC was turned off;
  * works with two monitors (your choice), position lock and a reset button;
  * speaks the Windows language automatically (23 built-in languages, you can add your own);
  * has its own icon (the Attack Shark logo).


WHAT IT SHOWS
-------------
BATTERY WIDGET (right, next to the tray) - a mouse icon and the battery percentage, e.g. "93%".
  * normal - text color follows the Windows theme (light or dark)
  * 15% or less - red
  * charging - green, with a lightning bolt
  * no data for 15 seconds (mouse asleep or off) - gray, the last known value is shown

DPI WIDGET (to the left of the battery widget) - e.g. "DPI: 800". Can be hidden in the menu.
  The mouse reports only the DPI STAGE NUMBER, not the DPI value itself, so the number comes from a
  table that you enter once (see "DPI setup"). While no value is set for a stage, "DPI: --" is shown.

TOOLTIP on hover (appears after ~0.4 s; drawn by the program itself: rounded, no white border, follows the
theme - dark in dark mode, with a thin gray border in light mode):
  * on the battery widget - two lines: "ATTACK SHARK X11: 93%" (+ "(charging)") and "DPI: 800"
  * on the DPI widget - "DPI: 800"

FONT - Segoe UI Variable Text (as in the Windows 11 Start menu); Segoe UI if it is not available.
The widgets are transparent (no background), anti-aliased and follow the display scale.

There is no separate icon in the system tray. The menu opens with the RIGHT mouse button on a widget.


MENU
----
Right-click on either widget opens the menu (left click does nothing except dragging).
The menu is Windows 11 style: follows the Windows theme (dark/light, like the taskbar menu) and has
Segoe Fluent Icons. Active toggles are marked with a check mark at the end of the line (right side).
Items:
  * two gray lines: current battery level and DPI
  * Start with Windows - autostart
  * Show DPI near the tray - show/hide the DPI widget
  * Lock position - prevents moving the widgets
  * Reset position - puts the widgets back to the default place next to the tray
  * Monitor for the widgets - submenu (appears only with 2+ monitors)
  * Set DPI values... - a window with 6 fields
  * Language - automatic (Windows language) or choose manually
  * Version (info line)
  * Exit

The battery widget is always shown: the menu is opened through it.


DPI SETUP
---------
The X11 has 6 DPI stages. To make the widget show numbers, enter the values of your stages once:

  Menu > "Set DPI values..."

A window with 6 fields opens ("Stage 1" ... "Stage 6"; dark if the Windows theme is dark):
  * enter the DPI of each stage (see the vendor software for your values)
  * an empty field = value not set for that stage
  * allowed values: 1 to 100000
  * "Save" (Enter) applies, "Cancel" (Esc) closes without changes, Tab moves to the next field
Changes apply immediately, no restart needed.

The values are stored in dpi.txt next to the program (lines like "1 = 400"). You can also edit the
file by hand; lines starting with # are ignored; changes are picked up within a few seconds.

The mouse sends the DPI stage only at the moment the DPI button is pressed. That is why the program
remembers the last stage and shows it after a PC restart. If you changed the DPI while the program was
not running (e.g. the mouse was connected to another device), the shown DPI will be outdated - just
press the DPI button once.


WIDGET POSITION
---------------
* Dragging: hold the left mouse button on a widget and drag left/right. Both widgets move together,
  the position is remembered.
* Limits: the widgets cannot leave the bar - on the right they stop at the tray, on the left at the
  edge of the taskbar.
* "Lock position" disables dragging (the right-click menu still works).
* "Reset position" restores the default position (works even when the position is locked).
* Monitor: "Monitor for the widgets" moves the widgets to the taskbar of the chosen monitor.
  The choice is remembered, each monitor keeps its own position.
  - For a secondary monitor, Windows must have "Show my taskbar on all displays" enabled
    (Settings > Personalization > Taskbar > Taskbar behaviors). If a monitor has no taskbar, its menu
    item is disabled and the widgets stay on the main monitor.
  - A secondary taskbar has no tray (only the clock), so the default position there is to the left of
    the clock at an estimated offset. Just drag the widgets if needed.


INTERFACE LANGUAGE
------------------
The language is detected automatically from the Windows display language (using its priority list):
Ukrainian Windows - Ukrainian program, Japanese Windows - Japanese program, and so on.
23 languages are built in: English, Українська, Русский, Polski, Deutsch, Français, Español, Português,
Italiano, Nederlands, Türkçe, Čeština, Română, العربية, עברית, हिन्दी, ไทย, Tiếng Việt,
Bahasa Indonesia, 日本語, 한국어, 简体中文, 繁體中文. If your Windows language is not among them, English is used.
Arabic and Hebrew are shown right-to-left (mirrored interface).

To change it manually: menu > "Language" > choose a language. "Auto" returns to the Windows language.
The choice is remembered and applies immediately (no restart).

Translated: the menu, tooltips, the DPI values window, the comments in dpi.txt.
Not translated: the text on the widgets themselves (the number, % and "DPI" are the same everywhere),
the README files and build_exe.bat.

Adding your own language (no rebuild needed):
  1) in the lang folder next to X11Battery.exe copy _template.json to lang\xx.json,
     where xx is the language code (sr, hu, sv, pt-BR, ...);
  2) translate the values (keep the placeholders {n}, {pct}, {v}, {menu} unchanged) and put the
     language name in "_name";
  3) restart the program - the language appears in the "Language" menu and, if it matches the
     Windows language, is selected automatically.
Such a file can also fix individual strings of a built-in language (it takes priority over the built-in
text). The built-in translations are machine-made and have not been checked by native speakers - fix
any inaccuracies this way.


AUTOSTART
---------
Autostart is enabled automatically on the first launch. Toggle it with the check item in the menu.
A second copy of the program cannot be started.
If you move the exe to another folder, switch autostart off and on again in the menu so it points to the new place.


REQUIREMENTS
------------
* Windows 10/11 (the widgets are designed for the Windows 11 taskbar; only a horizontal taskbar -
  bottom or top - is supported).
* The mouse connected through the 2.4 GHz dongle (VID 1D57, PID FA60).
* Close the Attack Shark vendor software (it may intercept the mouse reports).
* To build the exe: Python 3 from python.org (with "Add to PATH") and internet access to install PyInstaller.
  The program itself uses only the Python standard library + ctypes, no third-party packages.


FILES
-----
x11_battery.py       - the program
build_exe.bat        - builds X11Battery.exe (PyInstaller) and puts it next to the script; removes the
                       temporary build and dist folders afterwards
version_info.txt     - the version shown in the exe properties (Properties > Details)
X11Battery.ico       - the program icon (Attack Shark logo): the exe icon and the DPI window icon.
                       To change the icon, replace this file and rebuild the exe (build_exe.bat).
lang\_template.json  - template for adding your own language (see "Interface language")
x11_scan.py          - helper HID scanner, only needed for diagnostics
README.txt           - description in Ukrainian
README_EN.txt        - this file (English)

What the program creates while running:
dpi.txt                          - next to the program: DPI values of the stages
x11_battery.log                  - next to the program: appears only if an error occurred
%APPDATA%\X11Battery\state.json  - the last known DPI stage
Registry HKCU\Software\X11Battery - settings: DPI widget shown or not, position lock, chosen monitor,
                                   language, position (separately per monitor)
Registry HKCU\...\Run            - the autostart entry (value X11Battery)


RUNNING AND BUILDING
--------------------
Test:       python x11_battery.py   (or pythonw x11_battery.py - without a console)
Permanent:  run build_exe.bat (Python 3 required) - X11Battery.exe appears next to it; use that file.
Updating:   just run build_exe.bat again - it closes the old program itself and builds the new one.
During the build the window should show the line "Іконка: X11Battery.ico знайдена, додаю в exe"
(the build script messages are in Ukrainian; it means "icon file found, adding it to the exe").
If you move the exe to another folder, move dpi.txt (and the lang folder, if present) along with it.
If the exe folder is write-protected (e.g. Program Files), dpi.txt cannot be saved -
keep the exe in a normal folder.

Uninstall: menu > Exit; switch autostart off (menu item, before exiting) and delete the program files.
Optionally also delete the %APPDATA%\X11Battery folder and the registry key HKCU\Software\X11Battery.


HOW IT WORKS (TECHNICAL)
------------------------
The program reads the input reports of the dongle interface with usage page 0x0A (MI_02 COL03) directly
through SetupAPI and hid.dll (pure ctypes, no hidapi):
  03 55 40 <state> <level>   - arrives about every 2 seconds
        state: 01 - normal operation, 03 - charging (bit 0x02)
        level: 0-100 (%)
  03 55 10 <stage> 00        - arrives when the DPI button is pressed (stages count from 1)
The format was derived from scanner logs; there is no official documentation. The widgets are
transparent (per-pixel alpha) child windows of the taskbar (Shell_TrayWnd / Shell_SecondaryTrayWnd).
The dark theme of the menu and the DPI window uses undocumented Windows features (uxtheme) and DWM; the tooltip
is the program's own transparent window.
If the display does not match the vendor software on some firmware - run
python x11_scan.py listen 40 and send the log.


LIMITATIONS
-----------
* Works only through the dongle. Over Bluetooth or a cable the interface and reports may differ.
* The charging flag (bit 0x02) and the DPI stage numbering from 1 were derived from tests, not from documentation.
* The mouse does not report the DPI value, only the stage number - so the values are entered manually.
* The widgets have not been tested on every Windows 11 build or monitor configuration.
* The theme of the menu and the DPI window is switched with undocumented Windows functions. If they do not
  work on some build, the elements stay in the system look (they work, but without the dark theme).
  Menu icons need the Segoe Fluent Icons font (Windows 11); Segoe MDL2 Assets is used otherwise (Windows 10).
* The built-in translations have not been checked by native speakers.


TROUBLESHOOTING
---------------
* Something looks wrong - take a screenshot.
* No widgets visible: check that the mouse is connected through the dongle and the program is running
  (Task Manager); right-click a widget > "Reset position"; look into x11_battery.log if it exists.
* The exe icon did not change: 1) X11Battery.ico must be next to build_exe.bat - the build window should
  show "Іконка: X11Battery.ico знайдена"; 2) rebuild the exe (do not use the old one); 3) Windows caches
  icons - the batch file clears the cache itself, but if the old icon stays, restart Explorer
  (Task Manager > Windows Explorer > Restart) or copy the exe under another name;
  4) Properties > Details should show the current version.
* Errors are written to x11_battery.log next to the program (the file appears only on an error).
* Scanner: python x11_scan.py (list interfaces), python x11_scan.py feature, python x11_scan.py listen 40
  (mouse reports; move the mouse, press DPI, plug the charger). The log goes to x11_scan_log.txt.


VERSION HISTORY
---------------
0.8.1  The hover tooltip is now drawn by the program: no white border, rounded corners, follows the theme
       (it used to be the system tooltip with a bright border).
0.8.0  Windows language auto-detection and program translation (23 languages), manual language choice in
       the menu, extra languages via lang\xx.json, mirrored interface for Arabic and Hebrew.
       README rewritten, program description and English version (README_EN.txt) added.
0.7.7  The hover tooltip follows the Windows theme (dark in dark mode).
0.7.6  DPI window: removed the hint about pasting all values at once.
0.7.5  The DPI window is dark when the Windows theme is dark.
0.7.4  Check marks of active menu items at the end of the line (right); plain menu icons.
0.7.3  Active toggles in the menu are marked with a check mark.
0.7.2  Exe icon: the .ico file in the classic format (small sizes without PNG compression); the build shows
       whether the icon was found and clears the Windows icon cache.
0.7.1  Program icon (Attack Shark logo): in the exe and in the DPI window title.
0.7.0  Windows 11 style menu: Windows theme (dark/light) and Segoe Fluent Icons.
0.6.3  The menu opens only with the right mouse button.
0.6.2  DPI window: the hint height is measured with the real font, the text is no longer cut off.
0.6.1  DPI window: wider, larger font.
0.6.0  "Set DPI values..." opens its own window with 6 fields instead of Notepad.
0.5.0  Text and mouse icon aligned on one center line; limits for the widgets; "Reset position".
0.4.1  Format "DPI: 300" (without the stage number); no value - "DPI: --".
0.4.0  Monitor choice for the widgets, separate position per monitor; position lock.
0.3.0  Removed the number icon from the system tray; second (DPI) widget; Segoe UI Variable Text font;
       switch for the DPI widget.
0.2.0  Battery widget next to the tray (mouse icon + %); DPI stage remembered between runs;
       settings in the registry; error log.
0.1.0  First version: battery shown as a number icon in the system tray; autostart.
