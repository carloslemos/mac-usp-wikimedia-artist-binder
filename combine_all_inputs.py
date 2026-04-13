"""
Meta-Acervo: Combinação de todos os inputs
===========================================

Combina os 4 CSVs de inputs em um único arquivo deduplciado,
enriquece com dados de educação via fuzzy match e cruza com o
JSON de obras para associar o museu/acervo de cada criador.

Saída:  outputs/resultado_combinado.csv
Relatório no console:
  - criadores únicos no JSON que NÃO aparecem no arquivo combinado
"""

import json
import logging
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

INPUT_DIR = Path("inputs")
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

FUZZY_THRESHOLD = 80

# ---------------------------------------------------------------------------
# Fase 1 – Carregar e normalizar CSVs biográficos
# ---------------------------------------------------------------------------

def _load_bio_csv(filename: str, acervo_tag: str) -> pd.DataFrame:
    """Carrega um CSV biográfico, renomeia 'Coluna 1' → 'creator' e descarta
    linhas sem nome de criador."""
    df = pd.read_csv(INPUT_DIR / filename)
    df.rename(columns={"Coluna 1": "creator"}, inplace=True)
    df["acervo"] = acervo_tag
    df["source"] = acervo_tag
    # Descartar linhas sem criador (inclusive as que têm dados em outras colunas)
    df = df[df["creator"].notna() & (df["creator"].str.strip() != "")]
    df["creator"] = df["creator"].str.strip()
    return df


def load_bio_csvs() -> pd.DataFrame:
    """Carrega FILE, MAC e OUT_merged e retorna o concat bruto."""
    file_df = _load_bio_csv("FILE 0412.csv", "FILE")
    mac_df  = _load_bio_csv("MAC consolidado.csv", "MAC")
    out_df  = _load_bio_csv("OUT_merged.csv", "outros")

    logger.info(
        "Registros carregados — FILE: %d | MAC: %d | OUT: %d",
        len(file_df), len(mac_df), len(out_df),
    )
    return pd.concat([file_df, mac_df, out_df], ignore_index=True, sort=False)


def load_education_csv() -> pd.DataFrame:
    """Carrega a planilha de educação, descartando linhas sem criador."""
    df = pd.read_csv(INPUT_DIR / "planilha_focada_formacao_continua_56.csv")
    df = df[df["creator"].notna() & (df["creator"].str.strip() != "")]
    df["creator"] = df["creator"].str.strip()
    logger.info("Registros de educação carregados: %d", len(df))
    return df


# ---------------------------------------------------------------------------
# Fase 2 – Union e deduplicação
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    return str(name).lower().strip()


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplica por creator (case-insensitive).

    Para cada group de mesmo creator normalizado:
    - campos biográficos: primeiro valor não-nulo
    - 'acervo': união dos valores distintos separados por '; '
    - 'source': união dos valores distintos separados por '; '
    Mantém o nome canônico da primeira ocorrência.
    """
    df["_key"] = df["creator"].apply(_normalize)

    def merge_group(group: pd.DataFrame) -> pd.Series:
        result = {}
        for col in group.columns:
            if col == "_key":
                continue
            if col in ("acervo", "source"):
                vals = group[col].dropna().unique().tolist()
                result[col] = "; ".join(str(v) for v in vals if str(v).strip())
            else:
                # Primeiro valor não-nulo
                non_null = group[col].dropna()
                result[col] = non_null.iloc[0] if len(non_null) > 0 else None
        return pd.Series(result)

    deduped = df.groupby("_key", sort=False).apply(merge_group).reset_index(drop=True)
    logger.info(
        "Após deduplicação: %d criadores únicos (de %d linhas)", len(deduped), len(df)
    )
    return deduped


# ---------------------------------------------------------------------------
# Fase 3 – Enriquecimento com dados de educação
# ---------------------------------------------------------------------------

EDU_COLS = [
    "onde estudou",
    "nome da escola",
    "datas em que estudou",
    "fonte_onde_estudou",
    "fonte_nome_escola",
    "fonte_datas_estudo",
    "observacoes_pesquisa",
    "confianca_preenchimento",
]


def enrich_with_education(combined: pd.DataFrame, edu_df: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy-match de cada criador do combinado contra a planilha de educação
    e adiciona as colunas de educação ao combinado."""
    edu_creators = edu_df["creator"].tolist()
    # Índice creator → linha de educação para lookup rápido
    edu_index = {row["creator"]: row for _, row in edu_df.iterrows()}

    # Colunas de destino
    for col in EDU_COLS:
        combined[col] = None

    creators_to_match = [
        (idx, row["creator"])
        for idx, row in combined.iterrows()
        if not pd.isna(row["creator"]) and str(row["creator"]).strip()
    ]

    matched = 0
    for idx, creator in creators_to_match:
        result = process.extractOne(
            creator, edu_creators,
            scorer=fuzz.token_set_ratio,
            score_cutoff=FUZZY_THRESHOLD,
        )
        if result:
            edu_row = edu_index[result[0]]
            for col in EDU_COLS:
                if col in edu_df.columns:
                    combined.at[idx, col] = edu_row[col]
            matched += 1

    logger.info(
        "Enriquecimento de educação: %d de %d criadores com match", matched, len(combined)
    )
    return combined


# ---------------------------------------------------------------------------
# Fase 4 – Cruzamento com o JSON
# ---------------------------------------------------------------------------

def _is_valid_creator_name(name: str) -> bool:
    """Descarta blank nodes do Wikidata, QIDs e strings vazias."""
    if not name:
        return False
    # Blank nodes: http://www.wikidata.org/.well-known/genid/...
    if name.startswith("http://") or name.startswith("https://"):
        return False
    # Wikidata QIDs: Q seguido apenas de dígitos
    import re
    if re.fullmatch(r"Q\d+", name):
        return False
    return True


def load_json_creator_map() -> dict:
    """Extrai {creator → museum} único por creator a partir do JSON de obras.
    Exclui blank nodes do Wikidata e QIDs brutos."""
    json_path = INPUT_DIR / "20250705_processed.json"
    with open(json_path, "r", encoding="utf-8") as f:
        works = json.load(f)

    creator_museum: dict[str, str] = {}
    skipped = 0
    for work_data in works.values():
        creator = str(work_data.get("creator", "")).strip()
        museum  = str(work_data.get("museum", "")).strip()
        if not museum:
            continue
        if not _is_valid_creator_name(creator):
            skipped += 1
            continue
        if creator not in creator_museum:
            creator_museum[creator] = museum

    logger.info(
        "Criadores únicos no JSON: %d (descartados %d IDs/URIs sem nome)",
        len(creator_museum), skipped,
    )
    return creator_museum


def enrich_with_json(combined: pd.DataFrame, creator_museum: dict) -> tuple[pd.DataFrame, list[str]]:
    """Para cada creator do JSON, fuzzy-match com o combinado.

    - Adiciona coluna 'museum_json' onde há match.
    - Retorna lista de creators do JSON que NÃO matcharam.
    """
    combined_creators = combined["creator"].tolist()
    # Índice creator → posição no DataFrame para lookup O(1)
    creator_to_idx = {name: i for i, name in enumerate(combined_creators)}
    combined["museum_json"] = None

    matched_json_creators: set[str] = set()

    json_creators_list = list(creator_museum.keys())
    for json_creator in json_creators_list:
        result = process.extractOne(
            json_creator, combined_creators,
            scorer=fuzz.token_set_ratio,
            score_cutoff=FUZZY_THRESHOLD,
        )
        if result:
            matched_name = result[0]
            row_idx = creator_to_idx.get(matched_name)
            if row_idx is not None:
                combined.at[row_idx, "museum_json"] = creator_museum[json_creator]
            matched_json_creators.add(json_creator)

    unmatched = [c for c in creator_museum if c not in matched_json_creators]
    logger.info(
        "JSON × combinado — matchados: %d | ausentes: %d",
        len(matched_json_creators), len(unmatched),
    )
    return combined, unmatched


# ---------------------------------------------------------------------------
# Fase 5 – Exportação e relatório
# ---------------------------------------------------------------------------

def export(combined: pd.DataFrame) -> None:
    out_path = OUTPUT_DIR / "resultado_combinado.csv"
    combined.to_csv(out_path, index=False, encoding="utf-8-sig")
    logger.info("Exportado: %s", out_path)


def print_report(combined: pd.DataFrame, creator_museum: dict, unmatched: list[str]) -> None:
    total_combined  = len(combined)
    total_json      = len(creator_museum)
    total_matched   = total_json - len(unmatched)
    total_unmatched = len(unmatched)

    sep = "=" * 70
    logger.info("\n%s", sep)
    logger.info("RELATÓRIO FINAL")
    logger.info(sep)
    logger.info("Criadores únicos no arquivo combinado : %d", total_combined)
    logger.info("Criadores únicos no JSON              : %d", total_json)
    logger.info("JSON creators COM match no combinado  : %d", total_matched)
    logger.info("JSON creators SEM match no combinado  : %d  ← métrica principal", total_unmatched)
    logger.info(sep)

    if unmatched:
        logger.info("Artistas do JSON AUSENTES no combinado:")
        for name in sorted(unmatched):
            logger.info("  - %s", name)
    else:
        logger.info("Todos os artistas do JSON aparecem no combinado.")

    logger.info(sep + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("Iniciando combinação de inputs...")
    logger.info("=" * 70)

    # Fase 1
    bio_df  = load_bio_csvs()
    edu_df  = load_education_csv()

    # Fase 2
    combined = deduplicate(bio_df)

    # Fase 3
    combined = enrich_with_education(combined, edu_df)

    # Fase 4
    creator_museum       = load_json_creator_map()
    combined, unmatched  = enrich_with_json(combined, creator_museum)

    # Fase 5
    export(combined)
    print_report(combined, creator_museum, unmatched)

    logger.info("Concluído.")


if __name__ == "__main__":
    main()
