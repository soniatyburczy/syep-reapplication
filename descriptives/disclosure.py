"""
disclosure.py -- make provider-level outputs safe to publish.

Run this after the model and descriptive scripts, before committing:

    python descriptives/disclosure.py

Provider organizations are pseudonymized because this repository is meant to
demonstrate methods, not to rank named contractors. Swapping names for labels
is not enough on its own: a provider's size, borough mix, or interval width
can identify it to anyone who knows the program. So this script also coarsens
the fields that act as fingerprints.

What it does to the public outputs in results/:

1. Pseudonyms are assigned in random order ("Provider 01" is NOT the largest).
   The key is written to the private data directory and reused on later runs,
   so labels stay stable across reruns.
2. Exact counts (n, people, returners) are replaced by a size band.
3. Rates and adjusted excess are rounded to whole percentage points, so the
   unlabeled caterpillar plot cannot be matched row-for-row to the table.
4. Confidence intervals, per-provider composition (age, hours, no-show share)
   and fixed-effect odds ratios are dropped from the public tables. Whether a
   provider's interval excludes zero is kept as a yes/no flag.
5. Any remaining real provider name anywhere in results/ is replaced, and the
   script fails loudly if one survives.

The full-precision tables stay in the private data directory for internal use.
"""

from __future__ import annotations

import random
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root
import paths

KEY_PATH = paths.TO_USE / "provider_pseudonym_key.csv"
PRIVATE_COPY = paths.TO_USE / "provider_tables_full_precision"

RETURN_BY_PROVIDER = paths.DESC_RESULTS / "return_by_provider.csv"
PROVIDER_SUMMARY = paths.MODEL_RESULTS / "provider_summary.csv"
PROVIDER_LOG = paths.MODEL_RESULTS / "provider_analysis_log.txt"
DESCRIPTIVES_MD = paths.DESC_RESULTS / "descriptives.md"

SIZE_BINS = [0, 999, 2499, float("inf")]
SIZE_LABELS = ["under 1,000", "1,000-2,499", "2,500+"]
UNRECORDED = "(provider unrecorded)"
PSEUDONYM = re.compile(r"^Provider \d{2}$")


def _is_missing(name) -> bool:
    return (pd.isna(name) or name == UNRECORDED
            or str(name).strip().lower() in {"", "nan", "none"})


def size_band(n: pd.Series) -> pd.Series:
    return pd.cut(n, bins=SIZE_BINS, labels=SIZE_LABELS).astype(str)


def load_or_build_key(names: set[str]) -> dict[str, str]:
    """Stable random pseudonyms; new providers are appended, never reshuffled."""
    key: dict[str, str] = {}
    if KEY_PATH.exists():
        k = pd.read_csv(KEY_PATH)
        key = dict(zip(k["provider"], k["pseudonym"]))

    new = sorted(n for n in names if n not in key and not PSEUDONYM.match(n))
    if new:
        used = {int(p.split()[-1]) for p in key.values()}
        free = [i for i in range(1, len(key) + len(new) + 1) if i not in used]
        random.SystemRandom().shuffle(free)
        for name, i in zip(new, free):
            key[name] = f"Provider {i:02d}"
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"pseudonym": list(key.values()),
                      "provider": list(key.keys())}).to_csv(KEY_PATH, index=False)
        print(f"pseudonym key: {len(key)} providers -> {KEY_PATH} (private)")
    return key


def _label(name, key) -> str:
    return UNRECORDED if _is_missing(name) else key.get(name, name)


def _stash(path: Path) -> None:
    """Keep the full-precision file privately before overwriting it."""
    PRIVATE_COPY.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, PRIVATE_COPY / path.name)


def public_return_by_provider(df: pd.DataFrame, key) -> pd.DataFrame:
    out = pd.DataFrame({
        "provider": [_label(p, key) for p in df["provider"]],
        "size_band": size_band(df["n"]),
        "return_rate_pct": (100 * df["rate"]).round(0).astype(int),
    })
    named = out[out.provider != UNRECORDED].sort_values("provider")
    return pd.concat([named, out[out.provider == UNRECORDED]], ignore_index=True)


def public_provider_summary(df: pd.DataFrame, key) -> pd.DataFrame:
    out = pd.DataFrame({
        "provider": [_label(p, key) for p in df["provider"]],
        "size_band": size_band(df["n"]),
        "raw_return_rate_pct": (100 * df["raw_rate"]).round(0).astype(int),
        "adjusted_excess_pp": df["excess_pp"].round(0).astype(int),
        "interval_excludes_zero": df["separates"].astype(bool),
        "rank_raw": df["rank_raw"].astype(int),
        "rank_adjusted": df["rank_adj"].astype(int),
        "rank_shift": df["rank_shift"].astype(int),
    })
    return out.sort_values("provider", ignore_index=True)


def scrub_log(text: str, key) -> str:
    # The reference provider is named with its exact size; describe it instead.
    text = re.sub(r"reference provider = .*", "reference provider = the largest provider", text)
    # Exact min/median/max provider sizes: report the banding instead.
    text = re.sub(r"size: min=.*", "size: banded in provider_summary.csv (under 1,000 / 1,000-2,499 / 2,500+)", text)
    # The rank-mover table repeats exact n and raw rate; point to the public table.
    text = re.sub(
        r"(=== 6\. BIGGEST RANK MOVERS.*?===\n)(.*?)(?=\n\S*wrote |\Z)",
        lambda m: m.group(1) + "See provider_summary.csv (rank_raw, rank_adjusted, rank_shift).\n",
        text, flags=re.S)
    return text


def replace_names(text: str, key) -> str:
    for name in sorted(key, key=len, reverse=True):
        text = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", key[name], text)
    return text


def rewrite_markdown_section(md: str, table: pd.DataFrame) -> str:
    head = "## Return rate by provider"
    if head not in md:
        return md
    start = md.index(head)
    nxt = md.find("\n## ", start + len(head))
    end = len(md) if nxt == -1 else nxt
    body = (f"{head}\n\nProviders are pseudonymized in random order; sizes are banded and "
            f"rates rounded to whole percentage points. See `descriptives/disclosure.py`.\n\n"
            f"{table.to_markdown(index=False)}\n")
    return md[:start] + body + md[end:]


def main() -> None:
    rbp = pd.read_csv(RETURN_BY_PROVIDER, encoding="utf-8-sig")
    summ = pd.read_csv(PROVIDER_SUMMARY) if PROVIDER_SUMMARY.exists() else None

    names = {p for p in rbp["provider"] if not _is_missing(p)}
    if summ is not None:
        names |= {p for p in summ["provider"] if not _is_missing(p)}
    key = load_or_build_key(names)

    if "size_band" not in rbp.columns:
        _stash(RETURN_BY_PROVIDER)
        pub = public_return_by_provider(rbp, key)
        pub.to_csv(RETURN_BY_PROVIDER, index=False, encoding="utf-8-sig")
        print(f"wrote {RETURN_BY_PROVIDER}")
        if DESCRIPTIVES_MD.exists():
            DESCRIPTIVES_MD.write_text(
                rewrite_markdown_section(DESCRIPTIVES_MD.read_text(encoding="utf-8"), pub),
                encoding="utf-8")

    if summ is not None and "size_band" not in summ.columns:
        _stash(PROVIDER_SUMMARY)
        public_provider_summary(summ, key).to_csv(PROVIDER_SUMMARY, index=False)
        print(f"wrote {PROVIDER_SUMMARY}")

    if PROVIDER_LOG.exists():
        PROVIDER_LOG.write_text(scrub_log(PROVIDER_LOG.read_text(encoding="utf-8"), key),
                                encoding="utf-8")

    # Safety net: no real provider name may survive anywhere in results/.
    leaks = []
    for f in paths.RESULTS.rglob("*"):
        if f.is_file() and f.suffix in {".csv", ".md", ".txt"}:
            t = f.read_text(encoding="utf-8", errors="ignore")
            t2 = replace_names(t, key)
            if t2 != t:
                f.write_text(t2, encoding="utf-8")
            leaks += [(f, n) for n in key if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", t2)]
    if leaks:
        raise RuntimeError(f"real provider names remain in results/: {leaks[:5]}")
    print("disclosure check passed: no provider names in results/")


if __name__ == "__main__":
    main()
