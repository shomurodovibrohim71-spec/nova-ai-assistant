"""Screenshot skill — screen capture OR Explorer folder / file capture (background), sent to Telegram."""
from __future__ import annotations

import asyncio
import math
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ...config import settings
from ..base import Skill

TELEGRAM_API = "https://api.telegram.org/bot{token}"


# ── helpers ───────────────────────────────────────────────────────────────────

def _take_screenshot(monitor: int = 0) -> Path:
    import mss, mss.tools
    with mss.mss() as sct:
        idx = min(monitor, len(sct.monitors) - 1)
        img = sct.grab(sct.monitors[idx])
        tmp = Path(tempfile.mktemp(suffix=".png"))
        mss.tools.to_png(img.rgb, img.size, output=str(tmp))
    return tmp


def _gdi_capture(hwnd: int, w: int, h: int):
    """Capture a window's content with PrintWindow. Returns PIL Image."""
    import win32gui, win32ui
    from ctypes import windll
    from PIL import Image

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc  = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp     = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)
    windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
    info = bmp.GetInfo()
    bits = bmp.GetBitmapBits(True)
    img  = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                             bits, "raw", "BGRX", 0, 1)
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bmp.GetHandle())
    return img


def _capture_folder_window(folder: Path) -> Path:
    """
    Open Explorer, hide it within milliseconds of creation, wait for full
    content load, show briefly at HWND_BOTTOM (behind every user window),
    capture with PrintWindow, close.
    """
    import win32gui, win32con

    WIN_W, WIN_H = 1280, 800

    before: set[int] = set()
    def _cb(hwnd, _):
        if win32gui.GetClassName(hwnd) == "CabinetWClass":
            before.add(hwnd)
    win32gui.EnumWindows(_cb, None)

    subprocess.Popen(["explorer.exe", str(folder)])

    # Poll at 10 ms so we catch the window within one display frame
    hwnd = None
    for _ in range(500):  # up to 5 s
        time.sleep(0.01)
        candidates: list[int] = []
        def _find(h, _):
            if win32gui.GetClassName(h) == "CabinetWClass" and h not in before:
                candidates.append(h)
        win32gui.EnumWindows(_find, None)
        if candidates:
            hwnd = candidates[-1]
            win32gui.ShowWindow(hwnd, 0)  # SW_HIDE — hide immediately
            break

    if hwnd is None:
        raise RuntimeError("Explorer window not found")

    # Resize while hidden — no visual effect
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_BOTTOM,
        0, 0, WIN_W, WIN_H,
        win32con.SWP_NOACTIVATE,
    )

    # Wait until Explorer finishes loading: title has folder name, no "Working on it"
    folder_name = folder.name
    for _ in range(200):  # up to 20 s
        time.sleep(0.1)
        title = win32gui.GetWindowText(hwnd).lower()
        if folder_name.lower() in title and "working" not in title:
            break
    time.sleep(2.0)  # extra buffer for icon rendering

    # Show briefly at HWND_BOTTOM (behind all user windows) so DWM renders content
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_BOTTOM,
        0, 0, WIN_W, WIN_H,
        win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
    )
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
    time.sleep(0.4)  # DWM needs a few frames to composite

    img = _gdi_capture(hwnd, WIN_W, WIN_H)

    win32gui.ShowWindow(hwnd, 0)  # hide again before closing
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    tmp = Path(tempfile.mktemp(suffix=".png"))
    img.save(str(tmp), "PNG")
    return tmp


def _find_excel_column(ws, col_name: str) -> tuple[int, int] | None:
    """
    Search for col_name in the first 10 rows.
    Returns (header_row_1based, col_index_1based) or None.
    """
    used = ws.UsedRange
    max_row = min(10, used.Rows.Count)
    max_col = used.Columns.Count
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            val = str(ws.Cells(r, c).Value or "").strip()
            if col_name.lower() in val.lower():
                return r, c
    return None


def _capture_excel_window(
    file_path: Path,
    sheet: str | None = None,
    filter_col: str | None = None,
    filter_val: str | None = None,
    clear_filters: bool = False,
    filter_col2: str | None = None,
    filter_val2: str | None = None,
) -> Path:
    """
    Open Excel via COM (Visible=False — truly invisible), optionally switch
    sheet, apply/clear AutoFilter(s), screenshot, close without saving.
    """
    import win32gui, win32con
    import win32com.client
    import pythoncom

    WIN_W, WIN_H = 1280, 800

    pythoncom.CoInitialize()
    excel = None
    wb    = None
    try:
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible       = False
        excel.DisplayAlerts = False

        wb = excel.Workbooks.Open(str(file_path))
        time.sleep(1.5)

        # ── Sheet selection ───────────────────────────────────────────────────
        ws = wb.ActiveSheet
        if sheet:
            for sh in wb.Sheets:
                if sheet.lower() in sh.Name.lower():
                    sh.Activate()
                    ws = sh
                    break

        # ── Show window first so outline/hidden ops take visual effect ───────
        hwnd = excel.Hwnd
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_BOTTOM,
            0, 0, WIN_W, WIN_H,
            win32con.SWP_NOACTIVATE,
        )
        excel.Visible = True
        time.sleep(0.2)

        # ── Expand all column groups + unhide every column (phone numbers) ───
        try:
            ws.Outline.ShowLevels(ColumnLevels=8)
        except Exception:
            pass
        try:
            ws.UsedRange.EntireColumn.Hidden = False
        except Exception:
            pass
        time.sleep(0.2)

        # ── Clear existing filters if requested ───────────────────────────────
        if clear_filters:
            try:
                if ws.AutoFilterMode:
                    ws.AutoFilterMode = False
            except Exception:
                pass

        # ── Apply AutoFilter(s) ───────────────────────────────────────────────
        filters: list[tuple[str, str]] = []
        if filter_col and filter_val:
            filters.append((filter_col, filter_val))
        if filter_col2 and filter_val2:
            filters.append((filter_col2, filter_val2))
        if filters:
            _apply_excel_filters(ws, excel, filters)

        time.sleep(0.2)
        img = _gdi_capture(hwnd, WIN_W, WIN_H)
        excel.Visible = False

    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    tmp = Path(tempfile.mktemp(suffix=".png"))
    img.save(str(tmp), "PNG")
    return tmp


def _capture_file_window(
    file_path: Path,
    sheet: str | None = None,
    filter_col: str | None = None,
    filter_val: str | None = None,
    clear_filters: bool = False,
    filter_col2: str | None = None,
    filter_val2: str | None = None,
) -> Path:
    """
    Open any file with its default application.
    Excel (.xls/.xlsx/…) uses COM automation for true invisibility.
    Other files use ShellExecute + SW_HIDE-ASAP approach.
    """
    if file_path.suffix.lower() in (".xls", ".xlsx", ".xlsm", ".xlsb"):
        return _capture_excel_window(file_path, sheet=sheet,
                                     filter_col=filter_col, filter_val=filter_val,
                                     clear_filters=clear_filters,
                                     filter_col2=filter_col2, filter_val2=filter_val2)

    import win32gui, win32con
    import ctypes

    WIN_W, WIN_H = 1280, 800

    before: set[int] = set()
    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            before.add(hwnd)
    win32gui.EnumWindows(_cb, None)

    ctypes.windll.shell32.ShellExecuteW(
        None, "open", str(file_path), None, str(file_path.parent), 1
    )

    file_stem = file_path.stem.lower()
    hwnd = None
    for _ in range(300):  # up to 3 s at 10 ms
        time.sleep(0.01)
        candidates: list[int] = []
        def _find(h, _):
            if (win32gui.IsWindowVisible(h) and
                    win32gui.GetWindowText(h) and
                    h not in before):
                candidates.append(h)
        win32gui.EnumWindows(_find, None)
        if candidates:
            for c in candidates:
                if file_stem in win32gui.GetWindowText(c).lower():
                    hwnd = c
                    break
            if hwnd is None:
                hwnd = candidates[-1]
            win32gui.ShowWindow(hwnd, 0)  # SW_HIDE immediately
            break

    if hwnd is None:
        raise RuntimeError(f"Application window not found for {file_path.name}")

    win32gui.SetWindowPos(
        hwnd, win32con.HWND_BOTTOM,
        0, 0, WIN_W, WIN_H,
        win32con.SWP_NOACTIVATE,
    )

    for _ in range(150):  # up to 15 s
        time.sleep(0.1)
        if file_stem in win32gui.GetWindowText(hwnd).lower():
            break
    time.sleep(2.5)

    win32gui.SetWindowPos(
        hwnd, win32con.HWND_BOTTOM,
        0, 0, WIN_W, WIN_H,
        win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
    )
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
    time.sleep(0.4)

    img = _gdi_capture(hwnd, WIN_W, WIN_H)

    win32gui.ShowWindow(hwnd, 0)
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    tmp = Path(tempfile.mktemp(suffix=".png"))
    img.save(str(tmp), "PNG")
    return tmp


def _apply_excel_filters(
    ws,
    excel,
    filters: list[tuple[str, str]],
) -> None:
    """
    Apply one or more (column_name, value) AutoFilters to *ws*.
    Clears existing filters first, then applies all requested ones.
    Automatically finds the correct header row for each column.
    """
    if not filters:
        return

    used = ws.UsedRange
    last_r = used.Row + used.Rows.Count - 1
    last_c = used.Column + used.Columns.Count - 1

    # Clear old filter
    try:
        if ws.AutoFilterMode:
            ws.AutoFilterMode = False
    except Exception:
        pass

    for col_name, col_val in filters:
        result = _find_excel_column(ws, col_name)
        if result is None:
            continue
        header_row, col_idx = result
        # Build range from actual header row so AutoFilter Field numbers are correct
        rng = ws.Range(ws.Cells(header_row, used.Column), ws.Cells(last_r, last_c))
        relative_col = col_idx - used.Column + 1
        rng.AutoFilter(
            Field=relative_col,
            Criteria1=col_val,
            VisibleDropDown=True,
        )

    # Scroll to top after filtering
    try:
        excel.ActiveWindow.ScrollRow    = 1
        excel.ActiveWindow.ScrollColumn = 1
    except Exception:
        pass
    time.sleep(0.2)


def _capture_excel_scrolled_pages(
    file_path: Path,
    filter_col: str | None = None,
    filter_val: str | None = None,
    sheet: str | None = None,
    filter_col2: str | None = None,
    filter_val2: str | None = None,
) -> list[Path]:
    """
    Open Excel hidden via COM, apply one or two filters, then scroll from top
    to bottom capturing each screenful with LargeScroll. Returns list of PNG paths.
    Shows ACTUAL Excel formatting — colours, merged cells, phone numbers, etc.
    """
    import win32gui, win32con
    import win32com.client
    import pythoncom

    WIN_W, WIN_H = 1600, 900   # wider window → more columns visible

    pythoncom.CoInitialize()
    excel = None
    wb    = None
    raw_imgs: list = []

    try:
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible       = False
        excel.DisplayAlerts = False

        wb = excel.Workbooks.Open(str(file_path))
        time.sleep(1.5)

        # ── Sheet selection ───────────────────────────────────────────────────
        ws = wb.ActiveSheet
        if sheet:
            for sh in wb.Sheets:
                if sheet.lower() in sh.Name.lower():
                    sh.Activate()
                    ws = sh
                    break

        # ── Position & show window FIRST so outline/hidden ops take effect ───
        hwnd = excel.Hwnd
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_BOTTOM,
            0, 0, WIN_W, WIN_H,
            win32con.SWP_NOACTIVATE,
        )
        excel.Visible = True
        excel.ActiveWindow.Zoom = 80
        try:
            excel.ActiveWindow.DisplayHeadings = False
        except Exception:
            pass
        time.sleep(0.2)

        # ── Expand all column groups + unhide every column (phone numbers) ───
        try:
            ws.Outline.ShowLevels(ColumnLevels=8)
        except Exception:
            pass
        try:
            ws.UsedRange.EntireColumn.Hidden = False
        except Exception:
            pass
        time.sleep(0.2)

        # ── Apply filters (one or two) ────────────────────────────────────────
        filters: list[tuple[str, str]] = []
        if filter_col and filter_val:
            filters.append((filter_col, filter_val))
        if filter_col2 and filter_val2:
            filters.append((filter_col2, filter_val2))
        if filters:
            _apply_excel_filters(ws, excel, filters)

        # ── Find last visible data row (after filtering) ─────────────────────
        last_data_row = None
        try:
            vis_rng = ws.UsedRange.SpecialCells(12)  # 12 = xlCellTypeVisible
            last_area = vis_rng.Areas(vis_rng.Areas.Count)
            last_data_row = last_area.Row + last_area.Rows.Count - 1
        except Exception:
            pass

        # Scroll to very top-left
        excel.ActiveWindow.ScrollRow    = 1
        excel.ActiveWindow.ScrollColumn = 1
        time.sleep(0.15)

        # ── Scroll & capture ──────────────────────────────────────────────────
        prev_scroll = None
        for _ in range(60):
            cur_scroll = excel.ActiveWindow.ScrollRow

            if last_data_row is not None and cur_scroll > last_data_row:
                break
            if cur_scroll == prev_scroll:
                break

            time.sleep(0.2)   # wait for DWM to render
            raw_imgs.append(_gdi_capture(hwnd, WIN_W, WIN_H))
            prev_scroll = cur_scroll

            excel.ActiveWindow.LargeScroll(Down=1)
            time.sleep(0.1)

        excel.Visible = False

    finally:
        try:
            if wb    is not None: wb.Close(False)
        except Exception:
            pass
        try:
            if excel is not None: excel.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

    paths: list[Path] = []
    for img in raw_imgs:
        tmp = Path(tempfile.mktemp(suffix=".png"))
        img.save(str(tmp), "PNG")
        paths.append(tmp)
    return paths


def _render_table_page(df, title: str) -> Path:
    """Render a DataFrame page as a styled PNG table."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if df.empty:
        fig, ax = plt.subplots(figsize=(8, 2))
        ax.text(0.5, 0.5, "Ma'lumot topilmadi", ha="center", va="center", fontsize=14)
        ax.axis("off")
        tmp = Path(tempfile.mktemp(suffix=".png"))
        fig.savefig(str(tmp), dpi=120, bbox_inches="tight")
        plt.close(fig)
        return tmp

    display_df = df.copy()
    for col in display_df.columns:
        display_df[col] = display_df[col].astype(str).str[:35]

    n_rows, n_cols = display_df.shape
    fig_w = max(10, n_cols * 2.0)
    fig_h = max(2, n_rows * 0.38 + 1.2)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")
    if title:
        fig.suptitle(title, fontsize=11, fontweight="bold", y=0.99)

    tbl = ax.table(
        cellText=display_df.values.tolist(),
        colLabels=list(display_df.columns),
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.auto_set_column_width(range(n_cols))

    for j in range(n_cols):
        tbl[0, j].set_facecolor("#2C3E50")
        tbl[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(1, n_rows + 1):
        color = "#F2F2F2" if i % 2 == 0 else "#FFFFFF"
        for j in range(n_cols):
            tbl[i, j].set_facecolor(color)

    tmp = Path(tempfile.mktemp(suffix=".png"))
    fig.savefig(str(tmp), dpi=130, bbox_inches="tight", facecolor="#FAFAFA")
    plt.close(fig)
    return tmp


def _filter_all_rows(
    file_path: Path,
    filter_col: str,
    filter_val: str,
    sheet: str | None = None,
    rows_per_page: int = 40,
) -> list[Path]:
    """
    Read Excel with pandas, apply filter, render ALL matching rows as
    paginated table images (rows_per_page rows each). Returns list of PNG paths.
    """
    import pandas as pd

    xl = pd.ExcelFile(file_path)

    # Determine which sheet to use
    if sheet:
        sheet_names_to_try = [
            s for s in xl.sheet_names if sheet.lower() in s.lower()
        ] or xl.sheet_names
    else:
        sheet_names_to_try = xl.sheet_names  # search all sheets for the column

    df = None
    sheet_name = xl.sheet_names[0]
    matched_col = None

    for sname in sheet_names_to_try:
        raw = xl.parse(sname, header=None)
        # Find header row
        header_row = 0
        for i, row in raw.iterrows():
            if len(row.dropna()) >= 3:
                header_row = i
                break
        candidate = xl.parse(sname, header=header_row)
        candidate.columns = [str(c).strip() for c in candidate.columns]
        col = next((c for c in candidate.columns if filter_col.lower() in c.lower()), None)
        if col is not None:
            df = candidate
            sheet_name = sname
            matched_col = col
            break

    if df is None or matched_col is None:
        all_cols = []
        for sname in xl.sheet_names:
            raw = xl.parse(sname, header=None)
            hr = 0
            for i, row in raw.iterrows():
                if len(row.dropna()) >= 3:
                    hr = i
                    break
            tmp = xl.parse(sname, header=hr)
            all_cols.extend([str(c).strip() for c in tmp.columns[:5]])
        raise ValueError(f"'{filter_col}' ustuni topilmadi. Namuna ustunlar: {all_cols[:10]}")

    filtered = df[
        df[matched_col].astype(str).str.upper().str.strip() == filter_val.upper().strip()
    ].copy()

    # Pick most useful columns
    priority = ["#", "name", "student", "ism", "oquvchi", "paid", "status", "group", "tel"]
    keep: list[str] = []
    for kw in priority:
        for col in filtered.columns:
            if kw.lower() in col.lower() and col not in keep:
                keep.append(col)
                if len(keep) >= 7:
                    break
        if len(keep) >= 7:
            break
    if not keep:
        keep = list(filtered.columns[:7])

    filtered = filtered[keep].reset_index(drop=True)
    filtered.index = filtered.index + 1
    filtered.index.name = "№"
    filtered = filtered.reset_index()

    total = len(filtered)
    if total == 0:
        empty_title = f"{filter_val.upper()} — 0 ta o'quvchi  |  {file_path.name}"
        return [_render_table_page(filtered, empty_title)]

    num_pages = math.ceil(total / rows_per_page)
    pages: list[Path] = []
    for page in range(num_pages):
        chunk = filtered.iloc[page * rows_per_page: (page + 1) * rows_per_page]
        title = (
            f"{filter_val.upper()} — jami {total} ta  "
            f"[{page + 1}/{num_pages}]  |  {file_path.name}"
        )
        pages.append(_render_table_page(chunk, title))
    return pages


async def _send_document(img_path: Path, caption: str) -> dict[str, Any]:
    import httpx
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram not configured."}
    url = f"{TELEGRAM_API.format(token=token)}/sendDocument"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with img_path.open("rb") as fh:
                resp = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"document": (img_path.name, fh, "image/png")},
                )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "reply": f"Telegram error: {data.get('description')}"}
    except Exception as e:
        return {"ok": False, "reply": f"Failed to send: {e}"}
    finally:
        img_path.unlink(missing_ok=True)
    return {"ok": True}


# ── skill ─────────────────────────────────────────────────────────────────────

class ScreenshotSkill(Skill):
    name = "screenshot"
    description = "Capture the screen OR open a folder/file invisibly and screenshot it, send to Telegram."
    tool_description = (
        "Three modes — choose based on user intent:\n\n"
        "MODE 1 — Plain screen capture (no folder_path):\n"
        "  Use ONLY when user says 'screenshot ol', 'ekran rasm' with NO specific file/folder.\n\n"
        "MODE 2 — Folder capture (folder_path = directory path):\n"
        "  Use when user wants to see folder contents. Opens Windows Explorer invisibly.\n\n"
        "MODE 3 — Excel/file capture with optional operations (folder_path = file path):\n"
        "  For Excel files (.xlsx etc): opens via COM (completely invisible), performs any\n"
        "  requested operations, screenshots the result, closes without saving.\n"
        "  Supported Excel operations:\n"
        "    - sheet: switch to a specific worksheet by name\n"
        "    - filter_column + filter_value: primary AutoFilter (e.g. PAYMENT STATUS = UNP)\n"
        "    - filter_column2 + filter_value2: SECOND AutoFilter applied simultaneously\n"
        "      e.g. filter_column2='GROUP', filter_value2='MWF'\n"
        "    - clear_filters: remove all existing filters (set to true)\n"
        "    - capture_all=true: scroll through ALL matching rows page by page\n"
        "  Multiple filters can be combined — both are active at once (AND logic).\n"
        "  Examples:\n"
        "    'UNP va MWF oquvchilar' →\n"
        "      filter_column='PAYMENT STATUS', filter_value='UNP',\n"
        "      filter_column2='GROUP', filter_value2='MWF', capture_all=true\n"
        "    'payment status = UNP filter qo\\'y' →\n"
        "      filter_column='PAYMENT STATUS', filter_value='UNP'\n"
        "    'filterlarni olib tashla' → clear_filters=true\n\n"
        "CRITICAL: NEVER use MODE 1 when user mentions a specific file or folder.\n"
        "Use capture_all=true whenever user asks for ALL rows or says the list might be long."
    )
    patterns = [
        r"^\s*screenshot\s*(?:monitor\s*(?P<mon>\d+))?\s*[!.\?]*\s*$",
        r"^\s*(?:take\s+(?:a\s+)?|send\s+(?:a\s+)?)screenshot\s*[!.\?]*\s*$",
        r"^\s*ekran\s*(?:rasm[iga]*|surati?)\s*(?:ol|yubor)?\s*[!.\?]*\s*$",
        r"^\s*screenshot\s+(?:ol|yubor|jo[''`]?nat)\s*[!.\?]*\s*$",
        r"^\s*(?:ekran|screen)\s*(?:ol|sur[''`]?at|rasm)\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "folder_path": {
                "type": "string",
                "description": "Full absolute Windows path to the folder or file. E.g. 'C:\\Users\\user\\Desktop\\report.xlsx'.",
            },
            "sheet": {
                "type": "string",
                "description": "Excel sheet name to activate before screenshot. Partial match supported.",
            },
            "filter_column": {
                "type": "string",
                "description": "Excel column name to filter on. Partial, case-insensitive match. E.g. 'PAYMENT STATUS'.",
            },
            "filter_value": {
                "type": "string",
                "description": "Value to filter by. E.g. 'UNP', 'PAID'.",
            },
            "filter_column2": {
                "type": "string",
                "description": "Second column to filter on simultaneously. E.g. 'GROUP'.",
            },
            "filter_value2": {
                "type": "string",
                "description": "Second filter value. E.g. 'MWF', 'TTS'.",
            },
            "clear_filters": {
                "type": "boolean",
                "description": "Set true to remove all AutoFilters from the sheet before screenshotting.",
                "default": False,
            },
            "capture_all": {
                "type": "boolean",
                "description": (
                    "Set true to capture ALL filtered rows by scrolling through the actual Excel view. "
                    "Opens Excel invisibly, applies the filter, then scrolls page-by-page capturing "
                    "each screenful with real Excel formatting (colours, merged cells, phone numbers). "
                    "Sends multiple photos if needed. "
                    "Use when user says 'hammasini', 'barchasi', 'all rows', 'scroll qilib ko\\'rsating', "
                    "or when the filtered result may have more rows than fit in one screenshot."
                ),
                "default": False,
            },
            "monitor": {
                "type": "integer",
                "description": "Monitor index for plain screen capture (0=all, 1=primary). Ignored when folder_path is set.",
                "default": 0,
            },
        },
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        mon = 0
        if match:
            try:
                mon = int(match.group("mon") or 0)
            except Exception:
                mon = 0
        return await self.run_tool({"monitor": mon})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        folder_path = (args.get("folder_path") or "").strip()

        if folder_path:
            target = Path(folder_path)
            if not target.exists():
                return {"ok": False, "reply": f"Topilmadi: {folder_path}"}

            # ── Folder → Explorer ─────────────────────────────────────────────
            if target.is_dir():
                try:
                    img_path = await asyncio.to_thread(_capture_folder_window, target)
                except Exception as e:
                    return {"ok": False, "reply": f"Papka oynasi suratga olinmadi: {e}"}
                result = await _send_document(img_path, f"📁 {target.name}")
                if not result["ok"]:
                    return result
                return {"ok": True, "reply": f"📁 {target.name} papkasi yuborildi."}

            # ── File → default app (Excel via COM) ────────────────────────────
            sheet         = (args.get("sheet") or "").strip() or None
            filter_col    = (args.get("filter_column") or "").strip() or None
            filter_val    = (args.get("filter_value") or "").strip() or None
            filter_col2   = (args.get("filter_column2") or "").strip() or None
            filter_val2   = (args.get("filter_value2") or "").strip() or None
            clear_filters = bool(args.get("clear_filters", False))
            capture_all   = bool(args.get("capture_all", False))

            # capture_all: scroll through actual Excel view and send each page
            if capture_all and filter_col and filter_val:
                try:
                    pages = await asyncio.to_thread(
                        _capture_excel_scrolled_pages,
                        target, filter_col, filter_val, sheet, filter_col2, filter_val2,
                    )
                except Exception as e:
                    return {"ok": False, "reply": f"Filtr xatosi: {e}"}

                if not pages:
                    label = filter_val.upper()
                    if filter_val2:
                        label += f" + {filter_val2.upper()}"
                    return {"ok": False, "reply": f"{label} — hech qanday yozuv topilmadi."}

                total_pages = len(pages)
                sent = 0
                label = filter_val.upper()
                if filter_val2:
                    label += f" + {filter_val2.upper()}"
                for i, img_path in enumerate(pages):
                    caption = f"📊 {label} — {i+1}/{total_pages}  |  {target.name}"
                    res = await _send_document(img_path, caption)
                    if res.get("ok"):
                        sent += 1
                if sent == 0:
                    return {"ok": False, "reply": "Rasmlar yuborishda xato."}
                return {
                    "ok": True,
                    "reply": f"📊 {label} filtridagi barcha o'quvchilar {total_pages} ta rasm sifatida yuborildi.",
                }

            try:
                img_path = await asyncio.to_thread(
                    _capture_file_window, target,
                    sheet, filter_col, filter_val, clear_filters,
                    filter_col2, filter_val2,
                )
            except Exception as e:
                return {"ok": False, "reply": f"Fayl oynasi suratga olinmadi: {e}"}
            result = await _send_document(img_path, f"📄 {target.name}")
            if not result["ok"]:
                return result
            return {"ok": True, "reply": f"📄 {target.name} yuborildi."}

        # ── Plain screen capture ──────────────────────────────────────────────
        monitor = int(args.get("monitor") or 0)
        try:
            img_path = await asyncio.to_thread(_take_screenshot, monitor)
        except Exception as e:
            return {"ok": False, "reply": f"Screenshot failed: {e}"}
        result = await _send_document(img_path, "📸 Screenshot")
        if not result["ok"]:
            return result
        return {"ok": True, "reply": "Screenshot yuborildi."}
