"""Excel query skill — filter rows and send result as a table image to Telegram."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from ...config import settings
from ..base import Skill

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _token() -> str | None:
    return settings.telegram_bot_token


def _chat() -> str | None:
    return settings.telegram_chat_id


def _render_table_image(df, title: str = "") -> Path:
    """Render a pandas DataFrame as a PNG image and return the path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    if df.empty:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "No data found", ha="center", va="center", fontsize=14)
        ax.axis("off")
        tmp = Path(tempfile.mktemp(suffix=".png"))
        fig.savefig(str(tmp), dpi=120, bbox_inches="tight")
        plt.close(fig)
        return tmp

    # Limit columns width for display
    display_df = df.copy()
    for col in display_df.columns:
        display_df[col] = display_df[col].astype(str).str[:30]

    n_rows, n_cols = display_df.shape
    fig_w = max(8, n_cols * 1.8)
    fig_h = max(2, n_rows * 0.45 + 1.5)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")

    if title:
        fig.suptitle(title, fontsize=13, fontweight="bold", y=0.98)

    col_labels = list(display_df.columns)
    cell_data = display_df.values.tolist()

    tbl = ax.table(
        cellText=cell_data,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.auto_set_column_width(range(n_cols))

    # Style header
    for j in range(n_cols):
        cell = tbl[0, j]
        cell.set_facecolor("#2C3E50")
        cell.set_text_props(color="white", fontweight="bold")

    # Alternating row colors
    for i in range(1, n_rows + 1):
        color = "#F2F2F2" if i % 2 == 0 else "#FFFFFF"
        for j in range(n_cols):
            tbl[i, j].set_facecolor(color)

    tmp = Path(tempfile.mktemp(suffix=".png"))
    fig.savefig(str(tmp), dpi=130, bbox_inches="tight", facecolor="#FAFAFA")
    plt.close(fig)
    return tmp


async def _send_document(file_path: Path, caption: str) -> dict[str, Any]:
    import httpx
    token = _token()
    chat_id = _chat()
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram not configured."}
    url = f"{TELEGRAM_API.format(token=token)}/sendDocument"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with file_path.open("rb") as fh:
                resp = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"document": (file_path.name, fh)},
                )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "reply": f"Telegram error: {data.get('description')}"}
    except Exception as e:
        return {"ok": False, "reply": f"Send failed: {e}"}
    return {"ok": True}


async def _send_photo(img_path: Path, caption: str) -> dict[str, Any]:
    import httpx
    token = _token()
    chat_id = _chat()
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram not configured."}
    url = f"{TELEGRAM_API.format(token=token)}/sendPhoto"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with img_path.open("rb") as fh:
                resp = await client.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": ("table.png", fh, "image/png")},
                )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "reply": f"Telegram error: {data.get('description')}"}
    except Exception as e:
        return {"ok": False, "reply": f"Send failed: {e}"}
    return {"ok": True}


def _filter_excel(file_path: str, filter_col: str, filter_val: str, sheet: str | None = None) -> tuple[Any, str]:
    """Read Excel file and filter rows. Returns (DataFrame, sheet_name)."""
    import pandas as pd

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    xl = pd.ExcelFile(path)
    sheet_name = sheet or xl.sheet_names[0]
    # Try to find the requested sheet by partial name match
    if sheet:
        for s in xl.sheet_names:
            if sheet.lower() in s.lower():
                sheet_name = s
                break

    df = xl.parse(sheet_name, header=None)

    # Find header row — first row that has more than 3 non-null string values
    header_row = 0
    for i, row in df.iterrows():
        non_null = row.dropna()
        if len(non_null) >= 3:
            header_row = i
            break

    df = xl.parse(sheet_name, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Find the column matching filter_col (partial, case-insensitive)
    matched_col = None
    for col in df.columns:
        if filter_col.lower() in col.lower():
            matched_col = col
            break

    if matched_col is None:
        # Try searching all cell values in first few rows
        raise ValueError(
            f"Column '{filter_col}' not found. Available: {list(df.columns)[:10]}"
        )

    # Filter rows
    filtered = df[df[matched_col].astype(str).str.upper().str.strip() == filter_val.upper().strip()]

    # Pick the most useful columns to show
    keep_cols = []
    priority_keywords = ["name", "student", "ism", "oquvchi", "#", "paid", "to be", "unpaid", "status", "group"]
    for kw in priority_keywords:
        for col in filtered.columns:
            if kw.lower() in col.lower() and col not in keep_cols:
                keep_cols.append(col)
                if len(keep_cols) >= 6:
                    break
        if len(keep_cols) >= 6:
            break

    if not keep_cols:
        keep_cols = list(filtered.columns[:6])

    result = filtered[keep_cols].reset_index(drop=True)
    result.index = result.index + 1  # start numbering from 1
    result.index.name = "#"
    result = result.reset_index()

    return result, sheet_name


class ExcelQuerySkill(Skill):
    name = "excel_query"
    description = "Filter rows in an Excel file and send the result as a table image to Telegram."
    tool_description = (
        "Open an Excel file, filter rows by a column value (e.g. payment status = 'UNP'), "
        "and send a screenshot of the filtered table to Telegram."
    )
    patterns = [
        # Skip if user also says "screenshot" — that goes to the screenshot skill instead
        r"^(?!.*screenshot).*(?P<file>[^\s]+\.xlsx?)\s+.*?(?P<col>status|holat|payment|paid|unpaid)\s*[=:]\s*(?P<val>\w+)",
        r"^(?!.*screenshot).*(?P<val>UNP|PAID|unpaid|paid)\s+(?:status|holat).*?(?P<file>[^\s]+\.xlsx?)",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Full path to the Excel file.",
            },
            "filter_column": {
                "type": "string",
                "description": "Column name to filter on (e.g. 'PAYMENT STATUS', 'status').",
            },
            "filter_value": {
                "type": "string",
                "description": "Value to filter for (e.g. 'UNP', 'PAID').",
            },
            "sheet": {
                "type": "string",
                "description": "Sheet name (optional, defaults to first sheet).",
            },
            "send_file": {
                "type": "boolean",
                "description": "If true, also send filtered data as a .xlsx file. Default false (only image).",
                "default": False,
            },
        },
        "required": ["file", "filter_column", "filter_value"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return {"ok": False, "reply": "Please use the tool form: specify file path, column, and value."}

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        file_path = (args.get("file") or "").strip()
        filter_col = (args.get("filter_column") or "").strip()
        filter_val = (args.get("filter_value") or "").strip()
        sheet = (args.get("sheet") or "").strip() or None
        send_file = bool(args.get("send_file", False))

        if not file_path or not filter_col or not filter_val:
            return {"ok": False, "reply": "Need: file path, filter_column, and filter_value."}

        try:
            df, sheet_name = await asyncio.to_thread(
                _filter_excel, file_path, filter_col, filter_val, sheet
            )
        except FileNotFoundError as e:
            return {"ok": False, "reply": str(e)}
        except ValueError as e:
            return {"ok": False, "reply": str(e)}
        except Exception as e:
            return {"ok": False, "reply": f"Excel read error: {e}"}

        count = len(df) - 1 if "#" in df.columns else len(df)
        title = f"{filter_val.upper()} o'quvchilar — {count} ta  |  {Path(file_path).name}  [{sheet_name}]"
        caption = f"📊 <b>{filter_val.upper()} status</b>: {count} ta o'quvchi\n📁 {Path(file_path).name}"

        img_path = await asyncio.to_thread(_render_table_image, df, title)
        try:
            result = await _send_photo(img_path, caption)
            if not result["ok"]:
                return result
        finally:
            img_path.unlink(missing_ok=True)

        if send_file:
            import pandas as pd
            xlsx_path = Path(tempfile.mktemp(suffix=f"_{filter_val.upper()}.xlsx"))
            try:
                await asyncio.to_thread(lambda: df.to_excel(str(xlsx_path), index=False))
                file_caption = f"📎 <b>{filter_val.upper()} — filtrlangan fayl</b>\n{count} ta qator  |  {Path(file_path).name}"
                file_result = await _send_document(xlsx_path, file_caption)
                if not file_result["ok"]:
                    return file_result
            finally:
                xlsx_path.unlink(missing_ok=True)

        reply = f"✅ {filter_val.upper()} statusdagi {count} ta o'quvchi"
        reply += " — rasm va fayl yuborildi." if send_file else " — jadval rasmi yuborildi."
        return {"ok": True, "reply": reply, "count": count, "sheet": sheet_name}
