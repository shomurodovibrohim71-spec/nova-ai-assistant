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


def _find_col(df, name: str) -> str | None:
    """Case-insensitive partial column name match."""
    name_l = name.lower()
    for col in df.columns:
        if name_l in col.lower():
            return col
    return None


def _filter_excel(
    file_path: str,
    filter_col: str,
    filter_val: str,
    sheet: str | None = None,
    filter_col2: str | None = None,
    filter_val2: str | None = None,
) -> tuple[Any, str]:
    """Read Excel file and filter rows. Returns (DataFrame, sheet_name)."""
    import pandas as pd

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    xl = pd.ExcelFile(path)
    sheet_name = sheet or xl.sheet_names[0]
    if sheet:
        for s in xl.sheet_names:
            if sheet.lower() in s.lower():
                sheet_name = s
                break

    df = xl.parse(sheet_name, header=None)

    # Find header row — first row with 3+ non-null values
    header_row = 0
    for i, row in df.iterrows():
        if len(row.dropna()) >= 3:
            header_row = i
            break

    df = xl.parse(sheet_name, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # First filter
    matched_col = _find_col(df, filter_col)
    if matched_col is None:
        raise ValueError(f"Column '{filter_col}' not found. Available: {list(df.columns)[:10]}")
    filtered = df[df[matched_col].astype(str).str.upper().str.strip() == filter_val.upper().strip()]

    # Second filter (optional)
    if filter_col2 and filter_val2:
        matched_col2 = _find_col(filtered, filter_col2)
        if matched_col2 is None:
            raise ValueError(f"Column '{filter_col2}' not found. Available: {list(filtered.columns)[:10]}")
        filtered = filtered[filtered[matched_col2].astype(str).str.upper().str.strip() == filter_val2.upper().strip()]

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
    description = "Filter rows in an Excel file and send the result as a table image or .xlsx file to Telegram."
    tool_description = (
        "Open an Excel file, filter rows by one or two column values, and send results to Telegram.\n"
        "Use filter_column2 + filter_value2 for AND filtering (e.g. STATUS=UNP AND GROUP=MWF).\n"
        "Set send_file=true when user asks to send/save the filtered file (not just view it).\n"
        "Examples:\n"
        "  'UNP oquvchilarni ko'rsat' → filter_column='STATUS', filter_value='UNP'\n"
        "  'MWF va UNP oquvchilarni faylini yubor' → filter_column='STATUS', filter_value='UNP', filter_column2='GROUP', filter_value2='MWF', send_file=true\n"
        "  'filter qilib faylni saqlab yubor' → send_file=true"
    )
    patterns = []  # always routed through Claude LLM for flexible natural language parsing
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
            "filter_column2": {
                "type": "string",
                "description": "Second column to filter on (optional, for AND filtering).",
            },
            "filter_value2": {
                "type": "string",
                "description": "Second filter value (optional, used with filter_column2).",
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
        import re as _re

        # Extract .xlsx file path
        file_m = _re.search(r'[\w\s\-]+\.xlsx?', text, _re.IGNORECASE)
        if not file_m:
            return {"ok": False, "reply": "Excel fayl yo'li topilmadi."}
        file_path = file_m.group(0).strip()

        # Extract key=value pairs like STATUS=UNP, GROUP=MWF
        pairs = _re.findall(r'(\w+)\s*=\s*(\w+)', text, _re.IGNORECASE)

        filter_col = filter_val = filter_col2 = filter_val2 = ""
        for i, (col, val) in enumerate(pairs):
            if i == 0:
                filter_col, filter_val = col, val
            elif i == 1:
                filter_col2, filter_val2 = col, val

        if not filter_col:
            return {"ok": False, "reply": "Filter ustuni topilmadi (masalan STATUS=UNP)."}

        send_file = bool(_re.search(
            r'fayl\w*\s*(yubor|saql)|yubor\w*\s*fayl|send\s*file|filtered\s*file',
            text, _re.IGNORECASE
        ))

        return await self.run_tool({
            "file": file_path,
            "filter_column": filter_col,
            "filter_value": filter_val,
            "filter_column2": filter_col2 or None,
            "filter_value2": filter_val2 or None,
            "send_file": send_file,
        })

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        file_path    = (args.get("file") or "").strip()
        filter_col   = (args.get("filter_column") or "").strip()
        filter_val   = (args.get("filter_value") or "").strip()
        filter_col2  = (args.get("filter_column2") or "").strip() or None
        filter_val2  = (args.get("filter_value2") or "").strip() or None
        sheet        = (args.get("sheet") or "").strip() or None
        send_file    = bool(args.get("send_file", False))

        if not file_path or not filter_col or not filter_val:
            return {"ok": False, "reply": "Need: file path, filter_column, and filter_value."}

        try:
            df, sheet_name = await asyncio.to_thread(
                _filter_excel, file_path, filter_col, filter_val, sheet, filter_col2, filter_val2
            )
        except FileNotFoundError as e:
            return {"ok": False, "reply": str(e)}
        except ValueError as e:
            return {"ok": False, "reply": str(e)}
        except Exception as e:
            return {"ok": False, "reply": f"Excel read error: {e}"}

        count      = len(df) - 1 if "#" in df.columns else len(df)
        filter_tag = filter_val.upper()
        if filter_col2 and filter_val2:
            filter_tag += f" + {filter_val2.upper()}"
        title   = f"{filter_tag} o'quvchilar — {count} ta  |  {Path(file_path).name}  [{sheet_name}]"
        caption = f"📊 <b>{filter_tag}</b>: {count} ta o'quvchi\n📁 {Path(file_path).name}"

        # ── 1. Rasm yuborish (faqat fayl so'ralmagan bo'lsa) ─────────────────
        if not send_file:
            img_path = await asyncio.to_thread(_render_table_image, df, title)
            try:
                img_result = await _send_photo(img_path, caption)
            finally:
                img_path.unlink(missing_ok=True)
            if not img_result.get("ok"):
                return img_result
            return {"ok": True, "reply": f"✅ {filter_tag} — {count} ta o'quvchi — jadval rasmi yuborildi.", "count": count, "sheet": sheet_name}

        # ── 2. Filtrlangan Excel fayl yuborish ────────────────────────────────
        stem = Path(file_path).stem
        xlsx_name = f"{filter_tag.replace(' ', '_')}_{stem}.xlsx"
        xlsx_path = Path(tempfile.mktemp(suffix=f"_{xlsx_name}"))
        try:
            def _write_xlsx():
                df.to_excel(str(xlsx_path), index=False, engine="openpyxl")

            await asyncio.to_thread(_write_xlsx)
            file_caption = (
                f"📎 <b>{filter_tag} — filtrlangan fayl</b>\n"
                f"{count} ta qator  |  {Path(file_path).name}"
            )
            file_result = await _send_document(xlsx_path, file_caption)
            if not file_result.get("ok"):
                return file_result
        except Exception as e:
            return {"ok": False, "reply": f"Fayl yaratishda xato: {e}"}
        finally:
            xlsx_path.unlink(missing_ok=True)

        return {"ok": True, "reply": f"✅ {filter_tag} — {count} ta o'quvchi filtrlangan fayl yuborildi.", "count": count, "sheet": sheet_name}
