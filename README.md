# RMSP — São Paulo para Subway Builder

Gera e instala uma cidade jogável da **Região Metropolitana de São Paulo
inteira** (capital + ABC + Guarulhos + Osasco/Barueri + Mogi + periferia) para
o jogo [Subway Builder](https://www.subwaybuilder.com) (modding API **v1.0.0**).
O bbox cobre todo o extent da Pesquisa OD (~157 × 101 km), para que nenhuma zona
de demanda fique fora do mapa.

A cidade traz ruas, prédios (3D), água (represas Billings/Guarapiranga, rios
Tietê/Pinheiros), aeroportos (Congonhas, Guarulhos, Campo de Marte) e **demanda
de passageiros real** da Pesquisa Origem-Destino do Metrô-SP, com trajetos que
seguem o viário (OSRM).

```
subway-builder-rmsp/
├── mod/                  # o mod (vai para <game>/mods/rmsp/)
│   ├── manifest.json
│   └── index.js
├── src/rmsp/             # gerador (pacote Python, CLI `rmsp`)
│   ├── config.py         #   Settings: bbox, zoom, knobs, URLs, paths  (fonte única)
│   ├── cli.py            #   comandos: sources cnefe build routes tiles validate install serve play all
│   ├── sources.py        #   downloads + clip (osmium) + extração OSM + CNEFE/Censo
│   ├── layers.py         #   roads / buildings / water / airports  -> .gz
│   ├── subpoints.py      #   desagregação dasimétrica (CNEFE / prédios -> sub-pontos)
│   ├── demand.py         #   Pesquisa OD + sub-pontos -> demand_data
│   ├── routing.py        #   OSRM (rota viária dos pops) + Douglas-Peucker
│   ├── tiles.py          #   tippecanoe -> PMTiles ; pmtiles serve
│   ├── validate.py · install.py · external.py · geojson.py
├── tests/                # pytest (funções puras)
└── data/                 # gitignored: sources/ build/ tiles/  (gerado em runtime)
```

## Pré-requisitos

```bash
brew install osmium-tool tippecanoe pmtiles osrm-backend uv
uv sync                       # cria o venv e instala o pacote + deps
```

A pasta de dados do jogo é resolvida por `SB_DATA_DIR`
(default `~/Library/Application Support/metro-maker4`).

## Uso

Pipeline completo (baixa fontes, gera tudo, valida e instala no jogo):

```bash
uv run rmsp all
```

Ou passo a passo:

```bash
uv run rmsp sources     # baixa OSM + Pesquisa OD + CNEFE/Censo; recorta no bbox; extrai
uv run rmsp build       # 5 arquivos de dados -> data/build/  (--only roads,demand,...)
uv run rmsp routes      # trajetos viários reais dos commuters (OSRM, sem Docker)
uv run rmsp tiles       # basemap vetorial (PMTiles)
uv run rmsp validate    # confere os .gz contra o schema das cidades nativas
uv run rmsp install     # copia mod + dados pro jogo (SB_DATA_DIR)

# uv run rmsp cnefe     # (re)constrói só o proxy CNEFE: cnefe.csv + setor_pop.csv
```

Ver a seção **Pipeline de dados** abaixo para as fontes baixadas e o modelo de demanda.

## Pipeline de dados

### Fontes baixadas (`rmsp sources`)

| Fonte | O que fornece | Tamanho | Onde |
|---|---|---|---|
| **Geofabrik Sudeste** (OSM PBF) | ruas, prédios, água, aeroportos, lugares | ~1,5 GB | `sources` → `<layer>.geojsonseq` |
| **Pesquisa OD 2023** (Metrô-SP) | zonas (527) + totais/matriz de demanda por zona | ~50 MB | `sources` → `od2023/` |
| **CNEFE 2022** (IBGE, UF-SP) | ~23 mi de endereços com lat/lng + espécie (residência/estabelecimento) | ~1 GB zip | `cnefe` → `cnefe.csv` (filtrado ao bbox: ~8,3 mi) |
| **Censo 2022 — Agregados por setor** (IBGE) | população residente por setor censitário (`v0001`) | ~15 MB | `cnefe` → `setor_pop.csv` |

Os downloads são idempotentes (pulam se o arquivo já existe). O CNEFE/Censo só
são baixados quando o proxy de demanda é `cnefe` (o padrão). O FTP do IBGE serve
cadeia TLS incompleta — usamos o bundle de CAs do `certifi`.

### Fluxo

```
OSM PBF ──clip(bbox)──extract──> roads/buildings/water/aero/places.geojsonseq ──layers──> *.gz  +  tiles ──> PMTiles
Pesquisa OD ───────────────────> zonas + matriz/totais por zona ─┐
CNEFE (endereços) ─┐                                             ├─ demand.py ──> demand_data(.gz) ──routes(OSRM)──> drivingPath
Censo (pop/setor) ─┴─ subpoints.py ─> sub-pontos (res_w/job_w) ──┘
```

### Modelo de demanda (desagregação dasimétrica)

A Pesquisa OD fixa **quanto** de demanda cada zona tem (totais e matriz zona→zona);
um **proxy** decide **onde dentro da zona** ela fica. Os totais oficiais nunca são
alterados — `Σ residents == Σ jobs == Σ pop.size` (invariante do jogo/Railyard).

Dois proxies, selecionáveis por `RMSP_DEMAND_PROXY`:

- **`cnefe`** (padrão) — endereços georreferenciados do CNEFE 2022. A espécie separa
  **residência** de **estabelecimento** direto do dado real (sem heurística). O peso
  residencial vem da **população real do setor censitário** (Censo `v0001`),
  distribuída entre os endereços residenciais do setor (`res_w = pop / nº endereços`);
  empregos = densidade de estabelecimentos. `RMSP_CNEFE_CENSUS=0` desliga a ponderação
  por censo (volta a peso por espécie). Resultado RMSP: ~26 mil `points`.
- **`buildings`** (fallback) — pegadas de prédio do OSM, peso = área × andares dividido
  pelas tags `building`/`amenity`/`shop`/`office`. Não precisa do download do CNEFE.
  Resultado RMSP: ~17 mil `points`.

Em ambos, os sub-pontos são agrupados numa grade fina (~300 m), cada célula vira um
`point`, e `pops` ligam sub-ponto residencial → sub-ponto de emprego (entrando nos
`popIds` das **duas** pontas, senão a aba *Workers* fica sem horários). `drivingPath`
segue as ruas via OSRM.

### Variáveis de ambiente

| Var | Default | Efeito |
|---|---|---|
| `RMSP_DEMAND_PROXY` | `cnefe` | proxy de demanda: `cnefe` ou `buildings` |
| `RMSP_CNEFE_CENSUS` | `1` | pondera residências pela população do setor (Censo) |
| `RMSP_BASIS` | `workers` | base OD: `workers` (FE_PESS, ~10,4 mi) ou `commute` (FE_VIA, ~14,3 mi) |
| `RMSP_BUILD_WORKERS` | `0` (auto) | nº de processos nas passadas por-feature do build |
| `SB_DATA_DIR` | macOS metro-maker4 | pasta de dados do jogo (alvo do `install`) |
| `RMSP_USE_DOCKER` | Linux: `1` | rodar ferramentas externas em container (ver abaixo) |

> **Build paralelo**: `buildings_index` e os sub-pontos da demanda são gerados em
> múltiplos processos (faixas de bytes do arquivo, com merge determinístico), e os
> `.gz` usam compressão nível 6 — ~2,5× mais rápido que a versão serial/nível 9.

## Jogar

O basemap precisa do servidor de tiles local (limitação do sandbox de mods):

```bash
uv run rmsp play        # sobe o pmtiles serve :8080 (se preciso) e abre o jogo
# ou: uv run rmsp serve  (num terminal) e abrir o jogo manualmente
```

No jogo: **Settings → Mods** → ligar **RMSP**; em **Selecionar cidade → aba 🇧🇷
Brasil → São Paulo (RMSP)**.

## Notas técnicas

- **Demanda OD**: ver **Pipeline de dados → Modelo de demanda** acima para os proxies
  (CNEFE/prédios) e a ponderação por censo. Detalhe de implementação: `residents`/`jobs`
  por `point` são **derivados dos pops** (não entradas independentes), garantindo a
  invariante `Σ residents == Σ jobs == Σ pop.size`.
- **Runtime Linux/Docker**: as ferramentas externas (osmium, tippecanoe, osrm-\*,
  pmtiles) rodam em containers — ver `src/rmsp/external.py` e `docker/tools.Dockerfile`.
  `use_docker=True` (default) monta a raiz do projeto no container; em macOS com
  Homebrew, `use_docker=False` usa os binários nativos.
- **Basemap**: PMTiles com as camadas que o estilo do jogo renderiza —
  `water/parks/buildings/airports`, os rótulos `city_labels/suburb_labels/
  neighborhood_labels` e as fundações `foundations/ocean_foundations`. Cada feature
  carrega só a propriedade que a camada lê: `parks→area`, `buildings→height` (m),
  `foundations→foundationDepth`, `water/ocean_foundations→depth_min`, labels→`name`.
  `index.js` liga `oceanFoundations:false` — sem isso a camada `water` fica
  `visibility:none`.
- **Prédios**: a altura 3D vem da tile `buildings.height` (de `height`/`building:levels`);
  o campo `f` do `buildings_index` é a **profundidade de fundação** (subsolos, default 1)
  que o jogo lê como `foundationDepth` ao tunelar sob prédios — não os andares acima.
- **API v1.0.0**: confirmado via `SubwayBuilderAPI` (`{"version":"1.0.0"}`),
  mesmo no app 1.3.0.

## Limitações conhecidas

- **`Error: layers[N]: source "general-tiles" not found`** no console (ao
  renderizar rotas). É um *diff* de estilo do MapLibre disparado pelo basemap
  custom (`setTileURLOverride`); **transitório e não-fatal** — o mapa renderiza
  normalmente. Acontece com qualquer mapa custom que use override (a comunidade
  [Subway Builder Modded](https://github.com/Subway-Builder-Modded) usa a mesma
  técnica). Não há correção limpa pelo lado do mod, pois o jogo reconstrói o
  estilo internamente e o MapLibre não é acessível a partir do mod.
- **Servidor de tiles**: o basemap só renderiza com `rmsp serve`/`rmsp play` no ar.

Inspirado no ecossistema [Subway Builder Modded](https://github.com/Subway-Builder-Modded).
