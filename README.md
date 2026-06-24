# RMSP — São Paulo para Subway Builder

Gera e instala uma cidade jogável da **mancha urbana central da Região
Metropolitana de São Paulo** (capital + ABC + Guarulhos + Osasco + Diadema) para
o jogo [Subway Builder](https://www.subwaybuilder.com) (modding API **v1.0.0**).

A cidade traz ruas, prédios (3D), água (represas Billings/Guarapiranga, rios
Tietê/Pinheiros), aeroportos (Congonhas, Guarulhos, Campo de Marte) e **demanda
de passageiros real** baseada na Pesquisa Origem-Destino do Metrô-SP.

```
rmsp-subway-builder/
├── mod/                     # o mod em si (vai para <game>/mods/rmsp/)
│   ├── manifest.json        #   id br.rodrigo.rmsp
│   └── index.js             #   registra a cidade + basemap + correções de runtime
└── pipeline/                # geração dos dados a partir de fontes abertas
    ├── config.py            #   bbox, código, caminhos, alvo de instalação
    ├── 01_extract.sh        #   recorta subconjuntos do OSM (osmium)
    ├── 02_roads.py          #   -> roads.geojson.gz
    ├── 03_buildings.py      #   -> buildings_index.json.gz (grade espacial)
    ├── 04_water.py          #   -> ocean_depth_index.json.gz (represas/rios)
    ├── 05_airports.py       #   -> runways_taxiways.geojson.gz
    ├── 06_demand.py         #   -> demand_data.json.gz (Pesquisa OD)
    ├── 07_tiles.sh          #   -> tiles/RMSP.pmtiles + RMSP_foundations.pmtiles
    ├── 08_routes.sh         #   rotas viárias reais (OSRM) p/ os trajetos dos pops
    ├── route_paths.py       #   roteia cada pop pela malha viária
    ├── simplify_paths.py    #   Douglas-Peucker p/ deixar os trajetos leves
    ├── validate.py          #   confere os .gz contra o schema das cidades nativas
    ├── serve_tiles.sh       #   sobe o servidor de tiles (pmtiles serve :8080)
    ├── install.sh           #   instala mod + dados no jogo
    └── play.sh              #   sobe o tile server + abre o jogo
```

## Pré-requisitos

Ferramentas de sistema + ambiente Python gerenciado por [uv](https://docs.astral.sh/uv/):

```bash
brew install osmium-tool tippecanoe pmtiles osrm-backend uv
uv sync                       # cria o venv e instala as deps (pyproject.toml/uv.lock)
```

Os scripts Python rodam com `uv run python …` (usam o venv do projeto
automaticamente).

A pasta de dados do jogo é resolvida por `SB_DATA_DIR`
(default `~/Library/Application Support/metro-maker4`). Exporte outra se o seu
jogo estiver em outro lugar.

## Fontes de dados

| Camada | Fonte | Como baixar |
|---|---|---|
| Ruas, prédios, água, aeroportos | **OpenStreetMap** (Geofabrik *sudeste*) | `pipeline/01_extract.sh` (ver abaixo) |
| Demanda (OD real) | **Pesquisa OD Metrô-SP** (2017 e 2023) | zips do Portal da Transparência |

Os dados brutos e gerados (`pipeline/sources/`, `out/`, `tiles/`) **não vão pro
git** (são grandes e reproduzíveis) — ver `.gitignore`.

## Pipeline completo

```bash
cd pipeline

# 1) baixar fontes (uma vez)
curl -L -o sources/sudeste-latest.osm.pbf \
  https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf
osmium extract -b -46.85,-23.82,-46.36,-23.40 \
  sources/sudeste-latest.osm.pbf -o sources/rmsp.osm.pbf -s smart
curl -L -o sources/od2023.zip \
  https://transparencia.metrosp.com.br/sites/default/files/Site_190225_PesquisaOD2023.zip
unzip -o sources/od2023.zip -d sources/od2023
# (OD 2017, alternativa: https://transparencia.metrosp.com.br/sites/default/files/OD-2017.zip)

# 2) extrair subconjuntos OSM
bash 01_extract.sh

# 3) gerar os 5 arquivos de dados (saída em pipeline/out/)
uv run python 02_roads.py
uv run python 03_buildings.py   # pesado: ~minutos, alguns GB de RAM
uv run python 04_water.py
uv run python 05_airports.py
uv run python 06_demand.py      # demanda real da Pesquisa OD

# 4) trajetos viários reais dos commuters (OSRM, sem Docker)
bash 08_routes.sh               # build do grafo + roteamento + simplificação

# 5) basemap vetorial (tiles)
bash 07_tiles.sh

# 6) validar e instalar no jogo
uv run python validate.py
bash install.sh
```

## Jogar

O basemap precisa do servidor de tiles local (limitação do sandbox de mods):

```bash
bash pipeline/play.sh        # sobe o pmtiles serve :8080 e abre o jogo
# ou: bash pipeline/serve_tiles.sh  (num terminal) e abrir o jogo manualmente
```

No jogo: **Settings → Mods** → ligar **RMSP**, e em **Selecionar cidade → aba 🇧🇷
Brasil → São Paulo (RMSP)**.

## Notas técnicas

- **Demanda OD**: `points` = zonas OD (centroides, com moradores/empregos reais);
  `pops` = pares origem→destino de viagens casa↔trabalho/educação expandidas.
  Cada pop entra nos `popIds` das **duas** zonas (residência e emprego) — senão a
  aba *Workers* fica sem horários. `drivingPath` segue as ruas (OSRM).
- **Basemap**: tiles PMTiles com camadas `water/parks/buildings/airports` (nomes
  nativos do estilo do jogo). `index.js` liga `oceanFoundations:false` para a
  água renderizar (a camada `water` do jogo some quando `oceanFoundations` está
  ligado).
- **API v1.0.0**: confirmado via `SubwayBuilderAPI` (`{"version":"1.0.0"}`),
  mesmo no app 1.3.0.

Inspirado no ecossistema [Subway Builder Modded](https://github.com/Subway-Builder-Modded).
