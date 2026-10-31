"""A minimal Excel workbook writer (standard library only): one sheet and one Excel table per name, which is what Power BI imports.

Numbers are written as numbers and ISO times as real date-times, so Power BI types the columns correctly.
"""
import io
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

EPOCH = datetime(1899, 12, 30, tzinfo=timezone.utc)
TIME_COLUMN = re.compile(r"(^|_)(at|started|ended)$|^(saved_at|recorded_at|rated_at)$")


def _col(n: int) -> str:
    s = ""
    while True:
        n, r = divmod(n, 26)
        s = chr(65 + r) + s
        if n == 0:
            return s
        n -= 1


def _serial(text) -> float | None:
    """An ISO date-time as an Excel serial number (UTC), or None when it is not one."""
    try:
        d = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (d - EPOCH).total_seconds() / 86400


def _cell(ref: str, value, as_time: bool) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    if as_time and (serial := _serial(value)) is not None:
        return f'<c r="{ref}" s="1"><v>{serial:.8f}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'


def _sheet(columns: list, rows: list, table_rid: str) -> str:
    time_cols = [bool(TIME_COLUMN.search(c)) for c in columns]
    body = rows or [[None] * len(columns)]                       # an Excel table needs at least one data row
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
           'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><cols><col min="1" max="%d" width="18" customWidth="1"/></cols><sheetData>' % len(columns)]
    out.append('<row r="1">' + "".join(f'<c r="{_col(i)}1" t="inlineStr"><is><t>{escape(c)}</t></is></c>' for i, c in enumerate(columns)) + "</row>")
    for n, row in enumerate(body, start=2):
        out.append(f'<row r="{n}">' + "".join(_cell(f"{_col(i)}{n}", v, time_cols[i]) for i, v in enumerate(row)) + "</row>")
    out.append(f'</sheetData><tableParts count="1"><tablePart r:id="{table_rid}"/></tableParts></worksheet>')
    return "".join(out)


def _table(tid: int, name: str, columns: list, n_rows: int) -> str:
    ref = f"A1:{_col(len(columns) - 1)}{max(n_rows, 1) + 1}"
    cols = "".join(f'<tableColumn id="{i + 1}" name="{escape(c)}"/>' for i, c in enumerate(columns))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="{tid}" name="{name}" displayName="{name}" ref="{ref}" totalsRowShown="0">'
            f'<autoFilter ref="{ref}"/><tableColumns count="{len(columns)}">{cols}</tableColumns>'
            '<tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/></table>')


STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd\\ hh:mm:ss"/></numFmts>'
          '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill>'
          '<fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
          '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
          '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
          '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
          '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


# PUBLIC_INTERFACE
def workbook_bytes(tables: dict) -> bytes:
    """``tables`` = {name: (columns, rows)}. One sheet and one Excel table per name."""
    names = list(tables)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    wb_sheets, wb_rels = [], ['<Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/styles.xml", STYLES)
        for i, name in enumerate(names, start=1):
            columns, rows = tables[name]
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet(columns, rows, "rId1"))
            z.writestr(f"xl/worksheets/_rels/sheet{i}.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table{i}.xml"/></Relationships>')
            z.writestr(f"xl/tables/table{i}.xml", _table(i, name, columns, len(rows)))
            ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      f'<Override PartName="/xl/tables/table{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>')
            wb_sheets.append(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>')
            wb_rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        z.writestr("[Content_Types].xml", "".join(ct) + "</Types>")
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(wb_sheets) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(wb_rels) + "</Relationships>")
    return buf.getvalue()
