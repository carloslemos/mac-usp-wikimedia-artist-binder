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
        SELECT ?artist ?artistLabel ?country ?countryLabel ?birth ?death ?birthPlace ?birthPlaceLabel ?deathPlace ?deathPlaceLabel WHERE {{
          ?artist wdt:P31 wd:Q5 .
          ?artist rdfs:label "{safe_name}"@en .
          
          OPTIONAL {{ ?artist wdt:P569 ?birth }}
          OPTIONAL {{ ?artist wdt:P570 ?death }}
          OPTIONAL {{ ?artist wdt:P27 ?country }}
          OPTIONAL {{ ?artist wdt:P19 ?birthPlace }}
          OPTIONAL {{ ?artist wdt:P20 ?deathPlace }}

          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,pt". }}
        }}
        """)
    sparql = SPARQLWrapper(
        WIKIDATA_ENDPOINT,
        agent="Acervos-Digitais/0.1 (https://www.acervosdigitais.fau.usp.br/; "
              "acervosdigitais@usp.br)"
    )
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.setTimeout(10)  # set a timeout to avoid hanging indefinitely
    sparql.setQuery(query)
    sparql.setReturnFormat("json")
    
    data = sparql.query().convert()

    results = []
    for item in data.get("results", {}).get("bindings", []):
        results.append({
            "artist_input": name,
            "wikidata_uri": item["artist"]["value"],
            "label": item.get("artistLabel", {}).get("value"),
            "country": item.get("countryLabel", {}).get("value"),
            "birth": item.get("birth", {}).get("value"),
            "birth_place": item.get("birthPlaceLabel", {}).get("value"),
            "death": item.get("death", {}).get("value"),
            "death_place": item.get("deathPlaceLabel", {}).get("value")
        })

    return results


def main():

    df = load_data()

    artists = get_unique_artists(df)

    all_results = []

    for artist in artists[:100]:

        print("Consultando:", artist)

        try:
            results = query_wikidata_artist(artist)
            
            if not results:
                results.append({
                    "artist_input": artist,
                    "wikidata_uri": None,
                    "label": None,
                    "country": None,
                    "birth": None,
                    "birth_place": None,
                    "death": None,
                })

            all_results.extend(results)

        except Exception as e:
            print("Erro:", artist, e)

        # evitar bloqueio da Wikidata
        time.sleep(1)

    output = pd.DataFrame(all_results)

    output.to_csv("wikidata_artists.csv", index=False)


if __name__ == "__main__":
    main()