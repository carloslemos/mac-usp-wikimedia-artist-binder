"""
Meta-Acervo: Geolocalização (OPCIONAL)
======================================

Pega 'resultado_consolidado.csv' e geocodifica:
- place_of_birth → lat_birth, lon_birth, score_birth
- place_of_death → lat_death, lon_death, score_death

Usa ArcGIS World Geocoding Service (público, sem chave).

Saída: resultado_geolocalizado.csv
"""

import pandas as pd
from pathlib import Path
import requests
import logging
from typing import Optional, Dict
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataGeocoder:
    """Geocodificador para coordenadas lat/lon."""
    
    def __init__(self, input_file: str = "outputs/resultado_combinado.csv", 
                 output_dir: str = "outputs"):
        """Inicializar."""
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.df = None
        self.geocoded_cities = {}  # Cache
        
        # ArcGIS endpoint
        self.arcgis_geocode_url = (
            "https://geocode.arcgis.com/arcgis/rest/services/"
            "World/GeocodeServer/findAddressCandidates"
        )
        
        # Estatísticas
        self.stats = {
            'total_birth': 0,
            'total_death': 0,
            'geocoded_birth': 0,
            'geocoded_death': 0,
            'api_calls': 0,
        }
    
    def load_consolidated_data(self) -> None:
        """Carregar resultado de consolidação."""
        logger.info(f"Carregando {self.input_file}...")
        
        if not self.input_file.exists():
            raise FileNotFoundError(f"{self.input_file} não encontrado")
        
        self.df = pd.read_csv(self.input_file)
        logger.info(f"✓ Carregados {len(self.df)} registros")
    
    def geocode_city(self, city: str, min_score: int = 50) -> Optional[Dict]:
        """
        Geocodificar uma cidade.
        
        Estratégia: Usar EXATAMENTE como fornecido, sem modificações.
        Isso evita falsos positivos.
        """
        if pd.isna(city) or not str(city).strip():
            return None
        
        city_clean = str(city).strip()
        
        # Verificar cache
        if city_clean in self.geocoded_cities:
            return self.geocoded_cities[city_clean]
        
        try:
            # Query EXATAMENTE como fornecido
            query = city_clean
            
            params = {
                'SingleLine': query,
                'f': 'json',
                'outSR': '{"wkid":4326}'
            }
            
            response = requests.get(
                self.arcgis_geocode_url, 
                params=params, 
                timeout=10
            )
            self.stats['api_calls'] += 1
            
            data = response.json()
            candidates = data.get('candidates', [])
            
            if candidates:
                best = candidates[0]
                score = best.get('score', 0)
                
                if score >= min_score:
                    result = {
                        'lat': best['location']['y'],
                        'lon': best['location']['x'],
                        'score': score,
                        'match_addr': best.get('address', '')
                    }
                    self.geocoded_cities[city_clean] = result
                    return result
        
        except Exception as e:
            logger.warning(f"Erro ao geocodificar '{city}': {str(e)}")
        
        return None
    
    def _geocode_unique_cities(self, cities: set) -> None:
        """Geocodifica cada cidade única exatamente uma vez, com delay apenas
        quando uma chamada à API é de fato realizada."""
        total = len(cities)
        logger.info("  %d locais únicos a geocodificar...", total)
        for i, city in enumerate(sorted(cities), 1):
            if i % 50 == 0:
                logger.info("  Geocodificados %d/%d locais únicos...", i, total)
            if city not in self.geocoded_cities:
                self.geocode_city(city)
                time.sleep(0.1)  # delay só quando a API é consultada

    def enrich_dataframe_with_coords(self) -> None:
        """Adicionar coordenadas ao DataFrame.

        Estratégia:
        1. Coletar todos os valores únicos de place_of_birth e place_of_death.
        2. Geocodificar cada valor único uma única vez (sem repetição).
        3. Mapear resultados de volta ao DataFrame via lookup no cache.
        """
        logger.info("Geocodificando coordenadas...")

        birth_col = self.df['place of birth'].dropna().str.strip()
        death_col = self.df['place of death'].dropna().str.strip()

        self.stats['total_birth'] = birth_col.count()
        self.stats['total_death'] = death_col.count()

        unique_cities = set(birth_col.unique()) | set(death_col.unique())
        unique_cities.discard('')
        logger.info(
            "Locais únicos: %d (nascimento: %d valores, morte: %d valores)",
            len(unique_cities), self.stats['total_birth'], self.stats['total_death'],
        )

        # Fase 1: geocodificar cada local único apenas uma vez
        self._geocode_unique_cities(unique_cities)

        # Fase 2: mapear resultados de volta ao DataFrame
        def _lat(city):
            r = self.geocoded_cities.get(str(city).strip()) if pd.notna(city) else None
            return r['lat'] if r else None

        def _lon(city):
            r = self.geocoded_cities.get(str(city).strip()) if pd.notna(city) else None
            return r['lon'] if r else None

        def _score(city):
            r = self.geocoded_cities.get(str(city).strip()) if pd.notna(city) else None
            return r['score'] if r else None

        self.df['lat_birth']   = self.df['place of birth'].map(_lat)
        self.df['lon_birth']   = self.df['place of birth'].map(_lon)
        self.df['score_birth'] = self.df['place of birth'].map(_score)
        self.df['lat_death']   = self.df['place of death'].map(_lat)
        self.df['lon_death']   = self.df['place of death'].map(_lon)
        self.df['score_death'] = self.df['place of death'].map(_score)

        self.stats['geocoded_birth'] = self.df['lat_birth'].notna().sum()
        self.stats['geocoded_death'] = self.df['lat_death'].notna().sum()

        logger.info(
            "✓ Geocodificação concluída (%d chamadas à API, %d locais únicos)",
            self.stats['api_calls'], len(unique_cities),
        )
    
    def export_results(self) -> None:
        """Exportar resultado geocodificado."""
        logger.info("Exportando resultado geocodificado...")
        
        output_file = self.output_dir / "resultado_geolocalizado.csv"
        self.df.to_csv(output_file, index=False, encoding='utf-8-sig')
        logger.info(f"✓ Exportado: {output_file}")
        
        self._generate_report()
    
    def _generate_report(self) -> None:
        """Gerar relatório."""
        logger.info("\n" + "="*70)
        logger.info("RELATÓRIO DE GEOLOCALIZAÇÃO")
        logger.info("="*70)
        
        total_records = len(self.df)
        
        logger.info(f"\nTotal de registros: {total_records}")
        
        if self.stats['total_birth'] > 0:
            pct_birth = 100 * self.stats['geocoded_birth'] / self.stats['total_birth']
            logger.info(f"\nLocal de nascimento:")
            logger.info(f"  - Registros com local de nascimento: {self.stats['total_birth']}")
            logger.info(f"  - Geocodificados: {self.stats['geocoded_birth']} ({pct_birth:.1f}%)")
        
        if self.stats['total_death'] > 0:
            pct_death = 100 * self.stats['geocoded_death'] / self.stats['total_death']
            logger.info(f"\nLocal de morte:")
            logger.info(f"  - Registros com local de morte: {self.stats['total_death']}")
            logger.info(f"  - Geocodificados: {self.stats['geocoded_death']} ({pct_death:.1f}%)")
        
        logger.info(f"\nChamadas à API: {self.stats['api_calls']}")
        
        logger.info("\n" + "="*70)
        logger.info("✓ Geolocalização concluída com sucesso!")
        logger.info("="*70 + "\n")
    
    def run(self) -> None:
        """Executar geocodificação."""
        logger.info("Iniciando Data Geocoder...")
        logger.info("="*70)
        
        try:
            self.load_consolidated_data()
            self.enrich_dataframe_with_coords()
            self.export_results()
            
        except Exception as e:
            logger.error(f"✗ Erro: {str(e)}")
            raise


def main():
    """Ponto de entrada."""
    geocoder = DataGeocoder(
        input_file="outputs/resultado_combinado.csv",
        output_dir="outputs"
    )
    geocoder.run()


if __name__ == "__main__":
    main()
