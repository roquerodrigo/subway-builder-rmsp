# Publicar o RMSP no Railyard

Fluxo oficial: empacotar → hospedar num Release do GitHub → abrir uma issue no
[registry](https://github.com/Subway-Builder-Modded/registry/issues) (*Publish New Map*).
Um mantenedor + validação automática criam o PR `maps/<id>/manifest.json`.

## 1. Empacotar

```bash
uv run rmsp all          # gera dados + tiles (se ainda não rodou)
uv run rmsp bundle --version 1.0.0 --repo https://github.com/roquerodrigo/subway-builder-rmsp
```

Saída em `data/dist/`:

| Arquivo | Para quê |
|---|---|
| `RMSP.zip` | asset do Release (config.json + dados `.gz` + `RMSP.pmtiles`, tudo no topo) |
| `config.json` | cópia avulsa (code, version, initialViewState) |
| `RMSP.json` | Update JSON (só se usar *Custom URL*; com *GitHub Releases* não precisa) |

O ZIP bate com a validação do registry (`scripts/lib/integrity.ts`): `config.json`,
`demand_data.json.gz`, `buildings_index.json.gz`, `roads.geojson.gz`,
`runways_taxiways.geojson.gz` e `RMSP.pmtiles` (nome = `code` do config). A `version`
do `config.json` **tem que bater com a tag** do Release. Fundações vêm do
`buildings_index` em runtime, então o pmtiles do basemap basta.

## 2. Hospedar (Release público) — ✅ feito

Repo e Release já estão no ar:

- Repo: <https://github.com/roquerodrigo/subway-builder-rmsp> (público)
- Release `v1.0.0` + asset `RMSP.zip` (206 MB):
  <https://github.com/roquerodrigo/subway-builder-rmsp/releases/download/v1.0.0/RMSP.zip>
- sha256: `88fa83a89bd11e9f7ff4cdc1b9b7b7ef55bf67d850e7de4869e91754994ac050`

Para versões futuras: rode `rmsp bundle --version X.Y.Z` e
`gh release create vX.Y.Z data/dist/RMSP.zip` (a `version` do config.json
precisa casar com a tag).

## 3. Abrir a issue *Publish New Map* — link pronto

Tem que ser pelo **formulário** (ele aplica o label `publish-map`; uma issue via API
sem label é fechada automática pelo `close-invalid.yml`). Link pré-preenchido com tudo:

**[→ Abrir a issue pré-preenchida](https://github.com/Subway-Builder-Modded/registry/issues/new?template=publish-map.yml&title=%5BPublish%20Map%5D%3A%20S%C3%A3o%20Paulo%20%28RMSP%29&map-id=sao-paulo-rmsp&name=S%C3%A3o%20Paulo%20%28RMSP%29&included-cities=Guarulhos%2C%20Osasco%2C%20Santo%20Andr%C3%A9%2C%20S%C3%A3o%20Bernardo%20do%20Campo%2C%20Diadema&city-code=RMSP&country=BR&description=The%20largest%20metropolis%20in%20the%20Southern%20Hemisphere%20%E2%80%94%20the%20central%20urban%20core%20of%20Greater%20S%C3%A3o%20Paulo%20%28capital%2C%20ABC%20region%2C%20Guarulhos%2C%20Osasco%2C%20Diadema%29%2C%20~17M%20residents%20and%20~9M%20jobs.%20Real%20demand%20from%20the%20S%C3%A3o%20Paulo%20Metro%202023%20Origin%E2%80%93Destination%20survey%2C%20with%20commute%20routes%20pre-calculated%20along%20roads%20%28OSRM%29.%20Includes%20neighborhood%20labels%2C%20parks%2Freserves%2C%20water%20and%20the%20GRU%20and%20CGH%20airports.&data_source=Metr%C3%B4-SP%20OD%202023%20%2F%20OSM&source_quality=high-quality&level_of_detail=medium-detail&methodology=Demand%20derived%20from%20the%20S%C3%A3o%20Paulo%20Metro%202023%20Origin%E2%80%93Destination%20survey%20%28434%20OD%20zones%29%3A%20residents%2Fjobs%20per%20zone%20%28FE_PESS%29%20and%20home%E2%86%92work%2Feducation%20pairs%20%28FE_VIA%2C%20origin%20motive%20%3D%20home%29%20expanded%20by%20the%20survey%20weights%3B%20zone%20centroids%20as%20demand%20points%3B%20commute%20trips%20routed%20along%20streets%20via%20OSRM.%20Streets%2C%20buildings%20%28with%20height%29%2C%20water%2C%20parks%20and%20labels%20from%20OSM.&location=south-america&gallery=https%3A%2F%2Fraw.githubusercontent.com%2Froquerodrigo%2Fsubway-builder-rmsp%2Fmain%2Fgallery%2Fscreenshot1.webp%0Ahttps%3A%2F%2Fraw.githubusercontent.com%2Froquerodrigo%2Fsubway-builder-rmsp%2Fmain%2Fgallery%2Fscreenshot2.webp%0Ahttps%3A%2F%2Fraw.githubusercontent.com%2Froquerodrigo%2Fsubway-builder-rmsp%2Fmain%2Fgallery%2Fscreenshot3.webp&source=https%3A%2F%2Fgithub.com%2Froquerodrigo%2Fsubway-builder-rmsp&update-type=GitHub%20Releases&github-repo=roquerodrigo%2Fsubway-builder-rmsp)**

Ao abrir, só falta marcar **2 caixas** (não dá pra pré-marcar por URL):
1. **Special Demand → airports**
2. **Terms** (atestação de autoria)

…e clicar **Create**. As imagens da galeria já estão hospedadas em `gallery/` do
repo (screenshot1 = Ibirapuera, 2 = centro, 3 = rios).

Valores pré-preenchidos (referência):

| Campo | Valor |
|---|---|
| **Map ID** | `sao-paulo-rmsp` |
| **City Name** | São Paulo (RMSP) |
| **Additional Cities** | Guarulhos, Osasco, Santo André, São Bernardo do Campo, Diadema |
| **City Code** | `RMSP` |
| **Country Code** | `BR` |
| **Description** | A maior metrópole do hemisfério sul — mancha urbana central da Grande São Paulo (capital, ABC, Guarulhos, Osasco, Diadema). Demanda real da Pesquisa OD 2023 do Metrô-SP; rotas de commute pré-calculadas (OSRM). |
| **Data Source** | Metrô-SP OD 2023 / OSM |
| **Source Quality** | pesquisa oficial de governo (selecionar a opção de maior qualidade) |
| **Level of Detail** | medium-detail (434 zonas OD) |
| **Methodology** | Residentes/empregos por zona OD (`FE_PESS`), pares casa→trabalho/educação (`FE_VIA`, motivo origem=casa) expandidos da Pesquisa OD 2023; centroides das zonas como pontos; trajetos pelas ruas via OSRM. Prédios/ruas/água/parques/labels do OSM. |
| **Location** | South America |
| **Special Demand** | airports (GRU + CGH) |
| **Gallery** | **≥1 screenshot do jogo (obrigatório)** — capturar in-game |
| **Source URL** | `https://github.com/roquerodrigo/subway-builder-rmsp` |
| **Update Type** | GitHub Releases |
| **GitHub Repository** | `roquerodrigo/subway-builder-rmsp` |

Se a validação falhar, edite a issue e comente **revalidate**.

> **Bloqueio:** a galeria exige pelo menos uma captura de tela do mapa rodando no
> jogo. É o único passo que não dá para automatizar aqui — gere o(s) screenshot(s)
> in-game e anexe na issue.
