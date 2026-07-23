# RMSP — São Paulo para Subway Builder

Gera uma cidade jogável da **Região Metropolitana de São Paulo
inteira** (capital + ABC + Guarulhos + Osasco/Barueri + Mogi + periferia) para
o jogo [Subway Builder](https://www.subwaybuilder.com), empacotada como um mapa
do **Railyard** (import local). O bbox cobre todo o extent da Pesquisa OD
(~157 × 101 km), para que nenhuma zona de demanda fique fora do mapa.

A cidade traz ruas, prédios (3D), água (represas Billings/Guarapiranga, rios
Tietê/Pinheiros), aeroportos (Congonhas, Guarulhos, Campo de Marte) e **demanda
de passageiros real** da Pesquisa Origem-Destino do Metrô-SP, com trajetos que
seguem o viário (OSRM).

```
subway-builder-rmsp/
├── src/rmsp/             # gerador (pacote Python, CLI `rmsp`)
│   ├── config.py         #   Settings: bbox, zoom, knobs, URLs, paths  (fonte única)
│   ├── cli.py            #   comandos: sources generate demand specials routes validate bundle all
│   ├── sources.py        #   download do PBF (Geofabrik) + clip no bbox (osmium)
│   ├── generate.py       #   arquivos não-demanda via depot (roads/buildings json+bin/água/aero/PMTiles)
│   ├── demand.py         #   baixa o demand_data da release do subway-builder-rmsp-demand-data
│   ├── specials.py       #   pontos de demanda especiais (aeroporto/parque/estádio…) via depot
│   ├── routing.py        #   OSRM (rota viária dos pops) + Douglas-Peucker
│   ├── publish.py        #   empacota o .zip do mapa Railyard + Update JSON
│   ├── validate.py · external.py · geojson.py
├── tests/                # pytest (funções puras)
└── data/                 # gitignored: sources/ build/ tiles/ dist/  (gerado em runtime)
```

## Pré-requisitos

Os arquivos não-demanda são gerados pela biblioteca oficial
[`depot`](https://github.com/Subway-Builder-Modded/depot) (instalada via `uv sync`),
que chama várias ferramentas de linha de comando — todas precisam estar no `PATH`:

```bash
# binários (Homebrew): osmium, tippecanoe/tile-join, pmtiles, osrm-*, gdal (ogr2ogr),
# jq, sqlite3, java, node
brew install osmium-tool tippecanoe pmtiles osrm-backend gdal jq sqlite node openjdk uv
npm install -g mapshaper                              # cleanup de geometria (depot)
# planetiler.jar num diretório do PATH (ex.: ~/.local/bin):
curl -L -o ~/.local/bin/planetiler.jar \
  "$(gh api repos/onthegomap/planetiler/releases/latest \
     --jq '.assets[]|select(.name=="planetiler.jar").browser_download_url')"

uv sync                       # cria o venv e instala o pacote + depot + deps pesadas
```

> O `depot.MapGen` valida essas ferramentas no construtor e **falha** se alguma faltar.
> As deps Python pesadas (duckdb, geopandas, xarray, netcdf4, osmnx, scipy, matplotlib…)
> vêm junto no `uv sync`.

> Também há um **pré-filtro** de prédios (`generate.py`): a Overture entrega ~7 M estruturas
> para a metrópole; dropar as menores que ~100 m² antes do mapshaper evita o OOM (2,8 GB → 1 GB).
> O `dist/RMSP.zip` publicado é gerado com `RMSP_MAXZOOM=15` (detalhe cheio); a regeneração
> completa dos tiles da RMSP inteira leva ~30 min.

## Uso

Pipeline completo (baixa fontes, gera tudo e valida):

```bash
uv run rmsp all
uv run rmsp bundle --version X.Y.Z --repo https://github.com/<owner>/<repo>
```

Ou passo a passo:

```bash
uv run rmsp sources     # baixa o PBF (Geofabrik) e recorta no bbox
uv run rmsp generate    # depot: roads/buildings(json+bin)/água/aero/PMTiles -> data/build + data/tiles
uv run rmsp demand      # baixa o demand_data.json da release do subway-builder-rmsp-demand-data
uv run rmsp specials    # opt-in (RMSP_SPECIAL_DEMAND=1): injeta POIs de demanda especial
uv run rmsp routes      # OSRM: rota, descarta trajetos de carro < 2 km, geometria reta
uv run rmsp validate    # confere os .gz contra o schema das cidades nativas
uv run rmsp bundle      # empacota dist/RMSP.zip (+ Update JSON) p/ importar no Railyard
```

### Instalar no jogo (import local no Railyard)

O `rmsp bundle` gera `data/dist/RMSP.zip` (config.json + os `.gz` + `RMSP.pmtiles`).
No [Railyard](https://subwaybuildermodded.com/railyard): **Library → Import Asset** e
selecione o `.zip`. O Railyard instala o mapa no jogo e serve os tiles — sem servidor
local, sem mod. (Ver a doc de [Importing Local Assets](https://subwaybuildermodded.com/railyard/docs/v0.2/importing-local-assets).)

Ver a seção **Pipeline de dados** abaixo para as fontes baixadas e o modelo de demanda.

## Pipeline de dados

### Fontes baixadas (`rmsp sources`)

| Fonte | O que fornece | Tamanho | Onde |
|---|---|---|---|
| **Geofabrik Sudeste** (OSM PBF) | input do `depot` (ruas/água/aero/labels) + grafo OSRM | ~1,5 GB | `sources` → `sudeste-latest.osm.pbf` |
| **Overture Maps** (prédios) | pegadas de prédio p/ `buildings_index` (baixado pelo `depot`) | — | `generate` (DuckDB/S3) |
| **Demanda** (release do [demand-data](https://github.com/roquerodrigo/subway-builder-rmsp-demand-data)) | `demand_data.json` pronto (Pesquisa OD 2023 + CNEFE/Censo + GeoSampa) | ~1 MB gz | `demand` → `data/build/demand_data.json` |

O download do PBF é idempotente (pula se o arquivo já existe).

### Fluxo

```
OSM PBF + Overture ──depot(generate)──> roads/buildings(json+bin)/água/aero + PMTiles
release do demand-data ──demand(fetch)──> demand_data.json ──[specials]──> routes(OSRM: rota + filtro + geometria reta)
```

Os arquivos não-demanda (roads, buildings `json`+`bin`, água, aeroportos, PMTiles) são
gerados pelo `depot`; prédios vêm do **Overture Maps**. A **demanda** é gerada no projeto
[**subway-builder-rmsp-demand-data**](https://github.com/roquerodrigo/subway-builder-rmsp-demand-data)
e publicada como release — aqui o RMSP só a **baixa** e a **roteia** (OSRM); a demanda
especial (`specials`) é **opt-in**.

### Demanda

A demanda de commuters (Pesquisa OD 2023 + CNEFE/Censo + GeoSampa) é modelada no projeto
[subway-builder-rmsp-demand-data](https://github.com/roquerodrigo/subway-builder-rmsp-demand-data)
e baixada pronta da release (`demand`). Sobre ela o RMSP:

- **`specials`** (opt-in, `RMSP_SPECIAL_DEMAND=1`) — injeta **pontos de demanda especial**
  (aeroportos, universidades, shoppings, parques, estádios, hospitais… — ver `rmsp/specials.py`)
  via `depot.add_points`: cada POI vira um ponto de id prefixado pelo código do tipo
  (`AIR_GRU`, `PRK_IBIRA`…), ligado à população por gravidade. Desligado por padrão porque
  a demanda-data já traz destinos nomeados do OSM. O `config.json` declara os
  `specialDemandTypes` presentes.
- **`routes`** — roteia cada commute na malha viária (OSRM, em paralelo) para obter
  `drivingSeconds`/`drivingDistance` reais, **descarta os trajetos de carro < 2 km**
  (`RMSP_MIN_DRIVING_DISTANCE_M`; reindexa os points) e reduz o `drivingPath` a uma **reta
  origem→destino** (`RMSP_STRAIGHT_PATH_GEOMETRY`, como o jogo o desenha). Ajuste os knobs
  para manter a linha viária (Douglas-Peucker) ou pular o OSRM (`RMSP_ROUTE_STRAIGHT_LINE=1`).

Os `residents`/`jobs` por `point` são derivados dos pops (invariante `Σ residents ==
Σ jobs == Σ pop.size`).

### Variáveis de ambiente

| Var | Default | Efeito |
|---|---|---|
| `RMSP_DEMAND_URL` | release v1.0.0 | asset `demand_data.json.gz` baixado pelo `demand` |
| `RMSP_SPECIAL_DEMAND` | `0` | injeta os POIs de demanda especial no pipeline `all` (opt-in) |
| `RMSP_MIN_DRIVING_DISTANCE_M` | `2000` | descarta commutes de carro abaixo disso (0 desliga) |
| `RMSP_STRAIGHT_PATH_GEOMETRY` | `1` | `drivingPath` = reta origem→destino (0 = Douglas-Peucker) |
| `RMSP_ROUTE_STRAIGHT_LINE` | `0` | liga os pontos por reta (pula o OSRM) |
| `RMSP_MAXZOOM` | `15` | zoom máximo das tiles (detalhe) |
| `RMSP_BUILD_WORKERS` | `0` (auto) | nº de processos nas passadas por-feature do build |

No jogo, após o import no Railyard: **Selecionar cidade → aba 🇧🇷 Brasil →
São Paulo**.

## Notas técnicas

- **Demanda**: gerada no projeto
  [subway-builder-rmsp-demand-data](https://github.com/roquerodrigo/subway-builder-rmsp-demand-data)
  e baixada pronta da release (ver **Pipeline de dados → Demanda**). O RMSP faz o
  **roteamento** (`routes`: rota, descarte de trajetos curtos e geometria reta) e,
  opcionalmente, a **demanda especial** (`specials`). `residents`/`jobs` por `point` são
  **derivados dos pops** e reindexados após o descarte, garantindo `Σ residents == Σ jobs
  == Σ pop.size`.
- **Geração não-demanda**: roads, `buildings_index` (`json`+`bin`), aeroportos,
  `ocean_depth_index` e o PMTiles basemap (com labels) são gerados pela biblioteca
  oficial [`depot`](https://github.com/Subway-Builder-Modded/depot); prédios vêm do
  **Overture Maps**. Enviamos `buildings_index.json.gz` **e** `.bin.gz` — o jogo
  migrou o formato do índice de prédios em 1.3.3, e ter ambos mantém o mapa
  compatível com todas as versões.
- **Ferramentas externas**: osmium e osrm-\* são binários nativos (Homebrew),
  chamados por `src/rmsp/external.py`; o `depot` usa as suas próprias (ver Pré-requisitos).
- **Prédios**: o campo `f` do `buildings_index` é a **profundidade de fundação**
  (subsolos, default 1) que o jogo lê como `foundationDepth` ao tunelar sob prédios —
  não os andares acima.
- **Notas sobre o `depot`**: [`docs/depot-performance.md`](docs/depot-performance.md)
  (gargalos medidos e propostas de otimização upstream) e
  [`docs/depot-issues.md`](docs/depot-issues.md) (bugs da 1.2.4 e mudanças de
  comportamento). O benchmark que embasa a primeira vive em
  `benchmarks/depot_tile_worker.py`.

Inspirado no ecossistema [Subway Builder Modded](https://github.com/Subway-Builder-Modded).

## Licença

**GPL v3** (ver [`LICENSE`](LICENSE)). O projeto depende da biblioteca
[`depot`](https://github.com/Subway-Builder-Modded/depot), licenciada sob GPL v3, então
o conjunto é distribuído sob os mesmos termos.
