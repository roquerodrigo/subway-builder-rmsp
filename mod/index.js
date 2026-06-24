// =====================================================================
//  RMSP — Região Metropolitana de São Paulo  |  Subway Builder mod
//  Registra a mancha urbana central da Grande São Paulo como cidade
//  jogável (capital + ABC + Guarulhos + Osasco + Diadema).
//  Dados: OpenStreetMap (vias/prédios/água/aeroportos) e Pesquisa
//  Origem-Destino 2017 do Metrô-SP (demanda real).
//  Docs: https://www.subwaybuilder.com/docs/v1.0.0/api-reference/cities
// =====================================================================
(function () {
    "use strict";

    if (!window.SubwayBuilderAPI) {
        console.error("[RMSP] SubwayBuilderAPI não encontrada!");
        return;
    }
    var api = window.SubwayBuilderAPI;
    var CODE = "RMSP";

    function safe(fn) { try { fn(); } catch (e) { console.warn("[RMSP]", e); } }

    // 0) Shim de window.fetch para dois casos que, em cidade modada, geram
    //    erro no console:
    //    (a) map://paths/RMSP/<popId> — o jogo busca a geometria do trajeto de
    //        cada commuter; sem serviço de rotas para mods, dava 404. Devolvemos
    //        o drivingPath que já está no demand_data.
    //    (b) data:image/svg+xml — o deck.gl carrega os ícones dos marcadores
    //        (pinos de casa/trabalho) via fetch() de data: URI, mas a CSP do app
    //        (connect-src) não permite data:, então dava "Refused to connect" +
    //        "deck: Failed to fetch". Decodificamos o data: URI localmente e
    //        devolvemos um Response — sem conexão de rede, sem violar a CSP.
    safe(function () {
        if (typeof window.fetch !== "function" || typeof Response === "undefined") return;
        var prefix = "map://paths/" + CODE + "/";
        var _fetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            try {
                var url = (typeof input === "string") ? input : (input && input.url);
                if (url && url.indexOf(prefix) === 0) {
                    var popId = url.slice(prefix.length).split("?")[0];
                    var dm = api.gameState && api.gameState.getDemandData &&
                        api.gameState.getDemandData();
                    var pm = dm && dm.popsMap;
                    var pop = pm && (pm.get ? pm.get(popId) : pm[popId]);
                    var path = pop && pop.drivingPath;
                    if (path && path.length) {
                        return Promise.resolve(new Response(
                            JSON.stringify({ coordinates: path }),
                            { status: 200, headers: { "Content-Type": "application/json" } }
                        ));
                    }
                } else if (url && url.indexOf("data:") === 0) {
                    var comma = url.indexOf(",");
                    if (comma > 0) {
                        var meta = url.substring(5, comma);
                        var mime = meta.split(";")[0] || "text/plain";
                        var payload = url.substring(comma + 1);
                        var body;
                        if (/;base64/i.test(meta)) {
                            var bin = atob(payload);
                            body = new Uint8Array(bin.length);
                            for (var i = 0; i < bin.length; i++) body[i] = bin.charCodeAt(i);
                        } else {
                            body = decodeURIComponent(payload);
                        }
                        return Promise.resolve(new Response(body,
                            { status: 200, headers: { "Content-Type": mime } }));
                    }
                }
            } catch (e) { /* cai para o fetch original */ }
            return _fetch(input, init);
        };
    });

    try {
        // 1) Registro da cidade — enquadra a mancha central (Praça da Sé).
        api.registerCity({
            name: "São Paulo (RMSP)",
            code: CODE,
            description:
                "A maior metrópole do hemisfério sul. Mancha urbana central da " +
                "Grande São Paulo — capital, ABC, Guarulhos, Osasco e Diadema — " +
                "com ~17 mi de habitantes e ~8 mi de empregos. Demanda baseada na " +
                "Pesquisa Origem-Destino 2017 do Metrô.",
            population: 17400000,
            initialViewState: {
                zoom: 11,
                latitude: -23.5505,
                longitude: -46.6333,
                bearing: 0
            },
            minZoom: 9
        });

        // 2) Basemap vetorial (tiles PMTiles servidos localmente).
        //    Registrado ANTES dos dados e de forma SÍNCRONA, para entrar já no
        //    primeiro build de estilo do mapa — caso contrário o override troca
        //    a fonte "general-tiles" depois, num diff de estilo, e o MapLibre
        //    loga "source general-tiles not found" (transitório, porém ruidoso).
        //    Só ativa se o tile server local (build/serve_tiles.sh) estiver no ar.
        safe(function () {
            if (!(api.map && typeof api.map.setTileURLOverride === "function")) return;
            var base = "http://127.0.0.1:8080";
            var up = false;
            try {
                var xhr = new XMLHttpRequest();
                xhr.open("GET", base + "/RMSP/12/1518/2323.mvt", false); // síncrono
                xhr.send();
                up = true; // qualquer resposta = servidor no ar
            } catch (e) { up = false; }
            if (!up) {
                console.log("[RMSP] tile server offline — rode build/serve_tiles.sh " +
                    "para o basemap (ruas/prédios). Sem ele, o mapa base fica vazio.");
                return;
            }
            api.map.setTileURLOverride({
                cityCode: CODE,
                tilesUrl: base + "/RMSP/{z}/{x}/{y}.mvt",
                foundationTilesUrl: base + "/RMSP_foundations/{z}/{x}/{y}.mvt",
                maxZoom: 15  // = tileZoomLevel padrão da comunidade (railyard)
            });
            console.log("[RMSP] basemap local ativado (tiles em " + base + ")");
        });

        // 3) Arquivos de dados (servidos a partir da pasta data/ do mod).
        api.cities.setCityDataFiles(CODE, {
            demandData: "/data/RMSP/demand_data.json.gz",
            buildingsIndex: "/data/RMSP/buildings_index.json.gz",
            oceanDepthIndex: "/data/RMSP/ocean_depth_index.json.gz",
            roads: "/data/RMSP/roads.geojson.gz",
            runwaysTaxiways: "/data/RMSP/runways_taxiways.geojson.gz"
        });

        // 4) Visibilidade de camadas. CRÍTICO para a água aparecer: no estilo do
        //    jogo a camada "water" tem visibility = showOceanFoundations ? "none"
        //    : "visible". Ou seja, com oceanFoundations LIGADO (default), a água
        //    dos tiles fica ESCONDIDA. Desligamos (como os mapas da comunidade)
        //    para os rios/represas renderizarem a partir da camada "water".
        safe(function () {
            if (api.map && typeof api.map.setDefaultLayerVisibility === "function") {
                api.map.setDefaultLayerVisibility(CODE, {
                    oceanFoundations: false,
                    trackElevations: false
                });
            }
        });

        // 5) Aba "Brasil" no seletor de cidades (se suportado).
        safe(function () {
            if (api.cities && typeof api.cities.registerTab === "function") {
                api.cities.registerTab({
                    id: "brasil",
                    label: "Brasil",
                    emoji: "🇧🇷",
                    cityCodes: [CODE]
                });
            }
        });

        // 6) Sabor: boas-vindas e marcos de estações.
        safe(function () {
            if (!(api.hooks && typeof api.hooks.onGameInit === "function")) return;
            api.hooks.onGameInit(function () {
                try {
                    if (api.gameState && api.gameState.getCityCode &&
                        api.gameState.getCityCode() !== CODE) return;
                } catch (e) {}
                api.ui && api.ui.showNotification &&
                    api.ui.showNotification(
                        "Bem-vindo à RMSP! Milhões de paulistanos esperam o seu metrô.",
                        "success");
            });
        });

        safe(function () {
            if (!(api.hooks && typeof api.hooks.onStationBuilt === "function")) return;
            var n = 0;
            var marcos = {
                5: "5 estações! O começo de uma rede.",
                20: "20 estações — já dá pra cruzar o centro expandido.",
                50: "50 estações! Comparável ao metrô real de SP.",
                100: "100 estações — a RMSP (e o trânsito) agradece."
            };
            api.hooks.onStationBuilt(function () {
                n++;
                if (marcos[n]) {
                    api.ui && api.ui.showNotification &&
                        api.ui.showNotification(marcos[n], "success");
                }
            });
        });

        console.log("[RMSP] Mod carregado: cidade '" + CODE + "' registrada.");
    } catch (err) {
        console.error("[RMSP] Erro ao carregar o mod:", err);
    }
})();
