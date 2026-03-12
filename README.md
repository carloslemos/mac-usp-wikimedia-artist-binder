# Meta-Acervo: Wikidata Artist Lookup

This project fetches artist data from a CSV file and queries Wikidata to retrieve additional information like birth/death dates and places.

## Installation

1. Clone or download the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the script to process the first 3 artists from the CSV and save results to `wikidata_artists.csv`:

```bash
python wikidata_artists.py
```

The script loads data from a remote CSV, extracts unique artist names, queries Wikidata for each, and outputs a CSV with enriched data.

## Dependencies

- pandas: For data manipulation
- SPARQLWrapper: For querying Wikidata SPARQL endpoint

## Notes

- Respects Wikidata's rate limits with a 1-second delay between queries.
- Uses the Wikidata SPARQL endpoint to fetch artist metadata.