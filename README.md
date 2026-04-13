# Meta-Acervo: Consolidação e Enriquecimento de Dados de Criadores

Sistema para combinar múltiplas fontes de dados sobre criadores de arte, deduplica registros, enriquece com informações de educação via fuzzy matching e geocodifica locais de nascimento/morte.

## Instalação

1. Clone ou baixe o repositório.
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

### 1. Combinação de Inputs (Principal)

Combina 4 CSVs biográficos e enriquece com dados de educação:

```bash
python combine_all_inputs.py
```

**Entrada:**
- `inputs/FILE 0412.csv` - Dados FILE
- `inputs/MAC consolidado.csv` - Dados MAC
- `inputs/OUT_merged.csv` - Dados de outras fontes
- `inputs/planilha_focada_formacao_continua_56.csv` - Dados de educação
- `inputs/20250705_processed.json` - Dados de obras/acervo

**Saída:**
- `outputs/resultado_combinado.csv` - Dados consolidados

**Funcionalidades:**
- Deduplica criadores (case-insensitive)
- Enriquece com educação via fuzzy matching (threshold: 80%)
- Associa museu/acervo de cada criador a partir do JSON

### 2. Geocodificação (Opcional)

Geocodifica locais de nascimento e morte:

```bash
python geocode_data.py
```

**Entrada:**
- `outputs/resultado_combinado.csv`

**Saída:**
- `outputs/resultado_geolocalizado.csv`

**Adiciona colunas:**
- `lat_birth`, `lon_birth`, `score_birth` - para local de nascimento
- `lat_death`, `lon_death`, `score_death` - para local de morte

Usa ArcGIS World Geocoding Service (público, sem chave).

## Estrutura do Projeto

```
meta-acervo/
├── combine_all_inputs.py      # Script principal de consolidação
├── geocode_data.py            # Script de geocodificação
├── requirements.txt           # Dependências
├── inputs/                    # Dados de entrada (CSVs e JSON)
├── outputs/                   # Dados processados
├── tests/                     # Testes automatizados
└── legacy/                    # Scripts anteriores (histórico)
```

## Dependências

- **pandas** - Manipulação de dados
- **rapidfuzz** - Fuzzy matching para enriquecimento de educação
- **requests** - Chamadas HTTP para geocodificação

## Notas

- Respeita limites de taxa da API de geocodificação ArcGIS com delay entre requisições.
- Usa token_set_ratio do rapidfuzz para fuzzy matching com threshold configurável (padrão: 80%).
- Deduplica mantendo todas as fontes/acervos em campos consolidados.