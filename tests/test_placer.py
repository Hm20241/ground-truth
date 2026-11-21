"""Offline tests for 0.12.0: country placement of headlines and posts (gt/placer.py).
Never touches the network (sockets are blocked). Every headline below is invented for the test.

Run: python3 -I tests/test_placer.py
"""
import json
import os
import shutil
import socket
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
sys.path.insert(0, PROJ)
TMP = tempfile.mkdtemp(prefix="gt-placer-")
os.environ["GT_DATA"] = TMP


def no_network(*a, **k):
    raise AssertionError("network call in an offline test")


socket.socket.connect = no_network
socket.create_connection = no_network
from gt import geo, placer  # noqa: E402

ok = 0


def check(cond, what):
    global ok
    if not cond:
        print("FAIL:", what)
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(1)
    ok += 1
    print("ok  ", what)


def P(text, extra=None):
    return placer.place(text, extra)


def top(text, extra=None):
    c = P(text, extra)["countries"]
    return c[0] if c else None


def has(text, a3):
    return a3 in P(text)["countries"]


# ---------------- tables are sound ----------------
idx = placer.index()
codes = set(geo.country_shapes())
bad = sorted({c for e in list(idx["terms"].values()) + list(idx["stems"].values()) for c in e["codes"]} - codes)
check(not bad, "every code in the tables is a map shape (%s)" % (bad or "none bad"))
th = {e["theatre"] for e in list(idx["terms"].values()) + list(idx["stems"].values()) if e["theatre"]}
check(th <= set(geo.THEATRES), "every region theatre is a GT theatre")
check(len(idx["terms"]) > 1500, "index holds country names, demonyms, actors and places (%d terms)" % len(idx["terms"]))
r = P("Russian missile strikes on Kyiv kill five")
check(set(r) == {"countries", "theatre", "matched"} and json.loads(json.dumps(r)) == r, "result shape, JSON-safe")
check(P("") == {"countries": [], "theatre": None, "matched": []} and P(None)["countries"] == [], "empty text")

# ---------------- plain placement and strength order ----------------
check(r["countries"][:2] == ["UKR", "RUS"] and r["theatre"] == "ukraine-russia", "the city struck beats the demonym")
check(top("Israeli strike kills five in southern Lebanon") == "LBN", "'in southern Lebanon' is the place")
check(top("Turkey strikes PKK positions in northern Iraq") == "IRQ", "locative beats actor (PKK, Turkey)")
check(top("US strikes Houthis in Yemen") == "YEM", "US strike in Yemen -> YEM first")
check(top("US strikes Houthis") == "YEM", "tie: another country before the US")
check(P("US carrier enters South China Sea")["theatre"] == "indo-pacific", "US actor in a named sea: theatre from the sea")
check(P("Houthis claim attack on tanker in Red Sea")["countries"] == ["YEM"], "Houthis -> YEM")
check(top("Hezbollah fires rockets at Haifa") in ("ISR", "LBN") and has("Hezbollah fires rockets at Haifa", "LBN"),
      "Hezbollah -> LBN, Haifa -> ISR")
check(top("Kataib Hezbollah claims drone attack") == "IRQ", "Kataib Hezbollah is Iraqi, not Lebanese (longest phrase)")
check(top("Hamas says talks stalled") == "PSX" and top("Clashes in the West Bank city of Jenin") == "PSX",
      "Hamas / West Bank / Jenin -> PSX (the shapes' code)")
check(top("IDF says it struck a tunnel shaft") == "ISR" and top("IRGC navy seizes vessel") == "IRN", "IDF, IRGC")
check(top("RSF shells El Fasher again") == "SDN" and top("Sudanese army retakes Omdurman district") == "SDN",
      "RSF, El Fasher, Sudanese")
check(top("RSF says journalists face record jailings") is None, "RSF = Reporters Without Borders in a press story")
check(top("SAF drones hit RSF supply line in Darfur") == "SDN", "SAF counts once Sudan is named another way")
check(top("SAF announces new fighter jets") is None, "SAF alone is too ambiguous (Singapore, South Africa)")
check(top("M23 rebels seize Uvira") == "COD" and top("Al-Shabaab attack near Mogadishu") == "SOM", "M23, al-Shabaab")
r = P("JNIM claims ambush on convoy")
check(r["countries"] == ["MLI", "BFA"], "JNIM -> MLI then BFA")
check(top("Kremlin rejects ceasefire terms") == "RUS" and top("Pentagon orders more interceptors") == "USA",
      "Kremlin, Pentagon")
check(top("Zelensky meets European leaders") == "UKR", "Zelensky -> UKR")
check(top("Tatmadaw airstrike hits village in Sagaing") == "MMR" and top("Arakan Army takes base") == "MMR",
      "Tatmadaw, Sagaing, Arakan Army")
check(top("Myanmar junta extends emergency rule") == "MMR", "Myanmar junta")
check(top("Junta leaders meet") is None, "bare 'junta' places nothing")
check(top("PLA drills around Taiwan") == "TWN" and has("PLA drills around Taiwan", "CHN"), "PLA -> CHN, Taiwan -> TWN")
check(top("Sinaloa Cartel factions clash in Culiacan") == "MEX" and top("CJNG leader arrested") == "MEX", "cartels -> MEX")
check(top("Gunmen kill 12 in Culiacán") == "MEX", "accented city name")
check(top("Police raid in Port-au-Prince kills 34 gang members") == "HTI", "Port-au-Prince")
check(top("Viv Ansanm gangs attack Kenscoff") == "HTI", "Viv Ansanm, Kenscoff")
check(top("ELN attack in Catatumbo") == "COL" and top("Ecuador declares state of emergency in Guayaquil") == "ECU",
      "Colombia, Ecuador")
check(top("Pakistan says militants killed in North Waziristan") == "PAK" and top("Gunfight in Srinagar") == "IND",
      "Pakistan, India")
check(top("Kashmir attack kills tourists") == "IND", "Kashmir -> IND (theatre south-asia, not the KAS sliver)")
check(P("Kashmir attack kills tourists")["theatre"] == "south-asia", "Kashmir theatre")
check(top("Explosion reported in Goma") == "COD" and top("Bamako fuel blockade tightens") == "MLI", "Goma, Bamako")
check(top("Ouagadougou curfew") == "BFA" and top("Niamey suspends flights") == "NER", "Ouagadougou, Niamey")
check(top("Yangon blast") == "MMR" and top("Taipei scrambles jets") == "TWN" and top("Pyongyang fires missile") == "PRK",
      "Yangon, Taipei, Pyongyang")
check(top("Karachi police on alert") == "PAK" and top("Lahore smog") == "PAK", "Karachi, Lahore")
check(top("Aden port reopens") == "YEM" and top("Sanaa airport struck") == "YEM" and top("Sana'a airport struck") == "YEM",
      "Aden, Sanaa, Sana'a")
check(top("Belgorod under drone attack") == "RUS" and top("Kursk governor resigns") == "RUS", "Belgorod, Kursk")
check(top("Caracas denies troop buildup") == "VEN" and top("Bogotá talks resume") == "COL" and top("Quito") == "ECU",
      "Caracas, Bogotá, Quito")

# ---------------- Georgia ----------------
check(top("Atlanta, Georgia police arrest suspect") == "USA", "'Atlanta, Georgia' is the US state")
check(top("Georgia governor signs election bill") == "USA", "'Georgia governor' is the US state")
check(top("Georgia's governor declares emergency ahead of storm") == "USA", "'Georgia's governor'")
check(top("Fort Stewart, Georgia soldiers deploy") == "USA", "'Fort Stewart, Georgia'")
check(top("Georgia Senate runoff tightens") == "USA", "'Georgia Senate runoff'")
check(top("Russia warns Georgia over EU bid") in ("RUS", "GEO") and has("Russia warns Georgia over EU bid", "GEO") and
      not has("Russia warns Georgia over EU bid", "USA"), "Georgia with Russia/EU context is the country")
check(top("Protesters fill Tbilisi as Georgia's parliament votes") == "GEO", "Tbilisi + Georgia")
check(top("Tbilisi, Georgia rally draws thousands") == "GEO", "'Tbilisi, Georgia' is the country")
check(has("Armenia, Azerbaijan, Georgia sign corridor deal", "GEO") and
      not has("Armenia, Azerbaijan, Georgia sign corridor deal", "USA"), "a list of countries ending in Georgia")
check(top("Georgia election protests enter third week as Georgian Dream holds on") == "GEO",
      "'Georgia election' with Georgian Dream is the country")
check(top("Georgia expels diplomats") == "GEO", "bare Georgia defaults to the country")
check(has("Athens, Georgia", "USA") and not has("Athens, Georgia", "GRC"), "'Athens, Georgia' is not Greece")

# ---------------- Jordan, Chad, Guerrero (names) ----------------
check(top("Michael Jordan buys stake in team") is None, "Michael Jordan")
check(top("Rep. Jim Jordan subpoenas officials") is None, "Jim Jordan")
check(top("Jordan Bardella leads French polls") == "FRA" and not has("Jordan Bardella leads French polls", "JOR"),
      "Jordan Bardella (surname after)")
check(top("Jordan says it shot down drones over Amman") == "JOR", "Jordan the country, sentence case")
check(top("King Abdullah of Jordan meets Trump") == "JOR", "'of Jordan'")
check(top("Jordan's foreign minister visits Damascus") in ("JOR", "SYR") and
      has("Jordan's foreign minister visits Damascus", "JOR"), "possessive Jordan's")
check(top("Michael Jordan Says Game Was Rigged") is None, "title case: a known first name before Jordan")
check(not has("Jordan Signs New Gas Deal", "JOR"), "title case, no corroboration: Jordan dropped")
check(has("Jordan Intercepts Iranian Drones Over Amman", "JOR"), "title case, corroborated by Iranian/Amman")
check(top("Chad Daybell appeal denied") is None, "Chad Daybell")
check(top("Sudanese refugees cross into Chad") in ("TCD", "SDN") and has("Sudanese refugees cross into Chad", "TCD"),
      "Chad the country")
check(top("Chad's army repels Boko Haram attack") in ("TCD", "NGA") and has("Chad's army repels Boko Haram attack", "TCD"),
      "Chad's army")
check(not has("hanging chad debate returns", "TCD"), "lowercase chad")
check(P("Boko Haram attacks near Lake Chad")["theatre"] == "africa" and
      not has("Boko Haram attacks near Lake Chad", "TCD"), "Lake Chad is a region, Boko Haram -> NGA")
check(top("Gunmen kill police in Guerrero state") == "MEX" and top("Pedro Guerrero scores twice") is None,
      "Guerrero the state vs the surname")

# ---------------- Turkey, Guinea, Niger, Congo ----------------
check(top("Thanksgiving turkey prices soar") is None and not has("Trump Pardons Thanksgiving Turkey", "TUR"),
      "turkey the bird")
check(top("Wild Turkey Hunting Season Opens") is None, "title-case turkey hunting")
check(top("Turkey detains suspects after Istanbul blast") == "TUR", "Turkey the country")
check(top("Türkiye summons ambassador") == "TUR", "Türkiye")
check(top("Guinea junta sets vote date") == "GIN", "Guinea")
check(top("Guinea-Bissau coup attempt") == "GNB" and top("Equatorial Guinea vote") == "GNQ" and
      top("Papua New Guinea quake") == "PNG", "Guinea-Bissau / Equatorial Guinea / Papua New Guinea")
check(top("Guinea pigs used in lab study") is None and not has("Piracy rises in the Gulf of Guinea", "GIN"),
      "guinea pigs and the Gulf of Guinea")
check(P("Piracy rises in the Gulf of Guinea")["theatre"] == "africa", "Gulf of Guinea -> africa theatre")
check(top("Niger junta expels envoy") == "NER" and top("Nigeria deploys troops") == "NGA", "Niger vs Nigeria")
check(top("Oil spill in the Niger Delta") == "NGA", "Niger Delta is Nigeria")
check(top("Nigerien soldiers killed") == "NER" and top("Nigerian soldiers killed") == "NGA", "Nigerien vs Nigerian")
check(top("Fighting in Congo as rebels advance") == "COD", "bare Congo = DRC")
check(top("DRC and Rwanda sign deal") == "COD" and top("DR Congo") == "COD" and
      top("Democratic Republic of the Congo") == "COD", "DRC spellings")
check(top("Republic of Congo holds election in Brazzaville") == "COG" and top("Congo-Brazzaville") == "COG",
      "Republic of Congo / Brazzaville")

# ---------------- Korea ----------------
check(top("Korea tests missile, Pyongyang says") == "PRK", "Korea + Pyongyang -> PRK")
check(top("Korea exports rise for third month") == "KOR", "bare Korea -> KOR")
check(top("North Korea fires ballistic missile") == "PRK" and top("South Korea scrambles jets") == "KOR", "North/South")
check(top("DPRK launches satellite") == "PRK" and top("Korean exports rise") == "KOR", "DPRK; Korean -> KOR")
check(set(P("Tension on the Korean Peninsula")["countries"]) == {"KOR", "PRK"}, "Korean Peninsula -> both")
check(top("Korean troops fighting for Russia in Kursk, says Kim Jong Un") in ("PRK", "RUS") and
      not has("Korean troops fighting for Russia in Kursk, says Kim Jong Un", "KOR"), "Korean + Kim Jong Un -> PRK")

# ---------------- US vs us ----------------
check(top("US imposes new sanctions") == "USA" and top("U.S. imposes new sanctions") == "USA", "US, U.S.")
check(top("Let us pray for peace") is None and top("They told us nothing") is None, "lowercase 'us'")
check(top("JOIN US FOR LIVE UPDATES") is None and top("Follow Us On Telegram") is None, "'JOIN US', 'Follow Us'")
check(top("IRAN THREATENS US BASES") == "IRN" and has("IRAN THREATENS US BASES", "USA"), "all-caps US the country")
check(top("Aid worth US$5 million for Somalia") == "SOM" and not has("Aid worth US$5 million for Somalia", "USA"),
      "US$ is a currency")
check(top("Latin American leaders meet in Brasília") == "BRA" and
      not has("Latin American leaders meet in Brasília", "USA"), "Latin American is not American")
check(P("Latin America braces for storms")["theatre"] == "americas" and not P("Latin America braces")["countries"],
      "Latin America -> theatre only")
check(not has("Indian Ocean patrol", "IND") and has("Indian navy patrol", "IND"), "Indian Ocean vs Indian")
check(top("New Mexico wildfire spreads") == "USA" and not has("New Mexico wildfire spreads", "MEX"), "New Mexico")
check(top("New Jersey drones sighting") == "USA" and top("New South Wales floods") == "AUS", "New Jersey, New South Wales")
check(top("Paris, Texas tornado") == "USA" and not has("Paris, Texas tornado", "FRA"), "Paris, Texas")
check(top("Moscow, Idaho trial") == "USA" and not has("Moscow, Idaho trial", "RUS"), "Moscow, Idaho")
check(top("Northern Ireland talks") == "GBR" and not has("Northern Ireland talks", "IRL"), "Northern Ireland -> GBR")
check(not has("Chinese porcelain from china cabinets", "CHN") or top("fine china sale") is None, "lowercase china")
check(top("fine china sale") is None, "lowercase china is porcelain")

# ---------------- other languages, flags, extra ----------------
check(top("🇷🇺❌🇺🇦 — Smoke rises over Kiev after impacts") == "UKR", "flags + Kiev spelling")
check(set(P("🇮🇱🇱🇧 Update")["countries"]) == {"ISR", "LBN"}, "flag emoji alone")
check(top("Ракетный удар по Киеву, повреждены мосты") == "UKR", "Russian: Киеву")
check(top("Зеленський: Крим - це Україна") == "UKR", "Ukrainian: Крим, Україна")
check(top("Путин заявил о переговорах с США") in ("RUS", "USA") and has("Путин заявил о переговорах с США", "RUS"),
      "Russian: Путин, США")
check(not has("Латинская Америка готовится", "USA"), "Russian: Latin America is not the US")
check(top("Ataque armado en Culiacán, Sinaloa") == "MEX" and top("Estados Unidos deporta a venezolanos") in ("USA", "VEN"),
      "Spanish names")
check(has("Estados Unidos deporta a venezolanos", "VEN"), "Spanish demonym, any case")
r = P("Explosions heard overnight", "Officials in Kharkiv said a power plant was hit.")
check(r["countries"] == ["UKR"] and r["theatre"] == "ukraine-russia", "extra text places when the headline cannot")
r = P("Strike on Beirut suburb", "Israel said the target was a Hezbollah commander; Iran condemned it.")
check(r["countries"][0] == "LBN", "headline outweighs the summary")
check(P("Cabinet reshuffle announced")["theatre"] is None, "no place, no theatre")
check(P("Sahel jihadists expand south")["theatre"] == "africa" and P("Sahel jihadists")["countries"] == [],
      "Sahel -> theatre only")
r = P("Strikes hit Kharkiv and Odesa; Moscow denies")
check(r["matched"] == ["Kharkiv", "Odesa", "Moscow"], "matched terms in order, as written")

shutil.rmtree(TMP, ignore_errors=True)
print("%d checks passed" % ok)
