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

## 3. Abrir a issue *Publish New Map*

Valores prontos para o formulário:

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
