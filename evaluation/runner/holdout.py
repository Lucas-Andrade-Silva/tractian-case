"""Holdout sintético auditado (ADR 0006).

Cenários NOVOS sobre ativos e dados que já existem nos parquets — os 16 originais ficam
inteiros como conjunto de desenvolvimento, porque cada um cobre uma faceta não-redundante
do domínio e dividi-los cortaria cobertura, não só volume.

## Auditoria mecânica

Um cenário só entra no holdout depois de ser executado de fato contra a API local com
`seed` fixo, confirmando que a resposta real sustenta a resolução esperada. Não é
julgamento por leitura de schema: é confirmação reproduzível contra o sistema real, o
mesmo processo que corrigiu CEN-05 e CEN-08 em `docs/test-scenarios.md`.

Rode com:  python -m runner.holdout
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .golden import GoldenCase

HOLDOUT_DIR = Path(__file__).resolve().parent.parent / "holdout"
CASES_PATH = HOLDOUT_DIR / "cases.json"
EXPECTED_PATH = HOLDOUT_DIR / "expected-paths.json"

# Seed fixo da auditoria: torna o comportamento probabilístico determinístico, isolando
# a dificuldade do domínio (baseline, qualidade, cobertura) da degradação de envelope,
# que os cenários originais já exercitam.
AUDIT_SEED = "complete"


def load_holdout_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Parte visível ao agente: mensagem e contexto, sem nada do gabarito."""
    return json.loads((path or CASES_PATH).read_text(encoding="utf-8"))


def load_holdout(path: Path | None = None) -> dict[str, GoldenCase]:
    """Parte de gabarito do holdout, no mesmo formato do golden set da Tractian."""
    raw: list[dict[str, Any]] = json.loads((path or EXPECTED_PATH).read_text(encoding="utf-8"))
    cases: dict[str, GoldenCase] = {}
    for entry in raw:
        steps = entry.get("expected_path", [])
        cases[entry["id"]] = GoldenCase(
            case_id=entry["id"],
            ticket_id=entry.get("ticket_id", ""),
            root_question=entry.get("root_question", ""),
            mode=entry.get("mode", ""),
            expected_path=[s["step"] for s in steps],
            expected_notes={s["step"]: s.get("note", "") for s in steps},
            declared_decisions=frozenset(entry["accepted_decisions"]),
            facet=entry.get("facet", ""),
        )
    return cases


# ---------------------------------------------------------------------------
# Auditoria
# ---------------------------------------------------------------------------
@dataclass
class AuditCheck:
    """Uma asserção sobre a resposta real da API."""

    case_id: str
    step: str
    field: str
    expected: Any
    actual: Any
    ok: bool

    def describe(self) -> str:
        mark = "OK  " if self.ok else "FALHA"
        return f"    [{mark}] {self.step} · {self.field}: esperado {self.expected!r}, obtido {self.actual!r}"


def _dig(payload: Any, dotted: str) -> Any:
    """Navega um caminho pontilhado (`data.baseline.state`) tolerando ausências."""
    current = payload
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _matches(actual: Any, expected: Any) -> bool:
    """Compara valor observado com a expectativa declarada.

    Além de igualdade, aceita `{"lt": x}`, `{"gt": x}` e `{"len": n}` — necessários para
    afirmar coisas como "completeness abaixo do requisito do modelo" sem fixar o valor
    exato, que é detalhe do gerador de dados e não o que o cenário afirma.
    """
    if isinstance(expected, dict):
        if "lt" in expected:
            return isinstance(actual, (int, float)) and actual < expected["lt"]
        if "gt" in expected:
            return isinstance(actual, (int, float)) and actual > expected["gt"]
        if "len" in expected:
            return hasattr(actual, "__len__") and len(actual) == expected["len"]
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(actual - expected) < 1e-6
    return actual == expected


def _call(client: httpx.Client, step: str, *, user_id: str, body: dict[str, Any] | None) -> tuple[int, Any]:
    """Executa um passo escrito no formato do gabarito (`"GET /assets/x?y=z"`)."""
    method, _, target = step.partition(" ")
    path, _, query = target.partition("?")
    params: dict[str, str] = {}
    for pair in filter(None, query.split("&")):
        key, _, value = pair.partition("=")
        params[key] = value
    if method == "GET":
        params.setdefault("seed", AUDIT_SEED)

    response = client.request(
        method, path, params=params, json=body, headers={"x-user-id": user_id}
    )
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"raw": response.text}


def audit_case(
    client: httpx.Client, case: dict[str, Any], spec: dict[str, Any]
) -> list[AuditCheck]:
    """Roda as asserções de um cenário contra a API real."""
    checks: list[AuditCheck] = []
    for assertion in spec.get("audit", []):
        step = assertion["step"]
        user_id = assertion.get("as_user", case["user_id"])
        status_code, payload = _call(client, step, user_id=user_id, body=assertion.get("body"))

        for field, expected in assertion["expect"].items():
            actual = status_code if field == "status_code" else _dig(payload, field)
            checks.append(
                AuditCheck(
                    case_id=case["id"],
                    step=step,
                    field=field,
                    expected=expected,
                    actual=actual,
                    ok=_matches(actual, expected),
                )
            )
    return checks


def audit_holdout(base_url: str = "http://localhost:8000") -> tuple[bool, list[AuditCheck]]:
    """Audita todos os cenários do holdout. Retorna (tudo_passou, verificações)."""
    cases = {c["id"]: c for c in load_holdout_cases()}
    specs: list[dict[str, Any]] = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    checks: list[AuditCheck] = []
    with httpx.Client(base_url=base_url, timeout=15) as client:
        for spec in specs:
            case = cases.get(spec["id"])
            if case is None:
                raise SystemExit(f"Cenário {spec['id']} não tem caso correspondente em cases.json")
            checks.extend(audit_case(client, case, spec))

    return all(c.ok for c in checks), checks


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Auditoria mecânica do holdout (ADR 0006)")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    try:
        passed, checks = audit_holdout(args.base_url)
    except httpx.HTTPError as exc:
        raise SystemExit(f"API industrial inacessível em {args.base_url}: {exc}") from exc

    holdout = load_holdout()
    print(f"\nAuditoria do holdout — {len(holdout)} cenários, seed='{AUDIT_SEED}'\n")

    by_case: dict[str, list[AuditCheck]] = {}
    for check in checks:
        by_case.setdefault(check.case_id, []).append(check)

    for case_id, case_checks in by_case.items():
        golden = holdout[case_id]
        ok = all(c.ok for c in case_checks)
        print(f"  [{'OK ' if ok else 'FALHA'}] {golden.ticket_id} ({case_id}) — resolução aceita: "
              f"{sorted(golden.accepted_decisions)}")
        for check in case_checks:
            if not check.ok:
                print(check.describe())

    total = len(checks)
    failed = sum(1 for c in checks if not c.ok)
    print(f"\n{total - failed}/{total} asserções confirmadas contra a API real.")
    if not passed:
        raise SystemExit("Auditoria FALHOU — cenários com asserção reprovada não entram no holdout.")
    print("Holdout auditado: todos os cenários sustentados pelos dados reais.\n")


if __name__ == "__main__":
    main()
