"""Deterministic financial relationships with explicit NOT_APPLICABLE results."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

from backend.app.schemas.document import (
    DocumentType,
    FinancialCheck,
    FinancialValidation,
    ValidationStatus,
)
from backend.app.schemas.extraction import ExtractedField, ExtractionResult


@dataclass(frozen=True)
class Rule:
    name: str
    formula: str
    operands: tuple[tuple[str, tuple[str, ...]], ...]
    reported: tuple[str, ...]
    calculator: Callable[[dict[str, float]], float]


class FinancialValidationService:
    def __init__(self, tolerance: float = 0.01) -> None:
        self.tolerance = tolerance

    def validate(
        self, document_type: DocumentType, extraction: ExtractionResult
    ) -> FinancialValidation:
        grouped = self._by_period(extraction.fields)
        checks: list[FinancialCheck] = []
        if document_type == DocumentType.invoice:
            checks = self._invoice_checks(extraction, grouped.get(None, extraction.fields))
        else:
            for period, fields in grouped.items():
                checks.extend(self._apply_rules(self._rules_for(document_type), fields, period))

        if not checks:
            checks.append(
                FinancialCheck(
                    name="financial_validation",
                    formula="Required financial relationship",
                    status=ValidationStatus.NOT_APPLICABLE,
                    notes="No applicable source fields were extracted.",
                )
            )

        statuses = {check.status for check in checks}
        if ValidationStatus.FAIL in statuses:
            overall = ValidationStatus.FAIL
        elif ValidationStatus.PASS in statuses:
            overall = ValidationStatus.PASS
        else:
            overall = ValidationStatus.NOT_APPLICABLE
        issues = [
            f"{check.name}{f' ({check.period})' if check.period else ''} did not reconcile."
            for check in checks
            if check.status == ValidationStatus.FAIL
        ]
        return FinancialValidation(checks=checks, overall_status=overall, issues=issues)

    def _invoice_checks(
        self, extraction: ExtractionResult, fields: list[ExtractedField]
    ) -> list[FinancialCheck]:
        checks: list[FinancialCheck] = []
        subtotal = self._find(fields, ("subtotal", "sub_total", "taxable_amount"))
        tax = self._find(fields, ("tax_amount", "tax", "gst", "vat"))
        discount = self._find(fields, ("discount", "discount_amount"))
        total = self._find(
            fields, ("total_amount", "grand_total", "amount_due", "invoice_total", "total")
        )
        discount_value = discount if discount is not None else 0.0

        if subtotal is not None and total is not None:
            tax_value = tax if tax is not None else 0.0
            standard_total = subtotal + tax_value - discount_value
            tax_included_total = subtotal - discount_value
            if tax is not None and self._matches(tax_included_total, total):
                checks.append(
                    self._comparison(
                        "invoice_total_check",
                        "subtotal - discount (displayed subtotal includes tax)",
                        {"subtotal": subtotal, "tax_amount": tax, "discount": discount_value},
                        tax_included_total,
                        total,
                    )
                )
            else:
                checks.append(
                    self._comparison(
                        "invoice_total_check",
                        "subtotal + tax_amount - discount",
                        {"subtotal": subtotal, "tax_amount": tax_value, "discount": discount_value},
                        standard_total,
                        total,
                    )
                )
        else:
            checks.append(
                self._not_applicable(
                    "invoice_total_check",
                    "subtotal + tax_amount - discount",
                    {"subtotal": subtotal, "tax_amount": tax, "discount": discount, "total_amount": total},
                )
            )

        item_amounts: list[float] = []
        for table in extraction.tables:
            columns = [self._key(column) for column in table.columns]
            quantity_index = self._column_index(columns, ("quantity", "qty"))
            unit_index = self._column_index(columns, ("unit_price", "price", "rate", "unit_rate"))
            amount_index = self._column_index(columns, ("amount", "line_total", "total"))
            if quantity_index is None or unit_index is None or amount_index is None:
                continue
            for row_number, row in enumerate(table.rows, start=1):
                if max(quantity_index, unit_index, amount_index) >= len(row):
                    continue
                quantity = self._decimal(row[quantity_index])
                unit_price = self._decimal(row[unit_index])
                amount = self._decimal(row[amount_index])
                if quantity is None or unit_price is None or amount is None:
                    continue
                item_amounts.append(amount)
                checks.append(
                    self._comparison(
                        f"line_item_{row_number}_check",
                        "quantity * unit_price",
                        {"quantity": quantity, "unit_price": unit_price},
                        quantity * unit_price,
                        amount,
                    )
                )

        if item_amounts:
            reported = subtotal if subtotal is not None else total
            if reported is None:
                checks.append(
                    self._not_applicable(
                        "line_items_sum_check",
                        "sum(line_item_amounts)",
                        {"line_item_sum": sum(item_amounts), "subtotal_or_total": None},
                    )
                )
            else:
                checks.append(
                    self._comparison(
                        "line_items_sum_check",
                        "sum(line_item_amounts)",
                        {"line_item_sum": sum(item_amounts)},
                        sum(item_amounts),
                        reported,
                    )
                )

        cash = self._find(fields, ("cash_paid", "amount_paid", "cash_tendered"))
        change = self._find(fields, ("change", "change_due"))
        if cash is not None and total is not None and change is not None:
            checks.append(
                self._comparison(
                    "cash_change_check",
                    "cash_paid - total_amount",
                    {"cash_paid": cash, "total_amount": total},
                    cash - total,
                    change,
                )
            )
        return checks

    def _apply_rules(
        self, rules: Iterable[Rule], fields: list[ExtractedField], period: str | None
    ) -> list[FinancialCheck]:
        checks: list[FinancialCheck] = []
        for rule in rules:
            values = {
                name: self._find(fields, aliases) for name, aliases in rule.operands
            }
            reported = self._find(fields, rule.reported)
            if reported is None or any(value is None for value in values.values()):
                operands = dict(values)
                operands["reported_value"] = reported
                checks.append(self._not_applicable(rule.name, rule.formula, operands, period))
                continue
            numeric_values = {
                key: float(value) for key, value in values.items() if value is not None
            }
            checks.append(
                self._comparison(
                    rule.name,
                    rule.formula,
                    values,
                    rule.calculator(numeric_values),
                    reported,
                    period,
                )
            )
        return checks

    @staticmethod
    def _rules_for(document_type: DocumentType) -> tuple[Rule, ...]:
        if document_type == DocumentType.balance_sheet:
            return (
                Rule(
                    "balance_sheet_equation",
                    "total_capital_and_liabilities = total_assets",
                    ((
                        "total_capital_and_liabilities",
                        ("total_capital_and_liabilities", "total_liabilities_and_equity", "total_liabilities_equity"),
                    ),),
                    ("total_assets", "assets_total"),
                    lambda value: value["total_capital_and_liabilities"],
                ),
            )
        if document_type == DocumentType.profit_and_loss:
            return (
                Rule(
                    "total_income_check",
                    "interest_earned + other_income",
                    (
                        ("interest_earned", ("interest_earned", "interest_income")),
                        ("other_income", ("other_income",)),
                    ),
                    ("total_income",),
                    lambda value: value["interest_earned"] + value["other_income"],
                ),
                Rule(
                    "total_expenditure_check",
                    "interest_expended + operating_expenses + provisions_and_contingencies",
                    (
                        ("interest_expended", ("interest_expended", "interest_expense")),
                        ("operating_expenses", ("operating_expenses",)),
                        ("provisions_and_contingencies", ("provisions_and_contingencies", "provisions_contingencies")),
                    ),
                    ("total_expenditure", "total_expenses"),
                    lambda value: value["interest_expended"] + value["operating_expenses"] + value["provisions_and_contingencies"],
                ),
                Rule(
                    "profit_before_minority_check",
                    "total_income - total_expenditure",
                    (
                        ("total_income", ("total_income",)),
                        ("total_expenditure", ("total_expenditure", "total_expenses")),
                    ),
                    ("consolidated_net_profit_before_minority_interest", "profit_before_minority_interest"),
                    lambda value: value["total_income"] - value["total_expenditure"],
                ),
                Rule(
                    "attributable_profit_check",
                    "profit_before_minority_interest - minority_interest",
                    (
                        ("profit_before_minority_interest", ("consolidated_net_profit_before_minority_interest", "profit_before_minority_interest")),
                        ("minority_interest", ("minority_interest",)),
                    ),
                    ("consolidated_net_profit_attributable_to_group", "net_profit_attributable_to_group", "attributable_profit"),
                    lambda value: value["profit_before_minority_interest"] - value["minority_interest"],
                ),
                Rule(
                    "appropriation_check",
                    "current_profit + brought_forward_profit",
                    (
                        ("current_profit", ("current_profit", "profit_for_the_year")),
                        ("brought_forward_profit", ("brought_forward_profit", "profit_brought_forward")),
                    ),
                    ("total_available_for_appropriation",),
                    lambda value: value["current_profit"] + value["brought_forward_profit"],
                ),
            )
        if document_type == DocumentType.cash_flow_statement:
            return (
                Rule(
                    "net_change_in_cash_check",
                    "operating_cash_flow + investing_cash_flow + financing_cash_flow + fx_translation_adjustment",
                    (
                        ("operating_cash_flow", ("operating_cash_flow", "net_cash_flow_from_operating_activities", "net_cash_from_operating_activities")),
                        ("investing_cash_flow", ("investing_cash_flow", "net_cash_flow_from_investing_activities", "net_cash_from_investing_activities")),
                        ("financing_cash_flow", ("financing_cash_flow", "net_cash_flow_from_financing_activities", "net_cash_from_financing_activities")),
                        ("fx_translation_adjustment", ("fx_translation_adjustment", "effect_of_exchange_rate_changes", "translation_adjustment")),
                    ),
                    ("net_change_in_cash", "net_increase_in_cash_and_cash_equivalents", "net_increase_in_cash"),
                    lambda value: value["operating_cash_flow"] + value["investing_cash_flow"] + value["financing_cash_flow"] + value["fx_translation_adjustment"],
                ),
                Rule(
                    "closing_cash_check",
                    "opening_cash + net_change_in_cash + other_adjustments",
                    (
                        ("opening_cash", ("opening_cash", "opening_cash_and_cash_equivalents", "cash_and_cash_equivalents_at_beginning")),
                        ("net_change_in_cash", ("net_change_in_cash", "net_increase_in_cash_and_cash_equivalents", "net_increase_in_cash")),
                        ("other_adjustments", ("cash_acquired_on_amalgamation", "other_cash_adjustments", "amalgamation_adjustment")),
                    ),
                    ("closing_cash", "closing_cash_and_cash_equivalents", "cash_and_cash_equivalents_at_end"),
                    lambda value: value["opening_cash"] + value["net_change_in_cash"] + value["other_adjustments"],
                ),
            )
        return ()

    @staticmethod
    def _by_period(fields: list[ExtractedField]) -> dict[str | None, list[ExtractedField]]:
        grouped: dict[str | None, list[ExtractedField]] = defaultdict(list)
        for field in fields:
            grouped[field.period].append(field)
        return dict(grouped)

    def _comparison(
        self,
        name: str,
        formula: str,
        operands: dict[str, float | None],
        calculated: float,
        reported: float | None,
        period: str | None = None,
    ) -> FinancialCheck:
        if reported is None:
            return self._not_applicable(name, formula, operands, period)
        variance = calculated - reported
        status = (
            ValidationStatus.PASS
            if self._matches(calculated, reported)
            else ValidationStatus.FAIL
        )
        return FinancialCheck(
            name=name,
            formula=formula,
            period=period,
            operands=operands,
            calculated_value=round(calculated, 4),
            reported_value=round(reported, 4),
            variance=round(variance, 4),
            status=status,
        )

    @staticmethod
    def _not_applicable(
        name: str,
        formula: str,
        operands: dict[str, float | None],
        period: str | None = None,
    ) -> FinancialCheck:
        missing = [key for key, value in operands.items() if value is None]
        return FinancialCheck(
            name=name,
            formula=formula,
            period=period,
            operands=operands,
            status=ValidationStatus.NOT_APPLICABLE,
            notes=f"Missing source fields: {', '.join(missing)}" if missing else "Not applicable.",
        )

    def _matches(self, calculated: float, reported: float) -> bool:
        absolute_tolerance = max(self.tolerance, abs(reported) * 0.000001)
        return math.isclose(
            calculated, reported, rel_tol=0.000001, abs_tol=absolute_tolerance
        )

    @classmethod
    def _find(cls, fields: list[ExtractedField], aliases: tuple[str, ...]) -> float | None:
        normalized_aliases = {cls._key(alias) for alias in aliases}
        for field in fields:
            if cls._key(field.key) in normalized_aliases or cls._key(field.label) in normalized_aliases:
                value = cls._decimal(field.value)
                if value is not None:
                    return value
        return None

    @staticmethod
    def _column_index(columns: list[str], aliases: tuple[str, ...]) -> int | None:
        for alias in aliases:
            normalized = FinancialValidationService._key(alias)
            if normalized in columns:
                return columns.index(normalized)
        return None

    @staticmethod
    def _key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")

    @staticmethod
    def _decimal(value: object) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text or text.lower() in {"null", "n/a", "na", "-", "--"}:
            return None
        negative = (
            (text.startswith("(") and text.endswith(")"))
            or (text.startswith("[") and text.endswith("]"))
        )
        cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned):
            return None
        number = float(cleaned)
        return -abs(number) if negative else number
