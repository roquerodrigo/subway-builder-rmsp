# RMSP — São Paulo para Subway Builder

Gera e instala uma cidade jogável da **mancha urbana central da Região
Metropolitana de São Paulo** (capital + ABC + Guarulhos + Osasco + Diadema) para
o jogo [Subway Builder](https://www.subwaybuilder.com) (modding API **v1.0.0**).

A cidade traz ruas, prédios (3D), água (represas Billings/Guarapiranga, rios
Tietê/Pinheiros), aeroportos (Congonhas, Guarulhos, Campo de Marte) e **demanda
de passageiros real** da Pesquisa Origem-Destino do Metrô-SP, com trajetos que
seguem o viário (OSRM).

```
rmsp-subway-builder/
├── mod/                  # o mod (vai para <game>/mods/rmsp/)
│   ├── manifest.json
│   └── index.js
├── src/rmsp/             # gerador (pacote Python, CLI `rmsp`)
│   ├── config.py         #   Settings: bbox, zoom, knobs, URLs, paths  (fonte única)
│   ├── cli.py            #   comandos: sources build routes tiles validate install serve play all
│   ├── sources.py        #   download + clip (osmium) + extração de subconjuntos OSM
│   ├── layers.py         #   roads / buildings / water / airports  -> .gz
│   ├── demand.py         #   Pesquisa OD -> demand_data
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
uv run rmsp sources     # Geofabrik sudeste + Pesquisa OD; recorta no bbox; extrai OSM
uv run rmsp build       # 5 arquivos de dados -> data/build/  (--only roads,demand,...)
uv run rmsp routes      # trajetos viários reais dos commuters (OSRM, sem Docker)
uv run rmsp tiles       # basemap vetorial (PMTiles)
uv run rmsp validate    # confere os .gz contra o schema das cidades nativas
uv run rmsp install     # copia mod + dados pro jogo (SB_DATA_DIR)
```

## Jogar

O basemap precisa do servidor de tiles local (limitação do sandbox de mods):

```bash
uv run rmsp play        # sobe o pmtiles serve :8080 (se preciso) e abre o jogo
# ou: uv run rmsp serve  (num terminal) e abrir o jogo manualmente
```

No jogo: **Settings → Mods** → ligar **RMSP**; em **Selecionar cidade → aba 🇧🇷
Brasil → São Paulo (RMSP)**.

## Notas técnicas

- **Demanda OD**: `points` = zonas OD (centroides, moradores/empregos reais);
  `pops` = pares origem→destino (casa↔trabalho/educação) expandidos. Cada pop é
  listado nos `popIds` das **duas** zonas (senão a aba *Workers* fica sem
  horários). `drivingPath` segue as ruas via OSRM, simplificado por Douglas-Peucker.
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
