"""
Excel reference reconciliation for ARS_LISTING_WORKING.

Compares the per-OPT (WERKS × MAJ_CAT × GEN_ART_NUMBER × CLR)
ALLOC_QTY / HOLD_QTY produced by ARS against the equivalent values
from the legacy 22-sheet Excel allocation file. Produces:

  - reconciliation_<MAJ_CAT>.csv  — every OPT with both sides + delta
  - console summary               — match %, top deltas

WHY EXCEL FIRST, NOT XLSB:
  The legacy files are .xlsb (binary Excel) at 80–90 MB. Native Python
  parsing of large xlsb is fragile. Easiest path: open the file once in
  Excel, save the relevant sheet as .xlsx or .csv, and feed that here.

USAGE:
  python scripts/excel_reconciliation.py \\
    --excel ~/Downloads/DH24-MENS-M_TEES_HS-OPTION_LISTING.xlsx \\
    --sheet "ST-OPTION" \\
    --maj-cat M_TEES_HS \\
    --werks-col WERKS \\
    --gen-art-col GEN_ART_NUMBER \\
    --clr-col CLR \\
    --alloc-col DISP_Q \\
    --hold-col HOLD_QTY

  Connects to the SQL DB using DB_SERVER / DB_NAME / DB_USERNAME /
  DB_PASSWORD env vars (same as the determinism test). Override with
  --sql-conn 'mssql+pyodbc://...' if needed.

EXIT CODES:
  0 — match within tolerance (default 5 units per OPT)
  1 — drift exceeds tolerance for at least one OPT
  2 — usage / connection error
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Lazy imports so --help works even if pandas/sqlalchemy are missing
def _load_excel(path: Path, sheet: str | None) -> "pd.DataFrame":
    import pandas as pd
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, low_memory=False)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return pd.read_excel(path, sheet_name=sheet or 0)
    if path.suffix.lower() == ".xlsb":
        try:
            import pyxlsb  # noqa: F401
        except ImportError:
            sys.exit(
                "ERROR: reading .xlsb requires pyxlsb. Install with:\n"
                "    pip install pyxlsb\n"
                "Or save the workbook as .xlsx in Excel first (recommended for"
                " large files)."
            )
        return pd.read_excel(path, sheet_name=sheet or 0, engine="pyxlsb")
    sys.exit(f"ERROR: unsupported extension: {path.suffix}")


def _load_sql(maj_cat: str, conn_url: str) -> "pd.DataFrame":
    import pandas as pd
    from sqlalchemy import create_engine, text
    eng = create_engine(conn_url)
    sql = text("""
        SELECT
            UPPER(LTRIM(RTRIM(WERKS)))               AS WERKS,
            UPPER(LTRIM(RTRIM(MAJ_CAT)))             AS MAJ_CAT,
            TRY_CAST(GEN_ART_NUMBER AS BIGINT)       AS GEN_ART_NUMBER,
            UPPER(LTRIM(RTRIM(ISNULL(CLR, ''))))     AS CLR,
            SUM(ISNULL(ALLOC_QTY, 0))                AS ARS_ALLOC,
            SUM(ISNULL(HOLD_QTY, 0))                 AS ARS_HOLD,
            MAX(OPT_TYPE)                            AS OPT_TYPE,
            MAX(ALLOC_STATUS)                        AS ALLOC_STATUS
        FROM ARS_LISTING_WORKING WITH (NOLOCK)
        WHERE UPPER(LTRIM(RTRIM(MAJ_CAT))) = :mc
        GROUP BY WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR
    """)
    with eng.connect() as conn:
        df = pd.read_sql(sql, conn, params={"mc": maj_cat.upper()})
    return df


def _normalize(df, werks_col, gen_col, clr_col, alloc_col, hold_col):
    import pandas as pd
    out = pd.DataFrame()
    out["WERKS"] = df[werks_col].astype(str).str.strip().str.upper()
    out["GEN_ART_NUMBER"] = pd.to_numeric(df[gen_col], errors="coerce").astype("Int64")
    out["CLR"] = df[clr_col].astype(str).str.strip().str.upper().fillna("")
    out["XLS_ALLOC"] = pd.to_numeric(df[alloc_col], errors="coerce").fillna(0)
    if hold_col and hold_col in df.columns:
        out["XLS_HOLD"] = pd.to_numeric(df[hold_col], errors="coerce").fillna(0)
    else:
        out["XLS_HOLD"] = 0
    out = out.dropna(subset=["GEN_ART_NUMBER"])
    return out.groupby(
        ["WERKS", "GEN_ART_NUMBER", "CLR"], as_index=False
    ).agg(XLS_ALLOC=("XLS_ALLOC", "sum"), XLS_HOLD=("XLS_HOLD", "sum"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--excel", required=True, type=Path,
                   help="Path to .xlsx/.csv (or .xlsb if pyxlsb installed)")
    p.add_argument("--sheet", default=None, help="Sheet name (xlsx/xlsb only)")
    p.add_argument("--maj-cat", required=True, help="MAJ_CAT to reconcile")
    p.add_argument("--werks-col", default="WERKS")
    p.add_argument("--gen-art-col", default="GEN_ART_NUMBER")
    p.add_argument("--clr-col", default="CLR")
    p.add_argument("--alloc-col", required=True,
                   help="Excel column with allocated qty (e.g. DISP_Q, ALLOC_QTY)")
    p.add_argument("--hold-col", default=None, help="Optional hold-qty column")
    p.add_argument("--out-dir", default=".", type=Path)
    p.add_argument("--tolerance", type=float, default=5.0,
                   help="Max abs delta per OPT considered a match (default 5)")
    p.add_argument("--sql-conn", default=None,
                   help="SQLAlchemy URL. Default: build from DB_* env vars.")
    args = p.parse_args()

    if not args.excel.exists():
        print(f"ERROR: file not found: {args.excel}", file=sys.stderr)
        return 2

    if args.sql_conn:
        conn_url = args.sql_conn
    else:
        srv = os.environ.get("DB_SERVER")
        usr = os.environ.get("DB_USERNAME")
        pwd = os.environ.get("DB_PASSWORD")
        db = os.environ.get("DATA_DB_NAME") or os.environ.get("DB_NAME")
        drv = os.environ.get("DB_DRIVER", "ODBC Driver 18 for SQL Server")
        if not all([srv, usr, pwd, db]):
            print(
                "ERROR: provide --sql-conn or set DB_SERVER, DB_USERNAME, "
                "DB_PASSWORD, DATA_DB_NAME (or DB_NAME) env vars.",
                file=sys.stderr,
            )
            return 2
        from urllib.parse import quote_plus
        conn_url = (
            f"mssql+pyodbc://{usr}:{quote_plus(pwd)}@{srv}/{db}"
            f"?driver={quote_plus(drv)}&TrustServerCertificate=yes"
        )

    print(f"Loading Excel: {args.excel} (sheet={args.sheet})...")
    xls_raw = _load_excel(args.excel, args.sheet)
    print(f"  {len(xls_raw):,} rows in Excel")

    missing = [c for c in (args.werks_col, args.gen_art_col, args.clr_col,
                            args.alloc_col)
               if c not in xls_raw.columns]
    if missing:
        print(f"ERROR: Excel sheet missing columns: {missing}", file=sys.stderr)
        print(f"  Available columns: {list(xls_raw.columns)[:30]}...",
              file=sys.stderr)
        return 2

    xls = _normalize(xls_raw, args.werks_col, args.gen_art_col,
                     args.clr_col, args.alloc_col, args.hold_col)
    print(f"  {len(xls):,} unique OPTs in Excel after group-by")

    print(f"Loading SQL: ARS_LISTING_WORKING for MAJ_CAT={args.maj_cat}...")
    try:
        ars = _load_sql(args.maj_cat, conn_url)
    except Exception as e:
        print(f"ERROR connecting to SQL: {e}", file=sys.stderr)
        return 2
    print(f"  {len(ars):,} OPTs in ARS")

    # Outer join to find matches and orphans on either side
    import pandas as pd
    merged = pd.merge(
        ars, xls, on=["WERKS", "GEN_ART_NUMBER", "CLR"], how="outer",
        indicator=True,
    )
    merged["XLS_ALLOC"] = merged["XLS_ALLOC"].fillna(0)
    merged["XLS_HOLD"] = merged["XLS_HOLD"].fillna(0)
    merged["ARS_ALLOC"] = merged["ARS_ALLOC"].fillna(0)
    merged["ARS_HOLD"] = merged["ARS_HOLD"].fillna(0)
    merged["DELTA_ALLOC"] = merged["ARS_ALLOC"] - merged["XLS_ALLOC"]
    merged["DELTA_HOLD"] = merged["ARS_HOLD"] - merged["XLS_HOLD"]
    merged["ABS_DELTA"] = merged["DELTA_ALLOC"].abs() + merged["DELTA_HOLD"].abs()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = args.out_dir / f"reconciliation_{args.maj_cat}.csv"
    merged.sort_values("ABS_DELTA", ascending=False).to_csv(out_csv, index=False)

    # Summary
    n_total = len(merged)
    n_only_ars = (merged["_merge"] == "left_only").sum()
    n_only_xls = (merged["_merge"] == "right_only").sum()
    n_both = (merged["_merge"] == "both").sum()
    within_tol = (merged["ABS_DELTA"] <= args.tolerance).sum()

    print()
    print("=" * 60)
    print(f"RECONCILIATION SUMMARY  ({args.maj_cat})")
    print("=" * 60)
    print(f"  Total OPTs (union)     : {n_total:>10,}")
    print(f"  In both                : {n_both:>10,}")
    print(f"  ARS only (Excel miss)  : {n_only_ars:>10,}")
    print(f"  Excel only (ARS miss)  : {n_only_xls:>10,}")
    print(f"  Within tolerance ({args.tolerance:g}) : {within_tol:>10,}"
          f"  ({within_tol/n_total*100 if n_total else 0:.1f}%)")
    print(f"  Drift > tolerance      : {n_total - within_tol:>10,}")
    print()
    print(f"Per-OPT detail saved to: {out_csv}")
    print()
    if n_total - within_tol > 0:
        print("Top 10 worst deltas:")
        cols = ["WERKS", "GEN_ART_NUMBER", "CLR", "OPT_TYPE",
                "ARS_ALLOC", "XLS_ALLOC", "DELTA_ALLOC",
                "ARS_HOLD", "XLS_HOLD", "DELTA_HOLD", "_merge"]
        print(merged.sort_values("ABS_DELTA", ascending=False)
                    .head(10)[cols].to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
