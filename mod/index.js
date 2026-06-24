// =====================================================================
//  RMSP — Região Metropolitana de São Paulo  |  Subway Builder mod
//  Registra a mancha urbana central da Grande São Paulo como cidade
//  jogável, com basemap vetorial e demanda real da Pesquisa OD do Metrô-SP.
//  Gerado pelo projeto rmsp-subway-builder (uv run rmsp ...).
//  Docs da API: https://www.subwaybuilder.com/docs/v1.0.0/api-reference/cities
// =====================================================================
(function () {
    "use strict";

    var api = window.SubwayBuilderAPI;
    if (!api) {
        console.error("[RMSP] SubwayBuilderAPI não encontrada!");
        return;
    }

    var CFG = {
        code: "RMSP",
        name: "São Paulo (RMSP)",
        tileHost: "http://127.0.0.1:8080"  // servidor de tiles local (rmsp serve / rmsp play)
    };

    function log(msg) { console.log("[RMSP] " + msg); }
    function safe(fn) { try { fn(); } catch (e) { console.warn("[RMSP]", e); } }

    // -----------------------------------------------------------------
    // Patches de runtime (não dependem da ordem de registro da cidade).
    // -----------------------------------------------------------------

    // Intercepta dois fetch que, em cidade modada, geram erro no console:
    //  (a) map://paths/<code>/<popId> — o jogo busca a geometria do trajeto de
    //      cada commuter; sem serviço de rotas para mods dava 404. Devolvemos o
    //      drivingPath que já está no demand_data.
    //  (b) data:image/svg+xml — o deck.gl carrega os ícones dos marcadores
    //      (pinos de casa/trabalho) via fetch() de data: URI, mas a CSP do app
    //      bloqueia data:. Decodificamos localmente e devolvemos um Response.
    function installFetchShim() {
        if (typeof window.fetch !== "function" || typeof Response === "undefined") return;
        var pathsPrefix = "map://paths/" + CFG.code + "/";
        var realFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            try {
                var url = (typeof input === "string") ? input : (input && input.url);
                if (url && url.indexOf(pathsPrefix) === 0) {
                    var popId = url.slice(pathsPrefix.length).split("?")[0];
                    var dm = api.gameState && api.gameState.getDemandData
                        && api.gameState.getDemandData();
                    var pm = dm && dm.popsMap;
                    var pop = pm && (pm.get ? pm.get(popId) : pm[popId]);
                    if (pop && pop.drivingPath && pop.drivingPath.length) {
                        return jsonResponse({ coordinates: pop.drivingPath });
                    }
                } else if (url && url.indexOf("data:") === 0) {
                    var res = dataUriResponse(url);
                    if (res) return res;
                }
            } catch (e) { /* cai para o fetch original */ }
            return realFetch(input, init);
        };
    }

    function jsonResponse(obj) {
        return Promise.resolve(new Response(JSON.stringify(obj),
            { status: 200, headers: { "Content-Type": "application/json" } }));
    }

    function dataUriResponse(url) {
        var comma = url.indexOf(",");
        if (comma <= 0) return null;
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

    // -----------------------------------------------------------------
    // Registro da cidade (ordem importa: city -> basemap -> dados -> camadas).
    // -----------------------------------------------------------------

    function registerCity() {
        api.registerCity({
            name: CFG.name,
            code: CFG.code,
            description:
                "A maior metrópole do hemisfério sul. Mancha urbana central da " +
                "Grande São Paulo — capital, ABC, Guarulhos, Osasco e Diadema — " +
                "com ~17 mi de habitantes e ~8 mi de empregos. Demanda baseada na " +
                "Pesquisa Origem-Destino do Metrô.",
            population: 17400000,
            initialViewState: { zoom: 11, latitude: -23.5505, longitude: -46.6333, bearing: 0 },
            minZoom: 9
        });
    }

    // Basemap vetorial: ativa o override só se o tile server local estiver no ar
    // (probe SÍNCRONO antes do primeiro build de estilo). Sem servidor, o jogo
    // roda normal e o mapa base fica vazio.
    function enableBasemap() {
        if (!(api.map && typeof api.map.setTileURLOverride === "function")) return;
        var base = CFG.tileHost;
        try {
            var xhr = new XMLHttpRequest();
            xhr.open("GET", base + "/RMSP/12/1518/2323.mvt", false);
            xhr.send();
        } catch (e) {
            log("tile server offline — rode `rmsp serve` para ver ruas/prédios.");
            return;
        }
        api.map.setTileURLOverride({
            cityCode: CFG.code,
            tilesUrl: base + "/RMSP/{z}/{x}/{y}.mvt",
            foundationTilesUrl: base + "/RMSP_foundations/{z}/{x}/{y}.mvt",
            maxZoom: 15
        });
        log("basemap local ativado (tiles em " + base + ")");
    }

    function setDataFiles() {
        api.cities.setCityDataFiles(CFG.code, {
            demandData: "/data/RMSP/demand_data.json.gz",
            buildingsIndex: "/data/RMSP/buildings_index.json.gz",
            oceanDepthIndex: "/data/RMSP/ocean_depth_index.json.gz",
            roads: "/data/RMSP/roads.geojson.gz",
            runwaysTaxiways: "/data/RMSP/runways_taxiways.geojson.gz"
        });
    }

    // CRÍTICO para a água aparecer: a camada "water" do jogo tem
    // visibility = showOceanFoundations ? "none" : "visible". Com oceanFoundations
    // ligado (default), os rios/represas dos tiles ficam escondidos.
    function fixWaterVisibility() {
        if (api.map && typeof api.map.setDefaultLayerVisibility === "function") {
            api.map.setDefaultLayerVisibility(CFG.code, {
                oceanFoundations: false,
                trackElevations: false
            });
        }
    }

    function registerBrasilTab() {
        if (api.cities && typeof api.cities.registerTab === "function") {
            api.cities.registerTab({
                id: "brasil", label: "Brasil", emoji: "🇧🇷", cityCodes: [CFG.code]
            });
        }
    }

    function installHooks() {
        var notify = function (msg) {
            api.ui && api.ui.showNotification && api.ui.showNotification(msg, "success");
        };
        var isThisCity = function () {
            try {
                return !(api.gameState && api.gameState.getCityCode
                    && api.gameState.getCityCode() !== CFG.code);
            } catch (e) { return true; }
        };
        if (api.hooks && typeof api.hooks.onGameInit === "function") {
            api.hooks.onGameInit(function () {
                if (isThisCity()) notify("Bem-vindo à RMSP! Milhões de paulistanos esperam o seu metrô.");
            });
        }
        if (api.hooks && typeof api.hooks.onStationBuilt === "function") {
            var milestones = {
                5: "5 estações! O começo de uma rede.",
                20: "20 estações — já dá pra cruzar o centro expandido.",
                50: "50 estações! Comparável ao metrô real de SP.",
                100: "100 estações — a RMSP (e o trânsito) agradece."
            };
            var n = 0;
            api.hooks.onStationBuilt(function () {
                n++;
                if (milestones[n]) notify(milestones[n]);
            });
        }
    }

    // -----------------------------------------------------------------
    installFetchShim();
    try {
        registerCity();
        safe(enableBasemap);
        setDataFiles();
        safe(fixWaterVisibility);
        safe(registerBrasilTab);
        safe(installHooks);
        log("Mod carregado: cidade '" + CFG.code + "' registrada.");
    } catch (err) {
        console.error("[RMSP] Erro ao carregar o mod:", err);
    }
})();
