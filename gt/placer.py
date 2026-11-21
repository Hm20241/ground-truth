"""Country placement for headlines and posts. v1.0, 2026-11-20 (Ground Truth 0.12.0).

place(text) -> {"countries": [a3, ...] strongest first, "theatre": ..., "matched": [terms as written]}

Text is matched, word by word and longest phrase first, against:
* country names: Natural Earth names from gt/geo.py plus NAME_ALIASES, short forms (US, UK, DRC, UAE), a few
  Spanish names for the Infobae and Google News es-419 feeds;
* demonyms (Ukrainian, Haitian, Sudanese ...), actors (Houthi -> YEM, M23 -> COD, JNIM -> MLI + BFA, Kremlin -> RUS,
  PLA -> CHN, cartels -> MEX ...) and heads of government;
* about 600 capitals, conflict towns, regions, US states and Mexican states (constant tables below);
* a short list of Russian and Ukrainian stems (rybar, nexta_live and UkraineNow post in Cyrillic);
* flag emoji (Telegram posts start with them).
Seas and regions (Red Sea, Sahel, Latin America ...) give a theatre without a country.

Weights: a place or a country name counts 3, an actor 3, a demonym or a leader 2, a metonym (Washington, Trump) 1, a
flag 1.5; text passed as `extra` (a summary) counts half. Ties go to the earlier mention. The theatre is
geo.theatre_for_a3 of the strongest country.

False friends handled: Georgia the US state ("Atlanta, Georgia", "Georgia governor"), Jordan and Chad as names
("Michael Jordan", "Jim Jordan", "Chad Daybell"), turkey the bird, guinea pigs, Niger vs Nigeria (word boundaries,
"Niger Delta" -> NGA), Guinea vs Guinea-Bissau / Equatorial Guinea / Papua New Guinea (longest phrase wins), Congo
(bare "Congo" is the DRC, as in AP and Reuters style; Brazzaville / Republic of Congo is COG), Korea (KOR unless the
text names Pyongyang, DPRK, Kim Jong Un or North Korea), US vs "us" (acronyms must match case; "JOIN US" and "US$"
are not the US), New Mexico / New Jersey / New South Wales, and "Paris, Texas"-style US towns. Proper nouns must be
capitalised in the text, so "china" (porcelain) and "chad" (paper) never match. Palestine is PSX, the code the map
shapes use (geo.MIDEAST has both).

Stdlib only; the index is built on first use from gt/geo.py's shapes (about 0.3 s).
"""
import re
import threading

from . import geo

VERSION = "1.0"

W_NAME, W_PLACE, W_ACTOR, W_DEMONYM, W_PERSON, W_METONYM, W_FLAG, W_REGION = 3.0, 3.0, 3.0, 2.0, 2.0, 1.0, 1.5, 1.0
LOC_BONUS = 1.5      # "in Iraq", "on Kyiv", "near northern Gaza": the place where it happened beats the actor
EXTRA_FACTOR = 0.5   # weight of the `extra` text (summary) relative to the main text (headline)
SECOND_CODE = 0.8    # weight of the 2nd+ country of a multi-country term (JNIM -> MLI, BFA)
MAX_COUNTRIES = 6

# ---------------- tables ----------------
# One entry per line: "CODES: term, term, ...". CODES is A3[+A3...], "@theatre" (no country) or "-" (consume the words,
# no country, no theatre). A term written with a leading lowercase letter matches any case; an all-capitals term of
# up to 6 letters, or one with a digit, must match exactly (IDF, US, M23); any other term must start with a capital in
# the text. A trailing "*" makes the last word a prefix (Russian and Spanish endings).

NAMES = """
USA: United States, United States of America, US, U.S., U.S.A., USA, America, Estados Unidos, EEUU, EE.UU., EE. UU.
GBR: UK, U.K., Britain, Great Britain, England, Scotland, Wales, Northern Ireland, Reino Unido
NLD: Holland
CIV: Ivory Coast, Cote d'Ivoire
COD: Congo, DRC, DR Congo, D.R. Congo, Democratic Republic of Congo, Democratic Republic of the Congo, Congo-Kinshasa,
    RDC, RD Congo, DR of Congo
COG: Republic of Congo, Republic of the Congo, Congo Republic, Congo-Brazzaville, Congo Brazzaville
TLS: East Timor
ARE: UAE, U.A.E., Emirates
SAU: KSA, Arabia Saudita
PSX: Palestine, Palestinian territories, Occupied Palestinian Territory, Gaza, Gaza Strip, West Bank, Cisjordania,
    Franja de Gaza
CHN: PRC, Mainland China, People's Republic of China
PRK: DPRK, North Korea, N. Korea, N Korea, Corea del Norte
KOR: ROK, South Korea, S. Korea, Corea del Sur
KOR+PRK: Korean Peninsula, Koreas, North and South Korea
TUR: Turkiye, Turquia
SWZ: Swaziland
MKD: Macedonia
MDA: Moldavia, Transnistria
BLR: Belorussia
AZE: Nagorno-Karabakh, Karabakh
GEO: Abkhazia, South Ossetia
UKR: Crimea, Ucrania
RUS: Russian Federation, Rusia
IRQ: Kurdistan, Iraqi Kurdistan, Kurdistan Region, Irak
SYR: Rojava, Siria
IND: Kashmir, Jammu and Kashmir, Indian-administered Kashmir, Siachen
PAK: Azad Kashmir, Pakistan-administered Kashmir
IND+PAK: Line of Control
VAT: Holy See
JOR: Jordania
BRA: Brasil
ESP: Espana
DEU: Alemania
FRA: Francia
JPN: Japon
EGY: Egipto
LBN: Libano
AFG: Afganistan
ZAF: Sudafrica
MAR: Marruecos
PHL: Filipinas
GRL: Groenlandia
DOM: Republica Dominicana
"""

# Theatre-only and swallowed phrases. "Latin America" must not read as the US, nor "Indian Ocean" as India.
REGIONS = """
@middle-east: Middle East, Mideast, Gulf states, Levant, Arab, Arab League, Red Sea, Gulf of Aden, Bab el-Mandeb,
    Bab al-Mandab, Strait of Hormuz, Hormuz, Persian Gulf, Arabian Gulf, Gulf of Oman, Kurdish, Kurds, Medio Oriente,
    Oriente Medio
@indo-pacific: Asia, Asian, Asia-Pacific, Asia Pacific, Indo-Pacific, Pacific, Southeast Asia, Southeast Asian,
    East Asia, East Asian, South China Sea, East China Sea, Taiwan Strait, Sea of Japan, Yellow Sea, Spratly,
    Spratlys, Spratly Islands, Paracel, Paracels, Paracel Islands, ASEAN
@south-asia: South Asia, South Asian, Central Asia, Central Asian
@ukraine-russia: Black Sea, Sea of Azov
@europe-nato: Europe, European, European Union, EU, NATO, Baltic, Baltics, Baltic Sea, Balkans, Caucasus,
    South Caucasus, North Sea, Barents Sea, Nordic, Europa
@americas: Latin America, Latin American, South America, South American, Central America, Central American,
    North America, North American, Caribbean, Americas, Gulf of Mexico, Gulf of America, America Latina,
    Latinoamerica, Sudamerica, Centroamerica
@africa: Africa, African, Sahel, Horn of Africa, Gulf of Guinea, Lake Chad, West Africa, East Africa, Sahara,
    sub-Saharan, African Union, ECOWAS, Africa Occidental
-: Indian Ocean, Atlantic, Atlantic Ocean, Arctic, Antarctic, New England, Chicken Kiev, Turkey Day
"""

DEMONYMS = """
USA: American, estadounidense*
GBR: British, Briton, Scottish, Welsh
IRL: Irish
FRA: French
DEU: German
NLD: Dutch
BEL: Belgian
ESP: Spanish
PRT: Portuguese
ITA: Italian
GRC: Greek
CHE: Swiss
AUT: Austrian
POL: Polish
CZE: Czech
SVK: Slovak
HUN: Hungarian
ROU: Romanian
BGR: Bulgarian
SRB: Serbian, Serb
HRV: Croatian
BIH: Bosnian
KOS: Kosovar
ALB: Albanian
LTU: Lithuanian
LVA: Latvian
EST: Estonian
FIN: Finnish
SWE: Swedish
NOR: Norwegian
DNK: Danish
ISL: Icelandic
GRL: Greenlandic
UKR: Ukrainian
RUS: Russian, Chechen
BLR: Belarusian, Belarussian
MDA: Moldovan
GEO: Georgian
ARM: Armenian
AZE: Azerbaijani, Azeri
TUR: Turkish
CYP: Cypriot
ISR: Israeli
PSX: Palestinian
LBN: Lebanese
SYR: Syrian, Alawite
JOR: Jordanian
IRQ: Iraqi
IRN: Iranian
SAU: Saudi
ARE: Emirati
QAT: Qatari
KWT: Kuwaiti
BHR: Bahraini
OMN: Omani
YEM: Yemeni
EGY: Egyptian
LBY: Libyan
TUN: Tunisian
DZA: Algerian
MAR: Moroccan
SAH: Sahrawi
MRT: Mauritanian
SDN: Sudanese
SDS: South Sudanese
ETH: Ethiopian
ERI: Eritrean
SOM: Somali
DJI: Djiboutian
KEN: Kenyan
UGA: Ugandan
RWA: Rwandan
BDI: Burundian
COD: Congolese
TZA: Tanzanian
MOZ: Mozambican
ZWE: Zimbabwean
ZMB: Zambian
MWI: Malawian
MDG: Malagasy
AGO: Angolan
NAM: Namibian
ZAF: South African
NGA: Nigerian
NER: Nigerien
MLI: Malian
BFA: Burkinabe
TCD: Chadian
CMR: Cameroonian
CAF: Central African
GAB: Gabonese
GHA: Ghanaian
CIV: Ivorian
SEN: Senegalese
GIN: Guinean
GNQ: Equatorial Guinean
GNB: Bissau-Guinean
PNG: Papua New Guinean
LBR: Liberian
SLE: Sierra Leonean
TGO: Togolese
BEN: Beninese
AFG: Afghan
PAK: Pakistani, Baloch, Baluch
IND: Indian, Kashmiri
BGD: Bangladeshi
LKA: Sri Lankan
NPL: Nepali, Nepalese
KAZ: Kazakh
UZB: Uzbek
KGZ: Kyrgyz
TJK: Tajik
TKM: Turkmen
CHN: Chinese, Uyghur, Uighur, Tibetan
TWN: Taiwanese
JPN: Japanese
PRK: North Korean
KOR: South Korean
PHL: Filipino, Philippine
VNM: Vietnamese
KHM: Cambodian
THA: Thai
LAO: Laotian
MMR: Burmese, Rohingya
MYS: Malaysian
SGP: Singaporean
IDN: Indonesian
AUS: Australian
NZL: New Zealander
MNG: Mongolian
CAN: Canadian
MEX: Mexican, mexican*
GTM: Guatemalan, guatemaltec*
HND: Honduran, hondurenn*, hondureno*, hondurena*
SLV: Salvadoran, Salvadorean, salvadoreno*, salvadorena*
NIC: Nicaraguan, nicaraguens*
CRI: Costa Rican, costarricens*
PAN: Panamanian, panameno*, panamena*
CUB: Cuban, cubano*, cubana*
HTI: Haitian, haitian*
DOM: Dominican
JAM: Jamaican
VEN: Venezuelan, venezolan*
COL: Colombian, colombian*
ECU: Ecuadorian, Ecuadorean, ecuatorian*
PER: Peruvian, peruano*, peruana*
BOL: Bolivian, bolivian*
CHL: Chilean, chileno*, chilena*
ARG: Argentine, Argentinian, argentino*, argentina*
BRA: Brazilian, brasileno*, brasilena*
URY: Uruguayan
PRY: Paraguayan
GUY: Guyanese
PRI: Puerto Rican
TTO: Trinidadian
"""

ACTORS = """
YEM: Houthi, Houthis, Huthi, Huthis, Ansar Allah, Ansarallah
LBN: Hezbollah, Hizbollah, Hizbullah, Hizballah, UNIFIL
IRQ: Kataib Hezbollah, Kata'ib Hezbollah, Popular Mobilization Forces, Popular Mobilisation Forces, PMF, Hashd,
    Islamic Resistance in Iraq
PSX: Hamas, Islamic Jihad, Palestinian Islamic Jihad, Qassam Brigades, al-Qassam, Palestinian Authority,
    Philadelphi Corridor, Netzarim Corridor
ISR: IDF, Israel Defense Forces, Israel Defence Forces, Israeli Air Force, Shin Bet, Mossad, Knesset, Israel Katz
IRN: IRGC, Revolutionary Guard, Revolutionary Guards, Quds Force, Basij
SDN: Rapid Support Forces, Sudanese Armed Forces, RSF
COD: M23, AFC/M23, FARDC, Allied Democratic Forces, CODECO, Wazalendo, MONUSCO
SOM: al-Shabaab, al-Shabab, al Shabaab, al Shabab, Shabaab, AUSSOM, AMISOM, ATMIS
MLI+BFA: JNIM, Jama'at Nusrat al-Islam wal-Muslimin
NGA: Boko Haram, ISWAP, Islamic State West Africa Province
AFG: Taliban
PAK: TTP, Pakistani Taliban, Tehrik-i-Taliban, Tehreek-e-Taliban, Baloch Liberation Army, BLA, Lashkar-e-Taiba,
    Jaish-e-Mohammed, ISPR
SYR: Hayat Tahrir al-Sham, Syrian Democratic Forces, YPG
TUR+IRQ: PKK
SAH: Polisario
ETH: TPLF, Fano, Tigray People's Liberation Front
COL: ELN, FARC, Clan del Golfo, Gulf Clan, Segunda Marquetalia
VEN: Tren de Aragua, Cartel de los Soles
SLV: MS-13, Barrio 18
HTI: Viv Ansanm, Gang Suppression Force, Gran Grif
MEX: Sinaloa Cartel, Cartel de Sinaloa, Chapitos, Los Chapitos, CJNG, Jalisco Cartel, Jalisco New Generation Cartel,
    Cartel Jalisco Nueva Generacion, Gulf Cartel, Cartel del Golfo, Zetas, Los Zetas, Familia Michoacana,
    La Familia Michoacana, Cartel del Noreste, Mayo Zambada, El Mencho, Sedena, SEDENA, Guardia Nacional
ECU: Los Lobos, Los Choneros
BRA: Comando Vermelho
MMR: Tatmadaw, Arakan Army, Kachin Independence Army, Karen National Union, KNU, National Unity Government, NUG,
    People's Defence Force, Three Brotherhood Alliance, MNDAA, TNLA
CHN: PLA, People's Liberation Army, PLA Navy, CCP
RUS: FSB, GRU, Rosgvardia, Roscosmos, Rosatom, Africa Corps
UKR: SBU, GUR, HUR, ZSU, AFU, Azov, Ukrenergo, Naftogaz, Energoatom
USA: CENTCOM, INDOPACOM, AFRICOM, SOUTHCOM, EUCOM, NORTHCOM, US military, U.S. military
"""

# Seats of government: they name the actor more than the place, so they count 2.
SEATS = """
RUS: Kremlin
USA: Pentagon, White House
GBR: Downing Street, Whitehall
FRA: Elysee
CHN: Zhongnanhai
ISR: Knesset
UKR: Verkhovna Rada
"""

# Weak acronyms that count only when the same country is named another way in the text.
CORROBORATE = """
SDN: SAF
SYR: SDF, HTS
COD+UGA: ADF
BRA: PCC
PAK: LeT
"""

PEOPLE = """
UKR: Zelensky, Zelenskyy, Zelenskiy, Zelenskyi, Klitschko, Syrskyi, Syrsky, Budanov, Umerov, Yermak, Svyrydenko,
    Sybiha
RUS: Putin, Peskov, Lavrov, Shoigu, Gerasimov, Belousov, Medvedev, Kadyrov, Zakharova, Dmitriev, Ushakov
ISR: Netanyahu, Smotrich, Ben-Gvir, Ben Gvir, Isaac Herzog, Eyal Zamir, Gideon Saar, Sa'ar
IRN: Khamenei, Pezeshkian, Araghchi, Larijani
TUR: Erdogan, Hakan Fidan
CHN: Xi, Xi Jinping, Wang Yi, Li Qiang, Dong Jun
PRK: Kim Jong Un, Kim Jong-un, Kim Yo Jong, Kim Yo-jong
IND: Modi, Narendra Modi, Jaishankar, Rajnath Singh
PAK: Shehbaz Sharif, Asim Munir, Ishaq Dar
VEN: Maduro, Diosdado Cabello, Padrino Lopez
COL: Gustavo Petro
MEX: Sheinbaum, Claudia Sheinbaum, Harfuch, Garcia Harfuch
SLV: Bukele
ECU: Noboa
ARG: Milei
BRA: Lula, Lula da Silva
CUB: Diaz-Canel
NIC: Daniel Ortega, Rosario Murillo
HTI: Cherizier, Jimmy Cherizier, Barbecue Cherizier, Fils-Aime
SDN: Burhan, al-Burhan, Hemedti, Dagalo
COD: Tshisekedi, Kabila
RWA: Kagame
KEN: Ruto
NGA: Tinubu
ZAF: Ramaphosa
UGA: Museveni
ETH: Abiy, Abiy Ahmed
SDS: Salva Kiir
BFA: Ibrahim Traore
MLI: Goita, Assimi Goita
NER: Tchiani
BLR: Lukashenko
AZE: Aliyev
ARM: Pashinyan
SYR: al-Sharaa, Sharaa, Jolani, Julani, Assad
LBN: Naim Qassem, Nasrallah, Joseph Aoun, Nawaf Salam
PSX: Sinwar, Mahmoud Abbas
TWN: Lai Ching-te, William Lai
PHL: Ferdinand Marcos, Marcos Jr, Bongbong Marcos
MMR: Min Aung Hlaing, Aung San Suu Kyi, Suu Kyi
GBR: Starmer, Keir Starmer
FRA: Macron
DEU: Merz
ITA: Meloni
POL: Tusk, Nawrocki
HUN: Orban
KOR: Lee Jae-myung, Lee Jae Myung
JPN: Takaichi, Ishiba
AUS: Anthony Albanese
CAN: Mark Carney
IDN: Prabowo
SAU: Mohammed bin Salman, MBS
EGY: Sisi, el-Sisi
LBY: Haftar
SOM: Hassan Sheikh Mohamud
"""

METONYMS = """
USA: Washington, Trump, Rubio, Hegseth, Vance, Witkoff, Congress, Capitol Hill, Трамп*, Вашингтон*
BEL: Brussels
"""

PLACES = """
UKR: Kyiv, Kiev, Kharkiv, Kharkov, Odesa, Odessa, Dnipro, Dnepr, Dnipropetrovsk, Dnepropetrovsk, Zaporizhzhia,
    Zaporizhia, Zaporozhye, Kherson, Mykolaiv, Nikolaev, Lviv, Lvov, Sumy, Chernihiv, Chernigov, Poltava, Vinnytsia,
    Vinnitsa, Zhytomyr, Zhitomir, Kryvyi Rih, Krivoy Rog, Donetsk, Luhansk, Lugansk, Donbas, Donbass, Pokrovsk,
    Krasnoarmeysk, Myrnohrad, Kupiansk, Kupyansk, Bakhmut, Artemovsk, Avdiivka, Kramatorsk, Sloviansk, Slavyansk,
    Kostiantynivka, Konstantinovka, Huliaipole, Gulyaipole, Vovchansk, Volchansk, Siversk, Seversk, Chasiv Yar,
    Toretsk, Mariupol, Melitopol, Berdiansk, Berdyansk, Enerhodar, Energodar, Nova Kakhovka, Kakhovka, Sevastopol,
    Simferopol, Kerch, Crimean Bridge, Kerch Bridge, Zhovti Vody, Izium, Izyum, Vuhledar, Ugledar, Kurakhove,
    Kurakhovo, Velyka Novosilka, Orikhiv, Stepnohirsk, Bucha, Irpin, Kremenchuk, Cherkasy, Kropyvnytskyi,
    Khmelnytskyi, Rivne, Lutsk, Ternopil, Ivano-Frankivsk, Uzhhorod, Chernivtsi, Starokostiantyniv, Burshtyn, Lyman,
    Kupiansk-Vuzlovyi, Zaporizhzhia Nuclear Power Plant
RUS: Moscow, St Petersburg, St. Petersburg, Saint Petersburg, Belgorod, Bryansk, Kursk, Voronezh, Rostov,
    Rostov-on-Don, Krasnodar, Novorossiysk, Tuapse, Sochi, Taganrog, Yeysk, Engels, Saratov, Volgograd, Samara,
    Ryazan, Tambov, Lipetsk, Oryol, Tula, Kaluga, Smolensk, Pskov, Kaliningrad, Murmansk, Severomorsk, Olenya,
    Olenegorsk, Mozdok, Morozovsk, Millerovo, Kazan, Tatarstan, Yelabuga, Alabuga, Bashkortostan, Ufa, Perm, Orenburg,
    Chelyabinsk, Yekaterinburg, Novosibirsk, Vladivostok, Khabarovsk, Chechnya, Grozny, Dagestan, Makhachkala,
    Ust-Luga, Primorsk, Yaroslavl, Nizhny Novgorod, Tver, Novocherkassk, Kstovo, Syzran, Afipsky, Siberia, Kamchatka,
    Sakhalin, Arkhangelsk
UKR+RUS: Kerch Strait
BLR: Minsk
MDA: Chisinau, Tiraspol
GEO: Tbilisi, Batumi, Kutaisi
ARM: Yerevan
AZE: Baku, Stepanakert
IRN: Tehran, Isfahan, Esfahan, Natanz, Fordow, Fordo, Bandar Abbas, Tabriz, Mashhad, Shiraz, Kharg, Kharg Island,
    Kermanshah, Ahvaz, Bushehr, Qom, Chabahar, Zahedan, Parchin
IRQ: Baghdad, Erbil, Irbil, Mosul, Basra, Kirkuk, Sulaymaniyah, Anbar, Ain al-Asad, Fallujah, Najaf, Karbala
SYR: Damascus, Aleppo, Idlib, Homs, Hama, Latakia, Tartus, Deir ez-Zor, Deir el-Zour, Deir ez-Zour, Raqqa, Daraa,
    Sweida, Suwayda, Quneitra, Qamishli, Palmyra, Kobani, Manbij
ISR+SYR: Golan, Golan Heights
LBN: Beirut, Tyre, Sidon, Baalbek, Nabatieh, Bekaa, Beqaa, Litani, Dahiyeh, Dahieh, Marjayoun, Bint Jbeil
PSX: Gaza City, Khan Younis, Khan Yunis, Rafah, Jabalia, Jabaliya, Deir al-Balah, Nuseirat, Beit Lahia, Beit Hanoun,
    Jenin, Nablus, Ramallah, Hebron, Tulkarm, Tubas, Qalqilya, Bethlehem, Jericho, East Jerusalem, Mawasi, al-Mawasi,
    Jordan Valley
ISR: Jerusalem, Tel Aviv, Haifa, Eilat, Ashkelon, Ashdod, Sderot, Negev, Dimona, Beersheba, Netanya, Nahariya,
    Kiryat Shmona, Metula, Ben Gurion Airport, Galilee
YEM: Sanaa, Sana'a, Aden, Hodeidah, Hudaydah, Marib, Taiz, Saada, Mukalla, Ras Isa, Hadramout, Hadramawt
SAU: Riyadh, Jeddah, Abqaiq, Ras Tanura, Dammam, Mecca
ARE: Abu Dhabi, Dubai, Fujairah
QAT: Doha, Al Udeid
BHR: Manama
OMN: Muscat, Duqm, Salalah
KWT: Kuwait City
JOR: Amman, Aqaba, Hashemite Kingdom of Jordan
EGY: Cairo, Sinai, Suez, Suez Canal, Alexandria, Port Said, Ismailia
TUR: Ankara, Istanbul, Incirlik, Izmir, Diyarbakir, Hatay, Gaziantep
CYP: Nicosia, Limassol, Akrotiri
SDN: Khartoum, Omdurman, El Fasher, El-Fasher, al-Fashir, Al Fashir, Fasher, Darfur, North Darfur, Kordofan,
    North Kordofan, South Kordofan, El Obeid, Port Sudan, Kassala, Gezira, Wad Madani, Nyala, Babanusa, Kadugli,
    Dilling, Tawila, Zamzam, El Geneina, Geneina
SDS: Juba, Malakal, Upper Nile, Jonglei
ETH: Addis Ababa, Tigray, Mekelle, Amhara, Oromia, Bahir Dar
ERI: Asmara
SOM: Mogadishu, Puntland, Jubaland, Baidoa, Kismayo, Beledweyne, Bosaso, Galmudug, Hirshabelle
SOL: Hargeisa, Berbera
KEN: Nairobi, Mombasa, Lamu, Garissa, Mandera
UGA: Kampala
RWA: Kigali
BDI: Bujumbura, Gitega
COD: Goma, Bukavu, Kinshasa, North Kivu, South Kivu, Kivu, Ituri, Bunia, Uvira, Butembo, Rutshuru, Masisi, Walikale,
    Kisangani, Lubumbashi, Minembwe
COG: Brazzaville, Pointe-Noire
CAF: Bangui
TCD: N'Djamena, Ndjamena, Abeche
MLI: Bamako, Timbuktu, Gao, Kidal, Mopti, Menaka, Kayes, Segou, Sikasso, Nioro
BFA: Ouagadougou, Djibo, Bobo-Dioulasso, Fada N'Gourma, Barsalogho
NER: Niamey, Tillaberi, Agadez, Diffa, Tahoua, Zinder, Maradi
NGA: Abuja, Lagos, Maiduguri, Borno, Zamfara, Kaduna, Katsina, Sokoto, Benue, Kano, Yobe, Adamawa, Niger Delta,
    Niger State, Plateau State, Kwara, Port Harcourt, Kebbi
CMR: Yaounde, Douala, Bamenda, Ambazonia
SEN: Dakar
GIN: Conakry
GNB: Bissau
SLE: Freetown
LBR: Monrovia
CIV: Abidjan, Yamoussoukro
GHA: Accra, Kumasi
TGO: Lome
BEN: Cotonou, Porto-Novo
MRT: Nouakchott
LBY: Tripoli, Benghazi, Misrata, Sirte, Derna, Tobruk
TUN: Tunis
DZA: Algiers
MAR: Rabat, Casablanca, Marrakech
SAH: Laayoune
MOZ: Maputo, Cabo Delgado, Mocimboa da Praia
ZAF: Pretoria, Johannesburg, Cape Town, Durban
ZWE: Harare
ZMB: Lusaka
MWI: Lilongwe
MDG: Antananarivo
TZA: Dodoma, Dar es Salaam, Zanzibar
AGO: Luanda
NAM: Windhoek
BWA: Gaborone
AFG: Kabul, Kandahar, Herat, Mazar-i-Sharif, Jalalabad, Bagram, Panjshir, Khost, Kunar, Nangarhar, Helmand, Paktika
PAK: Islamabad, Rawalpindi, Karachi, Lahore, Peshawar, Quetta, Balochistan, Baluchistan, Khyber Pakhtunkhwa,
    Waziristan, North Waziristan, South Waziristan, Bannu, Gwadar, Gilgit, Gilgit-Baltistan, Muzaffarabad, Bahawalpur,
    Muridke, Multan, Faisalabad, Sindh, Kurram
IND: New Delhi, Delhi, Mumbai, Srinagar, Jammu, Pahalgam, Ladakh, Manipur, Kolkata, Chennai, Bengaluru, Bangalore,
    Amritsar, Pathankot, Poonch, Rajouri, Kupwara, Arunachal Pradesh, Assam, Chhattisgarh, Bastar, Galwan, Andaman
BGD: Dhaka, Chittagong, Chattogram, Cox's Bazar
LKA: Colombo
NPL: Kathmandu
BTN: Thimphu
KAZ: Astana, Almaty, Baikonur
UZB: Tashkent
KGZ: Bishkek
TJK: Dushanbe
TKM: Ashgabat
CHN: Beijing, Shanghai, Xinjiang, Tibet, Lhasa, Fujian, Guangdong, Shenzhen, Guangzhou, Wuhan, Chongqing, Chengdu,
    Tianjin, Hainan, Xiamen, Zhejiang, Ningbo, Qingdao, Dalian, Harbin, Nanjing, Urumqi, Kashgar, Inner Mongolia,
    Yunnan, Sichuan
TWN: Taipei, Kaohsiung, Kinmen, Matsu, Penghu, Taichung, Tainan, Hualien, Keelung, Pratas
PRK: Pyongyang, Yongbyon, Sohae, Sinpo, Wonsan, Punggye-ri, Kaesong, Nampo
KOR: Seoul, Busan, Incheon, Osan, Pyeongtaek, Camp Humphreys, Jeju
JPN: Tokyo, Okinawa, Osaka, Yokosuka, Kadena, Hokkaido, Kyushu, Yonaguni, Senkaku, Senkakus, Senkaku Islands,
    Nagasaki, Hiroshima, Sasebo, Iwakuni, Misawa, Ishigaki
PHL: Manila, Mindanao, Luzon, Palawan, Scarborough Shoal, Second Thomas Shoal, Ayungin Shoal, Sabina Shoal, Subic,
    Subic Bay, Cebu, Davao, Marawi, Basilan
VNM: Hanoi, Ho Chi Minh City, Saigon, Da Nang, Haiphong
KHM: Phnom Penh
THA: Bangkok, Yala, Narathiwat, Pattani
LAO: Vientiane
MMR: Yangon, Rangoon, Mandalay, Naypyidaw, Naypyitaw, Nay Pyi Taw, Rakhine, Sagaing, Shan State, Kachin, Karen State,
    Kayin, Kayah, Karenni, Chin State, Myawaddy, Lashio, Sittwe, Bago, Magway, Mon State, Myitkyina, Bhamo
MYS: Kuala Lumpur, Sarawak
IDN: Jakarta, Papua, West Papua, Aceh, Bali, Sulawesi, West Java, East Java, Central Java, Sumatra
TLS: Dili
BRN: Bandar Seri Begawan
PNG: Port Moresby, Bougainville
AUS: Canberra, Sydney, Melbourne, Darwin, New South Wales, Queensland, Pine Gap
NZL: Auckland
MNG: Ulaanbaatar, Ulan Bator
USA: Washington D.C., Washington DC, New York City, Los Angeles, Chicago, San Francisco, Houston, Miami, Atlanta,
    Pearl Harbor, San Diego, Fort Bragg, Fort Liberty, Fort Hood, Fort Cavazos, Fort Stewart, Fort Campbell,
    Fort Drum, Camp Lejeune, Quantico, West Point, Norfolk Naval Station
MEX: Mexico City, Culiacan, Sinaloa, Tijuana, Ciudad Juarez, Juarez, Michoacan, Jalisco, Guadalajara, Tamaulipas,
    Reynosa, Matamoros, Nuevo Laredo, Monterrey, Nuevo Leon, Acapulco, Chiapas, Sonora, Chihuahua, Zacatecas,
    Guanajuato, Celaya, Baja California, Ensenada, Mazatlan, Oaxaca, Veracruz, Morelos, Cuernavaca, Durango, Colima,
    Quintana Roo, Cancun, Tabasco, Puebla, Uruapan, Apatzingan
GTM: Guatemala City
HND: Tegucigalpa, San Pedro Sula
SLV: San Salvador
NIC: Managua
PAN: Panama Canal, Darien, Darien Gap
CUB: Havana, Guantanamo, Guantanamo Bay
HTI: Port-au-Prince, Cap-Haitien, Petion-Ville, Croix-des-Bouquets, Cite Soleil, Artibonite, Mirebalais, Kenscoff,
    Delmas, Gonaives
DOM: Santo Domingo
TTO: Port of Spain
VEN: Caracas, Maracaibo, Zulia, Apure, Tachira, Barinas, La Guaira, Maiquetia
GUY: Essequibo
COL: Bogota, Medellin, Cali, Catatumbo, Cauca, Cucuta, Barranquilla, Cartagena, Arauca, Narino, Putumayo, Antioquia,
    Tumaco, Buenaventura
ECU: Quito, Guayaquil, Esmeraldas, Manabi, Machala, Los Rios
PER: Lima, Callao, VRAEM
BOL: La Paz, Cochabamba
ARG: Buenos Aires
BRA: Brasilia, Rio de Janeiro, Sao Paulo
URY: Montevideo
PRY: Asuncion
SUR: Paramaribo
CAN: Ottawa, Toronto, Montreal, Vancouver, Alberta, Ontario, Quebec, British Columbia
GRL: Nuuk, Pituffik, Thule
GBR: London, Manchester, Birmingham, Edinburgh, Glasgow, Belfast, Cardiff, Liverpool, Westminster
IRL: Dublin
FRA: Paris, Marseille, Lyon, Toulon
DEU: Berlin, Munich, Frankfurt, Hamburg, Ramstein, Bundeswehr, Cologne
POL: Warsaw, Rzeszow, Krakow, Gdansk, Lublin
LTU: Vilnius, Kaunas
LVA: Riga
EST: Tallinn, Narva
FIN: Helsinki
SWE: Stockholm, Gotland
NOR: Oslo, Svalbard
DNK: Copenhagen, Bornholm
NLD: Amsterdam, The Hague, Rotterdam
ITA: Rome, Milan, Sicily, Sigonella, Lampedusa, Naples
ESP: Madrid, Barcelona, Ceuta, Melilla, Canary Islands
PRT: Lisbon
GRC: Athens, Thessaloniki, Crete
ROU: Bucharest, Constanta
HUN: Budapest
CZE: Prague
SVK: Bratislava
AUT: Vienna
CHE: Geneva, Zurich, Davos
SRB: Belgrade
KOS: Pristina
BIH: Sarajevo, Republika Srpska
HRV: Zagreb
SVN: Ljubljana
ALB: Tirana
MKD: Skopje
MNE: Podgorica
ISL: Reykjavik
"""

US_STATES = ("Alabama, Alaska, Arizona, Arkansas, California, Colorado, Connecticut, Delaware, Florida, Hawaii, Idaho, "
             "Illinois, Indiana, Iowa, Kansas, Kentucky, Louisiana, Maine, Maryland, Massachusetts, Michigan, "
             "Minnesota, Mississippi, Missouri, Montana, Nebraska, Nevada, New Hampshire, New Jersey, New Mexico, "
             "New York, North Carolina, North Dakota, Ohio, Oklahoma, Oregon, Pennsylvania, Rhode Island, "
             "South Carolina, South Dakota, Tennessee, Texas, Utah, Vermont, Virginia, Washington State, West Virginia, Wisconsin, "
             "Wyoming, D.C.")

# Russian and Ukrainian: "*" = any ending. Lowercase-first stems match any case (adjectives are lowercase there).
CYRILLIC = """
UKR: украин*, україн*, Киев*, Київ*, Києв*, Харьков*, Харків*, Одесс*, Одес*, Херсон*, Запорож*, Запоріж*, Днепр*,
    Дніпр*, Львов*, Львів*, Николаев*, Миколаїв*, Сумы, Сумах, Сумской, Сумщин*, Суми, Чернигов*, Чернігів*,
    Чернігов*, Полтав*, Винниц*, Вінниц*, Житомир*, Донецк*, Донецьк*, Донбас*, ДНР, Луганск*, Луганськ*, ЛНР,
    Покровск*, Покровськ*, Купянск*, Купʼянськ*, Куп'янськ*, Константиновк*, Костянтинівк*, Гуляйпол*, Крым*, Крим,
    Криму, Кримом, Кримськ*, ВСУ, ЗСУ, Кривой Рог, Кривий Ріг, Мариупол*, Маріупол*
RUS: росси*, росій*, Росія, Росії, Росією, русск*, РФ, Москв*, Кремл*, Белгород*, Бєлгород*, Курск*, Брянск*,
    Брянськ*, Воронеж*, Ростов*, Краснодар*, Новороссийск*, Туапсе, Энгельс*, Енгельс*, Саратов*, Татарстан*,
    Калининград*, Петербург*, Чечн*, Дагестан*
USA: США, америк*
-: Латинская Америка, Латинской Америки, Латинскую Америку, Латинська Америка, Латинської Америки, Латинську Америку
ISR: Израил*, израил*, Ізраїл*, ізраїл*, Тель-Авив*, Тель-Авів*
IRN: Иран*, иран*, Іран*, іран*, Тегеран*
IRQ: Ирак*, Ірак*
SYR: Сири*, сирий*, Сирі*, Дамаск*
LBN: Ливан*, Ліван*, Бейрут*, Хезболл*
YEM: Йемен*, Ємен*, хусит*, хусит*
PSX: ХАМАС, сектор Газа, секторе Газа, сектора Газа, секторі Газа
CHN: Китай, Китая, Китае, Китаю, Китаем, Китаї, китайск*, китайськ*, Пекин*, Пекін*
TWN: Тайван*
PRK: КНДР, Северная Корея, Северной Кореи, Северную Корею, Північна Корея, Північної Кореї, Пхеньян*
KOR: Южная Корея, Южной Кореи, Південна Корея, Південної Кореї
JPN: Япони*, Японі*, японск*, японськ*
BLR: Беларус*, белорус*, білорус*, Минск*, Мінськ*
POL: Польш*, Польщ*, польск*, польськ*
DEU: Германи*, Німеччин*, немецк*, німецьк*
FRA: Франци*, Франці*, французск*, французьк*
GBR: Британи*, Британі*, британск*, британськ*, Великобритани*, Великобританії, Лондон*
FIN: Финлянд*, Фінлянд*
EST: Эстони*, Естоні*
LVA: Латви*, Латві*
LTU: Литв*
ROU: Румын*, Румун*
HUN: Венгри*, Угорщин*
MDA: Молдов*, Молдав*, Приднестров*, Придністров*
GEO: Грузи*, Грузії
ARM: Армени*, Вірмен*
AZE: Азербайджан*
KAZ: Казахстан*
TUR: Турци*, Туреччин*
VEN: Венесуэл*, Венесуел*
IND: Индия, Индии, Индию, Индией, Індія, Індії, Індію
PAK: Пакистан*
AFG: Афганистан*, Афганістан*
"""

CYRILLIC_PEOPLE = """
UKR: Зеленск*, Зеленськ*, Кличко
RUS: Путин*, путин*, путін*, Шойгу, Лавров*, Песков*
ISR: Нетаньяху
CHN: Си Цзиньпин*, Сі Цзіньпін*
BLR: Лукашенк*
"""

# Ambiguous words with their own rule (see _special): code, weight, rule.
SPECIAL = (
    ("Georgia", "GEO", W_NAME, "georgia"),
    ("Jordan", "JOR", W_NAME, "person"),
    ("Chad", "TCD", W_NAME, "person"),
    ("Guerrero", "MEX", W_PLACE, "person"),
    ("Turkey", "TUR", W_NAME, "turkey"),
    ("Guinea", "GIN", W_NAME, "guinea"),
    ("Korea", "KOR", W_NAME, "korea"),
    ("Korean", "KOR", W_DEMONYM, "korea"),
    ("Koreans", "KOR", W_DEMONYM, "korea"),
    ("US", "USA", W_NAME, "us"),
    ("U.S.", "USA", W_NAME, "us"),
    ("U.S", "USA", W_NAME, "us"),
    ("RSF", "SDN", W_ACTOR, "rsf"),
)
# Natural Earth names left out: handled above, or too often a common word (Jersey, Guernsey).
SKIP_SHAPE_NAMES = {"georgia", "jordan", "chad", "turkey", "guinea", "jersey", "guernsey", "congo", "kashmir",
                    "bailiwick of jersey", "bailiwick of guernsey", "man"}

GEO_PLACES = {"tbilisi", "batumi", "kutaisi", "gori", "rustavi", "zugdidi", "abkhazia", "south ossetia", "poti"}
_GA_US_AFTER = re.compile(
    r"^\s*(?:['’]s\s+)?(?:gov\.?|governor|senat\w*|legislat\w*|lawmakers?|republicans?|democrats?|gop|voters?|"
    r"elections?|primar\w*|runoffs?|county|counties|sheriffs?|judges?|jury|prosecutors?|police|man|woman|teens?|"
    r"family|school\w*|universit\w*|tech|bulldogs|power|southern|dome|aquarium|bureau|congressional|district|"
    r"state\s+(?:senat\w*|rep\w*|house|universit\w*|patrol|troopers?|capitol)|house|supreme court|court|attorney|"
    r"secretary of state|national guard|peach|congressman|congresswoman|rep\.|sen\.|delegation|towns?|city|cities)\b",
    re.I)
_GA_US_ANY = re.compile(r"\b(?:Atlanta|Savannah|Macon|Fulton County|Brian Kemp|Raffensperger|Peach State|Georgia Tech|"
                        r"University of Georgia|Fort Stewart|Fort Benning|Fort Moore|Fort Gordon|Fort Eisenhower|"
                        r"Kings Bay|Moody Air Force|Robins Air Force)\b")
_GA_GEO_ANY = re.compile(r"\b(?:Tbilisi|Batumi|Kutaisi|Abkhaz\w*|Ossetia\w*|Georgian Dream|Kobakhidze|Ivanishvili|"
                         r"Zourabichvili|Kavelashvili|Caucasus|Kremlin|Moscow|Russia\w*|Armenia\w*|Azerbaijan\w*|"
                         r"Black Sea|EU|European Union|NATO)\b")
_FIRST_NAMES = {
    "Michael", "Jim", "Jimmy", "James", "John", "Johnny", "Robert", "Bob", "Chris", "Christopher", "David", "Dave",
    "Mike", "Matt", "Matthew", "Mark", "Paul", "Peter", "Steve", "Steven", "Stephen", "Tom", "Thomas", "Tony",
    "Kevin", "Brian", "Bryan", "Jason", "Justin", "Ryan", "Eric", "Adam", "Andrew", "Andy", "Ben", "Josh", "Joshua",
    "Daniel", "Dan", "Danny", "Joe", "Joseph", "Jack", "Jake", "Kyle", "Scott", "Sam", "Nick", "Bill", "Billy",
    "Brad", "Greg", "Gary", "Larry", "Jerry", "Terry", "Barbara", "Katie", "Kate", "Amy", "Mary", "Sarah", "Jessica",
    "Jennifer", "Emma", "Anna", "Laura", "Lisa", "Linda", "Karen", "Susan", "Michelle", "Ashley", "Taylor", "DeAndre",
    "Vernon", "Eddie", "Lamar", "Marcus", "Anthony", "Malik", "Isaiah", "Hakeem", "Ty", "Tyler", "Kai", "Max", "Leo",
}
_KNOWN_SURNAMES = {"Bardella", "Peterson", "Spieth", "Henderson", "Love", "Chiles", "Poole", "Clarkson", "Pickford",
                   "Daybell", "Kroeger", "Smith", "Johnson", "Brown", "Williams", "Jones", "Miller", "Davis"}
_OK_BEFORE = {"In", "To", "From", "Of", "And", "Into", "Across", "Near", "Via", "With", "For", "Against", "By", "On",
              "At", "King", "Queen", "Neighbouring", "Neighboring", "Lake", "Northern", "Southern", "Eastern",
              "Western", "Central", "Hashemite", "Kingdom", "Republic", "Visit", "Visits", "Says", "Tells", "Warns",
              "The", "A", "As", "Or", "Than", "Like", "Both", "Over", "Under", "Between", "Toward", "Towards", "Inside",
              "Outside", "Says", "Hits", "Strikes", "Attacks", "Joins", "Urges", "Backs", "Slams", "Accuses", "Rejects"}
_OK_AFTER = {"River", "Valley", "Border", "Army", "Armed", "King", "Times", "News", "Crossing", "Bridge", "Basin",
             "Lake", "Government", "Military", "Junta", "President", "Prime", "Foreign", "Defence", "Defense",
             "Interior", "Ministry", "Minister", "Forces", "Troops", "Rebels", "Opposition", "Election", "Elections",
             "Refugee", "Refugees", "Air", "Navy", "Police", "Parliament", "Embassy", "Authorities", "Capital",
             "Region", "Oblast", "Province", "State"}
_STRONG_BEFORE = re.compile(r"(?:\b(?:in|to|from|into|across|of|near|via|neighbou?ring|visits?|visited|for|against|"
                            r"and|with|between|inside|outside|toward|towards|over|en|de|del|desde|hacia)\s+$)", re.I)
_PRK_CUES = re.compile(r"\b(?:DPRK|Pyongyang|Kim Jong|Kim Yo|North Korea\w*|N\.? ?Korea\w*|KCNA|Juche|Yongbyon)\b")
_TURKEY_FOOD = re.compile(r"\b(?:thanksgiving|roast\w*|gobbl\w*|feathers?|gravy|stuffing|recipes?|dinners?|feast|"
                          r"poultry|birds?|vultures?|hunt(?:ing|ers?)?|sandwich\w*|trot|leftovers?|deep[- ]fr\w*|"
                          r"brin(?:e|ed|ing)|carving|ovens?|butterball|drumsticks?|wishbone)\b", re.I)
_LOCATIVE = re.compile(r"\b(?:in|on|at|near|over|around|along|inside|outside|across|off|into|en)\s+(?:the\s+)?"
                       r"(?:(?:north|south|east|west|central|northern|southern|eastern|western|north-?eastern|"
                       r"north-?western|south-?eastern|south-?western|occupied|besieged|rural|coastal)\s+)?$", re.I)
_GUINEA_ANIMAL = re.compile(r"^\s*(?:pigs?|fowls?|worms?|hens?)\b", re.I)
_US_PRONOUN = {"JOIN", "FOLLOW", "CONTACT", "SUPPORT", "HELP", "TELL", "LET", "GIVE", "SEND", "SHOW", "ASK",
               "SUBSCRIBE", "MESSAGE", "DM", "OF", "BEHIND", "AMONG", "TRUST", "SAVE", "UNITE", "BLESS"}
_RSF_PRESS = re.compile(r"Reporters Without Borders|Reporters sans|press freedom|journalists?\b", re.I)

_FLAG = re.compile("([\U0001F1E6-\U0001F1FF])([\U0001F1E6-\U0001F1FF])")
_TOKEN = re.compile(r"[^\W_]+")

# ---------------- index ----------------

_LOCK = threading.Lock()
_IDX = {}


def _fold(s):
    """Latin accents off (same length, so positions line up); typographic apostrophes and dashes to ASCII."""
    out = []
    for c in s:
        o = ord(c)
        if 0xC0 <= o <= 0x24F:
            c = _FOLD.get(c) or c
        elif c in "’‘ʼʻ`´":
            c = "'"
        elif c in "‐‑‒–—−":
            c = "-"
        out.append(c)
    return "".join(out)


def _mk_fold():
    import unicodedata
    m = {}
    for o in range(0xC0, 0x250):
        c = chr(o)
        b = unicodedata.normalize("NFD", c)[0]
        if b != c and b.isalpha():
            m[c] = b
    return m


_FOLD = _mk_fold()


def _toks(s):
    return [m.group().lower() for m in _TOKEN.finditer(_fold(s))]


def _case_mode(raw):
    letters = [c for c in raw if c.isalpha()]
    if not letters:
        return "any"
    if letters[0].islower():
        return "any"
    if all(c.isupper() for c in letters) and (len(letters) <= 6 or any(c.isdigit() for c in raw)):
        return "exact"
    if any(c.isdigit() for c in raw) and all(c.isupper() for c in letters):
        return "exact"
    return "cap"


_CODES = re.compile(r"^([A-Z]{3}(?:\+[A-Z]{3})*|@[a-z-]+|-)\s*:(.*)$")


def _table(text):
    """'CODES: term, term, ...' lines; a line that does not start with CODES: continues the one above."""
    codes = None
    for line in text.strip().splitlines():
        line = line.strip()
        m = _CODES.match(line)
        if m:
            codes, terms = m.group(1), m.group(2)
        elif line and codes:
            terms = line
        else:
            continue
        for t in terms.split(","):
            t = t.strip()
            if t:
                yield codes, t


def _add(idx, raw, codes, weight, kind, rule=None, overwrite=True):
    stem = raw.endswith("*")
    body = raw[:-1] if stem else raw
    toks = tuple(_toks(body))
    if not toks:
        return
    if codes.startswith("@"):
        cc, theatre = (), codes[1:]
    elif codes == "-":
        cc, theatre = (), None
    else:
        cc, theatre = tuple(codes.split("+")), None
    e = {"raw": body, "codes": cc, "theatre": theatre, "w": weight, "kind": kind, "rule": rule,
         "case": _case_mode(body), "rtoks": [m.group() for m in _TOKEN.finditer(_fold(body))]}
    d = idx["stems"] if stem else idx["terms"]
    if overwrite or toks not in d:
        d[toks] = e
    idx["maxn"] = max(idx["maxn"], len(toks))


def _plural(t):
    return None if t.endswith(("ese", "sh", "ch", "ss", "s", "x", "z", "*")) else t + "s"


def _build():
    idx = {"terms": {}, "stems": {}, "maxn": 1}
    shapes = geo.country_shapes()
    for a3, s in sorted(shapes.items()):
        for n in sorted(s["names"]):  # sorted: the same raw spelling wins on every run
            if n in SKIP_SHAPE_NAMES:
                continue
            _add(idx, n.title() if n[:1].isalpha() else n, a3, W_NAME, "name", overwrite=False)
    for n, a3 in geo.NAME_ALIASES.items():
        if n not in SKIP_SHAPE_NAMES and a3 in shapes:
            _add(idx, n.title(), a3, W_NAME, "name")
    for codes, t in _table(NAMES):
        _add(idx, t, codes, W_NAME, "name")
    for codes, t in _table(REGIONS):
        _add(idx, t, codes, W_REGION, "region")
    for codes, t in _table(DEMONYMS):
        _add(idx, t, codes, W_DEMONYM, "demonym")
        p = _plural(t)
        if p and t[:1].isupper():
            _add(idx, p, codes, W_DEMONYM, "demonym")
    for codes, t in _table(ACTORS):
        _add(idx, t, codes, W_ACTOR, "actor")
        if t.endswith("i") and t[:1].isupper():
            _add(idx, t + "s", codes, W_ACTOR, "actor", overwrite=False)
    for codes, t in _table(CORROBORATE):
        _add(idx, t, codes, W_ACTOR, "actor", rule="corroborate")
    for codes, t in _table(SEATS):
        _add(idx, t, codes, W_PERSON, "actor")
    for codes, t in _table(PEOPLE):
        _add(idx, t, codes, W_PERSON, "person")
    for codes, t in _table(CYRILLIC_PEOPLE):
        _add(idx, t, codes, W_PERSON, "person")
    for codes, t in _table(METONYMS):
        _add(idx, t, codes, W_METONYM, "metonym")
    for codes, t in _table(PLACES):
        _add(idx, t, codes, W_PLACE, "place")
    for t in US_STATES.split(","):
        _add(idx, t.strip(), "USA", W_PLACE, "usstate")
    for codes, t in _table(CYRILLIC):
        _add(idx, t, codes, W_PLACE, "cyrillic")
    for raw, a3, w, rule in SPECIAL:
        _add(idx, raw, a3, w, "special", rule=rule)
    # Regions and seas inside longer names stay with the longer name ("South Africa", "Central African Republic").
    idx["a2"] = {s["a2"]: a3 for a3, s in shapes.items() if s.get("a2")}
    idx["first"] = {k[0] for k in idx["terms"]} | {k[0] for k in idx["stems"] if len(k) > 1}
    idx["stem1"] = {k[0] for k in idx["stems"] if len(k) == 1}
    idx["stemlen"] = sorted({len(k[0]) for k in idx["stems"] if len(k) == 1}, reverse=True)
    return idx


def index():
    with _LOCK:
        if not _IDX:
            _IDX.update(_build())
    return _IDX


# ---------------- matching ----------------

def _title_case(seg):
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", seg)
    long_ = [w for w in words if len(w) >= 4]
    if len(long_) < 3:
        return False
    return sum(1 for w in long_ if w[0].isupper()) / float(len(long_)) >= 0.75


def _case_ok(e, seg, spans):
    mode = e["case"]
    if mode == "any":
        return True
    if mode == "cap":
        return seg[spans[0][0]].isupper()
    return [seg[a:b] for a, b in spans] == e["rtoks"]  # exact: acronyms (US, IDF, M23)


def _person(seg, s, end, tc, raw):
    """True when the word reads as a person's name ("Michael Jordan", "Chad Daybell", "Jordan Bardella")."""
    before, after = seg[max(0, s - 40):s], seg[end:end + 40]
    mb = re.search(r"([A-Z][a-z]+)\.?\s+$", before)
    ma = re.match(r"\s+([A-Z][a-z]+)\b", after)
    if mb:
        w = mb.group(1)
        if w in _FIRST_NAMES or (not tc and w not in _OK_BEFORE and not _is_term(w)):
            if raw != "Chad" or w in _FIRST_NAMES:
                return True
    if ma:
        w = ma.group(1)
        if w in _KNOWN_SURNAMES or (not tc and w not in _OK_AFTER and not _is_term(w)):
            return True
    return False


def _is_term(word):
    t = tuple(_toks(word))
    return t in index()["terms"]


def _special(e, seg, s, end, tc, prev):
    """(codes, needs_corroboration) for a SPECIAL entry, or None to drop the match."""
    rule = e["rule"]
    after = seg[end:end + 60]
    if rule == "georgia":
        before = seg[max(0, s - 60):s]
        geo_ctx = _GA_GEO_ANY.search(seg)
        m = re.search(r"([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2}),\s*$", before)
        if m:  # "Atlanta, Georgia" is the state; "Tbilisi, Georgia" and "Armenia, Azerbaijan, Georgia" the country
            listed = prev and prev["kind"] in ("name", "special") and prev["codes"] and prev["codes"] != ("USA",) and \
                re.fullmatch(r",\s*", seg[prev["end"]:s])
            if _fold(m.group(1)).lower() in GEO_PLACES or listed:
                return ("GEO",), False
            return ("USA",), False
        if _GA_US_AFTER.match(after) and not geo_ctx:
            return ("USA",), False
        if re.search(r"\b(?:north|south|east|west|central|rural|coastal|metro|southwest|southeast|northwest|"
                     r"northeast|middle)\s+$", before, re.I) and not geo_ctx:
            return ("USA",), False
        if geo_ctx:
            return ("GEO",), False
        if _GA_US_ANY.search(seg):
            return ("USA",), False
        return ("GEO",), False
    if rule == "person":
        if _person(seg, s, end, tc, e["raw"]):
            return None
        strong = _STRONG_BEFORE.search(seg[max(0, s - 30):s]) or re.match(r"['’]s\b", after) or \
            re.match(r"\s*,\s*(?:[A-Z]|the\b)", after)
        return e["codes"], (tc and not strong)
    if rule == "turkey":
        if _TURKEY_FOOD.search(seg[max(0, s - 50):end + 50]):
            return None
        return e["codes"], False
    if rule == "guinea":
        return (None if _GUINEA_ANIMAL.match(after) else (e["codes"], False))
    if rule == "korea":
        return (("PRK",) if _PRK_CUES.search(seg) else ("KOR",)), False
    if rule == "us":
        if after[:1] == "$":
            return None
        mb = re.search(r"([A-Z]{2,})\s+$", seg[max(0, s - 20):s])
        if mb and mb.group(1) in _US_PRONOUN and seg[s:end] == "US":
            return None
        return e["codes"], False
    if rule == "rsf":
        return (None if _RSF_PRESS.search(seg) else (e["codes"], False))
    return e["codes"], False


def _scan(seg, factor, base):
    idx = index()
    terms, stems, maxn = idx["terms"], idx["stems"], idx["maxn"]
    folded = _fold(seg)
    spans = [(m.start(), m.end()) for m in _TOKEN.finditer(folded)]
    low = [folded[a:b].lower() for a, b in spans]
    tc = _title_case(seg)
    hits, i, n_tok = [], 0, len(spans)
    first, stem1, stemlen = idx["first"], idx["stem1"], idx["stemlen"]
    while i < n_tok:
        t0 = low[i]
        if t0 not in first and not any(t0[:L] in stem1 for L in stemlen if L <= len(t0)):
            i += 1
            continue
        found = None
        for n in range(min(maxn, n_tok - i), 0, -1):
            key = tuple(low[i:i + n])
            e = terms.get(key)
            if e is None:
                last = key[-1]
                for L in range(len(last), 2, -1):
                    e = stems.get(key[:-1] + (last[:L],))
                    if e is not None:
                        e = dict(e, stem=True)
                        break
            if e is None or not _case_ok(e, seg, spans[i:i + n]):
                continue
            s, end = spans[i][0], spans[i + n - 1][1]
            codes, weak = e["codes"], False
            if e["kind"] == "special":
                r = _special(e, seg, s, end, tc, hits[-1] if hits else None)
                if r is None:
                    continue
                codes, weak = r
            w = e["w"]
            if codes and e["kind"] in ("name", "place", "usstate", "cyrillic", "special") and \
                    _LOCATIVE.search(seg[max(0, s - 40):s]):
                w += LOC_BONUS
            found = {"s": s, "end": end, "pos": base + s, "codes": codes, "theatre": e["theatre"],
                     "w": w * factor, "kind": e["kind"], "surface": seg[s:end], "weak": weak,
                     "corroborate": e.get("rule") == "corroborate"}
            i += n
            break
        if found:
            hits.append(found)
        else:
            i += 1
    # "Paris, Texas" / "Lebanon, Pennsylvania": a place followed by ", <US state>" is in the US.
    for a, b in zip(hits, hits[1:]):
        if b["codes"] == ("USA",) and b["kind"] in ("usstate", "special") and a["codes"] != ("USA",) and \
                re.fullmatch(r",\s*", seg[a["end"]:b["s"]]) and a["kind"] in ("place", "name", "special"):
            a["codes"] = ("USA",)
    for m in _FLAG.finditer(seg):
        a2 = chr(ord(m.group(1)) - 0x1F1E6 + 65) + chr(ord(m.group(2)) - 0x1F1E6 + 65)
        a3 = idx["a2"].get(a2)
        if a3:
            hits.append({"s": m.start(), "end": m.end(), "pos": base + m.start(), "codes": (a3,), "theatre": None,
                         "w": W_FLAG * factor, "kind": "flag", "surface": m.group(0), "weak": False,
                         "corroborate": False})
    return hits


def place(text, extra=None):
    """Countries named in `text` (a headline), strongest first; `extra` (a summary) counts half."""
    hits = []
    if text:
        hits.extend(_scan(str(text), 1.0, 0))
    if extra:
        hits.extend(_scan(str(extra), EXTRA_FACTOR, 10 ** 6))
    solid = [h for h in hits if not h["weak"] and not h["corroborate"]]
    solid_codes = {c for h in solid for c in h["codes"]}
    solid_theatres = {geo.theatre_for_a3(c) for c in solid_codes}
    kept = []
    for h in hits:
        if h["corroborate"] and not (set(h["codes"]) & solid_codes):
            continue
        if h["weak"] and not any(geo.theatre_for_a3(c) in solid_theatres for c in h["codes"]):
            continue
        kept.append(h)
    scores, first, theatres = {}, {}, {}
    for h in kept:
        for k, c in enumerate(h["codes"]):
            scores[c] = scores.get(c, 0.0) + h["w"] * (1.0 if k == 0 else SECOND_CODE)
            first[c] = min(first.get(c, h["pos"]), h["pos"])
        if h["theatre"]:
            t = theatres.setdefault(h["theatre"], [0.0, h["pos"]])
            t[0] += h["w"]
    # Ties: another country before the US (it is so often the actor), then the earlier mention.
    countries = sorted(scores, key=lambda c: (-round(scores[c], 3), c == "USA", first[c]))[:MAX_COUNTRIES]
    region = sorted(theatres, key=lambda t: (-theatres[t][0], theatres[t][1]))[0] if theatres else None
    if countries:
        theatre = geo.theatre_for_a3(countries[0])
        if countries[0] == "USA" and region and region != "americas":
            theatre = region  # "US carrier enters the South China Sea": the US is the actor, not the place
    else:
        theatre = region
    matched = []
    for h in sorted(kept, key=lambda h: h["pos"]):
        if (h["codes"] or h["theatre"]) and h["surface"] not in matched:
            matched.append(h["surface"])
    return {"countries": countries, "theatre": theatre, "matched": matched}
