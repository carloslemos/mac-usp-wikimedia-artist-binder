import pandas as pd
import time
import textwrap

# use SPARQLWrapper to simplify endpoint interaction instead of raw requests
from SPARQLWrapper import SPARQLWrapper, JSON

# raw.githubusercontent URLs do not include "refs/heads"
CSV_URL = "https://raw.githubusercontent.com/acervos-digitais/herbario-data/main/csv/macusp.csv"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"


def load_data():
    """
    Read a CSV file from a predefined URL into a pandas DataFrame.

    The function uses the global `CSV_URL` constant to locate the
    source file and invokes `pd.read_csv` to parse it. Returns the
    resulting DataFrame for further processing.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing the data loaded from `CSV_URL`.
    """
    df = pd.read_csv(CSV_URL)
    return df


def get_unique_artists(df):
    """
    Extract unique, non-null artist names from the provided DataFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing an 'artist' column.

    Returns
    -------
    numpy.ndarray
        Array of unique artist names.
    """
    return df["artist"].dropna().unique()


def query_wikidata_artist(name: str):
    """Run a SPARQL query against the Wikidata endpoint for a given artist name.

    This implementation uses :class:`SPARQLWrapper` to manage HTTP
    interactions, headers and result parsing. It mirrors the behaviour of the
    previous ``requests``-based version but is much simpler and more robust.

    Parameters
    ----------
    name : str
        The artist name to look up.

    Returns
    -------
    list[dict]
        A list of result dictionaries with the same keys as before.
    """

    # escape quotes/backslashes so the SPARQL string stays valid
    safe_name = name.replace('"', '\\"').replace('\\', '\\\\')
    query = textwrap.dedent(f"""\
        SELECT ?artist ?artistLabel ?country ?countryLabel ?country_lat ?country_lon ?birth ?death ?birthPlace ?birthPlaceLabel ?birth_lat ?birth_lon ?deathPlace ?deathPlaceLabel WHERE {{
          ?artist wdt:P31 wd:Q5 .
          ?artist rdfs:label "{safe_name}"@en .

          OPTIONAL {{ ?artist wdt:P569 ?birth }}
          OPTIONAL {{ ?artist wdt:P570 ?death }}
          OPTIONAL {{ ?artist wdt:P27 ?country }}
          OPTIONAL {{ ?country wdt:P625 ?countryCoord .
            BIND(xsd:float(REPLACE(STR(?countryCoord), "Point\\\\(([^ ]+) .+\\\\)", "$1")) AS ?country_lon)
            BIND(xsd:float(REPLACE(STR(?countryCoord), "Point\\\\([^ ]+ ([^ ]+)\\\\)", "$1")) AS ?country_lat)
          }}
          OPTIONAL {{ ?artist wdt:P19 ?birthPlace }}
          OPTIONAL {{ ?birthPlace wdt:P625 ?birthCoord .
            BIND(xsd:float(REPLACE(STR(?birthCoord), "Point\\\\(([^ ]+) .+\\\\)", "$1")) AS ?birth_lon)
            BIND(xsd:float(REPLACE(STR(?birthCoord), "Point\\\\([^ ]+ ([^ ]+)\\\\)", "$1")) AS ?birth_lat)
          }}
          OPTIONAL {{ ?artist wdt:P20 ?deathPlace }}

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pt,en". }}
        }}
        LIMIT 1
        """)
    sparql = SPARQLWrapper(
        WIKIDATA_ENDPOINT,
        agent="Acervos-Digitais/0.1 (https://www.acervosdigitais.fau.usp.br/; "
              "acervosdigitais@usp.br)"
    )
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(10)  # increased timeout for complex coordinate lookups
    
    data = sparql.query().convert()

    results = []
    for item in data.get("results", {}).get("bindings", []):
        results.append({
            "artist_input": name,
            "wikidata_uri": item["artist"]["value"],
            "label": item.get("artistLabel", {}).get("value"),
            "country": item.get("countryLabel", {}).get("value"),
            "country_lat": item.get("country_lat", {}).get("value"),
            "country_lon": item.get("country_lon", {}).get("value"),
            "birth": item.get("birth", {}).get("value"),
            "birth_place": item.get("birthPlaceLabel", {}).get("value"),
            "birth_lat": item.get("birth_lat", {}).get("value"),
            "birth_lon": item.get("birth_lon", {}).get("value"),
            "death": item.get("death", {}).get("value"),
            "death_place": item.get("deathPlaceLabel", {}).get("value")
        })

    return results


def pick_best_result(results: list[dict]) -> dict:
    """Return the single best result from a list by counting non-None fields."""
    return max(results, key=lambda r: sum(v is not None for v in r.values()))


def main():

    df = load_data()

    artists = get_unique_artists(df)
    artists = sorted(artists)

    all_results = []

    for artist in artists:

        print("Consultando:", artist)

        try:
            results = query_wikidata_artist(artist)
            
            if not results:
                results.append({
                    "artist_input": artist,
                    "wikidata_uri": None,
                    "label": None,
                    "country": None,
                    "country_lat": None,
                    "country_lon": None,
                    "birth": None,
                    "birth_place": None,
                    "birth_lat": None,
                    "birth_lon": None,
                    "death": None,
                    "death_place": None,
                })

            all_results.append(pick_best_result(results))

        except Exception as e:
            print("Erro:", artist, e)
            results.append({
                "artist_input": artist,
                "wikidata_uri": None,
                "label": "Erro ao carregar",
                "country": None,
                "country_lat": None,
                "country_lon": None,
                "birth": None,
                "birth_place": None,
                "birth_lat": None,
                "birth_lon": None,
                "death": None,
                "death_place": None,
            })

        # evitar bloqueio da Wikidata
        time.sleep(1.1)

    output = pd.DataFrame(all_results)

    output.to_csv("wikidata_artists.csv", index=False)


if __name__ == "__main__":
    main()