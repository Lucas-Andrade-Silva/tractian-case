"""Coleta a leitura de vibracao de cada ativo nas tres seeds da bateria.

O artefato de referencia mostrava uma seed so (`complete`). Aqui as tres seeds da
bateria de avaliacao sao coletadas lado a lado, porque `s2` e `s3` nao sao repeticao
cosmetica: a API decide o modo de resposta por hash(seed|recurso|categoria), entao o
mesmo ativo pode vir `complete` numa seed, `unavailable` noutra e `partial` na terceira.
E exatamente essa variacao que o agente enfrentou nas 3 execucoes de cada cenario.

Saida: dados/ativos.json, consumido por leitura.html.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

API = "http://127.0.0.1:8000"
SEEDS = ["complete", "s2", "s3"]
RAIZ = Path(__file__).resolve().parents[3]
DADOS = RAIZ / "tractian" / "data"
SAIDA = Path(__file__).resolve().parent.parent / "dados" / "ativos.json"


def get(caminho: str, seed: str) -> dict | None:
    """GET com seed. Devolve None em 404 — ausencia e um resultado valido aqui."""
    sep = "&" if "?" in caminho else "?"
    url = f"{API}{caminho}{sep}seed={seed}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def envelope(resp: dict | None) -> tuple[str, str | None, dict | list | None]:
    """Desempacota {mode, notes, data}. Sem resposta = indisponivel."""
    if resp is None:
        return "unavailable", "Recurso nao encontrado para este ativo.", None
    return resp.get("mode", "complete"), resp.get("notes"), resp.get("data")


def serie_rms(data: dict | list | None) -> dict:
    """Normaliza /rms para o formato que o grafico consome."""
    if not isinstance(data, dict):
        return {"samples": [], "ref": None, "alarm": None, "state": None, "point": None}
    amostras = []
    for s in data.get("samples") or []:
        ts = s.get("timestamp") or s.get("date") or s.get("ts")
        v = s.get("rms_mm_s", s.get("value"))
        if ts is None or v is None:
            continue
        amostras.append([str(ts)[:10], round(float(v), 3)])
    return {
        "samples": amostras,
        "ref": data.get("baseline_reference"),
        "alarm": data.get("alarm_threshold"),
        "state": data.get("baseline_state"),
        "point": data.get("point_id"),
    }


def coletar_ativo(aid: str, seed: str) -> dict:
    """As quatro leitura tecnicas de um ativo numa seed."""
    m_rms, n_rms, d_rms = envelope(get(f"/assets/{aid}/rms", seed))
    m_bl, n_bl, d_bl = envelope(get(f"/assets/{aid}/baseline", seed))
    m_sp, n_sp, d_sp = envelope(get(f"/assets/{aid}/spectrum", seed))
    m_dq, n_dq, d_dq = envelope(get(f"/assets/{aid}/data-quality", seed))
    m_an, n_an, d_an = envelope(get(f"/assets/{aid}/analyses", seed))

    rms = serie_rms(d_rms)
    rms.update({"mode": m_rms, "notes": n_rms, "unit": "mm/s"})

    bl = d_bl if isinstance(d_bl, dict) else {}
    spec = d_sp if isinstance(d_sp, dict) else {}
    dq = d_dq if isinstance(d_dq, dict) else {}

    # /analyses devolve {analyses: [...]}, nao a lista crua.
    lista_an = d_an.get("analyses") if isinstance(d_an, dict) else d_an
    analises = []
    for an in (lista_an if isinstance(lista_an, list) else []):
        analises.append({
            "type": an.get("type") or "none",
            "severity": an.get("severity") or "none",
            "conf": an.get("confidence"),
            "dm": an.get("detection_mode"),
            "status": an.get("status"),
            "evidence": [
                {"metric": e.get("metric"), "value": e.get("value"),
                 "reference": e.get("reference"), "note": e.get("note")}
                for e in (an.get("evidence") or [])
            ],
            "limitations": an.get("limitations") or [],
        })

    return {
        "seed": seed,
        "rms": rms,
        "baseline": {
            "mode": m_bl, "notes": n_bl,
            "state": bl.get("state"),
            "detection_mode": bl.get("detection_mode"),
            "features": bl.get("features") or [],
            "invalidation_reason": bl.get("invalidation_reason"),
        },
        "spectrum": {
            "mode": m_sp, "notes": n_sp,
            "peaks": [
                {"freq_hz": p.get("freq_hz"), "amplitude_mm_s": p.get("amplitude_mm_s"),
                 "note": p.get("note")}
                for p in (spec.get("peaks") or [])
            ],
            "missing": spec.get("bands_missing") or [],
        },
        "dq": {
            "mode": m_dq, "notes": n_dq,
            "completeness": dq.get("completeness"),
            "snr": dq.get("snr_db"),
            "fresh": dq.get("freshness_minutes"),
            "stale": dq.get("staleness_flag"),
        },
        "analyses_mode": m_an,
        "analyses": analises,
    }


def main() -> None:
    ativos_df = pd.read_parquet(DADOS / "assets.parquet")
    pontos = pd.read_parquet(DADOS / "points.parquet")
    com_ponto = set(pontos["asset_id"].unique())

    registros = []
    for _, a in ativos_df.iterrows():
        aid = a["id"]
        if aid not in com_ponto:
            continue  # sem ponto de medicao nao ha o que ler — mesmo criterio do artefato
        por_seed = {}
        for seed in SEEDS:
            por_seed[seed] = coletar_ativo(aid, seed)
            print(f"  {aid} | {seed} | rms={por_seed[seed]['rms']['mode']}")
        registros.append({
            "id": aid,
            "name": a["name"],
            "company": a["company_id"],
            "crit": a["criticality"],
            "plant": a["plant"],
            "line": a["line"],
            "mtype": a["machine_type"],
            "rpm": None if pd.isna(a["rotation_rpm"]) else int(a["rotation_rpm"]),
            "sensor": a["sensor_status"],
            "bpfo": None if pd.isna(a["bpfo_hz"]) else float(a["bpfo_hz"]),
            "bpfi": None if pd.isna(a["bpfi_hz"]) else float(a["bpfi_hz"]),
            "seeds": por_seed,
        })

    empresas_df = pd.read_parquet(DADOS / "companies.parquet")
    empresas = {r["id"]: r["name"] for _, r in empresas_df.iterrows()}

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({
        "ativos": registros,
        "empresas": empresas,
        "seeds": SEEDS,
        "origem": API,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(registros)} ativos x {len(SEEDS)} seeds -> {SAIDA}")


if __name__ == "__main__":
    main()
