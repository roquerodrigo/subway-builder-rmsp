"""Pontos de demanda especiais (aeroporto, parque, estádio, …) via depot.

Cada POI vira um ponto no ``demand_data.json`` cujo id é prefixado pelo código do tipo
(``AIR_GRU``, ``PRK_Ibirapuera``, …) — é esse prefixo que o jogo reconhece. ``add_points``
do depot liga o POI à população existente por um modelo de gravidade (decaimento com a
distância, ``exponent``): com ``residential_split=0`` o ponto é um ATRATOR (todos vão até
ele — jobs). Os pops criados saem sem rota (``drivingSeconds=0``) e são roteados no passo
de routing como qualquer outro pop.

Num mapa importado via Railyard os arquivos de special demand NÃO são membros do zip
(o validador só aceita config/demand/roads/…): a demanda especial viaja dentro do
``demand_data.json`` e os códigos presentes são declarados em ``config.json.specialDemandTypes``
(:func:`codes_present`).

A lista ``POIS`` reúne os principais POIs reais da RMSP em 21 dos tipos do depot (removidos os
de encaixe fraco em SP: port, bathhouse, resort, military_base). Capacidades/coords no próprio dict.
"""

from __future__ import annotations

import json
import logging
import os

from rmsp.config import settings

log = logging.getLogger(__name__)

# exponent de decaimento por tipo (peso ∝ residentes / distância^exp). Revisado e achatado
# para 0.5–1.2: os defaults altos do depot (convention_center 3.0, school 2.5, …) despejavam
# ~80% da demanda no único ponto residencial vizinho. Menor = catchment mais amplo (POIs que
# atraem da metrópole inteira: aeroporto, rodoviária, estádio, universidade, convenção).
_EXP = {
    "airport": 0.5, "outside_connection": 0.5, "heritage_site": 0.7, "events": 0.7,
    "convention_center": 0.8, "sports_facility": 0.8, "resort": 0.8, "port": 0.7,
    "amusement_park": 0.9, "aquarium": 0.9, "museum": 0.9, "zoo": 0.9, "university": 0.9,
    "natural_feature": 0.9, "shopping_center": 1.0, "hospital": 1.0, "cultural_center": 1.0,
    "government_facility": 1.0, "custom": 1.0, "military_base": 1.0, "bathhouse": 1.0,
    "religious_institution": 1.1, "library": 1.1, "park": 1.1, "school": 1.2,
}


def _poi(type_, name, code, lon, lat, capacity, pop_size=150, **extra):
    return {"type": type_, "name": name, "code": code, "location": [lon, lat],
            "total_capacity": capacity, "pop_size": pop_size,
            "exponent": _EXP[type_], **extra}


# POIs reais da RMSP, um por tipo (sports_facility com 3 estádios). Todos atratores
# (residential_split=0). Coordenadas [lon, lat] em WGS84, dentro do bbox da RMSP.
POIS = [
    _poi("airport", "Guarulhos", "GRU", -46.4731, -23.4356, 150000, 250,
         required_locs=[[-46.6388, -23.5475]]),           # liga ao Centro
    _poi("airport", "Congonhas", "CGH", -46.6556, -23.6266, 90000, 200),
    _poi("amusement_park", "Parque da Monica", "MONICA", -46.7016, -23.5735, 8000, 100),
    _poi("aquarium", "Aquario de Sao Paulo", "AQUASP", -46.6086, -23.5945, 6000, 100),
    _poi("convention_center", "Sao Paulo Expo", "SPEXPO", -46.6726, -23.6285, 30000, 150),
    _poi("cultural_center", "Centro Cultural SP", "CCSP", -46.6392, -23.5713, 12000, 120),
    _poi("custom", "Mercado Municipal", "MERCADAO", -46.6336, -23.5417, 20000, 150),
    _poi("government_facility", "Palacio Bandeirantes", "BANDGOV", -46.7219, -23.5962, 10000, 120),
    _poi("heritage_site", "Patio do Colegio", "PATIO", -46.6335, -23.5479, 8000, 100),
    _poi("hospital", "Hospital das Clinicas", "HCFMUSP", -46.6699, -23.5573, 35000, 150),
    _poi("library", "Biblioteca Mario de Andrade", "BMA", -46.6420, -23.5446, 6000, 100),
    _poi("museum", "MASP", "MASP", -46.6558, -23.5614, 8000, 100),
    _poi("natural_feature", "Pico do Jaragua", "JARAGUA", -46.7660, -23.4560, 5000, 100),
    _poi("outside_connection", "Rodoviaria Tiete", "TIETE", -46.6255, -23.5157, 40000, 200),
    _poi("park", "Parque Ibirapuera", "IBIRA", -46.6573, -23.5874, 40000, 200),
    _poi("religious_institution", "Catedral da Se", "SE", -46.6339, -23.5502, 12000, 120),
    _poi("school", "Colegio Bandeirantes", "BAND", -46.6392, -23.5877, 6000, 100),
    _poi("shopping_center", "Shopping Aricanduva", "ARICA", -46.5093, -23.5637, 60000, 250),
    _poi("sports_facility", "Allianz Parque", "ALLIANZ", -46.6785, -23.5275, 43000, 200),
    _poi("sports_facility", "Estadio do Morumbi", "MORUMBI", -46.7197, -23.6000, 67000, 250),
    _poi("sports_facility", "Neo Quimica Arena", "ITAQUERA", -46.4737, -23.5453, 49000, 200),
    _poi("university", "USP Cidade Universitaria", "USP", -46.7300, -23.5590, 90000, 250),
    _poi("events", "Autodromo de Interlagos", "INTERLAGOS", -46.6997, -23.7010, 60000, 250),
    _poi("zoo", "Zoologico de Sao Paulo", "ZOOSP", -46.6190, -23.6512, 12000, 150),

    # universidades
    _poi("university", "PUC-SP", "PUCSP", -46.6772, -23.5353, 20000, 150),
    _poi("university", "Mackenzie", "MACKENZIE", -46.6520, -23.5478, 40000, 200),
    _poi("university", "UNIFESP", "UNIFESP", -46.6440, -23.5985, 15000, 150),
    _poi("university", "USP Leste (EACH)", "USPLESTE", -46.5000, -23.4830, 10000, 150),
    _poi("university", "Universidade Sao Judas", "SAOJUDAS", -46.5930, -23.5820, 15000, 150),
    _poi("university", "FMU", "FMU", -46.6390, -23.5720, 20000, 150),

    # shoppings
    _poi("shopping_center", "Shopping Iguatemi SP", "IGUATEMI", -46.6931, -23.5762, 40000, 200),
    _poi("shopping_center", "Shopping Morumbi", "SHMORUMBI", -46.6980, -23.6230, 50000, 200),
    _poi("shopping_center", "Shopping Ibirapuera", "SHIBIRA", -46.6660, -23.6100, 40000, 200),
    _poi("shopping_center", "Shopping Center Norte", "CENTERNORTE", -46.6178, -23.5155, 50000, 200),
    _poi("shopping_center", "Shopping Analia Franco", "ANALIA", -46.5560, -23.5610, 35000, 150),
    _poi("shopping_center", "Shopping Villa-Lobos", "SHVILALOBOS", -46.7220, -23.5460, 30000, 150),
    _poi("shopping_center", "JK Iguatemi", "JKIGUATEMI", -46.6870, -23.6000, 30000, 150),
    _poi("shopping_center", "Shopping SP Market", "SPMARKET", -46.7070, -23.6640, 25000, 150),

    # parques
    _poi("park", "Parque Villa-Lobos", "PQVILALOBOS", -46.7230, -23.5460, 20000, 200),
    _poi("park", "Parque do Carmo", "PQCARMO", -46.4720, -23.5670, 15000, 150),
    _poi("park", "Horto Florestal", "HORTO", -46.6320, -23.4560, 8000, 100),
    _poi("park", "Parque da Juventude", "JUVENTUDE", -46.6250, -23.5060, 12000, 150),
    _poi("park", "Jardim Botanico", "JARDIMBOT", -46.6330, -23.6410, 8000, 100),
    _poi("park", "Parque do Povo", "PQPOVO", -46.6870, -23.5960, 10000, 120),

    # rodoviárias / conexões externas
    _poi("outside_connection", "Terminal Barra Funda", "BFUNDA", -46.6650, -23.5265, 35000, 200),
    _poi("outside_connection", "Terminal Jabaquara", "JABAQUARA", -46.6420, -23.6460, 30000, 200),

    # aeroportos
    _poi("airport", "Campo de Marte", "CDM", -46.6355, -23.5090, 20000, 150),
    # museus
    _poi("museum", "Pinacoteca do Estado", "PINA", -46.6335, -23.5340, 10000, 120),
    _poi("museum", "Museu do Ipiranga", "IPIRANGA", -46.6095, -23.5855, 10000, 120),
    _poi("museum", "MAM Ibirapuera", "MAM", -46.6560, -23.5878, 6000, 100),
    _poi("museum", "MAC-USP Ibirapuera", "MACUSP", -46.6540, -23.5882, 6000, 100),
    _poi("museum", "Museu Afro Brasil", "AFRO", -46.6580, -23.5842, 6000, 100),
    _poi("museum", "Museu Catavento", "CATAVENTO", -46.6260, -23.5460, 8000, 100),
    _poi("museum", "Museu do Futebol", "MUSFUT", -46.6660, -23.5470, 6000, 100),
    _poi("museum", "Farol Santander", "FAROL", -46.6345, -23.5462, 8000, 100),
    _poi("museum", "Japan House", "JAPANHOUSE", -46.6560, -23.5620, 5000, 100),
    # hospitais
    _poi("hospital", "Albert Einstein", "EINSTEIN", -46.7180, -23.5995, 30000, 150),
    _poi("hospital", "Sirio-Libanes", "SIRIO", -46.6510, -23.5560, 25000, 150),
    _poi("hospital", "Beneficencia Portuguesa", "BENEF", -46.6425, -23.5685, 25000, 150),
    _poi("hospital", "HCor", "HCOR", -46.6480, -23.5685, 15000, 120),
    _poi("hospital", "Oswaldo Cruz", "OSWALDO", -46.6420, -23.5720, 15000, 120),
    _poi("hospital", "ICESP", "ICESP", -46.6690, -23.5545, 15000, 120),
    _poi("hospital", "Hospital Samaritano", "SAMARIT", -46.6580, -23.5420, 12000, 120),
    # universidades
    _poi("university", "FGV-EAESP", "FGV", -46.6485, -23.5610, 15000, 150),
    _poi("university", "FAAP", "FAAP", -46.6600, -23.5430, 15000, 150),
    _poi("university", "UNINOVE Barra Funda", "UNINOVE", -46.6620, -23.5245, 25000, 150),
    _poi("university", "Belas Artes", "BELASARTES", -46.6410, -23.5765, 10000, 120),
    _poi("university", "Casper Libero", "CASPER", -46.6555, -23.5560, 8000, 120),
    _poi("university", "Anhembi Morumbi", "ANHEMBIM", -46.6900, -23.6010, 15000, 150),
    _poi("university", "Insper", "INSPER", -46.6870, -23.6000, 8000, 120),
    # shoppings
    _poi("shopping_center", "Shopping Cidade Jardim", "CIDJARDIM", -46.7020, -23.5920, 30000, 150),
    _poi("shopping_center", "Shopping Eldorado", "ELDORADO", -46.7016, -23.5732, 45000, 200),
    _poi("shopping_center", "Shopping Patio Paulista", "PATIOPAU", -46.6435, -23.5700, 30000, 150),
    _poi("shopping_center", "Shopping Cidade Sao Paulo", "CIDSP", -46.6560, -23.5615, 25000, 150),
    _poi("shopping_center", "Shopping Metro Tatuape", "TATUAPE", -46.5760, -23.5405, 40000, 200),
    _poi("shopping_center", "Shopping Bourbon", "BOURBON", -46.6825, -23.5250, 25000, 150),
    _poi("shopping_center", "Shopping Market Place", "MARKETPL", -46.6960, -23.6110, 25000, 150),
    _poi("shopping_center", "Shopping Santa Cruz", "SANTACRUZ", -46.6390, -23.5990, 25000, 150),
    _poi("shopping_center", "Shopping Plaza Sul", "PLAZASUL", -46.6280, -23.6180, 30000, 150),
    _poi("shopping_center", "Shopping Interlagos", "SHINTER", -46.6870, -23.6890, 30000, 150),
    # parques
    _poi("park", "Parque Trianon", "TRIANON", -46.6560, -23.5680, 8000, 100),
    _poi("park", "Parque da Agua Branca", "AGUABRANCA", -46.6810, -23.5245, 10000, 120),
    _poi("park", "Parque da Independencia", "INDEP", -46.6095, -23.5850, 12000, 120),
    _poi("park", "Parque Burle Marx", "BURLEMARX", -46.7225, -23.6320, 8000, 100),
    _poi("park", "Parque Alfredo Volpi", "VOLPI", -46.7185, -23.5960, 8000, 100),
    _poi("park", "Parque Ecologico do Tiete", "PETIETE", -46.5100, -23.4790, 10000, 120),
    # cultura
    _poi("cultural_center", "Sala Sao Paulo", "SALASP", -46.6395, -23.5348, 8000, 100),
    _poi("cultural_center", "SESC Pompeia", "SESCPOMP", -46.6873, -23.5265, 15000, 150),
    _poi("cultural_center", "SESC Paulista", "SESCPAU", -46.6540, -23.5615, 12000, 120),
    _poi("cultural_center", "SESC 24 de Maio", "SESC24", -46.6410, -23.5455, 15000, 150),
    _poi("cultural_center", "CCBB Sao Paulo", "CCBB", -46.6330, -23.5470, 8000, 100),
    _poi("cultural_center", "Itau Cultural", "ITAUCULT", -46.6547, -23.5680, 8000, 100),
    # patrimônio histórico
    _poi("heritage_site", "Theatro Municipal", "TEATROMUN", -46.6388, -23.5455, 8000, 100),
    _poi("heritage_site", "Estacao da Luz", "LUZ", -46.6355, -23.5350, 12000, 120),
    _poi("heritage_site", "Edificio Copan", "COPAN", -46.6440, -23.5462, 6000, 100),
    _poi("heritage_site", "Edificio Martinelli", "MARTINELLI", -46.6350, -23.5440, 6000, 100),
    # religião
    _poi("religious_institution", "Mosteiro Sao Bento", "SAOBENTO", -46.6335, -23.5390, 8000, 100),
    _poi("religious_institution", "Templo de Salomao", "SALOMAO", -46.6060, -23.5432, 12000, 120),
    _poi("religious_institution", "Santuario Sao Judas", "STJUDAS", -46.6390, -23.6255, 8000, 100),
    _poi("religious_institution", "Catedral Ortodoxa", "ORTODOXA", -46.6420, -23.5765, 5000, 100),
    _poi("religious_institution", "Mesquita Brasil", "MESQUITA", -46.6180, -23.5615, 4000, 100),
    # convenções
    _poi("convention_center", "Expo Center Norte", "EXPONORTE", -46.6178, -23.5150, 30000, 150),
    _poi("convention_center", "Anhembi", "ANHEMBI", -46.6383, -23.5140, 35000, 150),
    _poi("convention_center", "Transamerica Expo", "TRANSAM", -46.7085, -23.6350, 20000, 150),
    # eventos
    _poi("events", "Sambodromo do Anhembi", "SAMBODROMO", -46.6360, -23.5155, 30000, 150),
    _poi("events", "Espaco Unimed", "UNIMED", -46.6850, -23.5230, 20000, 150),
    _poi("events", "Vibra Sao Paulo", "VIBRA", -46.7050, -23.6250, 15000, 150),
    # esportes
    _poi("sports_facility", "Estadio do Pacaembu", "PACAEMBU", -46.6660, -23.5470, 20000, 150),
    _poi("sports_facility", "Ginasio do Ibirapuera", "GINIBIRA", -46.6470, -23.5905, 12000, 120),
    _poi("sports_facility", "Estadio do Caninde", "CANINDE", -46.6110, -23.5155, 15000, 120),
    _poi("sports_facility", "Jockey Club", "JOCKEY", -46.7000, -23.6010, 10000, 120),
    # governo
    _poi("government_facility", "Prefeitura de SP", "PREFSP", -46.6395, -23.5460, 12000, 120),
    _poi("government_facility", "Assembleia (ALESP)", "ALESP", -46.6425, -23.5900, 10000, 120),
    _poi("government_facility", "Forum Joao Mendes", "FORUM", -46.6360, -23.5510, 12000, 120),
    # bibliotecas
    _poi("library", "Biblioteca Villa-Lobos", "BIBVILA", -46.7250, -23.5460, 5000, 100),
    _poi("library", "Biblioteca Sao Paulo", "BIBSP", -46.6250, -23.5065, 5000, 100),
    # escolas
    _poi("school", "Colegio Sao Luis", "SAOLUIS", -46.6560, -23.5680, 5000, 100),
    _poi("school", "Colegio Objetivo", "OBJETIVO", -46.6470, -23.5510, 6000, 100),
    _poi("school", "Colegio Etapa", "ETAPA", -46.6360, -23.5760, 5000, 100),
    _poi("school", "Colegio Rio Branco", "RIOBRANCO", -46.6560, -23.5430, 5000, 100),
    # pontos icônicos / comércio de rua (custom)
    _poi("custom", "Rua 25 de Marco", "R25MARCO", -46.6318, -23.5410, 40000, 200),
    _poi("custom", "Rua Oscar Freire", "OSCARFREIRE", -46.6690, -23.5625, 15000, 150),
    _poi("custom", "Beco do Batman", "BECOBATMAN", -46.6890, -23.5540, 8000, 100),
    _poi("custom", "Liberdade", "LIBERDADE", -46.6350, -23.5580, 15000, 150),
    _poi("custom", "Bras", "BRAS", -46.6150, -23.5380, 20000, 150),
    # natureza
    _poi("natural_feature", "Represa Guarapiranga", "GUARAPIR", -46.7300, -23.6900, 8000, 100),
    _poi("natural_feature", "Serra da Cantareira", "CANTAREIRA", -46.6300, -23.4350, 6000, 100),
    # zoo / diversão
    _poi("zoo", "Zoo Safari", "ZOOSAFARI", -46.6120, -23.6555, 8000, 100),
    _poi("amusement_park", "KidZania", "KIDZANIA", -46.7016, -23.5732, 5000, 100),
]


def _taxonomy_codes() -> dict[str, str]:
    """{type_id: code} da taxonomia do depot (fonte da verdade dos códigos)."""
    import depot
    path = os.path.join(os.path.dirname(depot.__file__), "special_demand_types.json")
    with open(path, encoding="utf-8") as f:
        return {t["id"]: t["code"] for t in json.load(f)["types"] if t.get("code")}


def codes_present(demand_path=None) -> list[str]:
    """Códigos de special demand presentes no demand_data.json (prefixo do id dos points),
    para ``config.json.specialDemandTypes``. [] se não houver nenhum."""
    demand_path = demand_path or settings.build_dir / "demand_data.json"
    if not demand_path.exists():
        return []
    valid = set(_taxonomy_codes().values())
    with open(demand_path, encoding="utf-8") as f:
        demand = json.load(f)
    present = {p["id"].split("_", 1)[0] for p in demand["points"] if "_" in p["id"]}
    return sorted(present & valid)


def add_specials(pois=None) -> list[str]:
    """Injeta os POIs especiais no data/build/demand_data.json (in-place) via depot e
    reescreve o arquivo. Deve rodar sobre a demanda base ANTES do routing. Retorna os
    códigos adicionados."""
    from depot.demand import DemandData

    pois = POIS if pois is None else pois
    path = settings.build_dir / "demand_data.json"
    if not path.exists():
        raise RuntimeError(f"missing {path} — gere a demanda base primeiro")

    dd = DemandData(str(path), settings.code, outputdir=str(settings.build_dir), verb=False)
    before = len(dd["points"]), len(dd["pops"])
    dd.add_points(pois)
    dd.save()  # reescreve demand_data.json (+ schemas em build/.railyard_map/)
    after = len(dd["points"]), len(dd["pops"])

    codes = codes_present(path)
    log.info(
        "special demand: +%d pontos, +%d pops (%d POIs, códigos: %s)",
        after[0] - before[0], after[1] - before[1], len(pois), ", ".join(codes),
    )
    return codes
