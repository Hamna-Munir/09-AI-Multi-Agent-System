"""
agents/analyst_agent.py
The Analyst owns the company's OWN data. Its tools are the read-only database
queries and nothing else.

  resolve_scope()     work out WHICH month the question is about, and whether the data has it.
  analyze_internal()  deterministic: all numbers and findings are computed in
                      Python from tool results (no LLM), so they cannot be invented.
                      `focus` decides which findings are produced, so a narrow question gets a narrow answer:
                        full         overall revenue + regions + products + top 3 (the default)
                        top_products the best sellers, their share of revenue and how each one moved
                        products     which products moved most, and whether price or demand drove it
                        regions      overall revenue and every region
  test_factors()      takes external hypotheses from the Research Agent and checks
                      each against the company data. The LLM only judges "does this
                      data support the claim?"; the numbers it sees come from tools.
"""

import re
from typing import Dict, List, Optional, Tuple

from ..prompts import FACTOR_JUDGE_SYSTEM
from ..schemas import (Evidence, ExternalFactor, FactorCheck, FactorTestResult, FactorVerdict, Finding,
                       InternalAnalysis)
from ..tools import DATA_TOOLS
from .base import BaseAgent
from .. import config

# =============================================================================
# Month requests ("top products in August") -> which months the question names
# =============================================================================
MONTH_NUMBERS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
MONTH_LABELS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 7: "July",
                8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}
# "may" is also an ordinary verb, so it only counts as a month after one of these words, or before a year
_MAY_AS_MONTH_AFTER = {"in", "for", "of", "during", "since", "from", "to", "by", "until", "through", "last",
                       "this", "next", "and", "vs", "versus", "between", "than"}
_MONTH_WORD = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|apr|jun|jul|aug|sept|sep|oct|nov|dec)\b(?:\s+(?:of\s+)?(20\d{2}))?")
_ISO_MONTH = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b")
_YEAR = re.compile(r"\b(20\d{2})\b")


def parse_requested_months(question: str) -> List[Tuple[Optional[int], int]]:
    """Return [(year or None, month_number)] for every month the question names."""
    q = question.lower()
    found: List[Tuple[Optional[int], int]] = [(int(y), int(m)) for y, m in _ISO_MONTH.findall(q)]
    for match in _MONTH_WORD.finditer(q):
        word, year = match.group(1), match.group(2)
        if word == "may" and not year:
            before = q[:match.start()].split()
            if not before or before[-1] not in _MAY_AS_MONTH_AFTER:
                continue
        found.append((int(year) if year else None, MONTH_NUMBERS[word]))
    return found


def _join_names(names: List[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


# =============================================================================
# Number helpers
# =============================================================================
def pct_change(old: float, new: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100, 1)


def _s(value: Optional[float]) -> str:
    return f"{value:+.1f}%" if value is not None else "n/a"


def _pick(rows: List[dict], prev: Optional[str], latest: Optional[str]) -> Tuple[Optional[dict], Optional[dict]]:
    """The two rows to compare: the named months if given, otherwise the last two rows."""
    if prev and latest:
        by_month = {r["month"]: r for r in rows}
        return by_month.get(prev), by_month.get(latest)
    if len(rows) < 2:
        return None, None
    return rows[-2], rows[-1]


def _units_per_order(row: dict) -> Optional[float]:
    units, orders = row.get("units"), row.get("orders")
    return units / orders if units is not None and orders else None


def _trend(rows: List[dict], prev: Optional[str] = None, latest: Optional[str] = None) -> Optional[dict]:
    """Compare two months of one product's rows (the last two months unless prev/latest are given)."""
    a, b = _pick(rows, prev, latest)
    if a is None or b is None:
        return None
    per_a, per_b = _units_per_order(a), _units_per_order(b)
    return {"product": b["product"], "prev": a["month"], "latest": b["month"], "a": a, "b": b,
            "rev": pct_change(a["revenue"], b["revenue"]),
            "orders": pct_change(a["orders"], b["orders"]),
            "price": pct_change(a["avg_unit_price"], b["avg_unit_price"]),
            "basket": pct_change(per_a, per_b) if per_a is not None and per_b is not None else None}


def _product_detail(t: dict) -> str:
    a, b = t["a"], t["b"]
    return (f"{t['product']}: revenue {t['prev']} PKR {a['revenue']:,.0f} -> {t['latest']} PKR {b['revenue']:,.0f} "
            f"({_s(t['rev'])}); orders {a['orders']} -> {b['orders']} ({_s(t['orders'])}); "
            + (f"units {a['units']} -> {b['units']} ({_s(pct_change(a['units'], b['units']))}); "
               if "units" in a and "units" in b else "") +
            f"average unit price PKR {a['avg_unit_price']:,.0f} -> PKR {b['avg_unit_price']:,.0f} ({_s(t['price'])})")


def _label(t: dict) -> str:
    rev, orders, price = t["rev"], t["orders"], t["price"]
    if rev is None or orders is None or price is None:
        return "unclear"
    if abs(rev) < 10:
        return "small (under 10%)"
    if rev < -5:
        if abs(orders) < 10 and price < -10:
            return "price-driven (orders roughly stable while the average price fell)"
        if orders < -10:
            return "demand-driven (the number of orders fell)"
    if rev > 5:
        if orders > 10:
            return "volume-driven (more orders)"
        if price > 10:
            return "price-driven (the average price rose)"
    basket = t.get("basket")   # orders and price both steady: did each order hold more or fewer units?
    if (basket is not None and abs(orders) < 10 and abs(price) < 10 and abs(basket) >= 10
            and (basket > 0) == (rev > 0)):
        return f"quantity-driven (units per order {'rose' if basket > 0 else 'fell'})"
    return "mixed or unclear"


def _region_detail(region: str, rows: List[dict], prev: Optional[str] = None,
                   latest: Optional[str] = None) -> Optional[Tuple[str, Optional[float]]]:
    a, b = _pick(rows, prev, latest)
    if a is None or b is None:
        return None
    change = pct_change(a["revenue"], b["revenue"])
    return (f"{region} revenue: {a['month']} PKR {a['revenue']:,.0f} -> {b['month']} PKR {b['revenue']:,.0f} "
            f"({_s(change)}); orders {a['orders']} -> {b['orders']}"), change


class _Builder:
    def __init__(self):
        self.evidence: List[Evidence] = []
        self.findings: List[Finding] = []

    def add_evidence(self, detail: str) -> str:
        eid = f"E{len(self.evidence) + 1}"
        self.evidence.append(Evidence(id=eid, source="database", detail=detail))
        return eid

    def add_finding(self, statement: str, evidence_ids: List[str]) -> None:
        self.findings.append(Finding(id=f"F{len(self.findings) + 1}", statement=statement,
                                     evidence_ids=evidence_ids, produced_by="analyst"))


class AnalystAgent(BaseAgent):
    name = "analyst"

    def __init__(self, llm=None, tools=None):
        super().__init__(llm, DATA_TOOLS if tools is None else tools)

    # ------------------------------------------------------------------ which month is the question about?
    def resolve_scope(self, question: str) -> dict:
        """Return {"month": the month to analyse, "available": [...], "note": a warning or None}.

        A question about a month the data does not cover (e.g. August when the data ends in June) is NOT answered
        silently with another month: the note says what was asked, what exists, and what is shown instead."""
        available = sorted(self.use_tool("list_available_months"))
        if not available:
            return {"month": None, "available": [], "note": None}
        hits: List[str] = []
        misses: List[str] = []
        asked = parse_requested_months(question)
        # a bare year the data does not have ("top products in 2027") is flagged too
        data_years = {int(a[:4]) for a in available}
        named_years = {y for y, _ in asked if y}
        for y in sorted({int(y) for y in _YEAR.findall(question)} - data_years - named_years):
            misses.append(str(y))
        for year, number in asked:
            matches = [a for a in available if int(a[5:7]) == number and (year is None or int(a[:4]) == year)]
            if matches:
                hits.append(max(matches))
            else:
                label = MONTH_LABELS[number] + (f" {year}" if year else "")
                if label not in misses:
                    misses.append(label)
        latest = available[-1]
        month = max(hits) if hits else latest
        note = None
        if misses:
            note = (f"You asked about {_join_names(misses)}, but the business data only covers {available[0]} to "
                    f"{latest}. This report uses {month}" + ("." if hits else " (the latest month available)."))
        return {"month": month, "available": available, "note": note}

    # ------------------------------------------------------------------ internal analysis
    def analyze_internal(self, month: Optional[str] = None, focus: str = "full") -> InternalAnalysis:
        regional = self.use_tool("get_regional_trend", months=0)    # months=0 -> every month in the data
        products = self.use_tool("get_product_sales", months=0)
        b = _Builder()
        limitations: List[str] = []

        totals: Dict[str, float] = {}
        for row in regional:
            totals[row["month"]] = totals.get(row["month"], 0) + row["revenue"]
        months = sorted(totals)
        if len(months) < 2:
            return InternalAnalysis(evidence=[], findings=[], limitations=["Fewer than two months of data."])
        latest = month if month in totals else months[-1]
        idx = months.index(latest)
        prev = months[idx - 1] if idx > 0 else None
        comparing = prev is not None

        want_overall = want_regions = comparing and focus in ("full", "regions")
        want_products = comparing and focus in ("full", "products")
        want_top = focus in ("full", "top_products") or not comparing
        top_limit = 5 if focus == "top_products" else 3

        by_product: Dict[str, List[dict]] = {}
        for row in products:
            by_product.setdefault(row["product"], []).append(row)
        for rows in by_product.values():
            rows.sort(key=lambda r: r["month"])

        # 1. overall revenue: does the premise "revenue dropped" even hold for the whole business?
        if want_overall:
            change = pct_change(totals[prev], totals[latest])
            eid = b.add_evidence(f"Total revenue across all regions: {prev} PKR {totals[prev]:,.0f} -> "
                                 f"{latest} PKR {totals[latest]:,.0f} ({_s(change)})")
            if change is not None and change >= 0:
                b.add_finding(f"Total revenue grew {abs(change):.1f}% from {prev} to {latest}, so overall revenue did "
                              f"not decline; any decline is confined to specific products or regions.", [eid])
            elif change is not None:
                b.add_finding(f"Total revenue declined {abs(change):.1f}% from {prev} to {latest}.", [eid])

        # 2. regions (a "regions" question lists all of them; otherwise only the notable moves)
        if want_regions:
            by_region: Dict[str, List[dict]] = {}
            for row in regional:
                by_region.setdefault(row["region"], []).append(row)
            threshold = 0 if focus == "regions" else 8
            moves = []
            for region, rows in by_region.items():
                rows.sort(key=lambda r: r["month"])
                result = _region_detail(region, rows, prev, latest)
                if result and result[1] is not None and abs(result[1]) >= threshold:
                    moves.append((abs(result[1]), region, result[0], result[1]))
            for _mag, region, detail, ch in sorted(moves, reverse=True)[:4]:
                eid = b.add_evidence(detail)
                b.add_finding(f"{region} revenue {'declined' if ch < 0 else 'grew'} {abs(ch):.1f}% from {prev} to {latest}.", [eid])

        # 3. products with a notable move, and whether it is price-driven or demand-driven
        trends: List[dict] = []
        if comparing:
            for rows in by_product.values():
                t = _trend(rows, prev, latest)
                if t and t["rev"] is not None:
                    trends.append(t)
        if want_products:
            flagged = [t for t in trends if abs(t["rev"]) >= 10]
            # declines come first: a "why did revenue drop?" question must not lose a decline behind bigger gains
            declines = sorted([t for t in flagged if t["rev"] < 0], key=lambda t: t["rev"])[:4]
            growth = sorted([t for t in flagged if t["rev"] > 0], key=lambda t: -t["rev"])[:6 - len(declines)]
            for t in declines + growth:
                eid = b.add_evidence(_product_detail(t))
                b.add_finding(f"{t['product']} revenue {'declined' if t['rev'] < 0 else 'grew'} {abs(t['rev']):.1f}%; "
                              f"the change is {_label(t)}.", [eid])
            if not flagged and focus == "products" and trends:
                biggest = max(trends, key=lambda t: abs(t["rev"]))
                eid = b.add_evidence(_product_detail(biggest))
                b.add_finding(f"No product's revenue moved by 10% or more from {prev} to {latest}; the largest "
                              f"change was {biggest['product']} ({_s(biggest['rev'])}).", [eid])

        # 4. the best sellers
        if want_top:
            top = self.use_tool("get_top_products", month=latest, limit=top_limit)
            if top:
                if focus == "top_products":
                    detail = ", ".join(f"{r['product']} (PKR {r['revenue']:,.0f}, {r['units']} units)" for r in top)
                else:
                    detail = ", ".join(f"{r['product']} (PKR {r['revenue']:,.0f})" for r in top)
                eid = b.add_evidence(f"Top products in {latest} by revenue: {detail}")
                b.add_finding(f"The top {len(top)} products in {latest} by revenue are "
                              f"{', '.join(r['product'] for r in top)}.", [eid])

                if focus == "top_products":
                    k = min(3, len(top))
                    top_sum = sum(r["revenue"] for r in top[:k])
                    if totals.get(latest):
                        eid = b.add_evidence(f"Total revenue in {latest}: PKR {totals[latest]:,.0f}; the top {k} "
                                             f"products together: PKR {top_sum:,.0f}")
                        b.add_finding(f"The top {k} products account for {top_sum / totals[latest] * 100:.1f}% of "
                                      f"{latest} revenue.", [eid])
                    if comparing:
                        for r in top[:3]:
                            t = _trend(by_product.get(r["product"], []), prev, latest)
                            if t and t["rev"] is not None:
                                verb = "declined" if t["rev"] < 0 else "grew" if t["rev"] > 0 else "was flat at"
                                eid = b.add_evidence(_product_detail(t))
                                b.add_finding(f"{t['product']} revenue {verb} {abs(t['rev']):.1f}% compared with {prev}; "
                                              f"the change is {_label(t)}.", [eid])

        if comparing:
            span = "the latest two months only" if latest == months[-1] else "two months only"
            limitations.append(f"Comparison covers {span} ({prev} vs {latest}).")
        else:
            limitations.append(f"{latest} is the first month in the data, so there is no earlier month to compare it with.")
        limitations += ["No cost or profit data is available, so margins cannot be assessed.",
                        "The business data is a synthetic sample dataset."]
        return InternalAnalysis(evidence=b.evidence, findings=b.findings, limitations=limitations)

    # ------------------------------------------------------------------ testing external factors
    @staticmethod
    def _match_entity(text: str, product_names: List[str]) -> Optional[Tuple[str, str]]:
        lowered = text.lower()
        for name in product_names:
            for candidate in (name.lower(), name.split()[0].lower()):
                if re.search(rf"\b{re.escape(candidate)}\b", lowered):
                    return "product", name
        for region in config.REGIONS:
            if re.search(rf"\b{re.escape(region.lower())}\b", lowered):
                return "region", region
        return None

    def _entity_detail(self, kind: str, name: str) -> Optional[str]:
        if kind == "product":
            rows = [r for r in self.use_tool("get_product_sales", product_name=name, months=6) if r["product"] == name]
            t = _trend(sorted(rows, key=lambda r: r["month"]))
            return _product_detail(t) if t and t["rev"] is not None else None
        rows = sorted([r for r in self.use_tool("get_regional_trend", months=6) if r["region"] == name],
                      key=lambda r: r["month"])
        result = _region_detail(name, rows)
        return result[0] if result else None

    def _judge(self, claim: str, detail: str) -> FactorVerdict:
        try:
            return self.ask_model(FACTOR_JUDGE_SYSTEM, f"Claim: {claim}\nCompany data:\n{detail}",
                                  FactorVerdict, max_tokens=200)
        except Exception as e:  # a failed judgment must not break the run: record it and carry on
            return FactorVerdict(verdict="not_testable", reason=f"Judgment unavailable ({type(e).__name__}).")

    def test_factors(self, factors: List[ExternalFactor]) -> FactorTestResult:
        product_names = self.use_tool("get_product_names")
        evidence: List[Evidence] = []
        checks: List[FactorCheck] = []
        cache: Dict[str, Optional[Tuple[str, str]]] = {}

        for factor in factors:
            entity = self._match_entity(f"{factor.claim} {factor.testable_with or ''}", product_names)
            if entity is None:
                checks.append(FactorCheck(claim=factor.claim, verdict="not_testable",
                                          reason="No matching product or region in the company data."))
                continue
            kind, name = entity
            if name not in cache:
                detail = self._entity_detail(kind, name)
                if detail is None:
                    cache[name] = None
                else:
                    xid = f"X{len(evidence) + 1}"
                    evidence.append(Evidence(id=xid, source="database", detail=detail))
                    cache[name] = (xid, detail)
            if cache[name] is None:
                checks.append(FactorCheck(claim=factor.claim, verdict="not_testable",
                                          reason=f"Not enough months of data for {name}."))
                continue
            xid, detail = cache[name]
            verdict = self._judge(factor.claim, detail)
            checks.append(FactorCheck(claim=factor.claim, verdict=verdict.verdict, evidence_ids=[xid],
                                      reason=verdict.reason))
        return FactorTestResult(factor_checks=checks, evidence=evidence)